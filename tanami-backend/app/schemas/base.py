"""Response envelopes and shared schema pieces.

``design.md`` 10.1 fixes two shapes: ``{"data": ...}`` for an object and
``{"data": [...], "meta": {"next_cursor", "has_more"}}`` for a page. Errors use
``{"error": {...}}`` and are produced by the handlers, not by these models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, populate_by_name=True)


class Envelope[T](ApiModel):
    data: T


class PaginationMeta(ApiModel):
    next_cursor: str | None = None
    has_more: bool = False


class ListEnvelope[T](ApiModel):
    data: list[T]
    meta: PaginationMeta


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str


class ErrorResponse(ApiModel):
    error: ErrorBody


def utc(value: datetime) -> datetime:
    """Normalise to UTC so the serialised form ends with ``Z`` (TQA 6.3)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class TimestampedOut(ApiModel):
    id: str
    created_at: datetime
    updated_at: datetime | None = None


class Page(BaseModel):
    """Query parameters shared by every paginated endpoint."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = None
