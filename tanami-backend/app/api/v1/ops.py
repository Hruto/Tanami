"""Operational endpoints: liveness, readiness and Prometheus metrics.

Three probes, three different questions (``tqa.md`` 12):

``/health``
    Process is up. Never touches a dependency, so a database blip cannot make
    the orchestrator kill a healthy pod.
``/healthz``
    Alias of ``/health`` kept for load balancers that already point at it.
``/readyz``
    Can this instance serve traffic? Checks PostgreSQL and Redis and answers
    ``503`` with the failing dependency named.

``/metrics`` is Prometheus text exposition, unauthenticated, and therefore
expected to be reachable only on the internal network.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app import __version__
from app.api.deps import RedisDep, SessionDep, get_state
from app.core.context import get_request_id
from app.core.state import AppState

router = APIRouter(tags=["ops"])

StateDep = Annotated[AppState, Depends(get_state)]


@router.get("/health")
async def health(state: StateDep) -> dict[str, object]:
    """Liveness: answers even while PostgreSQL is down."""
    return {
        "status": "ok",
        "service": state.settings.service_name,
        "version": __version__,
        "uptime_seconds": state.uptime_seconds,
    }


@router.get("/healthz")
async def healthz(state: StateDep) -> dict[str, object]:
    return await health(state)


@router.get("/readyz")
async def readyz(
    response: Response,
    state: StateDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, object]:
    """Readiness: every hard dependency must answer."""
    checks: dict[str, str] = {}

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"

    try:
        # redis-py types ping() as ``Awaitable[bool] | bool`` because one
        # method serves both clients; on the asyncio client it is awaitable.
        await cast(Awaitable[bool], redis.ping())
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"

    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # Soft dependency: without vision only scans fail (503 service_unavailable,
    # which the app queues), so it is reported but never takes the API out of
    # rotation.
    ready = getattr(state.vision, "ready", None)
    if ready is not None:
        checks["vision"] = "ok" if await ready() else "unavailable"

    return {
        "status": "ok" if healthy and checks.get("vision", "ok") == "ok" else "degraded",
        "service": state.settings.service_name,
        "version": __version__,
        "request_id": get_request_id(),
        "uptime_seconds": state.uptime_seconds,
        "checks": checks,
    }


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
