"""Plant tracking records and the separate disease-detection list.

``plant_photos`` and ``care_logs`` are the growth history of a tracked plant
(requirements 1-2). ``detection_plants`` is the list of the disease-detection
feature, deliberately separate from the tracked plants (requirement 3); a
detection plant may optionally point at a tracked plant so its results also
appear in that plant history.
"""

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


class DetectionPlant(Base):
    """A plant registered only for disease detection (requirement 3-4)."""

    __tablename__ = "detection_plants"

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    commodity_code: Mapped[str] = mapped_column(String(32), nullable=False, server_default="chili")
    # Optional link to a tracked plant: its detections then also show in the
    # tracking history (requirement 2, "hasil deteksi penyakit yang terhubung").
    plant_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("plants.id", ondelete="SET NULL"), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    end_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("ix_detection_plants_user_ended", "user_id", "ended_at", text("created_at DESC")),
        Index("ix_detection_plants_plant_id", "plant_id"),
    )
