"""HTTP client for ``tanami-vision``.

The vision service is stateless (see ``docs/architecture.md`` in the vision
repo): it takes an image and returns a result. Everything stateful - auth,
storage, idempotency, advice, absolute harvest dates - belongs here.

Two behaviours matter and are tested directly:

* ``503`` and transport errors are retried with a short backoff, because the
  contract says the vision service may be temporarily unavailable.
* A ``200`` with ``status = invalid_image`` is a *successful* call. It is a
  conclusion, not a failure, and must be stored, not retried.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import (
    AppError,
    InvalidImage,
    PayloadTooLarge,
    ServiceUnavailable,
    UnsupportedMediaType,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.metrics import VISION_ERRORS

logger = get_logger("vision")

_RETRYABLE_STATUS = frozenset({502, 503, 504})


@dataclass(frozen=True, slots=True)
class VisionResult:
    scan_type: str
    status: str
    model_version: str
    commodity_code: str
    confidence: float | None
    quality: dict[str, object]
    result: dict[str, object]
    inference_ms: float
    shadow_model_version: str | None = None
    shadow_status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        code = error.get("code")
        return str(code) if code is not None else None
    return None


class VisionClient:
    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        headers = {"Accept": "application/json"}
        if settings.vision_service_token:
            headers["Authorization"] = f"Bearer {settings.vision_service_token}"
        self._client = httpx.AsyncClient(
            base_url=settings.vision_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.vision_timeout_seconds),
            headers=headers,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ready(self) -> bool:
        """``GET /readyz`` on tanami-vision: are the primary models loaded?"""
        try:
            response = await self._client.get("/readyz", timeout=2.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def predict(
        self,
        *,
        scan_type: str,
        image: bytes,
        content_type: str,
        client_uuid: str,
        commodity_code: str,
    ) -> VisionResult:
        files = {"image": ("upload", image, content_type)}
        data = {"type": scan_type, "commodity_code": commodity_code, "client_uuid": client_uuid}
        headers = {"Idempotency-Key": client_uuid}

        attempts = self._settings.vision_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = await self._client.post(
                    "/v1/predict", data=data, files=files, headers=headers
                )
            except httpx.TimeoutException as exc:
                last_error = exc
                VISION_ERRORS.labels(reason="timeout").inc()
                logger.warning("vision_timeout", attempt=attempt, scan_type=scan_type)
            except httpx.HTTPError as exc:
                last_error = exc
                VISION_ERRORS.labels(reason="transport").inc()
                logger.warning("vision_transport_error", attempt=attempt, error=type(exc).__name__)
            else:
                if response.status_code == 200:
                    return self._parse(response)
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = ServiceUnavailable("Layanan analisis foto belum siap.")
                    VISION_ERRORS.labels(reason="unavailable").inc()
                    logger.warning(
                        "vision_unavailable",
                        attempt=attempt,
                        status=response.status_code,
                    )
                else:
                    # A 4xx is about this request, so retrying it cannot help.
                    VISION_ERRORS.labels(reason=f"http_{response.status_code}").inc()
                    raise self._client_error(response)

            if attempt < attempts:
                await asyncio.sleep(0.15 * attempt)

        logger.error("vision_exhausted", attempts=attempts, error=str(last_error))
        raise ServiceUnavailable("Layanan analisis foto sedang sibuk. Coba lagi sebentar.")

    def _parse(self, response: httpx.Response) -> VisionResult:
        try:
            payload = response.json()
            data = payload["data"]
            return VisionResult(
                scan_type=str(data["type"]),
                status=str(data["status"]),
                model_version=str(data["model_version"]),
                commodity_code=str(data.get("commodity_code", "chili")),
                confidence=(
                    float(data["confidence"]) if data.get("confidence") is not None else None
                ),
                quality=dict(data["quality"]),
                result=dict(data["result"]),
                inference_ms=float(data.get("inference_ms", 0.0)),
                shadow_model_version=data.get("shadow_model_version"),
                shadow_status=data.get("shadow_status"),
                raw=payload,
            )
        except (KeyError, TypeError, ValueError) as exc:
            VISION_ERRORS.labels(reason="bad_payload").inc()
            logger.error("vision_bad_payload", error=str(exc))
            raise ServiceUnavailable("Hasil analisis foto tidak dapat dibaca.") from exc

    def _client_error(self, response: httpx.Response) -> AppError:
        _error_code(response)
        if response.status_code == 413:
            return PayloadTooLarge("Foto terlalu besar. Kompres ulang lalu coba lagi.")
        if response.status_code == 415:
            return UnsupportedMediaType("Format foto tidak didukung. Gunakan JPEG atau PNG.")
        if response.status_code == 422:
            return InvalidImage("Gambar ini sepertinya bukan foto daun atau buah.")
        if response.status_code in {400, 401}:
            return ValidationError("Permintaan analisis foto tidak valid.")
        return ServiceUnavailable("Layanan analisis foto sedang bermasalah.")


def build_vision_client(settings: Settings) -> VisionClient:
    return VisionClient(settings)
