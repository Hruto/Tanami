"""Scheduled work (``design.md`` 12.2).

The scheduler is deliberately a thin wrapper: every job is a plain async
function over an ``AppState``, so a test can call ``run_weather_refresh``
directly without starting APScheduler.

Schedule (``TANAMI_TIMEZONE``, Asia/Jakarta by default):

``fetch_weather``       06:00 and 18:00, for every village with an active farm
``generate_reminders``  06:15 and 18:15, right after each weather fetch
``care_reminders``      daily at 06:30, watering/photo/monitoring (requirement 7)
``scan_followup``       daily at 07:00
``dispatch_pushes``     every hour at :05, sends pushes deferred by quiet hours
``expire_reminders``    daily at 00:15, marking stale reminders dismissed
``decay_health``        daily at 00:30, plants without a leaf scan -> unknown
``purge_accounts``      daily at 03:00, removes accounts deleted long enough ago

Only one replica runs the scheduler (``TANAMI_JOBS_ENABLED``); a second copy
would double the BMKG calls and the pushes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import JOB_RUNS
from app.core.state import AppState
from app.domain import Placement
from app.models.farm import Farm
from app.services.care_reminders import build_care_reminders, load_care_contexts
from app.services.maintenance import decay_stale_health, purge_deleted_accounts
from app.services.reminder import (
    ReminderService,
    build_scan_followups,
    build_weather_reminders,
    load_plant_contexts,
)
from app.services.weather import WeatherService

logger = get_logger("jobs")


async def run_weather_refresh(state: AppState) -> dict[str, int]:
    """Fetch and archive the forecast for every village with an active farm.

    Calls are spaced by ``bmkg_min_interval_seconds`` to stay under the BMKG
    limit of 60 requests per minute per IP (design 12.1).
    """
    fetched = 0
    failed = 0
    async with state.session_factory() as session:
        weather = WeatherService(session, state.redis, state.settings, state.weather)
        codes = await weather.active_adm4_codes()
        for index, code in enumerate(codes):
            if index and state.settings.bmkg_min_interval_seconds:
                await asyncio.sleep(state.settings.bmkg_min_interval_seconds)
            try:
                await weather.refresh(code)
                fetched += 1
            except Exception as exc:
                failed += 1
                await session.rollback()
                logger.warning("weather_fetch_failed", adm4_code=code, error=str(exc))

    JOB_RUNS.labels(job="fetch_weather", result="ok" if failed == 0 else "partial").inc()
    logger.info("weather_refresh_done", villages=len(codes), fetched=fetched, failed=failed)
    return {"villages": len(codes), "fetched": fetched, "failed": failed}


async def run_reminder_generation(
    state: AppState, *, now: datetime | None = None
) -> dict[str, int]:
    """Build weather reminders per village, then dispatch what is due.

    The rules read the forecast for the village of each farm. A village without
    any forecast (not even a stale one) is skipped; the next run picks it up.
    """
    moment = now or datetime.now(UTC)
    created_total = 0
    pushed_total = 0

    async with state.session_factory() as session:
        weather = WeatherService(session, state.redis, state.settings, state.weather)
        service = ReminderService(session, state.settings, state.push)
        today = service.today(moment)

        for code in await weather.active_adm4_codes():
            try:
                forecast = await weather.for_adm4(code)
            except Exception as exc:
                await session.rollback()
                logger.warning("reminder_weather_missing", adm4_code=code, error=str(exc))
                continue

            contexts = await load_plant_contexts(
                session,
                thresholds=service.thresholds,
                now=moment,
                farm_ids=await _farm_ids_for_village(session, code),
            )
            if not contexts:
                continue
            candidates = build_weather_reminders(
                plants=contexts,
                forecast=forecast,
                thresholds=service.thresholds,
                now=moment,
                today=today,
            )
            created = await service.persist(candidates)
            created_total += len(created)
            pushed_total += await service.dispatch_pushes(created, now=moment)

    JOB_RUNS.labels(job="generate_reminders", result="ok").inc()
    logger.info("reminders_generated", created=created_total, pushed=pushed_total)
    return {"created": created_total, "pushed": pushed_total}


async def run_scan_followup(state: AppState, *, now: datetime | None = None) -> int:
    """The ``scan_followup`` rule, daily (design 12.2)."""
    moment = now or datetime.now(UTC)
    async with state.session_factory() as session:
        service = ReminderService(session, state.settings, state.push)
        contexts = await load_plant_contexts(session, thresholds=service.thresholds, now=moment)
        candidates = build_scan_followups(
            plants=contexts,
            followup_days=state.settings.scan_followup_days,
            now=moment,
            today=service.today(moment),
        )
        created = await service.persist(candidates)
        pushed = await service.dispatch_pushes(created, now=moment)

    JOB_RUNS.labels(job="scan_followup", result="ok").inc()
    logger.info("scan_followup_done", created=len(created), pushed=pushed)
    return len(created)


async def run_care_reminders(state: AppState, *, now: datetime | None = None) -> int:
    """Watering, photo and monitoring reminders for tracked plants (requirement 7)."""
    moment = now or datetime.now(UTC)
    async with state.session_factory() as session:
        service = ReminderService(session, state.settings, state.push)
        contexts = await load_care_contexts(session, tz_name=state.settings.timezone)
        candidates = build_care_reminders(plants=contexts, now=moment, today=service.today(moment))
        created = await service.persist(candidates)
        await service.dispatch_pushes(created, now=moment)
    JOB_RUNS.labels(job="care_reminders", result="ok").inc()
    logger.info("care_reminders_done", created=len(created))
    return len(created)


async def run_push_dispatch(state: AppState, *, now: datetime | None = None) -> int:
    """Send pushes that quiet hours deferred (design 12.4: ditunda, not dropped)."""
    async with state.session_factory() as session:
        service = ReminderService(session, state.settings, state.push)
        pushed = await service.dispatch_pending(now=now)
    JOB_RUNS.labels(job="dispatch_pushes", result="ok").inc()
    return pushed


async def run_reminder_expiry(state: AppState, *, now: datetime | None = None) -> int:
    async with state.session_factory() as session:
        expired = await ReminderService(session, state.settings, state.push).expire_stale(now)
    JOB_RUNS.labels(job="expire_reminders", result="ok").inc()
    return expired


async def run_health_decay(state: AppState, *, now: datetime | None = None) -> int:
    async with state.session_factory() as session:
        changed = await decay_stale_health(
            session,
            now=now or datetime.now(UTC),
            stale_days=state.settings.plant_status_stale_days,
        )
    JOB_RUNS.labels(job="decay_health", result="ok").inc()
    return changed


async def run_account_purge(state: AppState, *, now: datetime | None = None) -> int:
    async with state.session_factory() as session:
        purged = await purge_deleted_accounts(
            session,
            state.storage,
            now=now or datetime.now(UTC),
            after_days=state.settings.account_purge_days,
        )
    JOB_RUNS.labels(job="purge_accounts", result="ok").inc()
    return purged


async def _farm_ids_for_village(session: AsyncSession, adm4_code: str) -> list[UUID]:
    rows = (
        await session.execute(
            # Weather rules make no sense for an indoor garden (requirement 0).
            select(Farm.id).where(
                Farm.adm4_code == adm4_code,
                Farm.archived_at.is_(None),
                Farm.placement == Placement.OUTDOOR.value,
            )
        )
    ).scalars()
    return list(rows)


def _guarded(job: Callable[[AppState], Awaitable[Any]], name: str) -> Callable[..., Any]:
    """A job failure is logged and counted; it never kills the scheduler."""

    async def runner(state: AppState) -> None:
        try:
            await job(state)
        except Exception:
            JOB_RUNS.labels(job=name, result="error").inc()
            logger.exception("job_failed", job=name)

    return runner


JOBS: tuple[tuple[str, Callable[[AppState], Awaitable[Any]], dict[str, int]], ...] = (
    ("fetch_weather_morning", run_weather_refresh, {"hour": 6, "minute": 0}),
    ("fetch_weather_evening", run_weather_refresh, {"hour": 18, "minute": 0}),
    ("generate_reminders_morning", run_reminder_generation, {"hour": 6, "minute": 15}),
    ("generate_reminders_evening", run_reminder_generation, {"hour": 18, "minute": 15}),
    ("care_reminders", run_care_reminders, {"hour": 6, "minute": 30}),
    ("scan_followup", run_scan_followup, {"hour": 7, "minute": 0}),
    ("dispatch_pushes", run_push_dispatch, {"minute": 5}),
    ("expire_reminders", run_reminder_expiry, {"hour": 0, "minute": 15}),
    ("decay_health", run_health_decay, {"hour": 0, "minute": 30}),
    ("purge_accounts", run_account_purge, {"hour": 3, "minute": 0}),
)


def build_scheduler(state: AppState) -> AsyncIOScheduler:
    tz = ZoneInfo(state.settings.timezone)
    scheduler = AsyncIOScheduler(timezone=tz)
    for job_id, job, cron in JOBS:
        scheduler.add_job(
            _guarded(job, job_id),
            trigger=CronTrigger(timezone=tz, **cron),
            args=[state],
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=600,
        )
    return scheduler
