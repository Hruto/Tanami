"""Auth, profile and notification-settings schemas (requirement 6, design 10.4)."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import EmailStr, Field, field_validator, model_validator

from app.core.errors import ValidationError
from app.domain import Platform, ReminderType, UserRole
from app.schemas.base import ApiModel

_USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,32}$")
_PASSWORD_MIN = 8


def clean_username(value: str) -> str:
    cleaned = value.strip().lower()
    if not _USERNAME_RE.match(cleaned):
        raise ValidationError(
            "Username 3-32 karakter: huruf kecil, angka, titik, atau garis bawah.",
            details={"field": "username"},
        )
    return cleaned


def clean_name(value: str, *, field: str = "full_name") -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValidationError("Nama lengkap tidak boleh kosong.", details={"field": field})
    return cleaned


class RegisterRequest(ApiModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    full_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=_PASSWORD_MIN, max_length=128)
    consent_training_data: bool = False

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return clean_username(value)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str) -> str:
        return clean_name(value)


class LoginRequest(ApiModel):
    """Log in with the email **or** the username."""

    email: EmailStr | None = None
    username: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> LoginRequest:
        if (self.email is None) == (self.username is None):
            raise ValidationError(
                "Isi salah satu: email atau username.", details={"field": "email/username"}
            )
        return self


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=_PASSWORD_MIN, max_length=128)


class RefreshRequest(ApiModel):
    refresh_token: str = Field(min_length=10, max_length=512)


class TokenPair(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class UserOut(ApiModel):
    id: str
    email: str
    username: str
    full_name: str
    role: UserRole
    consent_training_data: bool
    consent_at: datetime | None
    created_at: datetime


class UserUpdate(ApiModel):
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=32)
    full_name: str | None = Field(default=None, min_length=1, max_length=80)
    consent_training_data: bool | None = None

    @field_validator("username")
    @classmethod
    def _username(cls, value: str | None) -> str:
        return clean_username(value or "")

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str | None) -> str:
        return clean_name(value or "")

    @model_validator(mode="after")
    def _no_null_required(self) -> UserUpdate:
        if "email" in self.model_fields_set and self.email is None:
            raise ValidationError("Email tidak boleh dikosongkan.", details={"field": "email"})
        return self


class NotificationSettingsOut(ApiModel):
    """Per-type switches, quiet hours and the reminder periods (requirement 6-7)."""

    enabled: dict[ReminderType, bool]
    quiet_hours: dict[str, int]
    # Every N days a tracked plant without a new photo gets a photo reminder;
    # 0 turns the reminder off.
    photo_reminder_days: int
    # Every N days without any check (photo, scan or care log): monitoring reminder.
    monitoring_reminder_days: int


class NotificationSettingsUpdate(ApiModel):
    enabled: dict[ReminderType, bool] | None = None
    quiet_hours_start: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_end: int | None = Field(default=None, ge=0, le=23)
    photo_reminder_days: int | None = Field(default=None, ge=0, le=60)
    monitoring_reminder_days: int | None = Field(default=None, ge=0, le=60)


class DeviceCreate(ApiModel):
    fcm_token: str = Field(min_length=10, max_length=512)
    platform: Platform


class DeviceOut(ApiModel):
    id: str
    platform: Platform
    last_seen_at: datetime | None
    created_at: datetime
