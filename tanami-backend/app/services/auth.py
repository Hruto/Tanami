"""Authentication: registration, login, refresh rotation, logout, account deletion.

Sessions live in Redis as ``session:<sid> -> {"user_id", "refresh_hash"}``. Storing
the *hash* means a Redis dump cannot be replayed, and deleting the key on logout
revokes the refresh token immediately - which is the gap ``design.md`` 9 left
open when it mentioned JWT without saying where the refresh token lives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Conflict, Unauthorized, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    new_refresh_token,
    verify_password,
)
from app.domain import UserRole
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair

logger = get_logger("auth")

_SESSION_PREFIX = "session:"
# Set of live session ids per user, so "log out everywhere" is one lookup
# instead of a SCAN over the whole keyspace.
_USER_SESSIONS_PREFIX = "user_sessions:"
# Verified against when the account does not exist, so a wrong email costs the
# same Argon2 time as a wrong password and response timing does not reveal
# which accounts are registered.
_DUMMY_HASH = hash_password("tanami-timing-equaliser")


def session_id_for(refresh_token: str) -> str:
    """A stable key derived from the refresh token.

    Derived from the *digest*, not from the token's prefix, so knowing ``sid``
    from an access token reveals nothing about the refresh token.
    """
    return hash_refresh_token(refresh_token)[:32]


@dataclass(frozen=True, slots=True)
class SessionInfo:
    user_id: UUID
    role: str


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis, settings: Settings) -> None:
        self.session = session
        self.redis = redis
        self.settings = settings

    # ------------------------------------------------------------------ #
    # Registration and login
    # ------------------------------------------------------------------ #
    async def register(self, payload: RegisterRequest) -> tuple[User, TokenPair]:
        email = str(payload.email).lower()
        username = payload.username
        for field, condition, message in (
            ("email", User.email == email, "Email sudah terdaftar."),
            ("username", User.username == username, "Username sudah dipakai."),
        ):
            taken = (await self.session.execute(select(User.id).where(condition))).first()
            if taken is not None:
                raise Conflict(message, details={"field": field})

        now = datetime.now(UTC)
        bootstrap = self.settings.bootstrap_admin_set
        role = (
            UserRole.ADMIN.value
            if email in bootstrap or username in bootstrap
            else UserRole.FARMER.value
        )
        user = User(
            email=email,
            username=username,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            role=role,
            consent_training_data=payload.consent_training_data,
            consent_at=now if payload.consent_training_data else None,
            notification_settings={},
        )
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise Conflict("Email atau username sudah terdaftar.") from exc

        tokens = await self._issue_tokens(user)
        await self.session.commit()
        logger.info("user_registered", user_id=str(user.id))
        return user, tokens

    async def login(self, payload: LoginRequest) -> tuple[User, TokenPair]:
        if payload.email is not None:
            condition = User.email == str(payload.email).lower()
        else:
            condition = User.username == (payload.username or "").strip().lower()
        user = (await self.session.execute(select(User).where(condition))).scalar_one_or_none()

        # One message for "no such account" and "wrong password" so the endpoint
        # cannot be used to enumerate registered users.
        if user is None:
            verify_password(payload.password, _DUMMY_HASH)
            raise Unauthorized("Email/username atau kata sandi salah.")
        if not verify_password(payload.password, user.password_hash):
            raise Unauthorized("Email/username atau kata sandi salah.")
        if user.deleted_at is not None:
            raise Unauthorized("Akun ini sudah dihapus.")

        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)

        tokens = await self._issue_tokens(user)
        await self.session.commit()
        return user, tokens

    # ------------------------------------------------------------------ #
    # Tokens
    # ------------------------------------------------------------------ #
    async def _issue_tokens(self, user: User) -> TokenPair:
        refresh_token = new_refresh_token()
        session_id = session_id_for(refresh_token)
        access_token, expires_at = create_access_token(
            user_id=UUID(str(user.id)),
            role=str(user.role),
            session_id=session_id,
            secret=self.settings.jwt_secret,
            algorithm=self.settings.jwt_algorithm,
            issuer=self.settings.jwt_issuer,
            ttl_seconds=self.settings.access_token_ttl_seconds,
        )
        await self.redis.set(
            f"{_SESSION_PREFIX}{session_id}",
            json.dumps(
                {
                    "user_id": str(user.id),
                    "refresh_hash": hash_refresh_token(refresh_token),
                    "role": str(user.role),
                }
            ),
            ex=self.settings.refresh_token_ttl_seconds,
        )
        index_key = f"{_USER_SESSIONS_PREFIX}{user.id}"
        await self.redis.sadd(index_key, session_id)  # type: ignore[misc]
        await self.redis.expire(index_key, self.settings.refresh_token_ttl_seconds)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int((expires_at - datetime.now(UTC)).total_seconds()),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Rotate the refresh token.

        Rotation matters: a stolen token is usable at most once, and the reuse of
        an already-rotated token is visible as a failed lookup.
        """
        session_id = session_id_for(refresh_token)
        key = f"{_SESSION_PREFIX}{session_id}"
        raw = await self.redis.get(key)
        if raw is None:
            raise Unauthorized("Sesi sudah berakhir. Silakan masuk lagi.")

        data = json.loads(raw)
        if data.get("refresh_hash") != hash_refresh_token(refresh_token):
            # A mismatch means the presented token is not the one issued for this
            # session id; drop the session rather than leaving it dangling.
            await self.redis.delete(key)
            raise Unauthorized("Sesi tidak valid. Silakan masuk lagi.")

        user = await self.session.get(User, UUID(str(data["user_id"])))
        if user is None or user.deleted_at is not None:
            await self.redis.delete(key)
            raise Unauthorized("Akun ini sudah tidak aktif.")

        await self._drop_session(session_id, user.id)
        tokens = await self._issue_tokens(user)
        await self.session.commit()
        return tokens

    async def logout(self, refresh_token: str) -> None:
        session_id = session_id_for(refresh_token)
        raw = await self.redis.get(f"{_SESSION_PREFIX}{session_id}")
        user_id = None
        if raw is not None:
            try:
                user_id = UUID(str(json.loads(raw).get("user_id")))
            except (ValueError, TypeError):
                user_id = None
        await self._drop_session(session_id, user_id)

    async def _drop_session(self, session_id: str, user_id: UUID | None) -> None:
        await self.redis.delete(f"{_SESSION_PREFIX}{session_id}")
        if user_id is not None:
            await self.redis.srem(f"{_USER_SESSIONS_PREFIX}{user_id}", session_id)  # type: ignore[misc]

    async def authenticate(self, token: str) -> SessionInfo:
        """Verify an access token and that its session still exists."""
        try:
            claims = decode_access_token(
                token,
                secret=self.settings.jwt_secret,
                algorithm=self.settings.jwt_algorithm,
                issuer=self.settings.jwt_issuer,
            )
        except TokenError as exc:
            raise Unauthorized("Sesi Anda tidak valid atau sudah berakhir.") from exc

        if not await self.redis.exists(f"{_SESSION_PREFIX}{claims.session_id}"):
            raise Unauthorized("Sesi sudah berakhir. Silakan masuk lagi.")
        return SessionInfo(user_id=claims.user_id, role=claims.role)

    async def revoke_all_sessions(self, user_id: UUID) -> int:
        """Account deletion and password change: every device is logged out."""
        index_key = f"{_USER_SESSIONS_PREFIX}{user_id}"
        session_ids: set[str] = set(await self.redis.smembers(index_key))  # type: ignore[misc]
        for session_id in session_ids:
            await self.redis.delete(f"{_SESSION_PREFIX}{session_id}")
        await self.redis.delete(index_key)
        return len(session_ids)

    async def change_password(self, user: User, current: str, new: str) -> TokenPair:
        """Replace the password, log out every device, and keep this one in."""
        if not verify_password(current, user.password_hash):
            raise ValidationError(
                "Kata sandi saat ini salah.", details={"field": "current_password"}
            )
        if current == new:
            raise ValidationError(
                "Kata sandi baru harus berbeda dari yang lama.",
                details={"field": "new_password"},
            )
        user.password_hash = hash_password(new)
        await self.revoke_all_sessions(user.id)
        tokens = await self._issue_tokens(user)
        await self.session.commit()
        return tokens
