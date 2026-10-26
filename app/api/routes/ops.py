from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.api.deps import RegistryDep, SettingsDep, StateDep
from app.core.config import Settings
from app.core.errors import NotFound, Unauthorized
from app.schemas.prediction import (
    HealthData,
    HealthResponse,
    ModelInfo,
    ReadyData,
    ReadyResponse,
)
from app.services.registry import ModelRegistry

router = APIRouter(tags=["ops"])


def _health_payload(settings: Settings, registry: ModelRegistry, uptime: float) -> HealthResponse:
    models = [
        ModelInfo(
            scan_type=model.scan_type,
            model_version=model.version,
            commodity_code=model.manifest.commodity_code,
            backend=settings.model_backend,
            labels=list(model.manifest.labels),
            input_size=model.manifest.input_size,
            metrics={
                key: value
                for key, value in model.manifest.metrics.items()
                if isinstance(value, (int, float, str))
            },
            is_shadow=model.is_shadow,
        )
        for model in registry.all_models()
    ]
    return HealthResponse(
        data=HealthData(
            status="ok" if registry.is_ready else "degraded",
            service=settings.service_name,
            version=__version__,
            environment=settings.app_env,
            uptime_seconds=uptime,
            models=models,
        )
    )


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness and model status",
    description=(
        "200 when every primary model is loaded, 503 otherwise. Covers this "
        "service only; the backend aggregates its own dependencies separately."
    ),
)
def healthz(
    response: Response, settings: SettingsDep, registry: RegistryDep, state: StateDep
) -> HealthResponse:
    if not registry.is_ready:
        response.status_code = 503
    return _health_payload(settings, registry, state.uptime_seconds)


@router.get(
    "/readyz",
    response_model=ReadyResponse,
    summary="Readiness probe",
    description="503 until every primary model is loaded.",
)
def readyz(response: Response, registry: RegistryDep) -> ReadyResponse:
    ready = registry.is_ready
    if not ready:
        response.status_code = 503
    return ReadyResponse(data=ReadyData(ready=ready, missing=registry.load_errors))


@router.get("/livez", include_in_schema=False)
def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get(
    "/v1/models",
    response_model=HealthResponse,
    summary="Loaded model inventory",
)
def list_models(settings: SettingsDep, registry: RegistryDep, state: StateDep) -> HealthResponse:
    return _health_payload(settings, registry, state.uptime_seconds)


@router.post(
    "/v1/models/reload",
    response_model=HealthResponse,
    summary="Reload models from disk without restarting",
    description=(
        "Used for a model-only release or rollback (TQA 8.4). Requires the admin "
        "bearer token; disabled when VISION_ADMIN_TOKEN is empty."
    ),
)
def reload_models(
    settings: SettingsDep,
    registry: RegistryDep,
    state: StateDep,
    authorization: str | None = Header(default=None),
) -> HealthResponse:
    expected = settings.admin_token
    if not expected:
        raise NotFound("API admin tidak diaktifkan.")

    scheme, _, presented = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(presented, expected):
        raise Unauthorized("Token admin tidak valid.")

    registry.load()
    return _health_payload(settings, registry, state.uptime_seconds)
