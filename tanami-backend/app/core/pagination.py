"""Cursor pagination helpers (``design.md`` 10.1).

The cursor is opaque to the client: base64url of ``<iso timestamp>|<uuid>`` for
keyset pagination. Keyset rather than offset so a new row cannot shift a page
and make a user see the same item twice.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.errors import ValidationError

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


@dataclass(frozen=True, slots=True)
class Cursor:
    created_at: datetime
    last_id: UUID


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int
    cursor: Cursor | None


def encode_cursor(created_at: datetime, last_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{last_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str) -> Cursor:
    padded = value + "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded).decode()
        timestamp, _, last_id = raw.partition("|")
        return Cursor(created_at=datetime.fromisoformat(timestamp), last_id=UUID(last_id))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValidationError(
            "Kursor halaman tidak valid.",
            details={"field": "cursor"},
        ) from exc


def page_request(limit: int | None, cursor: str | None) -> PageRequest:
    resolved = DEFAULT_LIMIT if limit is None else limit
    if resolved < 1 or resolved > MAX_LIMIT:
        raise ValidationError(
            f"limit harus antara 1 dan {MAX_LIMIT}.",
            details={"field": "limit", "min": 1, "max": MAX_LIMIT},
        )
    return PageRequest(limit=resolved, cursor=decode_cursor(cursor) if cursor else None)


def page_meta(next_cursor: str | None) -> dict[str, Any]:
    return {"next_cursor": next_cursor, "has_more": next_cursor is not None}


def has_more(rows: list[Any], limit: int) -> bool:
    return len(rows) > limit
