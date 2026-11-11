"""convert naive timestamps to timestamptz

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 19:30:00

``0001`` created every column declared as a bare ``Mapped[datetime]`` as
``timestamp without time zone``. The services write timezone-aware UTC values,
which asyncpg refuses for a naive column, so every scan, archive, harvest and
reminder write failed. ``Base.type_annotation_map`` now maps ``datetime`` to
``timestamptz``; this migration brings existing databases in line.

Existing values were written as UTC (or not at all), so ``AT TIME ZONE 'UTC'``
reinterprets them without shifting the instant. The downgrade is the exact
inverse.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column) pairs that 0001 created as ``timestamp without time zone``.
NAIVE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("users", "consent_at"),
    ("users", "deleted_at"),
    ("weather_snapshots", "fetched_at"),
    ("devices", "last_seen_at"),
    ("farms", "archived_at"),
    ("forum_reports", "resolved_at"),
    ("plants", "archived_at"),
    ("harvest_records", "harvested_at"),
    ("reminders", "valid_until"),
    ("reminders", "sent_at"),
    ("reminders", "read_at"),
    ("scans", "captured_at"),
    ("scan_feedback", "reviewed_at"),
    ("scan_feedback", "updated_at"),
)


def upgrade() -> None:
    for table, column in NAIVE_COLUMNS:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f"TYPE TIMESTAMP WITH TIME ZONE USING \"{column}\" AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    for table, column in NAIVE_COLUMNS:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f"TYPE TIMESTAMP WITHOUT TIME ZONE USING \"{column}\" AT TIME ZONE 'UTC'"
        )
