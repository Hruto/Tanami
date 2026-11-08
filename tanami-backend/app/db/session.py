"""Async SQLAlchemy engine and session factory.

The engine is created once per process. ``expire_on_commit=False`` keeps objects
usable after a commit, which matters because services build their response DTOs
after the transaction closes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"server_settings": {"application_name": settings.service_name}},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """A transaction per unit of work.

    Services call this directly (jobs, tests); request handling gets the same
    behaviour through the ``get_session`` dependency.
    """
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ping(engine: AsyncEngine) -> None:
    from sqlalchemy import text

    async with engine.connect() as connection:
        await connection.execute(text("select 1"))


def engine_info(engine: AsyncEngine) -> dict[str, Any]:
    """Pool statistics for ``/healthz``.

    ``AsyncEngine.pool`` is typed as the abstract ``Pool``, but a real engine is
    always backed by ``QueuePool``/``AsyncAdaptedQueuePool``, which is where the
    size counters live. ``getattr`` keeps this honest for a NullPool engine.
    """
    pool = engine.pool
    url = engine.url
    size = getattr(pool, "size", None)
    checked_out = getattr(pool, "checkedout", None)
    return {
        "driver": url.drivername,
        "pool_size": size() if callable(size) else None,
        "checked_out": checked_out() if callable(checked_out) else None,
    }
