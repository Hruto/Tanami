"""Disease knowledge base and user profile services."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.domain import ReminderType
from app.models.content import Disease
from app.models.user import User
from app.schemas.auth import (
    NotificationSettingsOut,
    NotificationSettingsUpdate,
    UserOut,
    UserUpdate,
)
from app.schemas.scan import DiseaseOut, DiseaseSummaryOut

# Requirement 6-7: default reminder periods when the user never set one.
DEFAULT_REMINDER_DAYS = {"photo_reminder_days": 7, "monitoring_reminder_days": 7}


def reminder_days(stored: dict[str, object], key: str) -> int:
    value = stored.get(key)
    if isinstance(value, int) and 0 <= value <= 60:
        return value
    return DEFAULT_REMINDER_DAYS[key]


class DiseaseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, commodity_code: str | None) -> list[DiseaseSummaryOut]:
        query = select(Disease).where(Disease.is_active.is_(True))
        if commodity_code:
            query = query.where(Disease.commodity_code == commodity_code)
        rows = (await self.session.execute(query.order_by(Disease.name_id))).scalars()
        return [
            DiseaseSummaryOut(
                code=row.code,
                commodity_code=row.commodity_code,
                name_id=row.name_id,
                cause_category=row.cause_category,
            )
            for row in rows
        ]

    async def get(self, code: str) -> DiseaseOut:
        disease = (
            await self.session.execute(
                select(Disease).where(Disease.code == code, Disease.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if disease is None:
            raise NotFound("Penyakit tidak ditemukan.")
        return DiseaseOut(
            code=disease.code,
            commodity_code=disease.commodity_code,
            name_id=disease.name_id,
            name_latin=disease.name_latin,
            cause_category=disease.cause_category,
            symptoms=disease.symptoms,
            causes_text=disease.causes_text,
            treatments=dict(disease.treatments),
            prevention=disease.prevention,
            severity_note=disease.severity_note,
            reviewed_by=disease.reviewed_by,
            reviewed_at=disease.reviewed_at,
        )


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def profile(self, user: User) -> UserOut:
        return self._out(user)

    async def update(self, user: User, payload: UserUpdate) -> UserOut:
        data = payload.model_dump(exclude_unset=True)
        await self._ensure_identifier_free(user, data)
        if data.get("full_name"):
            user.full_name = data["full_name"]
        if data.get("username"):
            user.username = data["username"]
        if data.get("email"):
            user.email = str(data["email"]).lower()
        if data.get("consent_training_data") is not None:
            enabled = bool(data["consent_training_data"])
            user.consent_training_data = enabled
            user.consent_at = datetime.now(UTC) if enabled else None
        await self.session.commit()
        return self._out(user)

    async def _ensure_identifier_free(self, user: User, data: dict[str, object]) -> None:
        """409 instead of a unique-index violation (and a 500) on PATCH."""
        checks = []
        if data.get("email"):
            checks.append(("email", User.email == str(data["email"]).lower(), "Email"))
        if data.get("username"):
            checks.append(("username", User.username == str(data["username"]), "Username"))
        for field, condition, label in checks:
            taken = (
                await self.session.execute(select(User.id).where(condition, User.id != user.id))
            ).scalar_one_or_none()
            if taken is not None:
                raise Conflict(f"{label} sudah dipakai akun lain.", details={"field": field})

    async def notification_settings(self, user: User) -> NotificationSettingsOut:
        stored = user.notification_settings or {}
        enabled = stored.get("enabled")
        resolved: dict[ReminderType, bool] = dict.fromkeys(ReminderType, True)
        if isinstance(enabled, dict):
            for key, value in enabled.items():
                try:
                    resolved[ReminderType(str(key))] = bool(value)
                except ValueError:
                    continue
        quiet = stored.get("quiet_hours")
        hours = quiet if isinstance(quiet, dict) else {}
        return NotificationSettingsOut(
            enabled=resolved,
            quiet_hours={
                "start": int(hours.get("start", 21)),
                "end": int(hours.get("end", 5)),
            },
            photo_reminder_days=reminder_days(stored, "photo_reminder_days"),
            monitoring_reminder_days=reminder_days(stored, "monitoring_reminder_days"),
        )

    async def update_notification_settings(
        self, user: User, payload: NotificationSettingsUpdate
    ) -> NotificationSettingsOut:
        stored = dict(user.notification_settings or {})
        if payload.enabled is not None:
            stored["enabled"] = {key.value: value for key, value in payload.enabled.items()}
        if payload.quiet_hours_start is not None or payload.quiet_hours_end is not None:
            raw_quiet = stored.get("quiet_hours")
            quiet: dict[str, object] = dict(raw_quiet) if isinstance(raw_quiet, dict) else {}
            if payload.quiet_hours_start is not None:
                quiet["start"] = payload.quiet_hours_start
            if payload.quiet_hours_end is not None:
                quiet["end"] = payload.quiet_hours_end
            stored["quiet_hours"] = quiet
        if payload.photo_reminder_days is not None:
            stored["photo_reminder_days"] = payload.photo_reminder_days
        if payload.monitoring_reminder_days is not None:
            stored["monitoring_reminder_days"] = payload.monitoring_reminder_days
        user.notification_settings = stored
        await self.session.commit()
        return await self.notification_settings(user)

    async def soft_delete(self, user: User) -> dict[str, object]:
        """Schedule account removal.

        ``tqa.md`` 9 asks for deletion "within a reasonable time"; this marks the
        account, revokes sessions (done by the caller) and records the timestamp
        the sweep job uses. Images are removed when the sweep runs, so an
        accidental deletion can be undone by support before then.
        """
        user.deleted_at = datetime.now(UTC)
        await self.session.commit()
        return {
            "deleted_at": user.deleted_at,
            "scheduled_removal_days": 30,
        }

    def _out(self, user: User) -> UserOut:
        return UserOut(
            id=str(user.id),
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            consent_training_data=user.consent_training_data,
            consent_at=user.consent_at,
            created_at=user.created_at,
        )


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFound("Pengguna tidak ditemukan.")
    return user
