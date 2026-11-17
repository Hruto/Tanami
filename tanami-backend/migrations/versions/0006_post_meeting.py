"""Pasca-rapat: varietas bebas, umur pembibitan, placement per tanaman, irigasi & kualitas panen.

Revision ID: 0006
Revises: 0005

Perubahan yang diminta setelah rapat:

* ``plants.nursery_started_at`` — estimasi tanggal mulai pembibitan, jadi dasar
  perhitungan umur (sebelumnya memakai ``planted_at``);
* ``plants.placement`` — indoor/outdoor dipindah dari ``farms`` ke tiap tanaman;
* ``irrigation_changes`` — riwayat perubahan jadwal penyiraman (saran sistem
  bisa ditimpa pengguna kapan saja);
* ``harvest_records.quality`` + ``success_pct`` — hasil akhir jadi pilihan
  kategori dan persentase keberhasilan dihitung backend.

Kolom lama ``farms.placement`` dan ``farms.archived_at`` tidak dipakai lagi
tetapi sengaja dibiarkan supaya downgrade tetap aman.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLACEMENTS = ("indoor", "outdoor")
SCHEDULES = ("daily", "every_3_5_days", "weekly", "never")
QUALITIES = ("gagal", "kurang_optimal", "normal", "panen_raya")


def upgrade() -> None:
    op.add_column("plants", sa.Column("nursery_started_at", sa.Date(), nullable=True))
    op.execute("UPDATE plants SET nursery_started_at = planted_at WHERE nursery_started_at IS NULL")
    op.alter_column("plants", "nursery_started_at", nullable=False)

    op.add_column(
        "plants",
        sa.Column("placement", sa.String(16), nullable=False, server_default="outdoor"),
    )
    op.create_check_constraint(
        "ck_plants_placement", "plants", "placement IN ('indoor', 'outdoor')"
    )
    op.create_index("ix_plants_placement", "plants", ["placement"])

    op.create_table(
        "irrigation_changes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "plant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_schedule", sa.String(16), nullable=False),
        sa.Column("to_schedule", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "from_schedule IN ('daily', 'every_3_5_days', 'weekly', 'never')",
            name="ck_irrigation_from_schedule",
        ),
        sa.CheckConstraint(
            "to_schedule IN ('daily', 'every_3_5_days', 'weekly', 'never')",
            name="ck_irrigation_to_schedule",
        ),
    )
    op.create_index(
        "ix_irrigation_changes_plant_time",
        "irrigation_changes",
        ["plant_id", sa.text("changed_at DESC")],
    )

    op.add_column("harvest_records", sa.Column("quality", sa.String(24), nullable=True))
    op.add_column("harvest_records", sa.Column("success_pct", sa.Numeric(6, 2), nullable=True))
    op.create_check_constraint(
        "ck_harvest_quality",
        "harvest_records",
        "quality IS NULL OR quality IN ('gagal', 'kurang_optimal', 'normal', 'panen_raya')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_harvest_quality", "harvest_records", type_="check")
    op.drop_column("harvest_records", "success_pct")
    op.drop_column("harvest_records", "quality")

    op.drop_index("ix_irrigation_changes_plant_time", table_name="irrigation_changes")
    op.drop_table("irrigation_changes")

    op.drop_index("ix_plants_placement", table_name="plants")
    op.drop_constraint("ck_plants_placement", "plants", type_="check")
    op.drop_column("plants", "placement")
    op.drop_column("plants", "nursery_started_at")
