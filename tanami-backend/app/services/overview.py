"""Aggregate numbers for the staff dashboard home.

Every figure is one grouped SQL query; nothing loads rows into Python. Days are
counted in the service timezone (``TANAMI_TIMEZONE``) so "today" on the chart is
the farmer's today, not UTC's.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import DISEASE_LABELS, FeedbackValue, ScanType, TrackingOutcome, UserRole
from app.models.farm import Plant
from app.models.forum import ForumReport
from app.models.scan import Scan, ScanFeedback
from app.models.user import User
from app.schemas.admin import (
    AdminOverviewOut,
    DailyScans,
    DetectionCounts,
    DiseaseCount,
    QueueCounts,
    TrackingCounts,
    UserCounts,
)

CHART_DAYS = 14
TOP_DISEASES = 5


class OverviewService:
    def __init__(self, session: AsyncSession, timezone: str) -> None:
        self.session = session
        self.timezone = timezone

    async def build(self, *, now: datetime | None = None) -> AdminOverviewOut:
        moment = now or datetime.now(UTC)
        return AdminOverviewOut(
            generated_at=moment,
            timezone=self.timezone,
            users=await self._users(moment),
            tracking=await self._tracking(),
            detection=await self._detection(moment),
            queues=await self._queues(),
            scans_daily=await self._scans_daily(moment),
            scan_status_30d=await self._scan_status(moment),
            top_diseases_30d=await self._top_diseases(moment),
        )

    async def _users(self, moment: datetime) -> UserCounts:
        active = User.deleted_at.is_(None)
        totals = (
            await self.session.execute(
                select(
                    func.count().filter(active),
                    func.count().filter(active, User.created_at >= moment - timedelta(days=7)),
                    func.count().filter(User.deleted_at.is_not(None)),
                )
            )
        ).one()
        by_role = {role.value: 0 for role in UserRole}
        rows = await self.session.execute(
            select(User.role, func.count()).where(active).group_by(User.role)
        )
        by_role.update(dict(rows.tuples().all()))
        return UserCounts(
            total=totals[0], new_7d=totals[1], pending_deletion=totals[2], by_role=by_role
        )

    async def _tracking(self) -> TrackingCounts:
        counts = (
            await self.session.execute(
                select(
                    func.count().filter(Plant.ended_at.is_(None)),
                    func.count().filter(Plant.ended_at.is_not(None)),
                )
            )
        ).one()
        outcomes = {member.value: 0 for member in TrackingOutcome}
        rows = await self.session.execute(
            select(Plant.outcome, func.count())
            .where(Plant.outcome.is_not(None))
            .group_by(Plant.outcome)
        )
        outcomes.update({str(result): count for result, count in rows.tuples()})
        return TrackingCounts(active_plants=counts[0], ended_plants=counts[1], outcomes=outcomes)

    async def _detection(self, moment: datetime) -> DetectionCounts:
        scans = (
            await self.session.execute(
                select(
                    func.count(),
                    func.count().filter(Scan.created_at >= moment - timedelta(days=7)),
                ).select_from(Scan)
            )
        ).one()
        return DetectionCounts(scans_total=scans[0], scans_7d=scans[1])

    async def _queues(self) -> QueueCounts:
        reports = await self.session.scalar(
            select(func.count(func.distinct(ForumReport.target_id))).where(
                ForumReport.resolved_at.is_(None)
            )
        )
        feedback = await self.session.scalar(
            select(func.count())
            .select_from(ScanFeedback)
            .where(
                ScanFeedback.value == FeedbackValue.INCORRECT.value,
                ScanFeedback.reviewed_at.is_(None),
            )
        )
        return QueueCounts(open_reports=reports or 0, feedback_pending=feedback or 0)

    async def _scans_daily(self, moment: datetime) -> list[DailyScans]:
        tz = ZoneInfo(self.timezone)
        today = moment.astimezone(tz).date()
        first = today - timedelta(days=CHART_DAYS - 1)
        start = datetime.combine(first, datetime.min.time(), tzinfo=tz)
        # The offset is passed as an interval rather than the zone name, so the
        # query does not depend on the database server's tz database. Exact for
        # Indonesian zones (no DST); a DST zone would be off for one hour on the
        # switch day, which is acceptable for a 14-day trend chart.
        offset = moment.astimezone(tz).utcoffset() or timedelta(0)
        local_day = func.date(func.timezone(offset, Scan.created_at))
        rows = await self.session.execute(
            select(local_day, Scan.scan_type, func.count())
            .where(Scan.created_at >= start)
            .group_by(local_day, Scan.scan_type)
        )
        counts: dict[tuple[date, str], int] = {
            (day, scan_type): count for day, scan_type, count in rows.tuples()
        }
        return [
            DailyScans(
                day=day,
                disease=counts.get((day, ScanType.DISEASE.value), 0),
                ripeness=counts.get((day, ScanType.RIPENESS.value), 0),
            )
            for day in (first + timedelta(days=offset) for offset in range(CHART_DAYS))
        ]

    async def _scan_status(self, moment: datetime) -> dict[str, int]:
        rows = await self.session.execute(
            select(Scan.status, func.count())
            .where(Scan.created_at >= moment - timedelta(days=30))
            .group_by(Scan.status)
        )
        return dict(rows.tuples().all())

    async def _top_diseases(self, moment: datetime) -> list[DiseaseCount]:
        total = func.count().label("total")
        rows = await self.session.execute(
            select(Scan.disease_code, total)
            .where(
                Scan.created_at >= moment - timedelta(days=30),
                Scan.scan_type == ScanType.DISEASE.value,
                Scan.disease_code.is_not(None),
                Scan.disease_code != "healthy",
            )
            .group_by(Scan.disease_code)
            .order_by(total.desc(), Scan.disease_code)
            .limit(TOP_DISEASES)
        )
        return [
            DiseaseCount(code=str(code), name=DISEASE_LABELS.get(str(code), str(code)), count=n)
            for code, n in rows.tuples()
        ]
