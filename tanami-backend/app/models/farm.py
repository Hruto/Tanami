"""Farms, plants and harvest records."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, updated_at_column
from app.domain import (
    COMMODITIES_V2,
    TRACKING_END_REASONS_V2,
    HealthStatus,
    IrrigationSchedule,
    Placement,
    PlantingMaterial,
    TrackingOutcome,
)
from app.models.columns import enum_check, uuid_pk, values_check

if TYPE_CHECKING:
    from app.models.episode import DiseaseEpisode
    from app.models.reminder import Reminder
    from app.models.scan import Scan
    from app.models.user import User


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Village/kelurahan code, e.g. ``32.75.02.1001``. Location is stored at this
    # granularity and never displayed to other users (TQA 9).
    adm4_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Requirement 0: indoor or outdoor. Weather rules only apply outdoors.
    placement: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=Placement.OUTDOOR.value
    )

    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    user: Mapped[User] = relationship(back_populates="farms")
    plants: Mapped[list[Plant]] = relationship(
        back_populates="farm", cascade="all, delete-orphan", order_by="Plant.created_at"
    )
    reminders: Mapped[list[Reminder]] = relationship(back_populates="farm")

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("lat IS NULL OR (lat >= -90 AND lat <= 90)", name="lat_range"),
        CheckConstraint("lon IS NULL OR (lon >= -180 AND lon <= 180)", name="lon_range"),
        CheckConstraint("area_m2 IS NULL OR area_m2 > 0", name="area_positive"),
        enum_check("placement", Placement, name="placement"),
        Index("ix_farms_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Farm {self.id} name={self.name!r}>"


class Plant(Base):
    """One tree, or one group of plants of the same kind planted together (design 8.1)."""

    __tablename__ = "plants"

    id: Mapped[UUID] = uuid_pk()
    farm_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("farms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised from the farm so a display code can be unique per user.
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # ``MGA-001``: commodity prefix + per-user counter. Never reused or edited.
    code: Mapped[str] = mapped_column(String(16), nullable=False)

    commodity_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    planting_material: Mapped[str] = mapped_column(String(16), nullable=False)
    variety: Mapped[str | None] = mapped_column(String(80), nullable=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    planted_at: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # planted_at + the profile's productive years; tracking ends by itself then.
    productive_until: Mapped[date] = mapped_column(Date, nullable=False)

    health_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=HealthStatus.UNKNOWN.value
    )

    # Requirement 1: watering frequency, drives the watering reminder.
    irrigation_schedule: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=IrrigationSchedule.EVERY_3_5_DAYS.value
    )

    # Requirement 1-2: ending tracking moves the plant to the history list.
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    end_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Only for ``end_reason = disease``: what the plant was lost to (design 8.6).
    end_disease_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)), nullable=True)
    end_cause_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    farm: Mapped[Farm] = relationship(back_populates="plants")
    scans: Mapped[list[Scan]] = relationship(back_populates="plant")
    reminders: Mapped[list[Reminder]] = relationship(back_populates="plant")
    harvests: Mapped[list[HarvestRecord]] = relationship(
        back_populates="plant", cascade="all, delete-orphan", order_by="HarvestRecord.harvested_at"
    )
    episodes: Mapped[list[DiseaseEpisode]] = relationship(
        back_populates="plant", cascade="all, delete-orphan", order_by="DiseaseEpisode.opened_at"
    )

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    __table_args__ = (
        values_check("commodity_code", COMMODITIES_V2, name="commodity_code"),
        enum_check("planting_material", PlantingMaterial, name="planting_material"),
        enum_check("health_status", HealthStatus, name="health_status"),
        enum_check("irrigation_schedule", IrrigationSchedule, name="irrigation_schedule"),
        values_check("end_reason", TRACKING_END_REASONS_V2, name="end_reason"),
        enum_check("outcome", TrackingOutcome, name="outcome"),
        CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="ended_with_reason"),
        CheckConstraint("(ended_at IS NULL) = (outcome IS NULL)", name="ended_with_outcome"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint(
            "end_reason IS DISTINCT FROM 'disease' "
            "OR cardinality(coalesce(end_disease_codes, '{}')) > 0 "
            "OR btrim(coalesce(end_cause_note, '')) <> ''",
            name="disease_end_has_cause",
        ),
        UniqueConstraint("user_id", "code", name="uq_plants_user_code"),
        Index("ix_plants_farm_ended", "farm_id", "ended_at"),
        Index("ix_plants_user_ended", "user_id", "ended_at"),
        Index("ix_plants_health_status", "health_status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Plant {self.code} label={self.label!r}>"


class HarvestRecord(Base):
    """One harvest of a plant; ``sequence`` is "panen ke-n" (design 8.1)."""

    __tablename__ = "harvest_records"

    id: Mapped[UUID] = uuid_pk()
    plant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("plants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recorded_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    harvested_at: Mapped[datetime] = mapped_column(nullable=False)
    # Numbered by harvest date per plant and renumbered when a record is edited or
    # deleted, so the unique constraint is checked at commit, not per row.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    plant: Mapped[Plant] = relationship(back_populates="harvests")

    __table_args__ = (
        CheckConstraint("quantity_kg IS NULL OR quantity_kg >= 0", name="quantity_non_negative"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        UniqueConstraint(
            "plant_id",
            "sequence",
            name="uq_harvest_records_plant_sequence",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_harvest_records_plant_harvested", "plant_id", "harvested_at"),
    )
