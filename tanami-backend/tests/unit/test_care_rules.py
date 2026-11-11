"""Requirement 7 reminder rules and the requirement 1 harvest buckets."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from app.domain import HarvestOutcome, ReminderType, outcome_for_percent
from app.services.care_reminders import CareContext, build_care_reminders

TODAY = date(2026, 11, 8)
NOW = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)


def ctx(**overrides: object) -> CareContext:
    values: dict[str, object] = {
        "plant_id": uuid4(),
        "user_id": uuid4(),
        "farm_id": uuid4(),
        "label": "Tomat Pot 1",
        "irrigation_schedule": "daily",
        "tracking_started": TODAY - timedelta(days=1),
        "last_photo": TODAY,
        "last_activity": TODAY,
    }
    values.update(overrides)
    return CareContext(**values)  # type: ignore[arg-type]


def types(plant: CareContext) -> set[ReminderType]:
    return {item.type for item in build_care_reminders(plants=[plant], now=NOW, today=TODAY)}


@pytest.mark.parametrize(
    ("schedule", "days_since_watering", "expected"),
    [
        ("daily", 1, True),
        ("daily", 0, False),
        ("every_3_5_days", 2, False),
        ("every_3_5_days", 3, True),
        ("weekly", 6, False),
        ("weekly", 7, True),
        ("never", 30, False),
    ],
)
def test_watering_follows_irrigation_schedule(
    schedule: str, days_since_watering: int, expected: bool
) -> None:
    plant = ctx(
        irrigation_schedule=schedule,
        last_watered=TODAY - timedelta(days=days_since_watering),
    )
    assert (ReminderType.WATERING in types(plant)) is expected


def test_never_watered_counts_from_tracking_start() -> None:
    assert ReminderType.WATERING in types(ctx(tracking_started=TODAY - timedelta(days=1)))
    assert ReminderType.WATERING not in types(ctx(tracking_started=TODAY))


def test_photo_reminder_period_and_off_switch() -> None:
    stale = ctx(last_photo=TODAY - timedelta(days=7), irrigation_schedule="never")
    assert types(stale) == {ReminderType.PHOTO}
    assert ReminderType.PHOTO not in types(ctx(last_photo=TODAY - timedelta(days=6)))
    off = ctx(last_photo=None, photo_days=0, tracking_started=TODAY - timedelta(days=40))
    assert ReminderType.PHOTO not in types(off)


def test_monitoring_waits_for_inactivity_and_never_doubles_the_photo_reminder() -> None:
    idle = ctx(
        irrigation_schedule="never",
        photo_days=0,
        last_activity=TODAY - timedelta(days=9),
    )
    reminders = build_care_reminders(plants=[idle], now=NOW, today=TODAY)
    assert [item.type for item in reminders] == [ReminderType.MONITORING]
    assert "9 hari" in reminders[0].body
    both_due = ctx(
        irrigation_schedule="never",
        last_photo=TODAY - timedelta(days=9),
        last_activity=TODAY - timedelta(days=9),
    )
    assert types(both_due) == {ReminderType.PHOTO}


def test_dedupe_key_is_per_plant_and_day() -> None:
    plant = ctx(last_watered=TODAY - timedelta(days=2))
    item = build_care_reminders(plants=[plant], now=NOW, today=TODAY)[0]
    assert item.dedupe_key == f"watering:{plant.plant_id}:2026-11-08"


@pytest.mark.parametrize(
    ("percent", "outcome"),
    [
        (0, HarvestOutcome.FAILED),
        (19.9, HarvestOutcome.FAILED),
        (20, HarvestOutcome.SUBOPTIMAL),
        (69.9, HarvestOutcome.SUBOPTIMAL),
        (70, HarvestOutcome.NORMAL),
        (100, HarvestOutcome.NORMAL),
        (100.1, HarvestOutcome.BUMPER),
    ],
)
def test_harvest_outcome_buckets(percent: float, outcome: HarvestOutcome) -> None:
    assert outcome_for_percent(percent) is outcome
