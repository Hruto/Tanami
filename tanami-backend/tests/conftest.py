"""Shared fixtures.

Integration tests run against a real PostgreSQL 16, migrated with the real
Alembic chain, because the bugs that matter here (timestamp types, CHECK
constraints, JSONB queries, cascades) do not exist in SQLite or in mocks.

* ``TANAMI_TEST_DATABASE_URL`` (``postgresql+asyncpg://...``) points at a
  disposable database, e.g. a CI service container.
* Otherwise ``pgserver`` (a dev dependency) starts a throwaway local cluster.

Redis is fakeredis, storage is in memory, vision and weather are scripted fakes
from ``tests.helpers``, and push notifications are recorded, never sent.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.state import AppState
from app.data.seed import seed_reference_data
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from app.providers.push import LogPushProvider
from app.providers.storage import MemoryStorage
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.helpers import FakeVision, FakeWeather

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_TABLES = {"diseases", "regions", "crop_profiles", "alembic_version"}


def _bootstrap_database(tmp_path_factory: pytest.TempPathFactory) -> str:
    configured = os.environ.get("TANAMI_TEST_DATABASE_URL")
    if configured:
        return configured

    from pgserver import get_server

    server = get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="stop")
    admin_uri = server.get_uri()
    with psycopg.connect(admin_uri, autocommit=True) as connection:
        connection.execute("DROP DATABASE IF EXISTS tanami_test")
        connection.execute("CREATE DATABASE tanami_test")
    base = admin_uri.rsplit("/", 1)[0]
    return base.replace("postgresql://", "postgresql+asyncpg://", 1) + "/tanami_test"


def _migrate(async_url: str, revision: str = "head") -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url.replace("+asyncpg", "+psycopg"))
    command.upgrade(config, revision)


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    url = _bootstrap_database(tmp_path_factory)
    _migrate(url)
    yield url


def make_settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "local",
        "database_url": database_url,
        "storage_backend": "memory",
        "seed_on_startup": False,
        "log_json": False,
        "log_level": "WARNING",
        "jwt_secret": "test-secret-0123456789-0123456789-abcdef",
        "bmkg_min_interval_seconds": 0,
        "jobs_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(make_settings(database_url))
    async with create_session_factory(engine)() as session:
        await seed_reference_data(session)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
async def clean_db(engine: AsyncEngine) -> AsyncEngine:
    """Empty every user-data table; reference data (diseases, regions) stays."""
    async with engine.begin() as connection:
        rows = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = [row[0] for row in rows if row[0] not in REFERENCE_TABLES]
        if tables:
            quoted = ", ".join(f'"{name}"' for name in tables)
            await connection.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    return engine


@pytest.fixture
def settings(database_url: str) -> Settings:
    return make_settings(database_url)


@pytest.fixture
def vision() -> FakeVision:
    return FakeVision()


@pytest.fixture
def weather() -> FakeWeather:
    return FakeWeather.with_defaults()


@pytest.fixture
def push() -> LogPushProvider:
    return LogPushProvider()


@pytest.fixture
def state(
    settings: Settings,
    clean_db: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    vision: FakeVision,
    weather: FakeWeather,
    push: LogPushProvider,
) -> AppState:
    redis = FakeAsyncRedis(decode_responses=True)
    return AppState(
        settings=settings,
        engine=clean_db,
        session_factory=session_factory,
        redis=redis,
        storage=MemoryStorage(),
        vision=vision,  # type: ignore[arg-type]
        weather=weather,
        push=push,
        rate_limiter=RateLimiter(redis),
    )


@pytest.fixture
async def session(
    clean_db: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db:
        yield db


@pytest.fixture
async def client(state: AppState) -> AsyncIterator[AsyncClient]:
    app = create_app(state=state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
