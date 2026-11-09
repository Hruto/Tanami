"""Reminders and push devices."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, updated_at_column
from app.domain import (
    REMINDER_TYPES_V2,
    Platform,
    PushState,
    ReminderPriority,
    ReminderStatus,
)
from app.models.columns import enum_check, uuid_pk, values_check

if TYPE_CHECKING:
    from app.models.farm import Farm, Plant
    from app.models.user import User


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # A reminder can concern a whole farm (weather) or one plant (harvest).
    farm_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("farms.id", ondelete="CASCADE"),
        nullable=True,
    )
    plant_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("plants.id", ondelete="CASCADE"),
        nullable=True,
    )

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=ReminderPriority.NORMAL.value
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=ReminderStatus.UNREAD.value
    )

    title: Mapped[str] = mapped_column(String(140), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # ``dedupe_key`` is what makes "do not send the same reminder twice in 24h"
    # enforceable; the unique index below is the enforcement (design 12.4).
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)

    valid_until: Mapped[datetime | None] = mapped_column(nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Where the push stands; ``pending`` rows are retried by the hourly
    # dispatcher (quiet hours), every other value is final.
    push_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=PushState.PENDING.value
    )

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    user: Mapped[User] = relationship(back_populates="reminders")
    farm: Mapped[Farm | None] = relationship(back_populates="reminders")
    plant: Mapped[Plant | None] = relationship(back_populates="reminders")

    __table_args__ = (
        values_check("type", REMINDER_TYPES_V2, name="type"),
        enum_check("priority", ReminderPriority, name="priority"),
        enum_check("status", ReminderStatus, name="status"),
        enum_check("push_state", PushState, name="push_state"),
        # A team broadcast (``general``) concerns the user, not a farm or plant.
        CheckConstraint(
            "farm_id IS NOT NULL OR plant_id IS NOT NULL OR type = 'general'",
            name="has_target",
        ),
        Index("ix_reminders_push_state_created", "push_state", "created_at"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_reminders_user_dedupe"),
        Index("ix_reminders_user_status_created", "user_id", "status", text("created_at DESC")),
        Index("ix_reminders_plant_created", "plant_id", text("created_at DESC")),
        Index("ix_reminders_valid_until", "valid_until"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Reminder {self.id} type={self.type} status={self.status}>"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fcm_token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    user: Mapped[User] = relationship(back_populates="devices")

    __table_args__ = (
        enum_check("platform", Platform, name="platform"),
        Index("ix_devices_user_last_seen", "user_id", text("last_seen_at DESC")),
    )
