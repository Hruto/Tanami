"""Ganti default komoditas scan dari cabai ke mangga.

Revision ID: 0007
Revises: 0006

Layanan vision sekarang hanya melayani tiga komoditas design.md v2
(``mango``, ``citrus``, ``strawberry``). Kolom ``scans.commodity_code``
punya default lama ``chili`` sejak 0001; default itu diubah supaya model
SQLAlchemy dan skema migrasi tidak lagi menyebut komoditas yang sudah
dipensiunkan. Baris lama sengaja tidak diubah -- itu riwayat scan, bukan
konfigurasi aktif.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "scans",
        "commodity_code",
        existing_type=sa.String(length=32),
        server_default="mango",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "scans",
        "commodity_code",
        existing_type=sa.String(length=32),
        server_default="chili",
        existing_nullable=False,
    )
