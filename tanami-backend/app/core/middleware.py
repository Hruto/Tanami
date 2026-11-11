"""HTTP middleware: request id, access log, security headers, body size, rate limit."""

from __future__ import annotations

import hashlib
import time
from typing import Any, ClassVar
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import (
    reset_request_id,
    reset_user_id,
    set_request_id,
)
from app.core.errors import RateLimited
from app.core.logging import get_logger

_MAX_REQUEST_ID_LENGTH = 128
# Liveness/readiness/metrics would otherwise flood the log with probes.
_QUIET_PATHS = frozenset({"/health", "/healthz", "/readyz", "/metrics", "/openapi.json"})


def _valid_request_id(value: str) -> bool:
    if not value or len(value) > _MAX_REQUEST_ID_LENGTH:
        return False
    return all(char.isalnum() or char in "-_." for char in value)


def client_ip(scope: Scope, *, trust_forwarded_for: bool) -> str:
    """The caller's IP address.

    ``X-Forwarded-For`` is only honoured behind a proxy we control
    (``TANAMI_TRUST_FORWARDED_FOR``). Otherwise anyone could rotate the header
    and walk past the login limit of design 10.3.
    """
    if trust_forwarded_for:
        forwarded = Headers(scope=scope).get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


class RequestContextMiddleware:
    """Assign a request id, echo it back, and emit one access log line."""

    def __init__(self, app: ASGIApp, *, trust_forwarded_for: bool = False) -> None:
        self.app = app
        self.trust_forwarded_for = trust_forwarded_for
        self.logger = get_logger("http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming = headers.get("x-request-id", "")
        request_id = incoming if _valid_request_id(incoming) else uuid4().hex
        set_request_id(request_id)

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
                response_headers.setdefault("X-Content-Type-Options", "nosniff")
                response_headers.setdefault("Referrer-Policy", "no-referrer")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            path = scope.get("path", "")
            if path not in _QUIET_PATHS:
                log = self.logger.info if status_code < 500 else self.logger.error
                log(
                    "http_request",
                    method=scope.get("method"),
                    path=path,
                    status=status_code,
                    duration_ms=duration_ms,
                    client=client_ip(scope, trust_forwarded_for=self.trust_forwarded_for),
                )
            reset_request_id()
            reset_user_id()


class BodySizeLimitMiddleware:
    """Reject oversized bodies before they are buffered.

    ``Content-Length`` is a hint, so the streaming guard below also counts bytes
    actually received. This is the first line of defence; the scan route still
    validates the decoded image.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Multipart adds boundary and field overhead on top of the image itself.
        limit = self.max_bytes + 64 * 1024
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await self._reject(scope, receive, send)
            return

        received = 0
        response_started = False

        async def guarded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    msg = "payload too large"
                    raise _BodyTooLarge(msg)
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, guarded_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        from app.core.handlers import error_response

        response = error_response(
            status_code=413,
            code="payload_too_large",
            message="Foto terlalu besar. Kompres ulang lalu coba lagi.",
            details={"max_bytes": self.max_bytes},
        )
        await response(scope, receive, send)


class _BodyTooLarge(Exception):
    pass


class GlobalRateLimitMiddleware:
    """Fixed window ``120 requests / minute / user`` (design 10.3, "Lainnya").

    Identity is a digest of the bearer token when one is present, otherwise the
    client IP. Health probes and docs are skipped so infrastructure polling
    cannot exhaust a shared bucket. The limiter is read from ``app.state`` on
    every call, so a test that swaps Redis for fakeredis is honoured. Fail-open
    on Redis errors, matching ``RateLimiter.check``.
    """

    _WINDOW_SECONDS = 60
    _SKIP_PATHS: ClassVar[frozenset[str]] = frozenset(
        {"/health", "/healthz", "/readyz", "/metrics", "/docs", "/openapi.json", "/redoc"}
    )

    def __init__(self, app: ASGIApp, *, limit: int = 120) -> None:
        self.app = app
        self.limit = limit
        self.logger = get_logger("rate_limit")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._SKIP_PATHS or path.startswith(("/docs", "/media/")):
            await self.app(scope, receive, send)
            return

        state: Any = getattr(scope.get("app"), "state", None)
        tanami = getattr(state, "tanami", None)
        limiter = getattr(tanami, "rate_limiter", None)
        settings = getattr(tanami, "settings", None)
        trust = bool(getattr(settings, "trust_forwarded_for", False))

        if limiter is not None:
            try:
                await limiter.check(
                    bucket="global",
                    identity=self._identity(scope, trust_forwarded_for=trust),
                    limit=self.limit,
                    window_seconds=self._WINDOW_SECONDS,
                )
            except RateLimited as exc:
                from app.core.handlers import error_response

                response = error_response(
                    status_code=exc.status_code,
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                    headers=exc.headers,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

    @staticmethod
    def _identity(scope: Scope, *, trust_forwarded_for: bool) -> str:
        auth = Headers(scope=scope).get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            # Not decoded here: the digest is only a bucket key, and the auth
            # layer rejects a forged token with 401 anyway.
            return "token:" + hashlib.sha256(token.encode()).hexdigest()[:16]
        return "ip:" + client_ip(scope, trust_forwarded_for=trust_forwarded_for)


def security_headers(app: ASGIApp) -> ASGIApp:
    """Baseline headers for an API that never serves HTML."""

    async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await app(scope, receive, send_wrapper)

    return wrapped
