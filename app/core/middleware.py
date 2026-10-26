"""HTTP middleware: request id propagation and one structured access log line."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import reset_request_id, set_request_id
from app.core.logging import get_logger

_REQUEST_ID_MAX_LENGTH = 128
_QUIET_PATHS = frozenset({"/healthz", "/metrics"})


def _valid_request_id(value: str) -> bool:
    if not value or len(value) > _REQUEST_ID_MAX_LENGTH:
        return False
    return all(char.isalnum() or char in "-_." for char in value)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = get_logger("http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming = headers.get("x-request-id", "")
        request_id = incoming if _valid_request_id(incoming) else uuid4().hex

        token = set_request_id(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-Id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            path = str(scope["path"])
            log: Any = self.logger.debug if path in _QUIET_PATHS else self.logger.info
            log(
                "request",
                method=scope["method"],
                path=path,
                status=status_code,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()
            reset_request_id(token)
