"""Push delivery rules (design 12.4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.domain import PushState
from app.services.reminder import DeliveryPrefs, is_quiet_hour, push_decision

TZ = "Asia/Jakarta"
PREFS = DeliveryPrefs(disabled_types=frozenset(), quiet_start=21, quiet_end=5)


def at_wib(hour: int) -> datetime:
    # WIB = UTC+7
    return datetime(2026, 11, 7, (hour - 7) % 24, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("hour", "quiet"), [(20, False), (21, True), (23, True), (4, True), (5, False), (12, False)]
)
def test_quiet_window_wraps_midnight(hour: int, quiet: bool) -> None:
    assert is_quiet_hour(at_wib(hour), start=21, end=5, tz_name=TZ) is quiet


def test_quiet_window_same_start_end_is_off() -> None:
    assert not is_quiet_hour(at_wib(23), start=0, end=0, tz_name=TZ)


def decide(**overrides: object) -> PushState:
    values: dict[str, object] = {
        "priority": "normal",
        "reminder_type": "fungal_risk",
        "prefs": PREFS,
        "now": at_wib(12),
        "tz_name": TZ,
        "pushes_today": 0,
        "max_per_day": 3,
    }
    values.update(overrides)
    return push_decision(**values)  # type: ignore[arg-type]


def test_daytime_push_is_sent() -> None:
    assert decide() is PushState.SENT


def test_quiet_hours_defer_normal_but_not_high() -> None:
    assert decide(now=at_wib(22)) is PushState.PENDING
    assert decide(now=at_wib(22), priority="high") is PushState.SENT


def test_daily_cap_applies_to_every_priority() -> None:
    assert decide(pushes_today=3) is PushState.SKIPPED_CAP
    assert decide(pushes_today=3, priority="high") is PushState.SKIPPED_CAP


def test_disabled_type_is_never_pushed() -> None:
    prefs = DeliveryPrefs(disabled_types=frozenset({"fungal_risk"}), quiet_start=21, quiet_end=5)
    assert decide(prefs=prefs) is PushState.DISABLED


def test_user_quiet_hours_override_defaults() -> None:
    late_sleeper = DeliveryPrefs(disabled_types=frozenset(), quiet_start=23, quiet_end=7)
    assert decide(prefs=late_sleeper, now=at_wib(22)) is PushState.SENT
    assert decide(prefs=late_sleeper, now=at_wib(6)) is PushState.PENDING
