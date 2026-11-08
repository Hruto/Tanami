"""Disease-detection plant list (requirements 3-4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.errors import ValidationError
from app.domain import DETECTION_COMMODITIES
from app.schemas.base import ApiModel
from app.schemas.scan import ScanOut


def _clean_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValidationError("Nama tanaman tidak boleh kosong.", details={"field": "name"})
    return cleaned


class DetectionPlantCreate(ApiModel):
    """Requirement 3: the user only types a name; the photo is the first scan."""

    name: str = Field(min_length=1, max_length=120)
    # Which model analyses the photos. Only commodities with a model are allowed.
    commodity_code: str = "chili"
    # Optional link to a tracked plant, so results also show in its history.
    plant_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("commodity_code")
    @classmethod
    def _commodity(cls, value: str) -> str:
        if value not in DETECTION_COMMODITIES:
            raise ValidationError(
                "Deteksi penyakit belum tersedia untuk jenis tanaman ini.",
                details={"field": "commodity_code", "supported": list(DETECTION_COMMODITIES)},
            )
        return value


class DetectionPlantUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    plant_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str:
        return _clean_name(value or "")


class DetectionEnd(ApiModel):
    note: str | None = Field(default=None, max_length=1000)


class DetectionPlantOut(ApiModel):
    id: str
    name: str
    commodity_code: str
    plant_id: str | None
    status: Literal["active", "ended"]
    ended_at: datetime | None
    end_note: str | None
    # Photo of the latest check, shown on the list card and history detail.
    cover_image_url: str | None
    scan_count: int
    # Headline of the latest check: disease name, confidence, status.
    last_result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class DetectionPlantDetailOut(DetectionPlantOut):
    """Requirement 3-4: every check of this plant, newest first."""

    scans: list[ScanOut]
