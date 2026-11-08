"""Test doubles: a scripted vision client, a canned weather provider, builders.

Everything here is synchronous-cheap and deterministic so a test failure always
points at application code, never at the test infrastructure.
"""

from __future__ import annotations

import io
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.errors import ServiceUnavailable
from app.domain import DISEASE_LABELS, ResultStatus, ScanType
from app.providers.vision import VisionResult
from app.providers.weather import (
    BMKG_ATTRIBUTION,
    WeatherDay,
    WeatherForecast,
    WeatherSlot,
)
from PIL import Image

# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #


def image_bytes(
    width: int = 64,
    height: int = 64,
    *,
    fmt: str = "JPEG",
    color: tuple[int, int, int] = (10, 140, 30),
) -> bytes:
    """A small, real JPEG/PNG so image validation exercises a real decoder."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format=fmt)
    return buffer.getvalue()


def text_bytes(size: int = 512) -> bytes:
    return b"this is definitely not an image\n" * 16


# --------------------------------------------------------------------------- #
# Vision results (design.md section 11.3 shapes)
# --------------------------------------------------------------------------- #


def disease_result(
    *,
    code: str = "anthracnose",
    cause: str = "fungus",
    confidence: float = 0.93,
    status: str = ResultStatus.CONFIDENT.value,
) -> dict[str, Any]:
    return {
        "top": {
            "disease_code": code,
            "label": DISEASE_LABELS.get(code, code),
            "cause_category": cause,
            "confidence": confidence,
        },
        "alternatives": [],
        "is_healthy": code == "healthy",
        "severity": None if code == "healthy" else "moderate",
    }


def ripeness_result(
    *,
    stage: str = "turning",
    days_min: int | None = 4,
    days_max: int | None = 7,
    confidence: float = 0.9,
    status: str = ResultStatus.CONFIDENT.value,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "stage_label": None,
        "confidence": confidence,
        "estimated_days_min": days_min,
        "estimated_days_max": days_max,
        "estimate_confidence": "high",
        "note": f"Perkiraan panen {days_min}-{days_max} hari lagi." if days_min else "-",
    }


def vision_payload(
    scan_type: ScanType = ScanType.DISEASE,
    *,
    result: dict[str, Any] | None = None,
    status: str | None = None,
    model_version: str = "disease-chili-v0.1.0",
    quality: dict[str, Any] | None = None,
    confidence: float | None = 0.9,
) -> VisionResult:
    """Build the exact dataclass ``VisionClient._parse`` would have returned."""
    if result is None:
        if scan_type is ScanType.DISEASE:
            result = disease_result(status=status or ResultStatus.CONFIDENT.value)
        else:
            result = ripeness_result(status=status or ResultStatus.CONFIDENT.value)
    return VisionResult(
        scan_type=scan_type.value,
        status=status or ResultStatus.CONFIDENT.value,
        model_version=model_version,
        commodity_code="chili",
        confidence=confidence if status != ResultStatus.UNKNOWN.value else None,
        quality=quality or {"exposure": "ok", "blur": "ok"},
        result=result,
        inference_ms=12.5,
    )


# --------------------------------------------------------------------------- #
# Fake vision client
# --------------------------------------------------------------------------- #


@dataclass
class FakeVision:
    """Queue-driven stand-in for ``VisionClient``.

    ``enqueue_result``/``enqueue_error`` program the next calls; an empty queue
    answers with ``default_result`` so simple tests stay one line.
    """

    default_result: VisionResult | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    _results: deque[VisionResult] = field(default_factory=deque)
    _errors: deque[Exception] = field(default_factory=deque)

    def enqueue_result(self, result: VisionResult) -> None:
        self._results.append(result)

    def enqueue_error(self, error: Exception) -> None:
        self._errors.append(error)

    async def predict(
        self,
        *,
        scan_type: str,
        image: bytes,
        content_type: str,
        client_uuid: str,
        commodity_code: str,
    ) -> VisionResult:
        self.calls.append(
            {
                "scan_type": scan_type,
                "image": image,
                "content_type": content_type,
                "client_uuid": client_uuid,
                "commodity_code": commodity_code,
            }
        )
        if self._errors:
            raise self._errors.popleft()
        if self._results:
            return self._results.popleft()
        if self.default_result is not None:
            return self.default_result
        return vision_payload(ScanType(scan_type))


# --------------------------------------------------------------------------- #
# Fake weather provider
# --------------------------------------------------------------------------- #


def hourly_slots(
    date_iso: str,
    *,
    humidity: float = 90.0,
    temperature: float = 27.0,
    description: str = "Hujan Ringan",
    count: int = 8,
) -> list[WeatherSlot]:
    """A day of 3-hourly slots, the BMKG cadence."""
    return [
        WeatherSlot(
            local_datetime=f"{date_iso} {hour:02d}:00:00",
            temperature_c=temperature,
            humidity_pct=humidity,
            weather_desc=description,
            wind_speed=8.0,
            wind_direction="TL",
        )
        for hour in range(0, count * 3, 3)
    ]


def forecast(
    adm4_code: str = "31.71.03.1001",
    *,
    days: list[WeatherDay] | None = None,
    fetched_at: datetime | None = None,
    is_stale: bool = False,
) -> WeatherForecast:
    if days is None:
        days = [WeatherDay(date="2026-11-07", slots=hourly_slots("2026-11-07"))]
    return WeatherForecast(
        adm4_code=adm4_code,
        source="bmkg",
        fetched_at=fetched_at or datetime.now(UTC),
        days=days,
        attribution=BMKG_ATTRIBUTION,
        is_stale=is_stale,
    )


@dataclass
class FakeWeather:
    """Yields a canned forecast or raises, and counts the fetches."""

    default: WeatherForecast
    calls: list[str] = field(default_factory=list)
    fail: bool = False

    @staticmethod
    def with_defaults(adm4_code: str = "31.71.03.1001") -> FakeWeather:
        return FakeWeather(default=forecast(adm4_code))

    async def fetch(self, adm4_code: str) -> WeatherForecast:
        self.calls.append(adm4_code)
        if self.fail:
            raise ServiceUnavailable("Cuaca sedang tidak tersedia.") from None
        # The service caches per adm4 code; keep the right code on the payload.
        days = self.default.days
        return WeatherForecast(
            adm4_code=adm4_code,
            source=self.default.source,
            fetched_at=self.default.fetched_at,
            days=days,
            attribution=self.default.attribution,
            is_stale=self.default.is_stale,
        )


# --------------------------------------------------------------------------- #
# API factories
# --------------------------------------------------------------------------- #


def register_payload(*, email: str | None = None, username: str | None = None) -> dict[str, Any]:
    suffix = uuid4().hex[:8]
    return {
        "email": email or f"petani-{suffix}@example.com",
        "username": username or f"petani_{suffix}",
        "full_name": "Pak Budi",
        "password": "sandi-keren-123",
        "consent_training_data": False,
    }


async def register(client: Any, **overrides: Any) -> dict[str, Any]:
    payload = register_payload()
    payload.update(overrides)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["data"]["access_token"], response.text
    return body["data"]


async def login(
    client: Any, *, email: str | None = None, username: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"password": "sandi-keren-123"}
    if email:
        payload["email"] = email
    else:
        payload["username"] = username
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def auth_headers(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def registered_client(client: Any, **overrides: Any) -> tuple[Any, dict[str, str]]:
    """Fresh user + a client with their bearer headers attached."""
    tokens = await register(client, **overrides)
    authed = type(client)(transport=client._transport, base_url=str(client.base_url))
    return authed, auth_headers(tokens)


FARM_PAYLOAD = {
    "name": "Kebun Belakang",
    "adm4_code": "31.71.03.1001",  # Gambir, in the seed
    "lat": -6.1761,
    "lon": 106.8271,
}


async def create_farm(client: Any, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    payload = {**FARM_PAYLOAD, **overrides}
    response = await client.post("/api/v1/farms", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


PLANT_PAYLOAD = {
    "label": "Cabai Keriting 1",
    "commodity_code": "chili",
    "planted_at": "2026-08-01",
    "growth_stage": "fruiting",
}


async def create_plant(
    client: Any, headers: dict[str, str], farm_id: str, **overrides: Any
) -> dict[str, Any]:
    payload = {**PLANT_PAYLOAD, **overrides}
    response = await client.post(f"/api/v1/farms/{farm_id}/plants", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def upload_scan(
    client: Any,
    headers: dict[str, str],
    *,
    scan_type: str = "disease",
    client_uuid: str | None = None,
    image: bytes | None = None,
    plant_id: str | None = None,
    captured_at: datetime | None = None,
) -> Any:
    client_uuid = client_uuid or str(uuid4())
    data: dict[str, Any] = {"type": scan_type, "client_uuid": client_uuid}
    if plant_id:
        data["plant_id"] = plant_id
    if captured_at is not None:
        data["captured_at"] = captured_at.isoformat()
    files = {"image": ("foto.jpg", image or image_bytes(), "image/jpeg")}
    response = await client.post(
        "/api/v1/scans",
        data=data,
        files=files,
        headers={**headers, "Idempotency-Key": client_uuid},
    )
    return response


def days_from_now(days: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)
