"""Care reminders for tracked plants (requirement 7).

* ``watering``   - per the plant irrigation schedule (daily, every 3-5 days,
  weekly; ``never`` has none), counted from the last logged watering.
* ``photo``      - every N days without a growth photo (user setting).
* ``monitoring`` - every N days without any check: photo, scan or care log
  (user setting). Skipped on a day the photo reminder already fires, so one
  neglected plant does not produce three notifications.

Only plants whose tracking is active get reminders: ending tracking stops them.
The rules are pure; ``load_care_contexts`` gathers the inputs in a few queries.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Result, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    IRRIGATION_INTERVAL_DAYS,
    CareAction,
    IrrigationSchedule,
    ReminderPriority,
    ReminderType,
)
from app.models.farm import Farm, Plant
from app.models.scan import Scan
from app.models.tracking import CareLog, PlantPhoto
from app.models.user import User
from app.services.content import reminder_days
from app.services.reminder import PendingReminder, dedupe_key

_SCHEDULE_TEXT = {
    IrrigationSchedule.DAILY.value: "setiap hari",
    IrrigationSchedule.EVERY_3_5_DAYS.value: "setiap 3-5 hari",
    IrrigationSchedule.WEEKLY.value: "setiap minggu",
}


@dataclass(frozen=True, slots=True)
class CareContext:
    plant_id: UUID
    user_id: UUID
    farm_id: UUID
    label: str
    irrigation_schedule: str
    tracking_started: date
    last_watered: date | None = None
    last_photo: date | None = None
    last_activity: date | None = None
    photo_days: int = 7
    monitoring_days: int = 7


def _due(last: date | None, start: date, every: int, today: date) -> int | None:
    """Days since the reference day once ``every`` days have passed, else None."""
    if every <= 0:
        return None
    elapsed = (today - (last or start)).days
    return elapsed if elapsed >= every else None


def _reminder(
    plant: CareContext,
    kind: ReminderType,
    priority: ReminderPriority,
    title: str,
    body: str,
    *,
    now: datetime,
    today: date,
) -> PendingReminder:
    return PendingReminder(
        user_id=plant.user_id,
        farm_id=plant.farm_id,
        plant_id=plant.plant_id,
        type=kind,
        priority=priority,
        title=title,
        body=body,
        dedupe_key=dedupe_key(kind, plant.plant_id, today),
        valid_until=now + timedelta(days=1),
    )


def build_care_reminders(
    *, plants: Sequence[CareContext], now: datetime, today: date
) -> list[PendingReminder]:
    out: list[PendingReminder] = []
    for plant in plants:
        interval = IRRIGATION_INTERVAL_DAYS.get(plant.irrigation_schedule)
        if interval is not None and (
            _due(plant.last_watered, plant.tracking_started, interval, today) is not None
        ):
            schedule = _SCHEDULE_TEXT[plant.irrigation_schedule]
            out.append(
                _reminder(
                    plant,
                    ReminderType.WATERING,
                    ReminderPriority.NORMAL,
                    "Waktunya menyiram",
                    f"Waktunya menyiram {plant.label} (jadwal {schedule}). "
                    "Catat penyiraman setelah selesai.",
                    now=now,
                    today=today,
                )
            )

        photo_due = _due(plant.last_photo, plant.tracking_started, plant.photo_days, today)
        if photo_due is not None:
            out.append(
                _reminder(
                    plant,
                    ReminderType.PHOTO,
                    ReminderPriority.LOW,
                    "Foto perkembangan tanaman",
                    f"Ambil foto {plant.label} hari ini untuk memantau pertumbuhannya.",
                    now=now,
                    today=today,
                )
            )

        idle = _due(plant.last_activity, plant.tracking_started, plant.monitoring_days, today)
        if idle is not None and photo_due is None:
            out.append(
                _reminder(
                    plant,
                    ReminderType.MONITORING,
                    ReminderPriority.LOW,
                    "Periksa kondisi tanaman",
                    f"Sudah {idle} hari {plant.label} belum diperiksa. "
                    "Cek daun dan batangnya, lalu catat atau scan bila ada gejala.",
                    now=now,
                    today=today,
                )
            )
    return out


async def load_care_contexts(session: AsyncSession, *, tz_name: str) -> list[CareContext]:
    """Active tracked plants of active accounts, with their last care dates."""
    tz = ZoneInfo(tz_name)
    rows = (
        await session.execute(
            select(
                Plant.id,
                Plant.label,
                Plant.farm_id,
                Plant.irrigation_schedule,
                Plant.created_at,
                Farm.user_id,
                User.notification_settings,
            )
            .join(Farm, Farm.id == Plant.farm_id)
            .join(User, User.id == Farm.user_id)
            .where(
                Plant.ended_at.is_(None),
                Farm.archived_at.is_(None),
                User.deleted_at.is_(None),
            )
        )
    ).all()
    if not rows:
        return []
    ids = [row.id for row in rows]

    def as_dates(result: Result[Any]) -> dict[UUID, date]:
        return {row[0]: row[1].astimezone(tz).date() for row in result.all() if row[1]}

    watered = as_dates(
        await session.execute(
            select(CareLog.plant_id, func.max(CareLog.performed_at))
            .where(CareLog.plant_id.in_(ids), CareLog.action == CareAction.WATERING.value)
            .group_by(CareLog.plant_id)
        )
    )
    cared = as_dates(
        await session.execute(
            select(CareLog.plant_id, func.max(CareLog.performed_at))
            .where(CareLog.plant_id.in_(ids))
            .group_by(CareLog.plant_id)
        )
    )
    photos = as_dates(
        await session.execute(
            select(PlantPhoto.plant_id, func.max(PlantPhoto.taken_at))
            .where(PlantPhoto.plant_id.in_(ids))
            .group_by(PlantPhoto.plant_id)
        )
    )
    scanned = as_dates(
        await session.execute(
            select(Scan.plant_id, func.max(Scan.captured_at))
            .where(Scan.plant_id.in_(ids))
            .group_by(Scan.plant_id)
        )
    )

    contexts: list[CareContext] = []
    for row in rows:
        stored = row.notification_settings if isinstance(row.notification_settings, dict) else {}
        activity = [d for d in (photos.get(row.id), cared.get(row.id), scanned.get(row.id)) if d]
        contexts.append(
            CareContext(
                plant_id=row.id,
                user_id=row.user_id,
                farm_id=row.farm_id,
                label=row.label,
                irrigation_schedule=row.irrigation_schedule,
                tracking_started=row.created_at.astimezone(tz).date(),
                last_watered=watered.get(row.id),
                last_photo=photos.get(row.id),
                last_activity=max(activity) if activity else None,
                photo_days=reminder_days(stored, "photo_reminder_days"),
                monitoring_days=reminder_days(stored, "monitoring_reminder_days"),
            )
        )
    return contexts
