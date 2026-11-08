"""Redis-backed rate limiting (``design.md`` 10.3).

A fixed-window counter is enough for the three limits that matter (login,
scan upload, everything else) and has none of the memory growth of a sliding
log. Fail-open when Redis is unreachable: a broken cache must not lock farmers
out of their own account.
"""

from __future__ import annotations

import time

from redis.asyncio import Redis

from app.core.errors import RateLimited
from app.core.logging import get_logger

logger = get_logger("rate_limit")


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def check(self, *, bucket: str, identity: str, limit: int, window_seconds: int) -> None:
        """Raise ``RateLimited`` once ``identity`` exceeds ``limit`` in the window."""
        if limit <= 0:
            return

        window = int(time.time()) // window_seconds
        key = f"ratelimit:{bucket}:{identity}:{window}"
        try:
            current = await self.redis.incr(key)
            if current == 1:
                await self.redis.expire(key, window_seconds)
        except Exception as exc:
            logger.warning("rate_limit_unavailable", bucket=bucket, error=str(exc))
            return

        if current > limit:
            retry_after = window_seconds - (int(time.time()) % window_seconds)
            raise RateLimited(
                "Terlalu banyak permintaan. Coba lagi sebentar.",
                details={"limit": limit, "window_seconds": window_seconds},
                headers={"Retry-After": str(max(retry_after, 1))},
            )
