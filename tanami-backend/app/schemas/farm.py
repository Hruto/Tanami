"""Farm, plant, harvest and region schemas."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.core.errors import ValidationError
from app.domain import (
    SUPPORTED_COMMODITIES,
    CareAction,
    GrowthStage,
    HarvestOutcome,
    HealthStatus,
    IrrigationSchedule,
    Placement,
    TrackingEndReason,
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
    commodity_code: str = "chili"
    variety: str | None = Field(default=None, max_length=80)
    planted_at: date
    growth_stage: GrowthStage = GrowthStage.SEEDLING
    irrigation_schedule: IrrigationSchedule = IrrigationSchedule.EVERY_3_5_DAYS

    @field_validator("commodity_code")
    @classmethod
    def _commodity(cls, value: str) -> str:
        if value not in SUPPORTED_COMMODITIES:
            raise ValidationError(
                "Jenis tanaman tidak ada di daftar.",
                details={"field": "commodity_code", "supported": list(SUPPORTED_COMMODITIES)},
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


class PlantUpdate(ApiModel):
    label: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    variety: str | None = Field(default=None, max_length=80)
    growth_stage: GrowthStage | None = None
    planted_at: date | None = None
    irrigation_schedule: IrrigationSchedule | None = None

    @field_validator("label")
    @classmethod
    def _label(cls, value: str | None) -> str | None:
        return _clean_required(value, field="label", label="Label tanaman")

    @model_validator(mode="after")
    def _no_null_required(self) -> PlantUpdate:
        for name in ("growth_stage", "planted_at", "irrigation_schedule"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValidationError("Kolom ini tidak boleh dikosongkan.", details={"field": name})
        if self.planted_at is not None and self.planted_at > date.today():
            raise ValidationError(
                "Tanggal tanam tidak boleh di masa depan.", details={"field": "planted_at"}
            )
        return self


class PlantOut(ApiModel):
    id: str
    farm_id: str
    label: str
    commodity_code: str
    commodity_label: str
    variety: str | None
    planted_at: date
    # Requirement 1: computed, never entered. Counted to the end date once
    # tracking has ended.
    age_days: int
    growth_stage: GrowthStage
    health_status: HealthStatus
    health_status_reason: str | None = None
    expected_harvest_min: date | None
    expected_harvest_max: date | None
    irrigation_schedule: IrrigationSchedule
    last_watered_at: datetime | None = None
    next_watering_on: date | None = None
    cover_photo_url: str | None = None
    last_scan_at: datetime | None = None
    # Requirement 2: location shown in the history detail.
    farm_name: str
    placement: Placement
    adm4_code: str
    village: str | None = None
    # Requirement 1-2: tracking end.
    status: Literal["active", "ended"]
    ended_at: datetime | None
    end_reason: TrackingEndReason | None = None
    end_note: str | None = None
    final_result: HarvestOutcome | None = None
    yield_percent: float | None = None
    created_at: datetime
    updated_at: datetime


class PlantTypeOut(ApiModel):
    code: str
    label: str
    detection_supported: bool


class EndTracking(ApiModel):
    """Requirement 1: end tracking; the plant moves to the history list."""

    reason: TrackingEndReason
    note: str | None = Field(default=None, max_length=1000)
    # "Hasil Akhir": either the bucket directly or the yield as % of target,
    # from which the bucket is derived.
    final_result: HarvestOutcome | None = None
    yield_percent: Decimal | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def _result_for_harvest(self) -> EndTracking:
        if self.reason is TrackingEndReason.HARVESTED and (
            self.final_result is None and self.yield_percent is None
        ):
            raise ValidationError(
                "Isi hasil akhir panen (final_result atau yield_percent).",
                details={"field": "final_result"},
            )
        return self


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
    harvested_at: datetime
    quality_note: str | None = Field(default=None, max_length=1000)
    quantity_kg: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    # Chili is picked many times per season. Only the last picking ends the
    # block (``growth_stage = finished``); the others mark it ``harvesting``.
    is_final: bool = False

    @field_validator("harvested_at")
    @classmethod
    def _aware_past(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValidationError(
                "harvested_at wajib memakai zona waktu (ISO 8601, mis. ...Z).",
                details={"field": "harvested_at"},
            )
        if value > datetime.now(UTC) + timedelta(minutes=5):
            raise ValidationError(
                "Tanggal panen tidak boleh di masa depan.", details={"field": "harvested_at"}
            )
        return value


class HarvestOut(ApiModel):
    id: str
    plant_id: str
    harvested_at: datetime
    quality_note: str | None
    quantity_kg: float | None
    created_at: datetime


class TimelineEntry(ApiModel):
    kind: str  # scan | harvest | reminder
    occurred_at: datetime
    id: str
    title: str
    subtitle: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class HealthPoint(ApiModel):
    date: date
    health_status: HealthStatus


class RipenessPoint(ApiModel):
    date: date
    stage: str
    estimated_days_min: int | None
    estimated_days_max: int | None


class EstimateVsActual(ApiModel):
    estimated_date_min: date | None
    estimated_date_max: date | None
    harvested_at: datetime | None
    within_range: bool | None


class PlantStats(ApiModel):
    health_series: list[HealthPoint]
    ripeness_series: list[RipenessPoint]
    estimate_vs_actual: list[EstimateVsActual]
