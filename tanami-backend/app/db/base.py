"""Declarative base and shared column types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming so Alembic autogenerate produces stable, reviewable constraint
# names instead of Postgres defaults (TQA 5.2: every schema change is a migration).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Every ``Mapped[datetime]`` is ``timestamptz``. Without this, SQLAlchemy maps
    # a bare annotation to ``timestamp without time zone`` and asyncpg rejects the
    # timezone-aware values the services write (``design.md`` 10.1: UTC).
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
    }


def utcnow() -> datetime:
    return datetime.now(UTC)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=utcnow,
    )


JsonDict = dict[str, object]
JsonList = list[object]

__all__ = [
    "JSONB",
    "Base",
    "JsonDict",
    "JsonList",
    "created_at_column",
    "updated_at_column",
    "utcnow",
]
