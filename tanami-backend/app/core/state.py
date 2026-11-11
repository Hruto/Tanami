"""Application state shared by every request.

The providers are created once at startup and disposed in the lifespan; holding
them here (rather than in module globals) is what makes the app testable: tests
build their own ``AppState`` with an in-memory storage and a fake vision client.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.providers.push import PushProvider
from app.providers.storage import StorageProvider
from app.providers.vision import VisionClient
from app.providers.weather import WeatherProvider


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    storage: StorageProvider
    vision: VisionClient
    weather: WeatherProvider
    push: PushProvider
    rate_limiter: RateLimiter
    started_at: float = field(default_factory=time.monotonic)

    @property
    def uptime_seconds(self) -> float:
        return round(time.monotonic() - self.started_at, 3)

    async def close(self) -> None:
        close = getattr(self.vision, "aclose", None)
        if close is not None:
            await close()
        close = getattr(self.weather, "aclose", None)
        if close is not None:
            await close()
        close = getattr(self.push, "aclose", None)
        if close is not None:
            await close()
        await self.redis.aclose()
        await self.engine.dispose()
