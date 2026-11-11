"""Weather: cache in front of BMKG, archive in PostgreSQL.

``design.md`` 12.1 asks for three things this module provides:

* a six-hour cache so the app never waits on BMKG,
* an archive row for every fetch, so historical data survives a provider outage,
* a stale fallback: if BMKG fails, the last cached forecast is returned with
  ``is_stale`` set, and the app labels it "Data terakhir diperbarui <waktu>".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound, ServiceUnavailable
from app.core.logging import get_logger
from app.models.content import WeatherSnapshot
from app.models.farm import Farm
from app.providers.weather import WeatherForecast, WeatherProvider

logger = get_logger("weather_service")

_CACHE_PREFIX = "weather:"
_LAST_GOOD_SUFFIX = ":last"


class WeatherService:
    def __init__(
        self,
        session: AsyncSession,
        redis: Redis,
        settings: Settings,
        provider: WeatherProvider,
    ) -> None:
        self.session = session
        self.redis = redis
        self.settings = settings
        self.provider = provider

    async def for_farm(self, user_id: UUID, farm_id: UUID) -> WeatherForecast:
        farm = await self.session.get(Farm, farm_id)
        if farm is None or farm.user_id != user_id:
            raise NotFound("Lahan tidak ditemukan.")
        return await self.for_adm4(farm.adm4_code)

    async def for_adm4(self, adm4_code: str) -> WeatherForecast:
        cached = await self._read_cache(adm4_code)
        if cached is not None:
            return cached

        try:
            forecast = await self.provider.fetch(adm4_code)
        except ServiceUnavailable:
            last = await self._read_last_good(adm4_code)
            if last is not None:
                logger.warning("weather_serving_stale", adm4_code=adm4_code)
                return last
            raise

        await self._write_cache(forecast)
        await self._archive(forecast)
        return forecast

    async def refresh(self, adm4_code: str) -> WeatherForecast:
        """Fetch from BMKG regardless of the cache (the scheduled job).

        The twice-daily job exists to pick up the new BMKG issue; answering it
        from a cache entry written a few hours earlier would defeat that.
        """
        forecast = await self.provider.fetch(adm4_code)
        await self._write_cache(forecast)
        await self._archive(forecast)
        return forecast

    async def _read_cache(self, adm4_code: str) -> WeatherForecast | None:
        try:
            raw = await self.redis.get(f"{_CACHE_PREFIX}{adm4_code}")
        except Exception as exc:
            logger.warning("weather_cache_read_failed", error=str(exc))
            return None
        if raw is None:
            return None
        try:
            return WeatherForecast.from_payload(json.loads(raw), is_stale=False)
        except (ValueError, KeyError):
            return None

    async def _write_cache(self, forecast: WeatherForecast) -> None:
        payload = json.dumps(forecast.to_payload())
        try:
            await self.redis.set(
                f"{_CACHE_PREFIX}{forecast.adm4_code}",
                payload,
                ex=self.settings.weather_cache_ttl_seconds,
            )
            # Kept far longer than the TTL: it is the outage fallback, not a cache.
            await self.redis.set(
                f"{_CACHE_PREFIX}{forecast.adm4_code}{_LAST_GOOD_SUFFIX}",
                payload,
                ex=60 * 60 * 24 * 30,
            )
        except Exception as exc:
            logger.warning("weather_cache_write_failed", error=str(exc))

    async def _read_last_good(self, adm4_code: str) -> WeatherForecast | None:
        try:
            raw = await self.redis.get(f"{_CACHE_PREFIX}{adm4_code}{_LAST_GOOD_SUFFIX}")
        except Exception:
            raw = None
        if raw is not None:
            try:
                return WeatherForecast.from_payload(json.loads(raw), is_stale=True)
            except (ValueError, KeyError):
                pass

        # Redis lost it: fall back to the archive, which is the durable copy.
        snapshot = (
            await self.session.execute(
                select(WeatherSnapshot)
                .where(WeatherSnapshot.adm4_code == adm4_code)
                .order_by(WeatherSnapshot.fetched_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is None:
            return None
        payload = {
            "adm4_code": snapshot.adm4_code,
            "source": snapshot.source,
            "fetched_at": snapshot.fetched_at.isoformat(),
            "days": snapshot.forecast.get("days", []),
        }
        return WeatherForecast.from_payload(payload, is_stale=True)

    async def _archive(self, forecast: WeatherForecast) -> None:
        """Append to ``weather_snapshots``; never fail the caller over it.

        The archive is history (design 12.1), not the answer: a failed insert
        is logged and rolled back to a savepoint so the farmer still gets the
        forecast and the reminder job still runs.
        """
        try:
            async with self.session.begin_nested():
                self.session.add(
                    WeatherSnapshot(
                        id=uuid4(),
                        adm4_code=forecast.adm4_code,
                        fetched_at=forecast.fetched_at.astimezone(UTC),
                        source=forecast.source,
                        forecast={
                            "days": forecast.to_forecast_data(),
                            "attribution": forecast.attribution,
                        },
                    )
                )
            await self.session.commit()
        except SQLAlchemyError as exc:
            logger.error("weather_archive_failed", adm4_code=forecast.adm4_code, error=str(exc))

    async def active_adm4_codes(self) -> list[str]:
        """Villages that have at least one active farm.

        ``design.md`` 12.1: BMKG is only queried for villages that actually
        have a farm, keeping us inside the 60 requests/minute budget.
        """
        rows = (
            await self.session.execute(
                select(Farm.adm4_code)
                .where(Farm.archived_at.is_(None))
                .distinct()
                .order_by(Farm.adm4_code)
            )
        ).scalars()
        return list(rows)

    async def last_fetched_at(self, adm4_code: str) -> datetime | None:
        return (
            await self.session.execute(
                select(WeatherSnapshot.fetched_at)
                .where(WeatherSnapshot.adm4_code == adm4_code)
                .order_by(WeatherSnapshot.fetched_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
