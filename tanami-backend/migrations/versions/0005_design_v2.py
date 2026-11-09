"""design v2: mango/citrus/strawberry tracking, disease episodes, scans tied to plants

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09

Implements ``docs/design.md`` v2 (sections 8-9):

* ``crop_profiles`` (seeded) drives the rule-based harvest estimate;
* ``plants`` gain a display ``code``, ``planting_material``, ``quantity``,
  ``productive_until`` and the new end-of-tracking fields; ``growth_stage``,
  ``final_result``, ``yield_percent`` and the stored harvest range are dropped;
* ``harvest_records`` are numbered (``sequence``);
* ``disease_episodes`` (new) and ``scans.disease_episode_id``;
* ``detection_plants`` is dropped and every scan must belong to a plant;
* ``diseases.harvest_delay_days`` and the new reminder types.

Data that cannot exist in v2 is **deleted**: plants of any commodity other than
mango, citrus or strawberry (with their photos, care logs, harvests and
reminders), ripeness scans, and scans that belonged to no plant. The project is
pre-MVP; downgrading restores the structure, not that data. Old end reasons are
mapped (``died`` -> ``died_other``, everything else -> ``other``) and the old
reason is kept in ``end_note``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMMODITIES = ("mango", "citrus", "strawberry")
END_REASONS = ("productive_period_over", "disease", "cut_down", "died_other", "other")
OLD_END_REASONS = ("harvested", "died", "not_maintained", "other")
OLD_REMINDER_TYPES = (
    "watering",
    "photo",
    "monitoring",
    "fungal_risk",
    "heavy_rain_harvest",
    "harvest_soon",
    "heat_stress",
    "scan_followup",
    "general",
)
NEW_REMINDER_TYPES = (
    "watering",
    "photo",
    "monitoring",
    "fungal_risk",
    "heavy_rain_harvest",
    "heat_stress",
    "scan_followup",
    "general",
    "harvest_due",
    "harvest_check",
    "productive_ending",
    "tracking_completed",
)

# design 8.3 [USULAN]: starting values, to be replaced by sourced numbers.
# (commodity, material, first min, first max, cycle min, cycle max, years, note)
PROFILES = (
    ("mango", "grafted", 1095, 1460, 330, 400, 40, "Musiman, sekali setahun"),
    ("mango", "seed", 1825, 2920, 330, 400, 40, "Musiman, sekali setahun"),
    ("citrus", "grafted", 730, 1095, 150, 210, 20, "1-2 kali setahun"),
    ("citrus", "seed", 1825, 2555, 150, 210, 20, "1-2 kali setahun"),
    ("strawberry", "runner", 60, 90, 3, 7, 2, "Terus-menerus selama berbuah"),
    ("strawberry", "seed", 120, 180, 3, 7, 2, "Terus-menerus selama berbuah"),
)


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # --- 1. data that cannot exist in v2 ----------------------------------
    op.execute(f"DELETE FROM plants WHERE commodity_code NOT IN ({_in(COMMODITIES)})")  # noqa: S608 - module constants, not user input
    op.execute("DELETE FROM scans WHERE plant_id IS NULL OR scan_type <> 'disease'")

    # --- 2. the separate detection list -----------------------------------
    op.drop_constraint(
        op.f("fk_scans_detection_plant_id_detection_plants"), "scans", type_="foreignkey"
    )
    op.drop_index("ix_scans_detection_plant_captured", table_name="scans")
    op.drop_column("scans", "detection_plant_id")
    op.drop_index("ix_detection_plants_user_ended", table_name="detection_plants")
    op.drop_index("ix_detection_plants_plant_id", table_name="detection_plants")
    op.drop_table("detection_plants")

    # --- 3. crop profiles --------------------------------------------------
    op.create_table(
        "crop_profiles",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("commodity_code", sa.String(length=32), nullable=False),
        sa.Column("planting_material", sa.String(length=16), nullable=False),
        sa.Column("first_harvest_min_days", sa.Integer(), nullable=False),
        sa.Column("first_harvest_max_days", sa.Integer(), nullable=False),
        sa.Column("harvest_cycle_min_days", sa.Integer(), nullable=False),
        sa.Column("harvest_cycle_max_days", sa.Integer(), nullable=False),
        sa.Column("productive_years", sa.Integer(), nullable=False),
        sa.Column("harvest_pattern_note", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.Date(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            f"commodity_code IN ({_in(COMMODITIES)})", name=op.f("ck_crop_profiles_commodity_code")
        ),
        sa.CheckConstraint(
            "planting_material IN ('grafted', 'seed', 'runner', 'other')",
            name=op.f("ck_crop_profiles_planting_material"),
        ),
        sa.CheckConstraint(
            "first_harvest_min_days > 0 AND first_harvest_min_days <= first_harvest_max_days",
            name=op.f("ck_crop_profiles_first_harvest_range"),
        ),
        sa.CheckConstraint(
            "harvest_cycle_min_days > 0 AND harvest_cycle_min_days <= harvest_cycle_max_days",
            name=op.f("ck_crop_profiles_harvest_cycle_range"),
        ),
        sa.CheckConstraint(
            "productive_years > 0", name=op.f("ck_crop_profiles_productive_years_positive")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crop_profiles")),
        sa.UniqueConstraint(
            "commodity_code", "planting_material", name="uq_crop_profiles_material"
        ),
    )
    for commodity, material, f_min, f_max, c_min, c_max, years, note in PROFILES:
        op.execute(
            sa.text(
                "INSERT INTO crop_profiles (commodity_code, planting_material, "
                "first_harvest_min_days, first_harvest_max_days, harvest_cycle_min_days, "
                "harvest_cycle_max_days, productive_years, harvest_pattern_note) "
                "VALUES (:c, :m, :a, :b, :d, :e, :y, :n)"
            ).bindparams(
                c=commodity, m=material, a=f_min, b=f_max, d=c_min, e=c_max, y=years, n=note
            )
        )

    # --- 4. diseases and users ---------------------------------------------
    op.add_column(
        "diseases",
        sa.Column("harvest_delay_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_diseases_harvest_delay_non_negative"), "diseases", "harvest_delay_days >= 0"
    )
    # Knowledge-base rows of other commodities stay (scans may point at them) but go inactive.
    op.execute(
        f"UPDATE diseases SET is_active = false WHERE commodity_code NOT IN ({_in(COMMODITIES)})"  # noqa: S608 - module constants, not user input
    )
    op.add_column(
        "users",
        sa.Column(
            "plant_code_seq",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    # --- 5. plants -----------------------------------------------------------
    for name in (
        "growth_stage",
        "harvest_range",
        "end_reason",
        "final_result",
        "ended_with_reason",
        "yield_non_negative",
    ):
        op.drop_constraint(op.f(f"ck_plants_{name}"), "plants", type_="check")
    op.add_column("plants", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column("plants", sa.Column("code", sa.String(length=16), nullable=True))
    op.add_column("plants", sa.Column("planting_material", sa.String(length=16), nullable=True))
    op.add_column(
        "plants",
        sa.Column("quantity", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("plants", sa.Column("productive_until", sa.Date(), nullable=True))
    op.add_column(
        "plants",
        sa.Column("end_disease_codes", postgresql.ARRAY(sa.String(length=64)), nullable=True),
    )
    op.add_column("plants", sa.Column("end_cause_note", sa.Text(), nullable=True))
    op.add_column("plants", sa.Column("outcome", sa.String(length=16), nullable=True))
    op.alter_column(
        "plants",
        "end_reason",
        existing_type=sa.String(length=16),
        type_=sa.String(length=24),
        existing_nullable=True,
    )

    op.execute("UPDATE plants p SET user_id = f.user_id FROM farms f WHERE f.id = p.farm_id")
    op.execute(
        "UPDATE plants SET planting_material = "
        "CASE WHEN commodity_code = 'strawberry' THEN 'runner' ELSE 'grafted' END"
    )
    op.execute(
        "UPDATE plants p SET code = n.code FROM ("
        "SELECT id, CASE commodity_code WHEN 'mango' THEN 'MGA' WHEN 'citrus' THEN 'JRK' "
        "ELSE 'STB' END || '-' || lpad(row_number() OVER ("
        "PARTITION BY user_id, commodity_code ORDER BY created_at, id)::text, 3, '0') AS code "
        "FROM plants) n WHERE n.id = p.id"
    )
    op.execute(
        "UPDATE users u SET plant_code_seq = coalesce(("
        "SELECT jsonb_object_agg(commodity_code, cnt) FROM ("
        "SELECT commodity_code, count(*) AS cnt FROM plants WHERE user_id = u.id "
        "GROUP BY commodity_code) c), '{}'::jsonb)"
    )
    op.execute(
        "UPDATE plants p SET productive_until = "
        "(p.planted_at + make_interval(years => cp.productive_years))::date "
        "FROM crop_profiles cp WHERE cp.commodity_code = p.commodity_code "
        "AND cp.planting_material = p.planting_material"
    )
    # Right-hand sides read the old row, so the old reason survives in the note.
    op.execute(
        "UPDATE plants SET end_note = concat_ws(E'\\n', end_note, "
        "'Alasan sebelum v2: ' || end_reason), "
        "end_reason = CASE end_reason WHEN 'died' THEN 'died_other' ELSE 'other' END "
        "WHERE end_reason IS NOT NULL"
    )
    op.execute(
        "UPDATE plants p SET outcome = CASE WHEN EXISTS ("
        "SELECT 1 FROM harvest_records h WHERE h.plant_id = p.id) "
        "THEN 'ended_early' ELSE 'failed' END WHERE p.ended_at IS NOT NULL"
    )

    op.alter_column("plants", "user_id", existing_type=sa.UUID(), nullable=False)
    op.alter_column("plants", "code", existing_type=sa.String(length=16), nullable=False)
    op.alter_column(
        "plants", "planting_material", existing_type=sa.String(length=16), nullable=False
    )
    op.alter_column("plants", "productive_until", existing_type=sa.Date(), nullable=False)
    for column in (
        "growth_stage",
        "expected_harvest_min",
        "expected_harvest_max",
        "final_result",
        "yield_percent",
    ):
        op.drop_column("plants", column)

    op.create_foreign_key(
        op.f("fk_plants_user_id_users"), "plants", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index(op.f("ix_plants_user_id"), "plants", ["user_id"], unique=False)
    op.create_index("ix_plants_user_ended", "plants", ["user_id", "ended_at"], unique=False)
    op.create_unique_constraint("uq_plants_user_code", "plants", ["user_id", "code"])
    op.create_check_constraint(
        op.f("ck_plants_commodity_code"), "plants", f"commodity_code IN ({_in(COMMODITIES)})"
    )
    op.create_check_constraint(
        op.f("ck_plants_planting_material"),
        "plants",
        "planting_material IN ('grafted', 'seed', 'runner', 'other')",
    )
    op.create_check_constraint(
        op.f("ck_plants_end_reason"),
        "plants",
        f"end_reason IS NULL OR end_reason IN ({_in(END_REASONS)})",
    )
    op.create_check_constraint(
        op.f("ck_plants_outcome"),
        "plants",
        "outcome IS NULL OR outcome IN ('completed', 'ended_early', 'failed')",
    )
    op.create_check_constraint(
        op.f("ck_plants_ended_with_reason"), "plants", "(ended_at IS NULL) = (end_reason IS NULL)"
    )
    op.create_check_constraint(
        op.f("ck_plants_ended_with_outcome"), "plants", "(ended_at IS NULL) = (outcome IS NULL)"
    )
    op.create_check_constraint(op.f("ck_plants_quantity_positive"), "plants", "quantity >= 1")
    op.create_check_constraint(
        op.f("ck_plants_disease_end_has_cause"),
        "plants",
        "end_reason IS DISTINCT FROM 'disease' "
        "OR cardinality(coalesce(end_disease_codes, '{}')) > 0 "
        "OR btrim(coalesce(end_cause_note, '')) <> ''",
    )

    # --- 6. harvest numbering ------------------------------------------------
    op.add_column("harvest_records", sa.Column("sequence", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE harvest_records h SET sequence = n.seq FROM ("
        "SELECT id, row_number() OVER (PARTITION BY plant_id ORDER BY harvested_at, id) AS seq "
        "FROM harvest_records) n WHERE n.id = h.id"
    )
    op.alter_column("harvest_records", "sequence", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint(
        op.f("ck_harvest_records_sequence_positive"), "harvest_records", "sequence >= 1"
    )
    op.create_unique_constraint(
        "uq_harvest_records_plant_sequence",
        "harvest_records",
        ["plant_id", "sequence"],
        deferrable=True,
        initially="DEFERRED",
    )

    # --- 7. disease episodes and scans ----------------------------------------
    op.create_table(
        "disease_episodes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("plant_id", sa.UUID(), nullable=False),
        sa.Column("disease_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_by_scan_id", sa.UUID(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delay_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(length=24), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('open', 'resolved')", name=op.f("ck_disease_episodes_status")
        ),
        sa.CheckConstraint(
            "close_reason IS NULL OR close_reason IN "
            "('user_marked_healed', 'healthy_scan', 'tracking_ended')",
            name=op.f("ck_disease_episodes_close_reason"),
        ),
        sa.CheckConstraint("delay_days >= 0", name=op.f("ck_disease_episodes_delay_non_negative")),
        sa.CheckConstraint(
            "(status = 'open') = (resolved_at IS NULL) "
            "AND (status = 'open') = (close_reason IS NULL)",
            name=op.f("ck_disease_episodes_resolution_matches_status"),
        ),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.id"],
            name=op.f("fk_disease_episodes_plant_id_plants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["disease_code"],
            ["diseases.code"],
            name=op.f("fk_disease_episodes_disease_code_diseases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disease_episodes")),
    )
    op.create_index(
        "uq_disease_episodes_open",
        "disease_episodes",
        ["plant_id", "disease_code"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_disease_episodes_plant_opened",
        "disease_episodes",
        ["plant_id", sa.literal_column("opened_at DESC")],
        unique=False,
    )

    op.drop_constraint(op.f("fk_scans_plant_id_plants"), "scans", type_="foreignkey")
    op.alter_column("scans", "plant_id", existing_type=sa.UUID(), nullable=False)
    op.create_foreign_key(
        op.f("fk_scans_plant_id_plants"),
        "scans",
        "plants",
        ["plant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column("scans", sa.Column("disease_episode_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_scans_disease_episode_id_disease_episodes"),
        "scans",
        "disease_episodes",
        ["disease_episode_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_scans_disease_episode_id", "scans", ["disease_episode_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_disease_episodes_opened_by_scan_id_scans"),
        "disease_episodes",
        "scans",
        ["opened_by_scan_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(op.f("ck_scans_scan_type"), "scans", type_="check")
    op.create_check_constraint(op.f("ck_scans_scan_type"), "scans", "scan_type IN ('disease')")

    # --- 8. reminder types -------------------------------------------------------
    op.execute("DELETE FROM reminders WHERE type = 'harvest_soon'")
    op.drop_constraint(op.f("ck_reminders_type"), "reminders", type_="check")
    op.create_check_constraint(
        op.f("ck_reminders_type"), "reminders", f"type IN ({_in(NEW_REMINDER_TYPES)})"
    )


def downgrade() -> None:
    """Restore the v0.3 structure. Rows deleted by ``upgrade`` are not restored."""
    op.execute(
        "DELETE FROM reminders WHERE type IN "
        "('harvest_due', 'harvest_check', 'productive_ending', 'tracking_completed')"
    )
    op.drop_constraint(op.f("ck_reminders_type"), "reminders", type_="check")
    op.create_check_constraint(
        op.f("ck_reminders_type"), "reminders", f"type IN ({_in(OLD_REMINDER_TYPES)})"
    )

    op.drop_constraint(op.f("ck_scans_scan_type"), "scans", type_="check")
    op.create_check_constraint(
        op.f("ck_scans_scan_type"), "scans", "scan_type IN ('disease', 'ripeness')"
    )
    op.drop_constraint(
        op.f("fk_disease_episodes_opened_by_scan_id_scans"), "disease_episodes", type_="foreignkey"
    )
    op.drop_index("ix_scans_disease_episode_id", table_name="scans")
    op.drop_constraint(
        op.f("fk_scans_disease_episode_id_disease_episodes"), "scans", type_="foreignkey"
    )
    op.drop_column("scans", "disease_episode_id")
    op.drop_index("ix_disease_episodes_plant_opened", table_name="disease_episodes")
    op.drop_index("uq_disease_episodes_open", table_name="disease_episodes")
    op.drop_table("disease_episodes")

    op.drop_constraint(op.f("fk_scans_plant_id_plants"), "scans", type_="foreignkey")
    op.alter_column("scans", "plant_id", existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key(
        op.f("fk_scans_plant_id_plants"),
        "scans",
        "plants",
        ["plant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "detection_plants",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("commodity_code", sa.String(length=32), server_default="chili", nullable=False),
        sa.Column("plant_id", sa.UUID(), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "length(trim(name)) > 0", name=op.f("ck_detection_plants_name_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.id"],
            name=op.f("fk_detection_plants_plant_id_plants"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_detection_plants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_plants")),
    )
    op.create_index("ix_detection_plants_plant_id", "detection_plants", ["plant_id"], unique=False)
    op.create_index(
        "ix_detection_plants_user_ended",
        "detection_plants",
        ["user_id", "ended_at", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.add_column("scans", sa.Column("detection_plant_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_scans_detection_plant_captured",
        "scans",
        ["detection_plant_id", sa.literal_column("captured_at DESC")],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_scans_detection_plant_id_detection_plants"),
        "scans",
        "detection_plants",
        ["detection_plant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("uq_harvest_records_plant_sequence", "harvest_records", type_="unique")
    op.drop_constraint(
        op.f("ck_harvest_records_sequence_positive"), "harvest_records", type_="check"
    )
    op.drop_column("harvest_records", "sequence")

    for name in (
        "disease_end_has_cause",
        "quantity_positive",
        "ended_with_outcome",
        "ended_with_reason",
        "outcome",
        "end_reason",
        "planting_material",
        "commodity_code",
    ):
        op.drop_constraint(op.f(f"ck_plants_{name}"), "plants", type_="check")
    op.drop_constraint("uq_plants_user_code", "plants", type_="unique")
    op.drop_index("ix_plants_user_ended", table_name="plants")
    op.drop_index(op.f("ix_plants_user_id"), table_name="plants")
    op.drop_constraint(op.f("fk_plants_user_id_users"), "plants", type_="foreignkey")
    op.add_column(
        "plants", sa.Column("yield_percent", sa.Numeric(precision=6, scale=1), nullable=True)
    )
    op.add_column("plants", sa.Column("final_result", sa.String(length=16), nullable=True))
    op.add_column("plants", sa.Column("expected_harvest_max", sa.Date(), nullable=True))
    op.add_column("plants", sa.Column("expected_harvest_min", sa.Date(), nullable=True))
    op.add_column(
        "plants",
        sa.Column("growth_stage", sa.String(length=16), server_default="fruiting", nullable=False),
    )
    op.alter_column("plants", "growth_stage", server_default=None)
    op.execute(
        "UPDATE plants SET end_reason = CASE end_reason "
        "WHEN 'disease' THEN 'died' WHEN 'died_other' THEN 'died' ELSE 'other' END "
        "WHERE end_reason IS NOT NULL"
    )
    op.alter_column(
        "plants",
        "end_reason",
        existing_type=sa.String(length=24),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
    for column in (
        "outcome",
        "end_cause_note",
        "end_disease_codes",
        "productive_until",
        "quantity",
        "planting_material",
        "code",
        "user_id",
    ):
        op.drop_column("plants", column)
    op.create_check_constraint(
        op.f("ck_plants_growth_stage"),
        "plants",
        "growth_stage IN ('seedling', 'vegetative', 'flowering', 'fruiting', 'harvesting', 'finished')",
    )
    op.create_check_constraint(
        op.f("ck_plants_harvest_range"),
        "plants",
        "(expected_harvest_min IS NULL AND expected_harvest_max IS NULL) "
        "OR (expected_harvest_min IS NOT NULL AND expected_harvest_max IS NOT NULL "
        "AND expected_harvest_min <= expected_harvest_max)",
    )
    op.create_check_constraint(
        op.f("ck_plants_end_reason"),
        "plants",
        f"end_reason IS NULL OR end_reason IN ({_in(OLD_END_REASONS)})",
    )
    op.create_check_constraint(
        op.f("ck_plants_final_result"),
        "plants",
        "final_result IS NULL OR final_result IN ('failed', 'suboptimal', 'normal', 'bumper')",
    )
    op.create_check_constraint(
        op.f("ck_plants_ended_with_reason"), "plants", "(ended_at IS NULL) = (end_reason IS NULL)"
    )
    op.create_check_constraint(
        op.f("ck_plants_yield_non_negative"),
        "plants",
        "yield_percent IS NULL OR yield_percent >= 0",
    )

    op.drop_column("users", "plant_code_seq")
    op.drop_constraint(op.f("ck_diseases_harvest_delay_non_negative"), "diseases", type_="check")
    op.drop_column("diseases", "harvest_delay_days")
    op.drop_table("crop_profiles")
