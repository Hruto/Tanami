"""The disease knowledge base, weather archive and region reference data."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, updated_at_column
from app.domain import COMMODITIES_V2, CauseCategory, PlantingMaterial
from app.models.columns import enum_check, uuid_pk, values_check

if TYPE_CHECKING:
    from app.models.scan import Scan


class Disease(Base):
    """Reviewed reference content. Rows are deactivated, never deleted."""

    __tablename__ = "diseases"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    commodity_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    name_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name_latin: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cause_category: Mapped[str] = mapped_column(String(32), nullable=False)

    symptoms: Mapped[str] = mapped_column(Text, nullable=False)
    causes_text: Mapped[str] = mapped_column(Text, nullable=False)
    prevention: Mapped[str] = mapped_column(Text, nullable=False)
    severity_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Days a confirmed episode of this disease pushes the harvest estimate back
    # (design 8.5). An expert fills it in; it is always shown as an estimate.
    harvest_delay_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    # Shape from design 9.3. Content is written and reviewed by an agronomist;
    # chemical entries carry a safety note and never a dose (TQA 8.3).
    treatments: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    scans: Mapped[list[Scan]] = relationship(back_populates="disease")

    __table_args__ = (
        enum_check("cause_category", CauseCategory, name="cause_category"),
        UniqueConstraint("commodity_code", "code", name="uq_diseases_commodity_code"),
        CheckConstraint(
            "NOT is_active OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="active_requires_review",
        ),
        CheckConstraint(
            "jsonb_typeof(treatments) = 'object'",
            name="treatments_object",
        ),
        CheckConstraint("harvest_delay_days >= 0", name="harvest_delay_non_negative"),
        Index("ix_diseases_active_commodity", "commodity_code", "is_active"),
    )


class CropProfile(Base):
    """Agronomic numbers behind the harvest estimate (design 8.3).

    Data, not code: an expert edits it from the team workspace. All values are
    days except ``productive_years``. ``source`` must be filled in before release.
    """

    __tablename__ = "crop_profiles"

    id: Mapped[UUID] = uuid_pk()
    commodity_code: Mapped[str] = mapped_column(String(32), nullable=False)
    planting_material: Mapped[str] = mapped_column(String(16), nullable=False)

    first_harvest_min_days: Mapped[int] = mapped_column(Integer, nullable=False)
    first_harvest_max_days: Mapped[int] = mapped_column(Integer, nullable=False)
    harvest_cycle_min_days: Mapped[int] = mapped_column(Integer, nullable=False)
    harvest_cycle_max_days: Mapped[int] = mapped_column(Integer, nullable=False)
    productive_years: Mapped[int] = mapped_column(Integer, nullable=False)

    harvest_pattern_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        values_check("commodity_code", COMMODITIES_V2, name="commodity_code"),
        enum_check("planting_material", PlantingMaterial, name="planting_material"),
        UniqueConstraint("commodity_code", "planting_material", name="uq_crop_profiles_material"),
        CheckConstraint(
            "first_harvest_min_days > 0 AND first_harvest_min_days <= first_harvest_max_days",
            name="first_harvest_range",
        ),
        CheckConstraint(
            "harvest_cycle_min_days > 0 AND harvest_cycle_min_days <= harvest_cycle_max_days",
            name="harvest_cycle_range",
        ),
        CheckConstraint("productive_years > 0", name="productive_years_positive"),
    )


class WeatherSnapshot(Base):
    """Append-only archive of a BMKG forecast, keyed by village code.

    There is no FK to ``farms``: many farms share one village and one snapshot
    serves all of them. ``updated_at`` is intentionally absent because a row is
    never updated.
    """

    __tablename__ = "weather_snapshots"

    id: Mapped[UUID] = uuid_pk()
    adm4_code: Mapped[str] = mapped_column(String(16), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="bmkg")
    forecast: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        UniqueConstraint("adm4_code", "fetched_at", name="uq_weather_adm4_fetched"),
        CheckConstraint(
            "source IN ('bmkg', 'open_meteo', 'manual')",
            name="source",
        ),
        Index("ix_weather_adm4_fetched", "adm4_code", text("fetched_at DESC")),
    )


class Region(Base):
    """Village/kelurahan reference table backing ``/regions/search``.

    Seeded from the official Kemendagri code list. It is read-only at runtime and
    exists so the app can turn a typed village name into an ``adm4_code`` and,
    with coordinates, resolve the nearest one offline.
    """

    __tablename__ = "regions"

    id: Mapped[UUID] = uuid_pk()
    adm4_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    village: Mapped[str] = mapped_column(String(120), nullable=False)
    district: Mapped[str] = mapped_column(String(120), nullable=False)
    regency: Mapped[str] = mapped_column(String(120), nullable=False)
    province: Mapped[str] = mapped_column(String(120), nullable=False)
    lat: Mapped[float | None] = mapped_column(nullable=True)
    lon: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        Index("ix_regions_village_lower", text("lower(village)")),
        Index("ix_regions_regency", "regency"),
    )
