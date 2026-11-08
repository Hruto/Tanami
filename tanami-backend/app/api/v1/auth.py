"""Auth, profile, notification settings and device routes (``design.md`` 10.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import delete, select

from app.api.deps import (
    AuthServiceDep,
    CurrentUser,
    RateLimiterDep,
    SessionDep,
    SettingsDep,
)
from app.core.context import set_user_id
from app.core.errors import NotFound
from app.core.middleware import client_ip
from app.models.reminder import Device
from app.schemas.auth import (
    DeviceCreate,
    DeviceOut,
    LoginRequest,
    NotificationSettingsOut,
    NotificationSettingsUpdate,
    PasswordChange,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
    UserUpdate,
)
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.services.content import UserService

router = APIRouter(tags=["auth"])


def _device_out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=str(device.id),
        platform=device.platform,
        last_seen_at=device.last_seen_at,
        created_at=device.created_at,
    )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    auth: AuthServiceDep,
    limiter: RateLimiterDep,
    settings: SettingsDep,
    request: Request,
) -> Envelope[TokenPair]:
    # Account creation is attractive to bots too, but see the setting for why
    # its budget is looser than login.
    await limiter.check(
        bucket="register",
        identity=client_ip(request.scope, trust_forwarded_for=settings.trust_forwarded_for),
        limit=settings.register_rate_limit_per_minute,
        window_seconds=60,
    )
    _, tokens = await auth.register(payload)
    return Envelope(data=tokens)


@router.post("/auth/login")
async def login(
    payload: LoginRequest,
    auth: AuthServiceDep,
    limiter: RateLimiterDep,
    settings: SettingsDep,
    request: Request,
) -> Envelope[TokenPair]:
    # design 10.3: 5 attempts per minute per IP.
    await limiter.check(
        bucket="login",
        identity=client_ip(request.scope, trust_forwarded_for=settings.trust_forwarded_for),
        limit=settings.login_rate_limit_per_minute,
        window_seconds=60,
    )
    user, tokens = await auth.login(payload)
    set_user_id(str(user.id))
    return Envelope(data=tokens)


@router.post("/auth/refresh")
async def refresh(payload: RefreshRequest, auth: AuthServiceDep) -> Envelope[TokenPair]:
    return Envelope(data=await auth.refresh(payload.refresh_token))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, auth: AuthServiceDep) -> Response:
    await auth.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/me")
async def me(user: CurrentUser, session: SessionDep) -> Envelope[UserOut]:
    return Envelope(data=await UserService(session).profile(user))


@router.patch("/users/me")
async def update_me(
    payload: UserUpdate, user: CurrentUser, session: SessionDep
) -> Envelope[UserOut]:
    return Envelope(data=await UserService(session).update(user, payload))


@router.post("/users/me/password")
async def change_password(
    payload: PasswordChange, user: CurrentUser, auth: AuthServiceDep
) -> Envelope[TokenPair]:
    """Change the password; every other device is logged out (TQA 9).

    The response carries a fresh token pair so this device stays signed in.
    """
    tokens = await auth.change_password(user, payload.current_password, payload.new_password)
    return Envelope(data=tokens)


@router.delete("/users/me", status_code=status.HTTP_202_ACCEPTED)
async def delete_me(
    user: CurrentUser, session: SessionDep, auth: AuthServiceDep
) -> Envelope[dict[str, object]]:
    # Revoke first: once the account is marked deleted, ``authenticate`` would
    # reject the token and the session cleanup could never run.
    await auth.revoke_all_sessions(user.id)
    await session.execute(delete(Device).where(Device.user_id == user.id))
    scheduled = await UserService(session).soft_delete(user)
    return Envelope(data=scheduled)


@router.get("/users/me/notification-settings")
async def get_notification_settings(
    user: CurrentUser, session: SessionDep
) -> Envelope[NotificationSettingsOut]:
    return Envelope(data=await UserService(session).notification_settings(user))


@router.patch("/users/me/notification-settings")
async def patch_notification_settings(
    payload: NotificationSettingsUpdate, user: CurrentUser, session: SessionDep
) -> Envelope[NotificationSettingsOut]:
    return Envelope(data=await UserService(session).update_notification_settings(user, payload))


@router.get("/devices")
async def list_devices(user: CurrentUser, session: SessionDep) -> ListEnvelope[DeviceOut]:
    rows = (
        await session.execute(
            select(Device).where(Device.user_id == user.id).order_by(Device.created_at.desc())
        )
    ).scalars()
    return ListEnvelope(
        data=[_device_out(device) for device in rows],
        meta=PaginationMeta(next_cursor=None, has_more=False),
    )


@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceCreate, user: CurrentUser, session: SessionDep
) -> Envelope[DeviceOut]:
    """Register or re-point an FCM token.

    ``fcm_token`` is globally unique. When someone else logs in on the same
    handset the token must move accounts, otherwise pushes for the previous user
    keep arriving.
    """
    now = datetime.now(UTC)
    device = (
        await session.execute(select(Device).where(Device.fcm_token == payload.fcm_token))
    ).scalar_one_or_none()

    if device is None:
        device = Device(
            user_id=user.id,
            fcm_token=payload.fcm_token,
            platform=payload.platform.value,
            last_seen_at=now,
        )
        session.add(device)
    else:
        device.user_id = user.id
        device.platform = payload.platform.value
        device.last_seen_at = now

    await session.commit()
    await session.refresh(device)
    return Envelope(data=_device_out(device))


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: UUID, user: CurrentUser, session: SessionDep) -> Response:
    device = await session.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise NotFound("Perangkat tidak ditemukan.")
    await session.execute(delete(Device).where(Device.id == device.id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
