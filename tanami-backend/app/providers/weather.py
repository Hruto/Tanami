"""BMKG weather provider (``design.md`` 12.1).

Only the backend calls BMKG; the app never does. Two things the contract is
explicit about and this module guarantees:

* results are cached per ``adm4_code`` for six hours (BMKG refreshes twice a day),
* the response always carries ``attribution`` because the licence requires the
  app to display the source.

The provider returns a normalised shape; ``forecast`` is stored verbatim in
``weather_snapshots`` so the archive can be re-parsed later without a migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import ServiceUnavailable, ValidationError
from app.core.logging import get_logger

logger = get_logger("weather")

BMKG_ATTRIBUTION = "Sumber data: BMKG"


@dataclass(frozen=True, slots=True)
class WeatherSlot:
    local_datetime: str
    temperature_c: float | None
    humidity_pct: float | None
    weather_desc: str
    wind_speed: float | None
    wind_direction: str
    # BMKG ``tp``: total precipitation in the slot, in mm. Optional because the
    # archive predates it and some responses omit it.
    precipitation_mm: float | None = None


@dataclass(frozen=True, slots=True)
class WeatherDay:
    date: str
    slots: list[WeatherSlot]


@dataclass(frozen=True, slots=True)
class WeatherForecast:
    adm4_code: str
    source: str
    fetched_at: datetime
    days: list[WeatherDay]
    attribution: str = BMKG_ATTRIBUTION
    is_stale: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "adm4_code": self.adm4_code,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
            "attribution": self.attribution,
            "is_stale": self.is_stale,
            "days": [
                {
                    "date": day.date,
                    "slots": [
                        {
                            "local_datetime": slot.local_datetime,
                            "t": slot.temperature_c,
                            "hu": slot.humidity_pct,
                            "weather_desc": slot.weather_desc,
                            "ws": slot.wind_speed,
                            "wd": slot.wind_direction,
                            "tp": slot.precipitation_mm,
                        }
                        for slot in day.slots
                    ],
                }
                for day in self.days
            ],
        }

    def to_forecast_data(self) -> list[dict[str, object]]:
        """The flat, JSON-friendly form persisted in ``weather_snapshots``."""
        return [
            {
                "date": day.date,
                "slots": [
                    {
                        "local_datetime": slot.local_datetime,
                        "t": slot.temperature_c,
                        "hu": slot.humidity_pct,
                        "weather_desc": slot.weather_desc,
                        "ws": slot.wind_speed,
                        "wd": slot.wind_direction,
                        "tp": slot.precipitation_mm,
                    }
                    for slot in day.slots
                ],
            }
            for day in self.days
        ]

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, is_stale: bool) -> WeatherForecast:
        return cls(
            adm4_code=str(payload["adm4_code"]),
            source=str(payload["source"]),
            fetched_at=datetime.fromisoformat(str(payload["fetched_at"])),
            days=[
                WeatherDay(
                    date=str(day["date"]),
                    slots=[
                        WeatherSlot(
                            local_datetime=str(slot["local_datetime"]),
                            temperature_c=_as_float(slot.get("t")),
                            humidity_pct=_as_float(slot.get("hu")),
                            weather_desc=str(slot.get("weather_desc", "")),
                            wind_speed=_as_float(slot.get("ws")),
                            wind_direction=str(slot.get("wd", "")),
                            precipitation_mm=_as_float(slot.get("tp")),
                        )
                        for slot in day.get("slots", [])
                    ],
                )
                for day in payload.get("days", [])
            ],
            attribution=str(payload.get("attribution", BMKG_ATTRIBUTION)),
            is_stale=is_stale,
        )


def _as_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


class WeatherProvider(Protocol):
    async def fetch(self, adm4_code: str) -> WeatherForecast: ...


class BmkgWeatherProvider:
    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._base_url = settings.bmkg_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.weather_timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "tanami-backend/0.1"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, adm4_code: str) -> WeatherForecast:
        _validate_adm4(adm4_code)
        try:
            response = await self._client.get(
                f"{self._base_url}/publik/prakiraan-cuaca",
                params={"adm4": adm4_code},
            )
        except httpx.HTTPError as exc:
            logger.warning("bmkg_transport_error", adm4_code=adm4_code, error=str(exc))
            raise ServiceUnavailable("Data cuaca sedang tidak tersedia.") from exc

        if response.status_code != 200:
            logger.warning("bmkg_status", adm4_code=adm4_code, status=response.status_code)
            raise ServiceUnavailable("Data cuaca sedang tidak tersedia.")

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("bmkg_bad_json", adm4_code=adm4_code)
            raise ServiceUnavailable("Data cuaca sedang tidak tersedia.") from exc

        days = _parse_bmkg(payload)
        if not days:
            logger.warning("bmkg_empty", adm4_code=adm4_code)
            raise ServiceUnavailable("Data cuaca sedang tidak tersedia.")

        return WeatherForecast(
            adm4_code=adm4_code,
            source="bmkg",
            fetched_at=datetime.now(UTC),
            days=days,
        )


def _validate_adm4(value: str) -> None:
    """adm4 codes look like ``32.75.02.1001``; anything else is a client error."""
    parts = value.split(".")
    valid = (
        len(parts) == 4
        and all(part.isdigit() for part in parts)
        and all(1 <= len(p) <= 4 for p in parts)
    )
    if not valid:
        raise ValidationError(
            "Kode wilayah tidak valid. Gunakan kode desa format 32.75.02.1001.",
            details={"field": "adm4_code"},
        )


def _parse_bmkg(payload: Any) -> list[WeatherDay]:
    """Parse BMKG's ``data[0].cuaca`` (list of lists grouped by day).

    The API has changed shape before, so unknown fields are ignored and a
    partially valid response still yields the slots it could read.
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []

    days: dict[str, WeatherDay] = {}
    for location in data:
        if not isinstance(location, dict):
            continue
        cuaca = location.get("cuaca")
        if not isinstance(cuaca, list):
            continue
        for group in cuaca:
            if not isinstance(group, list):
                continue
            for entry in group:
                if not isinstance(entry, dict):
                    continue
                local_dt = entry.get("local_datetime")
                if not local_dt:
                    continue
                slot = WeatherSlot(
                    local_datetime=str(local_dt).replace("T", " "),
                    temperature_c=_as_float(entry.get("t")),
                    humidity_pct=_as_float(entry.get("hu")),
                    weather_desc=str(entry.get("weather_desc") or ""),
                    wind_speed=_as_float(entry.get("ws")),
                    wind_direction=str(entry.get("wd") or ""),
                    precipitation_mm=_as_float(entry.get("tp")),
                )
                day_key = str(local_dt)[:10]
                day = days.setdefault(day_key, WeatherDay(date=day_key, slots=[]))
                day.slots.append(slot)

    ordered = [days[key] for key in sorted(days)]
    for day in ordered:
        day.slots.sort(key=lambda item: item.local_datetime)
    return ordered[:3]


def build_weather_provider(settings: Settings) -> WeatherProvider:
    return BmkgWeatherProvider(settings)
