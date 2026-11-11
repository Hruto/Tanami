"""Redis connection helpers.

One client per process, created in the app lifespan. Refresh tokens, weather
cache entries, rate-limit counters and the daily push cap all live here; none of
it is authoritative state, which is why Redis is allowed to be lossy.
"""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis


def build_redis(url: str) -> Redis:
    pool = ConnectionPool.from_url(
        url,
        decode_responses=True,
        max_connections=50,
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
        health_check_interval=30,
    )
    return Redis(connection_pool=pool)


async def close_redis(client: Redis) -> None:
    await client.aclose()
