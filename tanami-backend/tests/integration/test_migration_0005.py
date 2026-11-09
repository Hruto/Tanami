"""Migration 0005 on a database that already holds v0.3 data.

The schema test proves a fresh database matches the models; this one proves the
rows a real database already has survive (or are removed on purpose) when it is
upgraded, and that the downgrade still runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]


def _config(sync_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", sync_url)
    return config


@pytest.fixture
def mig_db(database_url: str) -> Iterator[tuple[str, str]]:
    """A throwaway database next to the shared test one, created empty."""
    base = database_url.replace("+asyncpg", "").rsplit("/", 1)[0]
    name = f"tanami_mig_{uuid4().hex[:8]}"
    with psycopg.connect(base + "/postgres", autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    try:
        yield base + f"/{name}", base.replace("postgresql://", "postgresql+psycopg://") + f"/{name}"
    finally:
        with psycopg.connect(base + "/postgres", autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def _seed_v03(conninfo: str) -> dict[str, str]:
    ids = {key: str(uuid4()) for key in ("user", "farm", "p1", "p2", "p3", "p4", "p5")}
    with psycopg.connect(conninfo, autocommit=True) as db:
        db.execute(
            "INSERT INTO users (id, email, username, full_name, password_hash) "
            "VALUES (%s, 'a@example.com', 'budi', 'Budi', 'x')",
            (ids["user"],),
        )
        db.execute(
            "INSERT INTO farms (id, user_id, name, adm4_code) "
            "VALUES (%s, %s, 'Kebun', '31.71.03.1001')",
            (ids["farm"], ids["user"]),
        )
        plants = [
            # key, commodity, planted, ended reason, created offset (orders the codes)
            ("p1", "mango", "2021-08-01", None),
            ("p2", "mango", "2022-01-10", "harvested"),
            ("p3", "chili", "2026-09-01", None),
            ("p4", "strawberry", "2026-01-01", "died"),
            ("p5", "citrus", "2023-03-01", None),
        ]
        for index, (key, commodity, planted, reason) in enumerate(plants):
            db.execute(
                "INSERT INTO plants (id, farm_id, commodity_code, label, planted_at, "
                "growth_stage, ended_at, end_reason, created_at) VALUES "
                "(%s, %s, %s, %s, %s, 'fruiting', "
                "CASE WHEN %s::text IS NULL THEN NULL ELSE now() END, %s::text, "
                "now() + make_interval(secs => %s))",
                (ids[key], ids["farm"], commodity, key, planted, reason, reason, index),
            )
        db.execute(
            "INSERT INTO harvest_records (plant_id, harvested_at) VALUES (%s, now())", (ids["p2"],)
        )
        db.execute(
            "INSERT INTO detection_plants (user_id, name, plant_id) VALUES (%s, 'Cabai', %s)",
            (ids["user"], ids["p3"]),
        )
        for plant, scan_type in (("p1", "disease"), ("p1", "ripeness"), ("p3", "disease")):
            db.execute(
                "INSERT INTO scans (user_id, plant_id, scan_type, image_key, image_content_type, "
                "client_uuid, captured_at, status, model_version, result, quality) VALUES "
                "(%s, %s, %s, 'k', 'image/jpeg', %s, now(), 'unknown', 'v', '{}', '{}')",
                (ids["user"], ids[plant], scan_type, str(uuid4())),
            )
        db.execute(
            "INSERT INTO reminders (user_id, plant_id, type, title, body, dedupe_key) "
            "VALUES (%s, %s, 'harvest_soon', 't', 'b', 'k1')",
            (ids["user"], ids["p1"]),
        )
    return ids


def test_upgrade_converts_v03_rows_and_downgrade_runs(mig_db: tuple[str, str]) -> None:
    conninfo, sync_url = mig_db
    config = _config(sync_url)
    command.upgrade(config, "0004")
    ids = _seed_v03(conninfo)

    command.upgrade(config, "0005")

    with psycopg.connect(conninfo) as db:
        plants = {
            row[0]: row
            for row in db.execute(
                "SELECT label, code, commodity_code, planting_material, productive_until, "
                "end_reason, outcome, end_note, user_id FROM plants"
            )
        }
        assert set(plants) == {"p1", "p2", "p4", "p5"}, "chili plant must be removed"
        assert plants["p1"][1] == "MGA-001"
        assert plants["p2"][1] == "MGA-002"
        assert plants["p4"][1] == "STB-001"
        assert plants["p5"][1] == "JRK-001"
        assert plants["p1"][3] == "grafted"
        assert plants["p4"][3] == "runner"
        assert str(plants["p1"][4]) == "2061-08-01"
        assert str(plants["p5"][4]) == "2043-03-01"
        assert str(plants["p1"][8]) == ids["user"]

        # Old reasons are mapped and remembered in the note.
        assert (plants["p2"][5], plants["p2"][6]) == ("other", "ended_early")
        assert "harvested" in plants["p2"][7]
        assert (plants["p4"][5], plants["p4"][6]) == ("died_other", "failed")
        assert plants["p1"][5] is None and plants["p1"][6] is None

        assert db.execute("SELECT sequence FROM harvest_records").fetchall() == [(1,)]
        assert db.execute("SELECT plant_code_seq FROM users").fetchone() == (
            {"mango": 2, "strawberry": 1, "citrus": 1},
        )
        assert db.execute("SELECT count(*) FROM crop_profiles").fetchone() == (6,)
        # Only the leaf scan of a surviving plant is left.
        assert db.execute("SELECT scan_type FROM scans").fetchall() == [("disease",)]
        assert db.execute("SELECT count(*) FROM reminders").fetchone() == (0,)
        assert db.execute("SELECT to_regclass('detection_plants')").fetchone() == (None,)

    command.downgrade(config, "0004")
    with psycopg.connect(conninfo) as db:
        assert db.execute("SELECT to_regclass('detection_plants')").fetchone() is not None
        assert db.execute("SELECT to_regclass('crop_profiles')").fetchone() == (None,)
        reasons = {
            row[0] for row in db.execute("SELECT end_reason FROM plants WHERE ended_at IS NOT NULL")
        }
        assert reasons <= {"harvested", "died", "not_maintained", "other"}

    command.upgrade(config, "head")
