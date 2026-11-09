"""Harvest estimate, disease delay and tracking outcome (design 8.3-8.6).

Everything here is a pure function over plain values: no database, no clock,
no settings. Services load the rows, call these, and the unit tests pin every
rule in design 8.4-8.6 without PostgreSQL.

The estimate is rule-based on purpose. There is no dataset that maps "planted
on" to "harvested on", so it is computed from an agronomic crop profile and is
always a *range* labelled as an estimate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain import LifecyclePhase, TrackingEndReason, TrackingOutcome

DEFAULT_MAX_DELAY_DAYS_PER_CYCLE = 60


@dataclass(frozen=True)
class CropProfile:
    """Agronomic numbers for one commodity + planting material (design 8.3)."""

    first_harvest_min_days: int
    first_harvest_max_days: int
    harvest_cycle_min_days: int
    harvest_cycle_max_days: int
    productive_years: int


@dataclass(frozen=True)
class EpisodeSpan:
    """The part of a disease episode the estimate needs."""

    episode_id: str
    disease_code: str
    opened_on: date
    resolved_on: date | None
    delay_days: int


@dataclass(frozen=True)
class DelayItem:
    episode_id: str
    disease_code: str
    days: int
    is_open: bool


@dataclass(frozen=True)
class NextHarvest:
    base_start: date
    base_end: date
    delay_days: int
    start: date
    end: date
    delays: tuple[DelayItem, ...]
    is_overdue: bool
    delay_capped: bool


def productive_until(planted_at: date, years: int) -> date:
    """End of the productive period: ``planted_at`` plus calendar years."""
    try:
        return planted_at.replace(year=planted_at.year + years)
    except ValueError:  # 29 Feb planted, target year is not a leap year
        return planted_at.replace(year=planted_at.year + years, day=28)


def age_days(planted_at: date, today: date, *, ended_on: date | None = None) -> int:
    return max(((ended_on or today) - planted_at).days, 0)


def lifecycle_phase(
    planted_at: date, today: date, harvest_count: int, profile: CropProfile
) -> LifecyclePhase:
    """``productive`` once harvested, or once old enough to be expected to fruit."""
    if harvest_count > 0 or age_days(planted_at, today) >= profile.first_harvest_min_days:
        return LifecyclePhase.PRODUCTIVE
    return LifecyclePhase.JUVENILE


def cycle_start(planted_at: date, last_harvest: date | None) -> date:
    """A cycle starts at the last harvest, or at planting before the first one."""
    return last_harvest or planted_at


def counted_delays(
    episodes: Sequence[EpisodeSpan],
    *,
    cycle_start_on: date,
    max_delay_days: int = DEFAULT_MAX_DELAY_DAYS_PER_CYCLE,
) -> tuple[int, tuple[DelayItem, ...], bool]:
    """Delay that the current cycle carries, per design 8.5.

    An episode counts for the cycle when it was still open at some point in it:
    opened during the cycle, or opened earlier and not resolved before the cycle
    began. Each episode counts **once** with the days copied when it opened, so
    scanning the same leaf five times can never add up to five delays. Closing
    an episode never gives days back for the running cycle. The total is capped.
    """
    items = tuple(
        DelayItem(
            episode_id=episode.episode_id,
            disease_code=episode.disease_code,
            days=episode.delay_days,
            is_open=episode.resolved_on is None,
        )
        for episode in episodes
        if episode.delay_days > 0
        and (episode.resolved_on is None or episode.resolved_on >= cycle_start_on)
    )
    total = sum(item.days for item in items)
    capped = total > max_delay_days
    return min(total, max_delay_days), items, capped


def next_harvest(
    *,
    planted_at: date,
    harvest_dates: Sequence[date],
    episodes: Sequence[EpisodeSpan],
    profile: CropProfile,
    today: date,
    max_delay_days: int = DEFAULT_MAX_DELAY_DAYS_PER_CYCLE,
) -> NextHarvest | None:
    """The estimated window of the next harvest, or ``None`` past the productive end."""
    last = max(harvest_dates) if harvest_dates else None
    start_of_cycle = cycle_start(planted_at, last)
    if last is None:
        base_start = planted_at + timedelta(days=profile.first_harvest_min_days)
        base_end = planted_at + timedelta(days=profile.first_harvest_max_days)
    else:
        base_start = last + timedelta(days=profile.harvest_cycle_min_days)
        base_end = last + timedelta(days=profile.harvest_cycle_max_days)

    delay, items, capped = counted_delays(
        episodes, cycle_start_on=start_of_cycle, max_delay_days=max_delay_days
    )
    start = base_start + timedelta(days=delay)
    end = base_end + timedelta(days=delay)

    last_day = productive_until(planted_at, profile.productive_years)
    if start > last_day:
        return None
    end = min(end, last_day)
    return NextHarvest(
        base_start=base_start,
        base_end=base_end,
        delay_days=delay,
        start=start,
        end=end,
        delays=items,
        is_overdue=today > end,
        delay_capped=capped,
    )


def delay_preview_days(
    *,
    disease_delay_days: int,
    episodes: Sequence[EpisodeSpan],
    disease_code: str,
    cycle_start_on: date,
    max_delay_days: int = DEFAULT_MAX_DELAY_DAYS_PER_CYCLE,
) -> int:
    """Days a confirmation would add right now (0 when it adds nothing).

    Zero when the disease already has an episode counted in this cycle, or when
    the cap is already reached; otherwise what is left under the cap.
    """
    current, items, _ = counted_delays(
        episodes, cycle_start_on=cycle_start_on, max_delay_days=max_delay_days
    )
    if any(item.disease_code == disease_code for item in items):
        return 0
    return max(min(disease_delay_days, max_delay_days - current), 0)


def tracking_outcome(end_reason: str, harvest_count: int) -> TrackingOutcome:
    """Status akhir (design 8.6)."""
    if end_reason == TrackingEndReason.PRODUCTIVE_PERIOD_OVER:
        return TrackingOutcome.COMPLETED
    return TrackingOutcome.ENDED_EARLY if harvest_count >= 1 else TrackingOutcome.FAILED


def end_request_error(
    *,
    reason: str,
    disease_codes: Sequence[str],
    cause_note: str | None,
    note: str | None,
) -> str | None:
    """Why a client's end-tracking request is invalid, or ``None`` (design 8.6)."""
    if reason == TrackingEndReason.PRODUCTIVE_PERIOD_OVER:
        return "Alasan ini hanya dipakai sistem."
    if reason == TrackingEndReason.DISEASE:
        if not disease_codes and not (cause_note or "").strip():
            return "Pilih penyakitnya atau tulis keterangannya."
    elif reason == TrackingEndReason.OTHER and not (note or "").strip():
        return "Tulis catatan untuk alasan lainnya."
    return None


def harvest_date_error(
    harvested_on: date, *, planted_at: date, today: date, previous: date | None
) -> str | None:
    """Why a harvest date is not allowed, or ``None`` (design 8.4)."""
    if harvested_on < planted_at:
        return "Tanggal panen tidak boleh sebelum tanggal tanam."
    if harvested_on > today:
        return "Tanggal panen tidak boleh di masa depan."
    if previous is not None and harvested_on < previous:
        return "Tanggal panen tidak boleh sebelum panen sebelumnya."
    return None
