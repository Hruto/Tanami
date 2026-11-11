"""reminder push state and team broadcasts

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07 20:00:00

* ``reminders.push_state`` records where each push stands. ``pending`` rows are
  retried by the hourly dispatcher, which is how quiet hours defer a push
  instead of dropping it (design 12.4). Existing rows are backfilled as final
  (``sent`` when ``sent_at`` is set, otherwise ``expired``) so the first deploy
  does not push old reminders.
* ``has_target`` now allows a ``general`` reminder without a farm or plant: a
  message from the team concerns the user, not a field.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PUSH_STATES = ("pending", "sent", "no_device", "disabled", "skipped_cap", "failed", "expired")


def upgrade() -> None:
    op.add_column(
        "reminders",
        sa.Column("push_state", sa.String(length=16), server_default="pending", nullable=False),
    )
    op.execute(
        "UPDATE reminders SET push_state = CASE WHEN sent_at IS NOT NULL "
        "THEN 'sent' ELSE 'expired' END"
    )
    values = ", ".join(f"'{state}'" for state in PUSH_STATES)
    op.create_check_constraint(
        op.f("ck_reminders_push_state"), "reminders", f"push_state IN ({values})"
    )
    op.create_index(
        "ix_reminders_push_state_created", "reminders", ["push_state", "created_at"], unique=False
    )
    op.drop_constraint(op.f("ck_reminders_has_target"), "reminders", type_="check")
    op.create_check_constraint(
        op.f("ck_reminders_has_target"),
        "reminders",
        "farm_id IS NOT NULL OR plant_id IS NOT NULL OR type = 'general'",
    )


def downgrade() -> None:
    op.execute("DELETE FROM reminders WHERE farm_id IS NULL AND plant_id IS NULL")
    op.drop_constraint(op.f("ck_reminders_has_target"), "reminders", type_="check")
    op.create_check_constraint(
        op.f("ck_reminders_has_target"), "reminders", "farm_id IS NOT NULL OR plant_id IS NOT NULL"
    )
    op.drop_index("ix_reminders_push_state_created", table_name="reminders")
    op.drop_constraint(op.f("ck_reminders_push_state"), "reminders", type_="check")
    op.drop_column("reminders", "push_state")
