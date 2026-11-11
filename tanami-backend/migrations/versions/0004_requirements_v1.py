"""requirements v1: gardens, tracking history, detection list, profile, likes

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08

Implements the product requirements (gardens indoor/outdoor, irrigation
schedule, ending tracking with a final result, growth photos and care logs, a
separate disease-detection plant list, username + full name, forum likes and
the watering/photo/monitoring reminders).

Renames are written by hand so no data is lost: ``plants.archived_at`` ->
``ended_at`` (archived plants become ended with reason ``other``) and
``users.display_name`` -> ``full_name``. ``users.phone`` is dropped: the
requirements identify an account by email and username only; phone-only
accounts get a placeholder email they must change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_REMINDER_TYPES = (
    "fungal_risk",
    "heavy_rain_harvest",
    "harvest_soon",
    "heat_stress",
    "scan_followup",
    "general",
)
NEW_REMINDER_TYPES = ("watering", "photo", "monitoring", *OLD_REMINDER_TYPES)
PLANT_CHECKS = {
    "irrigation_schedule": "irrigation_schedule IN ('daily', 'every_3_5_days', 'weekly', 'never')",
    "end_reason": (
        "end_reason IS NULL OR end_reason IN ('harvested', 'died', 'not_maintained', 'other')"
    ),
    "final_result": (
        "final_result IS NULL OR final_result IN ('failed', 'suboptimal', 'normal', 'bumper')"
    ),
    "ended_with_reason": "(ended_at IS NULL) = (end_reason IS NULL)",
    "yield_non_negative": "yield_percent IS NULL OR yield_percent >= 0",
}


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:

    op.create_table(
        "care_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("plant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "action IN ('watering', 'fertilizing', 'pest_control', 'pruning', 'weeding', 'other')",
            name=op.f("ck_care_logs_action"),
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) <= 1000", name=op.f("ck_care_logs_note_length")
        ),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.id"],
            name=op.f("fk_care_logs_plant_id_plants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_care_logs_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_care_logs")),
    )
    op.create_index(
        "ix_care_logs_plant_action",
        "care_logs",
        ["plant_id", "action", sa.literal_column("performed_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_care_logs_plant_performed",
        "care_logs",
        ["plant_id", sa.literal_column("performed_at DESC")],
        unique=False,
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
    op.create_table(
        "plant_photos",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("plant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("image_key", sa.String(length=255), nullable=False),
        sa.Column("caption", sa.String(length=280), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.id"],
            name=op.f("fk_plant_photos_plant_id_plants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_plant_photos_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plant_photos")),
    )
    op.create_index(
        "ix_plant_photos_plant_taken",
        "plant_photos",
        ["plant_id", sa.literal_column("taken_at DESC")],
        unique=False,
    )
    op.create_index("ix_plant_photos_user_id", "plant_photos", ["user_id"], unique=False)
    op.create_table(
        "forum_reactions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["forum_posts.id"],
            name=op.f("fk_forum_reactions_post_id_forum_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_forum_reactions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forum_reactions")),
        sa.UniqueConstraint("post_id", "user_id", name="uq_forum_reactions_post_user"),
    )
    op.create_index("ix_forum_reactions_user_id", "forum_reactions", ["user_id"], unique=False)

    # --- gardens ---------------------------------------------------------
    op.add_column(
        "farms",
        sa.Column("placement", sa.String(length=16), server_default="outdoor", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_farms_placement"), "farms", "placement IN ('indoor', 'outdoor')"
    )

    # --- forum likes -----------------------------------------------------
    op.add_column(
        "forum_posts",
        sa.Column("like_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    # --- tracked plants --------------------------------------------------
    op.alter_column("plants", "archived_at", new_column_name="ended_at")
    op.drop_index(op.f("ix_plants_farm_archived"), table_name="plants")
    op.create_index("ix_plants_farm_ended", "plants", ["farm_id", "ended_at"], unique=False)
    op.add_column(
        "plants",
        sa.Column(
            "irrigation_schedule",
            sa.String(length=16),
            server_default="every_3_5_days",
            nullable=False,
        ),
    )
    op.add_column("plants", sa.Column("end_reason", sa.String(length=16), nullable=True))
    op.add_column("plants", sa.Column("end_note", sa.Text(), nullable=True))
    op.add_column("plants", sa.Column("final_result", sa.String(length=16), nullable=True))
    op.add_column(
        "plants", sa.Column("yield_percent", sa.Numeric(precision=6, scale=1), nullable=True)
    )
    op.execute("UPDATE plants SET end_reason = 'other' WHERE ended_at IS NOT NULL")
    for name, condition in PLANT_CHECKS.items():
        op.create_check_constraint(op.f(f"ck_plants_{name}"), "plants", condition)

    # --- scans -> detection list ----------------------------------------
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

    # --- users: email + username + full name -----------------------------
    op.alter_column("users", "display_name", new_column_name="full_name")
    op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    op.execute(
        "UPDATE users SET email = 'hp-' || regexp_replace(phone, '[^0-9]', '', 'g') "
        "|| '@ganti-email.tanami.local' WHERE email IS NULL"
    )
    op.execute("UPDATE users SET username = 'u' || substr(replace(id::text, '-', ''), 1, 12)")
    op.alter_column("users", "username", nullable=False)
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=254), nullable=False)
    op.drop_constraint(op.f("ck_users_email_or_phone"), "users", type_="check")
    op.drop_index(op.f("uq_users_phone"), table_name="users")
    op.drop_index(op.f("uq_users_email"), table_name="users")
    op.create_index("uq_users_email", "users", ["email"], unique=True)
    op.create_index("uq_users_username", "users", ["username"], unique=True)
    op.create_check_constraint(
        op.f("ck_users_username_format"), "users", "username ~ '^[a-z0-9_.]{3,32}$'"
    )
    op.drop_column("users", "phone")

    # --- reminders: care reminders (requirement 7) ------------------------
    op.drop_constraint(op.f("ck_reminders_type"), "reminders", type_="check")
    op.create_check_constraint(
        op.f("ck_reminders_type"), "reminders", f"type IN ({_in(NEW_REMINDER_TYPES)})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM reminders WHERE type IN ('watering', 'photo', 'monitoring')")
    op.drop_constraint(op.f("ck_reminders_type"), "reminders", type_="check")
    op.create_check_constraint(
        op.f("ck_reminders_type"), "reminders", f"type IN ({_in(OLD_REMINDER_TYPES)})"
    )

    op.add_column("users", sa.Column("phone", sa.VARCHAR(length=32), nullable=True))
    op.drop_constraint(op.f("ck_users_username_format"), "users", type_="check")
    op.drop_index("uq_users_username", table_name="users")
    op.drop_index("uq_users_email", table_name="users")
    op.create_index(
        "uq_users_email", "users", ["email"], unique=True, postgresql_where="email IS NOT NULL"
    )
    op.create_index(
        "uq_users_phone", "users", ["phone"], unique=True, postgresql_where="phone IS NOT NULL"
    )
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=254), nullable=True)
    op.create_check_constraint(
        op.f("ck_users_email_or_phone"),
        "users",
        "(email IS NOT NULL AND phone IS NULL) OR (email IS NULL AND phone IS NOT NULL)",
    )
    op.drop_column("users", "username")
    op.alter_column("users", "full_name", new_column_name="display_name")

    op.drop_constraint(
        op.f("fk_scans_detection_plant_id_detection_plants"), "scans", type_="foreignkey"
    )
    op.drop_index("ix_scans_detection_plant_captured", table_name="scans")
    op.drop_column("scans", "detection_plant_id")

    for name in PLANT_CHECKS:
        op.drop_constraint(op.f(f"ck_plants_{name}"), "plants", type_="check")
    for column in (
        "yield_percent",
        "final_result",
        "end_note",
        "end_reason",
        "irrigation_schedule",
    ):
        op.drop_column("plants", column)
    op.drop_index("ix_plants_farm_ended", table_name="plants")
    op.alter_column("plants", "ended_at", new_column_name="archived_at")
    op.create_index("ix_plants_farm_archived", "plants", ["farm_id", "archived_at"], unique=False)

    op.drop_column("forum_posts", "like_count")
    op.drop_constraint(op.f("ck_farms_placement"), "farms", type_="check")
    op.drop_column("farms", "placement")

    op.drop_index("ix_forum_reactions_user_id", table_name="forum_reactions")
    op.drop_table("forum_reactions")
    op.drop_index("ix_plant_photos_user_id", table_name="plant_photos")
    op.drop_index("ix_plant_photos_plant_taken", table_name="plant_photos")
    op.drop_table("plant_photos")
    op.drop_index("ix_detection_plants_user_ended", table_name="detection_plants")
    op.drop_index("ix_detection_plants_plant_id", table_name="detection_plants")
    op.drop_table("detection_plants")
    op.drop_index("ix_care_logs_plant_performed", table_name="care_logs")
    op.drop_index("ix_care_logs_plant_action", table_name="care_logs")
    op.drop_table("care_logs")
