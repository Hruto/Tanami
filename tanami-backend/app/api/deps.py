"""FastAPI dependencies.

Routes only ever receive what they need: the current user, a session, or a
provider. Anything that touches the outside world is substitutable through
``app.state`` so integration tests can run without a network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.context import set_user_id
from app.core.errors import Forbidden, Unauthorized
from app.core.rate_limit import RateLimiter
from app.core.state import AppState
from app.domain import UserRole
from app.models.user import User
from app.providers.push import PushProvider
from app.providers.storage import StorageProvider
from app.providers.vision import VisionClient
from app.providers.weather import WeatherProvider
from app.services.auth import AuthService
from app.services.detection import DetectionService
from app.services.farm import FarmService, PlantService, RegionService
from app.services.forum import ForumService
from app.services.reminder import ReminderService
from app.services.scan import ScanService
from app.services.tracking import TrackingService
from app.services.weather import WeatherService


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.tanami
    return state


def get_settings(state: Annotated[AppState, Depends(get_state)]) -> Settings:
    return state.settings


def get_redis(state: Annotated[AppState, Depends(get_state)]) -> Redis:
    return state.redis


def get_storage(state: Annotated[AppState, Depends(get_state)]) -> StorageProvider:
    return state.storage


def get_vision(state: Annotated[AppState, Depends(get_state)]) -> VisionClient:
    return state.vision


def get_weather_provider(state: Annotated[AppState, Depends(get_state)]) -> WeatherProvider:
    return state.weather


def get_push(state: Annotated[AppState, Depends(get_state)]) -> PushProvider:
    return state.push


def get_rate_limiter(state: Annotated[AppState, Depends(get_state)]) -> RateLimiter:
    return state.rate_limiter


async def get_session(
    state: Annotated[AppState, Depends(get_state)],
) -> AsyncIterator[AsyncSession]:
    """One transaction per request.

    Committing here rather than in every service keeps the boundary honest: a
    service that raises rolls the whole request back.
    """
    async with state.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(session, redis, settings)


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized(
            "Sesi Anda tidak valid atau sudah berakhir.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


async def get_current_user(
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    info = await auth.authenticate(token)
    user = await session.get(User, info.user_id)
    if user is None or user.deleted_at is not None:
        raise Unauthorized("Akun ini sudah tidak aktif.")
    set_user_id(str(user.id))
    return user


async def get_optional_user(
    auth: Annotated[AuthService, Depends(get_auth_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """The caller if a valid bearer token is present, otherwise ``None``.

    For public reads (the forum) that show more to the author or a moderator.
    A malformed or expired token is treated as anonymous, not as an error.
    """
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    try:
        info = await auth.authenticate(token.strip())
    except Unauthorized:
        return None
    user = await session.get(User, info.user_id)
    if user is None or user.deleted_at is not None:
        return None
    set_user_id(str(user.id))
    return user


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """Dependency factory: the current user must hold one of ``roles``.

    The role is read from the database row, not from the access token, so a
    demotion takes effect on the next request rather than when the token
    expires.
    """
    allowed = {role.value for role in roles}

    async def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise Forbidden("Fitur ini hanya untuk moderator atau admin.")
        return user

    return dependency


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
ModeratorUser = Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
RedisDep = Annotated[Redis, Depends(get_redis)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
StorageDep = Annotated[StorageProvider, Depends(get_storage)]
VisionDep = Annotated[VisionClient, Depends(get_vision)]
WeatherProviderDep = Annotated[WeatherProvider, Depends(get_weather_provider)]
PushDep = Annotated[PushProvider, Depends(get_push)]


def scan_service(
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    vision: VisionDep,
) -> ScanService:
    return ScanService(session, settings, storage, vision)


def farm_service(session: SessionDep, settings: SettingsDep) -> FarmService:
    return FarmService(session, settings)


def plant_service(session: SessionDep, settings: SettingsDep, storage: StorageDep) -> PlantService:
    return PlantService(session, settings, storage)


def region_service(session: SessionDep) -> RegionService:
    return RegionService(session)


def weather_service(
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    provider: WeatherProviderDep,
) -> WeatherService:
    return WeatherService(session, redis, settings, provider)


def reminder_service(session: SessionDep, settings: SettingsDep, push: PushDep) -> ReminderService:
    return ReminderService(session, settings, push)


def forum_service(session: SessionDep, settings: SettingsDep, storage: StorageDep) -> ForumService:
    return ForumService(session, settings, storage)


def tracking_service(
    session: SessionDep, settings: SettingsDep, storage: StorageDep
) -> TrackingService:
    return TrackingService(session, settings, storage)


def detection_service(
    session: SessionDep, settings: SettingsDep, storage: StorageDep
) -> DetectionService:
    return DetectionService(session, settings, storage)


ScanServiceDep = Annotated[ScanService, Depends(scan_service)]
TrackingServiceDep = Annotated[TrackingService, Depends(tracking_service)]
DetectionServiceDep = Annotated[DetectionService, Depends(detection_service)]
FarmServiceDep = Annotated[FarmService, Depends(farm_service)]
PlantServiceDep = Annotated[PlantService, Depends(plant_service)]
RegionServiceDep = Annotated[RegionService, Depends(region_service)]
WeatherServiceDep = Annotated[WeatherService, Depends(weather_service)]
ReminderServiceDep = Annotated[ReminderService, Depends(reminder_service)]
ForumServiceDep = Annotated[ForumService, Depends(forum_service)]
