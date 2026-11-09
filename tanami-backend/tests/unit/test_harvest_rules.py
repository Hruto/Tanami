"""Harvest estimate, disease delay and outcome rules (design 8.4-8.6)."""

from __future__ import annotations

from datetime import date

import pytest
from app.domain import LifecyclePhase, TrackingEndReason, TrackingOutcome
from app.services.harvest import (
    CropProfile,
    EpisodeSpan,
    age_days,
    counted_delays,
    delay_preview_days,
    end_request_error,
    harvest_date_error,
    lifecycle_phase,
    next_harvest,
    productive_until,
    tracking_outcome,
)

MANGO = CropProfile(
    first_harvest_min_days=1095,
    first_harvest_max_days=1460,
    harvest_cycle_min_days=330,
    harvest_cycle_max_days=400,
    productive_years=40,
)
STRAWBERRY = CropProfile(60, 90, 3, 7, 2)


def episode(
    code: str = "mango_anthracnose",
    *,
    opened: date = date(2026, 10, 1),
    resolved: date | None = None,
    days: int = 14,
    ident: str = "e1",
) -> EpisodeSpan:
    return EpisodeSpan(ident, code, opened, resolved, days)


# --- productive end, age, phase ------------------------------------------------


def test_productive_until_adds_calendar_years() -> None:
    assert productive_until(date(2021, 8, 1), 40) == date(2061, 8, 1)


def test_productive_until_handles_leap_day() -> None:
    assert productive_until(date(2024, 2, 29), 2) == date(2026, 2, 28)


def test_age_days_stops_at_the_end_date() -> None:
    planted = date(2026, 1, 1)
    assert age_days(planted, date(2026, 1, 11)) == 10
    assert age_days(planted, date(2026, 6, 1), ended_on=date(2026, 1, 31)) == 30
    assert age_days(planted, date(2025, 12, 1)) == 0


@pytest.mark.parametrize(
    ("today", "harvests", "expected"),
    [
        (date(2026, 11, 9), 0, LifecyclePhase.JUVENILE),
        (date(2028, 12, 1), 0, LifecyclePhase.PRODUCTIVE),  # old enough, never logged
        (date(2026, 11, 9), 1, LifecyclePhase.PRODUCTIVE),  # harvested early
    ],
)
def test_lifecycle_phase(today: date, harvests: int, expected: LifecyclePhase) -> None:
    assert lifecycle_phase(date(2025, 11, 1), today, harvests, MANGO) == expected


# --- the estimate --------------------------------------------------------------


def test_first_harvest_window_comes_from_planting() -> None:
    result = next_harvest(
        planted_at=date(2025, 11, 1),
        harvest_dates=[],
        episodes=[],
        profile=MANGO,
        today=date(2026, 11, 9),
    )
    assert result is not None
    assert result.start == date(2028, 10, 31)  # 1095 days after 2025-11-01
    assert (result.end - result.start).days == 1460 - 1095
    assert result.delay_days == 0
    assert not result.is_overdue


def test_next_window_counts_from_the_last_harvest() -> None:
    result = next_harvest(
        planted_at=date(2021, 8, 1),
        harvest_dates=[date(2024, 12, 5), date(2025, 12, 10)],
        episodes=[],
        profile=MANGO,
        today=date(2026, 11, 9),
    )
    assert result is not None
    assert (result.base_start, result.base_end) == (date(2026, 11, 5), date(2027, 1, 14))
    assert (result.start, result.end) == (result.base_start, result.base_end)


def test_design_example_anthracnose_pushes_the_window_14_days() -> None:
    result = next_harvest(
        planted_at=date(2021, 8, 1),
        harvest_dates=[date(2025, 12, 10)],
        episodes=[episode(opened=date(2026, 11, 2), days=14)],
        profile=MANGO,
        today=date(2026, 11, 9),
    )
    assert result is not None
    assert (result.start, result.end) == (date(2026, 11, 19), date(2027, 1, 28))
    assert result.delay_days == 14
    assert [(d.disease_code, d.days, d.is_open) for d in result.delays] == [
        ("mango_anthracnose", 14, True)
    ]


def test_one_episode_counts_once_however_often_it_is_rescanned() -> None:
    """Re-confirming the same disease attaches to the open episode, so there is
    still exactly one episode and one delay (design 8.5)."""
    result = next_harvest(
        planted_at=date(2021, 8, 1),
        harvest_dates=[date(2025, 12, 10)],
        episodes=[episode(days=14)],
        profile=MANGO,
        today=date(2026, 11, 9),
    )
    assert result is not None
    assert result.delay_days == 14


def test_different_diseases_add_up() -> None:
    episodes = [
        episode("mango_anthracnose", days=14, ident="a"),
        episode("mango_sooty_mould", days=7, ident="b"),
    ]
    total, items, capped = counted_delays(episodes, cycle_start_on=date(2025, 12, 10))
    assert (total, len(items), capped) == (21, 2, False)


def test_total_delay_is_capped() -> None:
    episodes = [
        episode("mango_die_back", days=21, ident="a"),
        episode("mango_anthracnose", days=14, ident="b"),
        episode("mango_powdery_mildew", days=14, ident="c"),
        episode("mango_sooty_mould", days=14, ident="d"),
    ]
    total, _, capped = counted_delays(episodes, cycle_start_on=date(2025, 12, 10))
    assert total == 60
    assert capped


def test_cap_is_configurable() -> None:
    total, _, capped = counted_delays(
        [episode(days=14)], cycle_start_on=date(2025, 12, 10), max_delay_days=10
    )
    assert (total, capped) == (10, True)


def test_episode_resolved_before_the_cycle_started_is_ignored() -> None:
    old = episode(opened=date(2025, 3, 1), resolved=date(2025, 4, 1))
    total, items, _ = counted_delays([old], cycle_start_on=date(2025, 12, 10))
    assert (total, items) == (0, ())


def test_episode_still_open_when_the_cycle_began_still_counts() -> None:
    carried = episode(opened=date(2025, 11, 20))
    total, _, _ = counted_delays([carried], cycle_start_on=date(2025, 12, 10))
    assert total == 14


def test_resolving_an_episode_inside_the_cycle_does_not_give_days_back() -> None:
    healed = episode(opened=date(2026, 3, 1), resolved=date(2026, 3, 20))
    total, items, _ = counted_delays([healed], cycle_start_on=date(2025, 12, 10))
    assert total == 14
    assert items[0].is_open is False


def test_a_new_harvest_resets_the_delay() -> None:
    result = next_harvest(
        planted_at=date(2021, 8, 1),
        harvest_dates=[date(2025, 12, 10), date(2026, 11, 30)],
        episodes=[episode(opened=date(2026, 6, 1), resolved=date(2026, 7, 1))],
        profile=MANGO,
        today=date(2026, 12, 1),
    )
    assert result is not None
    assert result.delay_days == 0


def test_zero_day_episodes_are_not_listed() -> None:
    total, items, _ = counted_delays([episode(days=0)], cycle_start_on=date(2025, 1, 1))
    assert (total, items) == (0, ())


def test_overdue_when_today_is_past_the_window() -> None:
    result = next_harvest(
        planted_at=date(2021, 8, 1),
        harvest_dates=[date(2024, 12, 10)],
        episodes=[],
        profile=MANGO,
        today=date(2026, 6, 1),
    )
    assert result is not None
    assert result.is_overdue


def test_window_is_clipped_at_the_end_of_the_productive_period() -> None:
    planted = date(2025, 1, 15)  # strawberry: productive until 2027-01-15
    result = next_harvest(
        planted_at=planted,
        harvest_dates=[date(2027, 1, 12)],
        episodes=[],
        profile=STRAWBERRY,
        today=date(2027, 1, 13),
    )
    assert result is not None
    assert result.end == date(2027, 1, 15)


def test_no_estimate_once_the_window_starts_after_the_productive_end() -> None:
    result = next_harvest(
        planted_at=date(2025, 1, 15),
        harvest_dates=[date(2027, 1, 14)],
        episodes=[],
        profile=STRAWBERRY,
        today=date(2027, 1, 14),
    )
    assert result is None


# --- delay preview for the confirmation card -------------------------------------


def test_preview_is_the_disease_delay_when_nothing_is_counted_yet() -> None:
    assert (
        delay_preview_days(
            disease_delay_days=14,
            episodes=[],
            disease_code="mango_anthracnose",
            cycle_start_on=date(2025, 12, 10),
        )
        == 14
    )


def test_preview_is_zero_when_the_disease_already_counts() -> None:
    assert (
        delay_preview_days(
            disease_delay_days=14,
            episodes=[episode()],
            disease_code="mango_anthracnose",
            cycle_start_on=date(2025, 12, 10),
        )
        == 0
    )


def test_preview_is_limited_by_what_is_left_under_the_cap() -> None:
    episodes = [episode("mango_die_back", days=21, ident="a")] * 1 + [
        episode("mango_sooty_mould", days=21, ident="b"),
        episode("mango_powdery_mildew", days=14, ident="c"),
    ]
    assert (
        delay_preview_days(
            disease_delay_days=14,
            episodes=episodes,
            disease_code="mango_anthracnose",
            cycle_start_on=date(2025, 12, 10),
        )
        == 4
    )


# --- outcome and request validation ----------------------------------------------


@pytest.mark.parametrize(
    ("reason", "harvests", "expected"),
    [
        (TrackingEndReason.PRODUCTIVE_PERIOD_OVER, 0, TrackingOutcome.COMPLETED),
        (TrackingEndReason.PRODUCTIVE_PERIOD_OVER, 12, TrackingOutcome.COMPLETED),
        (TrackingEndReason.CUT_DOWN, 10, TrackingOutcome.ENDED_EARLY),
        (TrackingEndReason.DISEASE, 1, TrackingOutcome.ENDED_EARLY),
        (TrackingEndReason.DISEASE, 0, TrackingOutcome.FAILED),
        (TrackingEndReason.DIED_OTHER, 0, TrackingOutcome.FAILED),
    ],
)
def test_outcome(reason: TrackingEndReason, harvests: int, expected: TrackingOutcome) -> None:
    assert tracking_outcome(reason, harvests) == expected


def test_clients_cannot_end_with_the_system_reason() -> None:
    assert end_request_error(
        reason=TrackingEndReason.PRODUCTIVE_PERIOD_OVER,
        disease_codes=[],
        cause_note=None,
        note=None,
    )


def test_disease_end_needs_a_disease_or_a_note() -> None:
    kwargs = {"reason": TrackingEndReason.DISEASE, "note": None}
    assert end_request_error(disease_codes=[], cause_note=None, **kwargs)
    assert end_request_error(disease_codes=[], cause_note="   ", **kwargs)
    assert end_request_error(disease_codes=["citrus_greening"], cause_note=None, **kwargs) is None
    assert end_request_error(disease_codes=[], cause_note="Daun menguning", **kwargs) is None


def test_other_end_needs_a_note() -> None:
    kwargs = {"reason": TrackingEndReason.OTHER, "disease_codes": [], "cause_note": None}
    assert end_request_error(note=None, **kwargs)
    assert end_request_error(note="Lahan dijual", **kwargs) is None


@pytest.mark.parametrize("reason", [TrackingEndReason.CUT_DOWN, TrackingEndReason.DIED_OTHER])
def test_cut_down_and_died_other_need_nothing(reason: TrackingEndReason) -> None:
    assert end_request_error(reason=reason, disease_codes=[], cause_note=None, note=None) is None


def test_harvest_date_rules() -> None:
    kwargs = {"planted_at": date(2025, 1, 1), "today": date(2026, 11, 9)}
    assert harvest_date_error(date(2024, 12, 31), previous=None, **kwargs)
    assert harvest_date_error(date(2026, 11, 10), previous=None, **kwargs)
    assert harvest_date_error(date(2026, 3, 1), previous=date(2026, 5, 1), **kwargs)
    assert harvest_date_error(date(2026, 5, 1), previous=date(2026, 5, 1), **kwargs) is None
    assert harvest_date_error(date(2026, 11, 9), previous=None, **kwargs) is None
