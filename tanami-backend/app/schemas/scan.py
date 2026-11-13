"""Scan, feedback and disease schemas.

The result block mirrors ``design.md`` section 11.3 exactly. The backend adds
``advice`` (from the reviewed knowledge base, never from the model) and the
absolute harvest dates, which the vision service deliberately does not produce.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.domain import (
    CauseCategory,
    EstimateConfidence,
    FeedbackValue,
    QualityStatus,
    ResultStatus,
    RipenessStage,
    ScanType,
    Severity,
)
from app.schemas.base import ApiModel
from app.schemas.farm import EpisodeOut, NextHarvestOut


class DiseaseTopOut(ApiModel):
    disease_code: str
    label: str
    cause_category: CauseCategory
    confidence: float


class DiseaseAlternativeOut(ApiModel):
    disease_code: str
    label: str
    cause_category: CauseCategory
    confidence: float


class AdviceOut(ApiModel):
    """Built from the reviewed ``diseases`` row, never from the model (TQA 8.3)."""

    summary: str
    disease_name: str | None = None
    # Requirement 3: symptoms and the full reviewed treatment advice.
    symptoms: str | None = None
    prevention: str | None = None
    harvest_delay_days: int | None = None
    treatments: dict[str, Any] | None = None
    disease_detail_url: str | None = None
    first_aid: list[str] = Field(default_factory=list)
    reviewed_by: str | None = None
    reviewed_at: date | None = None


class DiseaseResultOut(ApiModel):
    top: DiseaseTopOut | None
    alternatives: list[DiseaseAlternativeOut]
    is_healthy: bool | None
    severity: Severity | None
    advice: AdviceOut | None = None
    quality: dict[str, QualityStatus] | None = None


class RipenessResultOut(ApiModel):
    stage: RipenessStage | None
    stage_label: str | None
    confidence: float | None
    estimated_days_min: int | None
    estimated_days_max: int | None
    estimate_confidence: EstimateConfidence | None
    estimated_harvest_date_min: date | None = None
    estimated_harvest_date_max: date | None = None
    note: str


class ScanOut(ApiModel):
    id: str
    type: ScanType
    status: ResultStatus
    model_version: str
    image_url: str
    plant_id: str
    captured_at: datetime
    result: dict[str, Any]
    quality: dict[str, Any]
    created_at: datetime


class ScanDetailOut(ScanOut):
    commodity_code: str
    feedback: FeedbackOut | None = None


class FeedbackOut(ApiModel):
    value: FeedbackValue
    comment: str | None
    created_at: datetime


class FeedbackCreate(ApiModel):
    value: FeedbackValue
    comment: str | None = Field(default=None, max_length=1000)


class DiseaseOut(ApiModel):
    code: str
    commodity_code: str
    name_id: str
    name_latin: str | None
    cause_category: CauseCategory
    symptoms: str
    causes_text: str
    treatments: dict[str, Any]
    prevention: str
    severity_note: str | None
    reviewed_by: str | None
    reviewed_at: date | None


class DiseaseSummaryOut(ApiModel):
    code: str
    commodity_code: str
    name_id: str
    cause_category: CauseCategory


class ConfirmationOut(ApiModel):
    """What the "Apakah tanaman ini memang sakit?" card needs (design 5.4, 8.5)."""

    can_confirm: bool
    existing_episode_id: str | None = None
    # Days a confirmation would add to the running cycle right now (0 = nothing).
    delay_preview_days: int = 0


class ScanCreated(ApiModel):
    """The 201 body of a stored scan, or the 200 body of a "cek cepat" (not stored)."""

    id: str | None
    saved: bool = True
    type: ScanType
    status: ResultStatus
    model_version: str
    image_url: str | None
    plant_id: str | None
    plant_code: str | None = None
    captured_at: datetime
    result: dict[str, Any]
    quality: dict[str, Any]
    created_at: datetime
    is_duplicate: bool = False
    confirmation: ConfirmationOut | None = None
    # Open episodes this (healthy) scan closed.
    closed_episode_ids: list[str] = Field(default_factory=list)


class ScanHistoryItem(ApiModel):
    """One row of Riwayat Scan (design 10.6)."""

    id: str
    captured_at: datetime
    plant_id: str
    plant_code: str
    plant_label: str
    plant_ended: bool
    commodity_code: str
    status: ResultStatus
    disease_code: str | None
    disease_label: str | None
    cause_category: CauseCategory | None
    confidence_percent: int | None
    is_healthy: bool | None
    prevention_summary: str | None
    disease_episode_id: str | None
    thumbnail_url: str


class ConfirmDiseaseOut(ApiModel):
    is_new: bool
    episode: EpisodeOut
    next_harvest: NextHarvestOut | None = None
