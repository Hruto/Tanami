"""Settings, registry and auth dependencies."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.config import Settings
from app.core.errors import Unauthorized
from app.core.state import AppState
from app.services.predict import PredictService
from app.services.registry import ModelRegistry


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.tanami
    return state


def get_settings(state: Annotated[AppState, Depends(get_state)]) -> Settings:
    return state.settings


def get_registry(state: Annotated[AppState, Depends(get_state)]) -> ModelRegistry:
    return state.registry


def get_predict_service(state: Annotated[AppState, Depends(get_state)]) -> PredictService:
    return state.predict_service


def require_service_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Bearer auth for ``/v1`` routes.

    Disabled when no token is configured (local development only); the settings
    model refuses to start in production without one.
    """
    expected = settings.service_token
    if not expected:
        return

    scheme, _, presented = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(presented, expected):
        raise Unauthorized(
            "Token layanan tidak valid.",
            headers={"WWW-Authenticate": "Bearer"},
        )


SettingsDep = Annotated[Settings, Depends(get_settings)]
RegistryDep = Annotated[ModelRegistry, Depends(get_registry)]
StateDep = Annotated[AppState, Depends(get_state)]
PredictServiceDep = Annotated[PredictService, Depends(get_predict_service)]
