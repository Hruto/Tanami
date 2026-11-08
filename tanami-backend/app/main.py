"""Application factory and lifespan.

Everything the app needs from the outside world is created once here and stored
on ``app.state.tanami``. That single choice is what makes the test suite cheap:
a test builds its own ``AppState`` with an in-memory storage, a fake vision
client and fakeredis, and passes it to ``create_app``.

Startup order matters:

1. logging, so every later failure is structured,
2. database engine and session factory,
3. Redis, with a ping that is reported but never fatal (rate limiting, sessions
   and the weather cache all degrade; refusing to boot does not help anyone),
4. providers (vision, weather, storage, push),
5. reference data seed, only when asked,
6. scheduler, only when enabled and only once per deployment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.media import router as media_router
from app.api.v1 import api_router
from app.api.v1.ops import router as ops_router
from app.core.config import Settings
from app.core.handlers import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.metrics import JOB_RUNS
from app.core.middleware import (
    BodySizeLimitMiddleware,
    GlobalRateLimitMiddleware,
    RequestContextMiddleware,
    security_headers,
)
from app.core.rate_limit import RateLimiter
from app.core.redis import build_redis
from app.core.state import AppState
from app.data.seed import seed_reference_data
from app.db.session import create_engine, create_session_factory
from app.providers.push import build_push_provider
from app.providers.storage import MemoryStorage, build_storage
from app.providers.vision import build_vision_client
from app.providers.weather import build_weather_provider

logger = get_logger("app")

DESCRIPTION = """
API Tanami: autentikasi, lahan dan tanaman, scan penyakit dan kematangan,
riwayat, cuaca BMKG, reminder, forum, moderasi, dan basis pengetahuan penyakit.

Semua respons memakai amplop `{"data": ...}`. Galat memakai
`{"error": {"code", "message", "details", "request_id"}}` dengan `message`
berbahasa Indonesia yang layak ditampilkan ke pengguna.
""".strip()


def build_state(settings: Settings) -> AppState:
    engine = create_engine(settings)
    redis = build_redis(settings.redis_url)
    return AppState(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        redis=redis,
        storage=build_storage(settings),
        vision=build_vision_client(settings),
        weather=build_weather_provider(settings),
        push=build_push_provider(settings),
        rate_limiter=RateLimiter(redis),
    )


async def _startup(state: AppState) -> None:
    try:
        # redis-py types ping() as ``Awaitable[bool] | bool`` because one
        # method serves both clients; on the asyncio client it is awaitable.
        await cast(Awaitable[bool], state.redis.ping())
        logger.info("redis_ready")
    except Exception as exc:
        logger.warning("redis_unavailable", error=str(exc))

    if state.settings.seed_on_startup:
        try:
            async with state.session_factory() as session:
                await seed_reference_data(session)
        except Exception as exc:
            # A missing seed degrades content, it does not make the API unusable.
            logger.error("seed_failed", error=str(exc))


async def _shutdown(state: AppState, scheduler: object | None) -> None:
    if scheduler is not None:
        shutdown = getattr(scheduler, "shutdown", None)
        if shutdown is not None:
            shutdown(wait=False)
    # Closes the vision/weather/push HTTP clients, Redis and the engine.
    await state.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    state: AppState = app.state.tanami
    scheduler = None

    await _startup(state)

    if state.settings.jobs_enabled:
        from app.jobs.scheduler import build_scheduler

        scheduler = build_scheduler(state)
        scheduler.start()
        JOB_RUNS.labels(job="scheduler", result="started").inc()
        logger.info("scheduler_started", timezone=state.settings.timezone)

    logger.info(
        "service_started",
        version=__version__,
        env=state.settings.app_env,
        jobs=state.settings.jobs_enabled,
    )
    try:
        yield
    finally:
        await _shutdown(state, scheduler)
        logger.info("service_stopped")


def create_app(settings: Settings | None = None, *, state: AppState | None = None) -> FastAPI:
    resolved = state.settings if state is not None else (settings or Settings())
    configure_logging(resolved.log_level, json_output=resolved.log_json)

    app = FastAPI(
        title="Tanami API",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if resolved.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved.app_env != "production" else None,
    )
    app.state.tanami = state if state is not None else build_state(resolved)

    # ``add_middleware`` wraps, so the *last* one added runs outermost. Request
    # order, outside in: CORS (so even a 413/429 carries CORS headers), request
    # id (so every response and log line has one), security headers, body size
    # guard, global rate limit, then the routes.
    app.add_middleware(GlobalRateLimitMiddleware, limit=resolved.global_rate_limit_per_minute)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=resolved.max_scan_upload_bytes)
    app.add_middleware(security_headers)
    app.add_middleware(RequestContextMiddleware, trust_forwarded_for=resolved.trust_forwarded_for)
    if resolved.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "X-Request-ID",
                "Accept-Language",
            ],
            expose_headers=["X-Request-ID", "Retry-After"],
            max_age=600,
        )

    register_error_handlers(app)
    app.include_router(ops_router)
    app.include_router(api_router)
    if resolved.app_env != "production" and isinstance(app.state.tanami.storage, MemoryStorage):
        # Lets the frontend team see uploaded photos against a local backend
        # without MinIO. Never mounted in production (S3 is mandatory there).
        app.include_router(media_router)
    return app
