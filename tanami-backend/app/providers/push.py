"""Push notification provider (FCM HTTP v1).

Payload shape is fixed by ``design.md`` section 15. Delivery is best-effort:
a push failure must never fail the job that triggered it, and the reminder row
remains in the list either way.

Google shut the legacy ``/fcm/send`` endpoint down in 2024, so the provider
speaks HTTP v1: a short-lived OAuth token is minted from a service account
(RS256 JWT bearer grant) and cached until shortly before it expires. A token
that FCM reports as unregistered is surfaced as ``PushOutcome.INVALID_TOKEN`` so
the caller can delete the device row instead of retrying it forever.
"""

from __future__ import annotations

import asyncio
import json
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import httpx
import jwt

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.metrics import PUSHES_SENT

logger = get_logger("push")

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL
_INVALID_TOKEN_CODES = frozenset({"UNREGISTERED", "INVALID_ARGUMENT", "SENDER_ID_MISMATCH"})


class PushOutcome(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    INVALID_TOKEN = "invalid_token"  # noqa: S105 - an outcome, not a secret
    SKIPPED = "skipped"


class PushProvider(Protocol):
    async def send(self, *, token: str, data: dict[str, str]) -> PushOutcome: ...


class LogPushProvider:
    """No-op provider for local development and tests.

    It records the payloads so tests can assert what would have been sent
    without mocking the network.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.invalid_tokens: set[str] = set()

    async def send(self, *, token: str, data: dict[str, str]) -> PushOutcome:
        if token in self.invalid_tokens:
            PUSHES_SENT.labels(result="invalid_token").inc()
            return PushOutcome.INVALID_TOKEN
        self.sent.append({"token": token, **data})
        PUSHES_SENT.labels(result="logged").inc()
        return PushOutcome.SENT


class FcmV1PushProvider:
    """FCM HTTP v1 with a service-account credential."""

    def __init__(
        self,
        credentials: dict[str, Any],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._project_id = str(credentials["project_id"])
        self._client_email = str(credentials["client_email"])
        self._private_key = str(credentials["private_key"])
        self._token_uri = str(credentials.get("token_uri") or _DEFAULT_TOKEN_URI)
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(5.0), transport=transport)
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _token(self, *, force: bool = False) -> str:
        async with self._lock:
            if not force and self._access_token and time.time() < self._expires_at - 60:
                return self._access_token
            now = int(time.time())
            assertion = jwt.encode(
                {
                    "iss": self._client_email,
                    "scope": _FCM_SCOPE,
                    "aud": self._token_uri,
                    "iat": now,
                    "exp": now + 3600,
                },
                self._private_key,
                algorithm="RS256",
            )
            response = await self._client.post(
                self._token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            response.raise_for_status()
            body = response.json()
            self._access_token = str(body["access_token"])
            self._expires_at = time.time() + float(body.get("expires_in", 3600))
            return self._access_token

    async def send(self, *, token: str, data: dict[str, str]) -> PushOutcome:
        message = {
            "message": {
                "token": token,
                # FCM data values must be strings.
                "data": {key: str(value) for key, value in data.items()},
                "android": {"priority": "high"},
                "apns": {"headers": {"apns-priority": "10"}},
            }
        }
        url = f"https://fcm.googleapis.com/v1/projects/{self._project_id}/messages:send"
        try:
            for attempt in range(2):
                access_token = await self._token(force=attempt > 0)
                response = await self._client.post(
                    url, json=message, headers={"Authorization": f"Bearer {access_token}"}
                )
                if response.status_code != 401:
                    break
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("push_transport_error", error=type(exc).__name__)
            PUSHES_SENT.labels(result="error").inc()
            return PushOutcome.FAILED

        if response.status_code == 200:
            PUSHES_SENT.labels(result="sent").inc()
            return PushOutcome.SENT

        if _is_invalid_token(response):
            PUSHES_SENT.labels(result="invalid_token").inc()
            return PushOutcome.INVALID_TOKEN

        logger.warning("push_status", status=response.status_code)
        PUSHES_SENT.labels(result="error").inc()
        return PushOutcome.FAILED


def _is_invalid_token(response: httpx.Response) -> bool:
    if response.status_code not in {400, 404}:
        return False
    try:
        error = response.json().get("error", {})
    except ValueError:
        return False
    codes = {str(error.get("status", ""))}
    for detail in error.get("details", []) or []:
        if isinstance(detail, dict) and detail.get("errorCode"):
            codes.add(str(detail["errorCode"]))
    return bool(codes & _INVALID_TOKEN_CODES)


def load_fcm_credentials(settings: Settings) -> dict[str, Any] | None:
    raw = settings.fcm_credentials_json.strip()
    if not raw and settings.fcm_credentials_file:
        raw = Path(settings.fcm_credentials_file).read_text(encoding="utf-8")
    if not raw:
        return None
    credentials = json.loads(raw)
    if not isinstance(credentials, dict):
        msg = "kredensial FCM harus berupa objek JSON service account"
        raise ValueError(msg)
    return credentials


def build_push_provider(settings: Settings) -> PushProvider:
    credentials = load_fcm_credentials(settings)
    if credentials is not None:
        return FcmV1PushProvider(credentials)
    if settings.app_env == "production":
        logger.warning("push_disabled_missing_fcm_credentials")
    return LogPushProvider()
