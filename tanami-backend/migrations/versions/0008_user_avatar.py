"""Tambah kolom foto profil pengguna.

Revision ID: 0008
Revises: 0007

``users.avatar_key`` menyimpan object key di storage (S3/MemoryStorage), bukan
URL. URL publik dihasilkan API saat membaca profil supaya rotasi/presign tidak
membuat URL basi di database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_key")
