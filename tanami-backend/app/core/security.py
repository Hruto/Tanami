"""Password hashing and JWT creation/verification.

Argon2id for passwords (TQA 9). Access tokens are short-lived JWTs; refresh
tokens are opaque random strings whose SHA-256 hash is stored in Redis so they
can be revoked on logout or account deletion (the open question in
``design.md`` 9).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

ACCESS_TOKEN_TYPE = "access"  # noqa: S105


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or of the wrong type."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def hash_refresh_token(token: str) -> str:
    """Store only a digest, so a Redis dump does not expose usable tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def refresh_token_matches(presented: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_refresh_token(presented), stored_hash)


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    role: str
    session_id: str
    expires_at: datetime


def create_access_token(
    *,
    user_id: UUID,
    role: str,
    session_id: str,
    secret: str,
    algorithm: str,
    issuer: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "sid": session_id,
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": issuer,
        "jti": uuid4().hex,
    }
    token = jwt.encode(payload, secret, algorithm=algorithm)
    return token, expires_at


def decode_access_token(
    token: str,
    *,
    secret: str,
    algorithm: str,
    issuer: str,
) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            issuer=issuer,
            options={"require": ["exp", "iat", "sub", "iss", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token kedaluwarsa") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token tidak valid") from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        msg = "jenis token tidak sesuai"
        raise TokenError(msg)

    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("sub bukan UUID") from exc

    session_id = payload.get("sid")
    if not isinstance(session_id, str) or not session_id:
        raise TokenError("sesi tidak ada di token")

    return AccessClaims(
        user_id=user_id,
        role=str(payload.get("role", "farmer")),
        session_id=session_id,
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
    )
