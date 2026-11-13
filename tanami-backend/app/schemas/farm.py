"""Farm, plant, harvest and region schemas."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.core.errors import ValidationError
from app.domain import (
    COMMODITIES_V2,
    MATERIALS_BY_COMMODITY,
    TRACKING_END_REASONS_V2,
    CareAction,
    HealthStatus,
    IrrigationSchedule,
    LifecyclePhase,
    Placement,
    PlantingMaterial,
    TrackingEndReason,
    TrackingOutcome,
)
from app.schemas.base import ApiModel

_ADM4_RE = re.compile(r"^\d{2}\.\d{2}\.\d{2}\.\d{4}$")


def _clean_required(value: str | None, *, field: str, label: str) -> str:
    """A PATCH may omit a required field, but must not null or blank it."""
    cleaned = " ".join((value or "").split())
    if not cleaned:
        raise ValidationError(f"{label} tidak boleh kosong.", details={"field": field})
    return cleaned


def validate_adm4(value: str) -> str:
    if not _ADM4_RE.match(value):
        raise ValidationError(
            "Kode wilayah tidak valid. Gunakan format 32.75.02.1001.",
            details={"field": "adm4_code"},
        )
    return value


class FarmCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    adm4_code: str
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lon: Decimal | None = Field(default=None, ge=-180, le=180)
    area_m2: Decimal | None = Field(default=None, gt=0, le=10_000_000)
    placement: Placement = Placement.OUTDOOR

    @field_validator("adm4_code")
    @classmethod
    def _adm4(cls, value: str) -> str:
        return validate_adm4(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValidationError("Nama lahan tidak boleh kosong.", details={"field": "name"})
        return cleaned

    @model_validator(mode="after")
    def _coords_together(self) -> FarmCreate:
        if (self.lat is None) != (self.lon is None):
            raise ValidationError(
                "Isi lat dan lon sekaligus, atau kosongkan keduanya.",
                details={"field": "lat/lon"},
            )
        return self


class FarmUpdate(ApiModel):
    """Partial update. ``adm4_code`` is fixed: weather history is per village."""

    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lon: Decimal | None = Field(default=None, ge=-180, le=180)
    area_m2: Decimal | None = Field(default=None, gt=0, le=10_000_000)
    placement: Placement | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return _clean_required(value, field="name", label="Nama lahan")

    @model_validator(mode="after")
    def _coords_together(self) -> FarmUpdate:
        if ("lat" in self.model_fields_set) != ("lon" in self.model_fields_set):
            raise ValidationError(
                "Ubah lat dan lon sekaligus.",
                details={"field": "lat/lon"},
            )
        if (self.lat is None) != (self.lon is None):
            raise ValidationError(
                "Isi lat dan lon sekaligus, atau kosongkan keduanya.",
                details={"field": "lat/lon"},
            )
        return self


class FarmOut(ApiModel):
    id: str
    name: str
    adm4_code: str
    lat: float | None
    lon: float | None
    area_m2: float | None
    placement: Placement
    village: str | None = None
    plant_count: int = 0
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RegionOut(ApiModel):
    adm4_code: str
    village: str
    district: str
    regency: str
    province: str


class PlantCreate(ApiModel):
    label: str = Field(min_length=1, max_length=120)
    commodity_code: str
    # Omitted: the default material of the commodity (grafted, or runner for strawberry).
    planting_material: PlantingMaterial | None = None
    variety: str | None = Field(default=None, max_length=80)
    planted_at: date
    quantity: int = Field(default=1, ge=1, le=100_000)
    irrigation_schedule: IrrigationSchedule = IrrigationSchedule.EVERY_3_5_DAYS

    @field_validator("commodity_code")
    @classmethod
    def _commodity(cls, value: str) -> str:
        if value not in COMMODITIES_V2:
            raise ValidationError(
                "Jenis tanaman tidak ada di daftar.",
                details={"field": "commodity_code", "supported": list(COMMODITIES_V2)},
            )
        return value

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValidationError("Label tanaman tidak boleh kosong.", details={"field": "label"})
        return cleaned

    @field_validator("planted_at")
    @classmethod
    def _not_future(cls, value: date) -> date:
        if value > date.today():
            raise ValidationError(
                "Tanggal tanam tidak boleh di masa depan.",
                details={"field": "planted_at"},
            )
        return value

    @model_validator(mode="after")
    def _material_fits_commodity(self) -> PlantCreate:
        if (
            self.planting_material is not None
            and self.planting_material.value not in MATERIALS_BY_COMMODITY[self.commodity_code]
        ):
            raise ValidationError(
                "Jenis bibit ini tidak dipakai untuk tanaman tersebut.",
                details={
                    "field": "planting_material",
                    "allowed": list(MATERIALS_BY_COMMODITY[self.commodity_code]),
                },
            )
        return self


class PlantUpdate(ApiModel):
    label: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    variety: str | None = Field(default=None, max_length=80)
    planted_at: date | None = None
    planting_material: PlantingMaterial | None = None
    quantity: int | None = Field(default=None, ge=1, le=100_000)
    irrigation_schedule: IrrigationSchedule | None = None

    @field_validator("label")
    @classmethod
    def _label(cls, value: str | None) -> str | None:
        return _clean_required(value, field="label", label="Label tanaman")

    @model_validator(mode="after")
    def _no_null_required(self) -> PlantUpdate:
        for name in ("planted_at", "planting_material", "quantity", "irrigation_schedule"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValidationError("Kolom ini tidak boleh dikosongkan.", details={"field": name})
        if self.planted_at is not None and self.planted_at > date.today():
            raise ValidationError(
                "Tanggal tanam tidak boleh di masa depan.", details={"field": "planted_at"}
            )
        return self


class DelayItemOut(ApiModel):
    episode_id: str
    disease_code: str
    label: str
    days: int
    status: Literal["open", "resolved"]


class NextHarvestOut(ApiModel):
    """The estimated window of the next harvest; always an estimate (design 8.4)."""

    base_start: date
    base_end: date
    delay_days: int
    start: date
    end: date
    delays: list[DelayItemOut]
    is_overdue: bool
    is_estimate: bool = True
    delay_capped: bool = False


class EndedDiseaseOut(ApiModel):
    code: str
    label: str


class PlantOut(ApiModel):
    id: str
    code: str
    farm_id: str
    label: str
    commodity_code: str
    commodity_label: str
    variety: str | None
    planting_material: PlantingMaterial
    quantity: int
    planted_at: date
    # Computed, never entered; counted to the end date once tracking has ended.
    age_days: int
    lifecycle_phase: LifecyclePhase
    productive_until: date
    health_status: HealthStatus
    health_status_reason: str | None = None
    harvest_count: int = 0
    last_harvest_at: date | None = None
    # ``None`` once the productive period is about to run out, and for ended plants.
    next_harvest: NextHarvestOut | None = None
    open_episode_count: int = 0
    irrigation_schedule: IrrigationSchedule
    last_watered_at: datetime | None = None
    next_watering_on: date | None = None
    cover_photo_url: str | None = None
    last_scan_at: datetime | None = None
    # Location shown in the history detail.
    farm_name: str
    placement: Placement
    adm4_code: str
    village: str | None = None
    # Tracking end (design 8.6).
    status: Literal["active", "ended"]
    ended_at: datetime | None
    end_reason: TrackingEndReason | None = None
    end_note: str | None = None
    end_diseases: list[EndedDiseaseOut] = Field(default_factory=list)
    end_cause_note: str | None = None
    outcome: TrackingOutcome | None = None
    created_at: datetime
    updated_at: datetime


class PlantMaterialOut(ApiModel):
    code: str
    label: str
    is_default: bool


class PlantTypeOut(ApiModel):
    code: str
    label: str
    detection_supported: bool
    materials: list[PlantMaterialOut]
    profile_summary: str | None = None


class CropProfileOut(ApiModel):
    commodity_code: str
    planting_material: str
    first_harvest_min_days: int
    first_harvest_max_days: int
    harvest_cycle_min_days: int
    harvest_cycle_max_days: int
    productive_years: int
    harvest_pattern_note: str | None
    source: str | None
    reviewed_by: str | None
    reviewed_at: date | None


class EndTracking(ApiModel):
    """End tracking before the productive period is over (design 8.6)."""

    reason: TrackingEndReason
    # ``disease``: the diseases the plant was lost to, from its own history, and/or free text.
    disease_codes: list[str] = Field(default_factory=list, max_length=10)
    cause_note: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _v2_reason(cls, value: TrackingEndReason) -> TrackingEndReason:
        # design 8.2: ``harvested``/``died``/``not_maintained`` are v0.3 values kept
        # only so old rows can be read; a request may never use them (10.2 wants 400,
        # not a check-constraint violation on write).
        if value.value not in TRACKING_END_REASONS_V2:
            raise ValidationError(
                "Alasan mengakhiri tracking tidak dikenal.",
                details={"field": "reason", "allowed": list(TRACKING_END_REASONS_V2)},
            )
        return value


class PhotoOut(ApiModel):
    id: str
    plant_id: str
    image_url: str
    caption: str | None
    taken_at: datetime
    created_at: datetime


class CareLogCreate(ApiModel):
    action: CareAction
    note: str | None = Field(default=None, max_length=1000)
    performed_at: datetime | None = None

    @field_validator("performed_at")
    @classmethod
    def _aware_past(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValidationError(
                "performed_at wajib memakai zona waktu.", details={"field": "performed_at"}
            )
        if value > datetime.now(UTC) + timedelta(minutes=5):
            raise ValidationError(
                "Waktu perawatan tidak boleh di masa depan.", details={"field": "performed_at"}
            )
        return value


class CareLogOut(ApiModel):
    id: str
    plant_id: str
    action: CareAction
    note: str | None
    performed_at: datetime
    created_at: datetime


class HarvestCreate(ApiModel):
    """A harvest. ``harvested_at`` is a day (``2026-11-08``); omitted means today."""

    harvested_at: date | datetime | None = None
    quality_note: str | None = Field(default=None, max_length=1000)
    quantity_kg: Decimal | None = Field(default=None, ge=0, le=1_000_000)


class HarvestUpdate(ApiModel):
    harvested_at: date | datetime | None = None
    quality_note: str | None = Field(default=None, max_length=1000)
    quantity_kg: Decimal | None = Field(default=None, ge=0, le=1_000_000)


class HarvestOut(ApiModel):
    id: str
    plant_id: str
    sequence: int
    harvested_at: date
    quality_note: str | None
    quantity_kg: float | None
    created_at: datetime
    # The estimate after this change, so the screen can update without a second call.
    next_harvest: NextHarvestOut | None = None


class EpisodeOut(ApiModel):
    id: str
    plant_id: str
    disease_code: str
    label: str
    status: Literal["open", "resolved"]
    opened_at: datetime
    last_seen_at: datetime
    delay_days: int
    resolved_at: datetime | None
    close_reason: str | None
    scan_ids: list[str]


class EpisodeUpdate(ApiModel):
    status: Literal["resolved"]


class TimelineEntry(ApiModel):
    # scan | photo | care | harvest | episode_opened | episode_resolved | reminder | ended
    kind: str
    occurred_at: datetime
    id: str
    title: str
    subtitle: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class HealthPoint(ApiModel):
    date: date
    health_status: HealthStatus


class HarvestPoint(ApiModel):
    date: date
    sequence: int
    quantity_kg: float | None


class EstimateVsActual(ApiModel):
    sequence: int
    estimated_date_min: date | None
    estimated_date_max: date | None
    harvested_at: date
    within_range: bool | None


class PlantStats(ApiModel):
    health_series: list[HealthPoint]
    harvest_series: list[HarvestPoint]
    estimate_vs_actual: list[EstimateVsActual]
