"""Staff-only schemas: roles, team broadcasts, model-feedback review."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.domain import FeedbackValue, UserRole
from app.schemas.base import ApiModel


class RoleUpdate(ApiModel):
    """design 13: ``expert`` after PM verification, ``moderator`` by appointment."""

    role: UserRole


class StaffUserOut(ApiModel):
    id: str
    username: str
    full_name: str
    email: str
    role: UserRole
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
    reviewed_at: datetime | None
    created_at: datetime


class FeedbackReview(ApiModel):
    correct_label: str = Field(min_length=1, max_length=64)
