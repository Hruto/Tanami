"""Ganti komoditas ketiga dari stroberi ke tomat.

Revision ID: 0009
Revises: 0008

Runtime v2 sekarang memakai ``mango``, ``citrus``, dan ``tomato``. Migrasi ini
memperbarui CHECK constraint yang masih menyebut ``strawberry``, mengganti
baris referensi ``crop_profiles``, dan menyesuaikan baris data lama yang masih
memakai kode komoditas ``strawberry``. ``runner`` (stolon) adalah material
stroberi; tomat memakai ``seed``/``grafted``, jadi constraint material juga
diperbarui.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOMATO_PROFILES = (
    ("tomato", "seed", 90, 120, 7, 10, 1, "Terus-menerus selama berbuah"),
    ("tomato", "grafted", 80, 110, 7, 10, 1, "Terus-menerus selama berbuah"),
)

_STRAWBERRY_PROFILES = (
    ("strawberry", "runner", 60, 90, 3, 7, 2, "Terus-menerus selama berbuah"),
    ("strawberry", "seed", 120, 180, 3, 7, 2, "Terus-menerus selama berbuah"),
)


def _insert_profiles(rows: tuple[tuple[str, str, int, int, int, int, int, str], ...]) -> None:
    for commodity, material, f_min, f_max, c_min, c_max, years, note in rows:
        op.execute(
            sa.text(
                "INSERT INTO crop_profiles "
                "(commodity_code, planting_material, first_harvest_min_days, "
                "first_harvest_max_days, harvest_cycle_min_days, harvest_cycle_max_days, "
                "productive_years, harvest_pattern_note) "
                "VALUES (:c, :m, :a, :b, :d, :e, :y, :n) "
                "ON CONFLICT (commodity_code, planting_material) DO NOTHING"
            ).bindparams(
                c=commodity, m=material, a=f_min, b=f_max, d=c_min, e=c_max, y=years, n=note
            )
        )


def upgrade() -> None:
    op.drop_constraint(op.f("ck_plants_commodity_code"), "plants", type_="check")
    op.drop_constraint(op.f("ck_plants_planting_material"), "plants", type_="check")
    op.drop_constraint(op.f("ck_crop_profiles_commodity_code"), "crop_profiles", type_="check")
    op.drop_constraint(
        op.f("ck_crop_profiles_planting_material"), "crop_profiles", type_="check"
    )

    op.execute(
        "UPDATE plants SET commodity_code = 'tomato', "
        "planting_material = CASE WHEN planting_material = 'runner' THEN 'seed' "
        "ELSE planting_material END "
        "WHERE commodity_code = 'strawberry'"
    )
    op.execute("UPDATE scans SET commodity_code = 'tomato' WHERE commodity_code = 'strawberry'")
    op.execute(
        "UPDATE forum_posts SET commodity_code = 'tomato' WHERE commodity_code = 'strawberry'"
    )
    op.execute("DELETE FROM crop_profiles WHERE commodity_code = 'strawberry'")
    _insert_profiles(_TOMATO_PROFILES)

    op.create_check_constraint(
        op.f("ck_plants_commodity_code"),
        "plants",
        "commodity_code IN ('mango', 'citrus', 'tomato')",
    )
    op.create_check_constraint(
        op.f("ck_plants_planting_material"),
        "plants",
        "planting_material IN ('grafted', 'seed', 'other')",
    )
    op.create_check_constraint(
        op.f("ck_crop_profiles_commodity_code"),
        "crop_profiles",
        "commodity_code IN ('mango', 'citrus', 'tomato')",
    )
    op.create_check_constraint(
        op.f("ck_crop_profiles_planting_material"),
        "crop_profiles",
        "planting_material IN ('grafted', 'seed', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_plants_commodity_code"), "plants", type_="check")
    op.drop_constraint(op.f("ck_plants_planting_material"), "plants", type_="check")
    op.drop_constraint(op.f("ck_crop_profiles_commodity_code"), "crop_profiles", type_="check")
    op.drop_constraint(
        op.f("ck_crop_profiles_planting_material"), "crop_profiles", type_="check"
    )

    op.execute(
        "UPDATE plants SET commodity_code = 'strawberry', "
        "planting_material = CASE WHEN planting_material = 'grafted' THEN 'seed' "
        "ELSE 'runner' END "
        "WHERE commodity_code = 'tomato'"
    )
    op.execute("UPDATE scans SET commodity_code = 'strawberry' WHERE commodity_code = 'tomato'")
    op.execute(
        "UPDATE forum_posts SET commodity_code = 'strawberry' WHERE commodity_code = 'tomato'"
    )
    op.execute("DELETE FROM crop_profiles WHERE commodity_code = 'tomato'")
    _insert_profiles(_STRAWBERRY_PROFILES)

    op.create_check_constraint(
        op.f("ck_plants_commodity_code"),
        "plants",
        "commodity_code IN ('mango', 'citrus', 'strawberry')",
    )
    op.create_check_constraint(
        op.f("ck_plants_planting_material"),
        "plants",
        "planting_material IN ('grafted', 'seed', 'runner', 'other')",
    )
    op.create_check_constraint(
        op.f("ck_crop_profiles_commodity_code"),
        "crop_profiles",
        "commodity_code IN ('mango', 'citrus', 'strawberry')",
    )
    op.create_check_constraint(
        op.f("ck_crop_profiles_planting_material"),
        "crop_profiles",
        "planting_material IN ('grafted', 'seed', 'runner', 'other')",
    )