"""Staff-only schemas: overview, users, roles, broadcasts, knowledge base, review."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.errors import ValidationError
from app.domain import FeedbackValue, UserRole
from app.schemas.base import ApiModel
from app.schemas.scan import DiseaseOut


class RoleUpdate(ApiModel):
    """design 13: ``expert`` after PM verification, ``moderator`` by appointment."""

    role: UserRole


class StaffUserOut(ApiModel):
    id: str
    username: str
    full_name: str
    email: str
    role: UserRole
    consent_training_data: bool = False
    deleted_at: datetime | None = None
    created_at: datetime


class GeneralReminderCreate(ApiModel):
    """A ``general`` reminder from the team (design 12.3), priority ``low``.

    ``user_id`` targets one account; omitted, it goes to every active account.
    """

    title: str = Field(min_length=5, max_length=140)
    body: str = Field(min_length=1, max_length=1000)
    user_id: UUID | None = None


class BroadcastOut(ApiModel):
    created: int


class FeedbackReviewItem(ApiModel):
    """One ``correct``/``incorrect`` verdict waiting for expert review (TQA 8.4)."""

    id: str
    scan_id: str
    scan_type: str
    image_url: str
    model_version: str
    predicted: dict[str, Any] | None
    value: FeedbackValue
    comment: str | None
    correct_label: str | None
    # TQA 8.1 / design 11.6: only consenting users may enter a training set.
    consent_training_data: bool
    # Labels the expert may choose from for this scan type (design 11.5).
    allowed_labels: list[str] = Field(default_factory=list)
    reviewed_at: datetime | None
    created_at: datetime


class FeedbackReview(ApiModel):
    correct_label: str = Field(min_length=1, max_length=64)


# --------------------------------------------------------------------------- #
# Overview (admin dashboard home)
# --------------------------------------------------------------------------- #
class UserCounts(ApiModel):
    total: int
    new_7d: int
    pending_deletion: int
    by_role: dict[str, int]


class TrackingCounts(ApiModel):
    active_plants: int
    ended_plants: int
    # Status akhir (design 8.6): completed / ended_early / failed.
    outcomes: dict[str, int]


class DetectionCounts(ApiModel):
    scans_total: int
    scans_7d: int


class QueueCounts(ApiModel):
    open_reports: int
    feedback_pending: int


class DailyScans(ApiModel):
    day: date
    disease: int
    ripeness: int


class DiseaseCount(ApiModel):
    code: str
    name: str
    count: int


class AdminOverviewOut(ApiModel):
    generated_at: datetime
    timezone: str
    users: UserCounts
    tracking: TrackingCounts
    detection: DetectionCounts
    queues: QueueCounts
    scans_daily: list[DailyScans]
    scan_status_30d: dict[str, int]
    top_diseases_30d: list[DiseaseCount]


# --------------------------------------------------------------------------- #
# Team broadcasts
# --------------------------------------------------------------------------- #
class BroadcastHistoryItem(ApiModel):
    batch: str
    title: str
    body: str
    audience: Literal["all", "user"]
    recipients: int
    read: int
    sent_at: datetime


# --------------------------------------------------------------------------- #
# Disease knowledge base (expert editing, TQA 8.3)
# --------------------------------------------------------------------------- #
class TreatmentStep(ApiModel):
    title: str = Field(min_length=1, max_length=120)
    how: str = Field(min_length=1, max_length=1000)


class TreatmentsIn(ApiModel):
    """Shape of ``diseases.treatments`` (design 9.3)."""

    first_aid: list[str] = Field(default_factory=list, max_length=10)
    organic: list[TreatmentStep] = Field(default_factory=list, max_length=10)
    chemical: list[TreatmentStep] = Field(default_factory=list, max_length=10)
    safety_note: str = Field(default="", max_length=1000)
    when_to_call_expert: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _chemical_needs_safety_note(self) -> TreatmentsIn:
        if any(not step.strip() for step in self.first_aid):
            raise ValidationError(
                "Langkah pertolongan pertama tidak boleh kosong.",
                details={"field": "treatments.first_aid"},
            )
        if self.chemical and not self.safety_note.strip():
            # TQA 8.3: chemical advice always ships with a safety note.
            raise ValidationError(
                "Saran bahan kimia wajib disertai catatan keselamatan.",
                details={"field": "treatments.safety_note"},
            )
        return self


class DiseaseAdminOut(DiseaseOut):
    is_active: bool
    updated_at: datetime


class DiseaseUpdate(ApiModel):
    """Every field optional; the editor becomes ``reviewed_by`` with today's date."""

    name_id: str | None = Field(default=None, min_length=2, max_length=120)
    name_latin: str | None = Field(default=None, max_length=160)
    symptoms: str | None = Field(default=None, min_length=10, max_length=4000)
    causes_text: str | None = Field(default=None, min_length=10, max_length=4000)
    prevention: str | None = Field(default=None, min_length=10, max_length=4000)
    severity_note: str | None = Field(default=None, max_length=1000)
    treatments: TreatmentsIn | None = None
    is_active: bool | None = None
