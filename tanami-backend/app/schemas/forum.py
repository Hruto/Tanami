"""Forum and moderation schemas (``design.md`` 10.10, 13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.errors import ValidationError
from app.domain import FORUM_CATEGORIES, PostStatus, ReportReason, ReportTargetType, UserRole
from app.schemas.base import ApiModel

MAX_POST_IMAGES = 3


class AuthorOut(ApiModel):
    """Public identity on the forum: the username is the handle, the full name
    is shown next to it. Email is never exposed (TQA 9)."""

    id: str
    username: str
    display_name: str
    role: UserRole
    is_expert: bool = False


class ForumCategoryOut(ApiModel):
    commodity_code: str
    label: str
    post_count: int


class ForumPostCreate(ApiModel):
    commodity_code: str = "chili"
    title: str = Field(min_length=5, max_length=120)
    body: str = Field(min_length=1, max_length=5000)
    scan_id: UUID | None = None
    # Keys returned by ``POST /uploads/forum-image``; never URLs.
    image_keys: list[str] = Field(default_factory=list)

    @field_validator("commodity_code")
    @classmethod
    def _category(cls, value: str) -> str:
        if value not in FORUM_CATEGORIES:
            raise ValidationError(
                "Kategori forum tidak dikenal.",
                details={"field": "commodity_code", "allowed": list(FORUM_CATEGORIES)},
            )
        return value

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 5:
            raise ValidationError("Judul minimal 5 karakter.", details={"field": "title", "min": 5})
        return cleaned

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValidationError("Isi posting tidak boleh kosong.", details={"field": "body"})
        return cleaned

    @field_validator("image_keys")
    @classmethod
    def _images(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_POST_IMAGES:
            raise ValidationError(
                "Maksimal 3 foto per posting.",
                details={"field": "image_keys", "max": MAX_POST_IMAGES},
            )
        if len(set(value)) != len(value):
            raise ValidationError(
                "Foto yang sama dikirim dua kali.", details={"field": "image_keys"}
            )
        return value


class ForumPostOut(ApiModel):
    id: str
    commodity_code: str
    title: str
    body: str
    status: PostStatus
    author: AuthorOut
    image_urls: list[str]
    scan_id: str | None
    # design 13: only the photo and a short result are shared, never the
    # plant, farm or any other private history.
    scan_summary: dict[str, Any] | None = None
    comment_count: int
    # Requirement 5: reactions ("suka") on posts.
    like_count: int = 0
    liked_by_me: bool = False
    created_at: datetime
    updated_at: datetime


class ForumCommentCreate(ApiModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValidationError("Komentar tidak boleh kosong.", details={"field": "body"})
        return cleaned


class ForumCommentOut(ApiModel):
    id: str
    post_id: str
    body: str
    status: PostStatus
    author: AuthorOut
    created_at: datetime


class ForumPostDetailOut(ForumPostOut):
    comments: list[ForumCommentOut]


class ForumReportCreate(ApiModel):
    target_type: ReportTargetType
    target_id: UUID
    reason: ReportReason
    note: str | None = Field(default=None, max_length=1000)


class ForumReportOut(ApiModel):
    id: str
    target_type: ReportTargetType
    target_id: str
    reason: ReportReason
    created_at: datetime


class ForumImageOut(ApiModel):
    image_key: str
    image_url: str


# --------------------------------------------------------------------------- #
# Moderation (design 13: PM or a moderator reviews reports within 2 work days)
# --------------------------------------------------------------------------- #
class ModerationStatusUpdate(ApiModel):
    status: PostStatus
    note: str | None = Field(default=None, max_length=1000)


ReportAction = Literal["dismiss", "hide", "remove"]


class ReportResolve(ApiModel):
    """Close every open report on the target; optionally act on the content."""

    action: ReportAction


class ReportedTargetOut(ApiModel):
    target_type: ReportTargetType
    target_id: str
    status: PostStatus
    excerpt: str
    author: AuthorOut
    post_id: str
    report_count: int
    reasons: dict[str, int]
    first_reported_at: datetime
    last_reported_at: datetime
