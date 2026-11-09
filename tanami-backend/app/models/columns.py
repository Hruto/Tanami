"""Shared column helpers for the ORM models."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk() -> Mapped[UUID]:
    return mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )


def enum_check(column: str, enum: type[StrEnum], *, name: str) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=name)


def values_check(column: str, values: Iterable[str], *, name: str) -> CheckConstraint:
    """A CHECK over an explicit value list, for columns whose allowed set is not a whole enum."""
    listed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({listed})", name=name)


def enum_values(enum: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum)


def enum_column(enum: type[StrEnum], *, length: int = 32) -> Any:
    """A VARCHAR column; the allowed values are enforced by a CHECK constraint."""
    # The argument is kept so callers can spell the allowed values even though the
    # constraint itself lives in ``enum_check``.
    _ = enum
    return String(length)


def timestamp() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False)


DefaultValues = dict[str, Any]
