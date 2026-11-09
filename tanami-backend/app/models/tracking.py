"""Growth history of a tracked plant: ``plant_photos`` and ``care_logs`` (requirements 1-2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, updated_at_column
from app.domain import CareAction
from app.models.columns import enum_check, uuid_pk


class PlantPhoto(Base):
    __tablename__ = "plant_photos"

    id: Mapped[UUID] = uuid_pk()
    plant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    image_key: Mapped[str] = mapped_column(String(255), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(280), nullable=True)
    taken_at: Mapped[datetime] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        Index("ix_plant_photos_plant_taken", "plant_id", text("taken_at DESC")),
        Index("ix_plant_photos_user_id", "user_id"),
    )


class CareLog(Base):
    """One care action: watering, fertilizing, pest control, ..."""

    __tablename__ = "care_logs"

    id: Mapped[UUID] = uuid_pk()
    plant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_at: Mapped[datetime] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        enum_check("action", CareAction, name="action"),
        CheckConstraint("note IS NULL OR char_length(note) <= 1000", name="note_length"),
        Index("ix_care_logs_plant_performed", "plant_id", text("performed_at DESC")),
        Index("ix_care_logs_plant_action", "plant_id", "action", text("performed_at DESC")),
    )
