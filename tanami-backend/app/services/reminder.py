"""Reminder rule engine and delivery.

The rules are the table in ``design.md`` 12.3 and the delivery rules are
12.4. The rules are pure functions over forecast + plant data so they can be
unit-tested without a database (TQA 7 asks for >= 85% on this module).

Values marked [USULAN] in the document live in ``ReminderThresholds`` so tuning
them is a config change, not a code change (design 12.5).

Dates are *local* (``TANAMI_TIMEZONE``, WIB by default): "today", the dedupe
key and the daily push cap all follow the calendar day of the farmer, not UTC.
A 06:15 WIB run is 23:15 UTC of the previous day, so a UTC date would let the
morning and evening runs of the same local day create the same reminder twice.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound, ValidationError
from app.core.logging import get_logger
from app.core.metrics import REMINDERS_CREATED
from app.domain import (
    GrowthStage,
    HealthStatus,
    PushState,
    ReminderPriority,
    ReminderStatus,
    ReminderType,
)
from app.models.farm import Farm, Plant
from app.models.reminder import Device, Reminder
from app.models.scan import Scan
from app.models.user import User
from app.providers.push import PushOutcome, PushProvider
from app.providers.weather import WeatherForecast, WeatherSlot

logger = get_logger("reminder")

# BMKG ``weather_desc`` wording for heavy precipitation and storms.
_HEAVY_RAIN_WORDS = ("hujan lebat", "hujan sangat lebat", "hujan petir", "petir", "badai")
_WET_WORDS = ("hujan", "berawan tebal", "mendung", "petir")


@dataclass(frozen=True, slots=True)
class ReminderThresholds:
    """Every tunable number from design 12.3, in one place."""

    fungal_humidity_pct: float = 85.0
    fungal_min_hours: int = 48
    fungal_history_days: int = 30
    # The BMKG daily category "hujan lebat" starts at 50 mm/day.
    heavy_rain_daily_mm: float = 50.0
    heavy_rain_window_days: int = 3
    harvest_soon_days: int = 2
    heat_stress_c: float = 35.0
    heat_stress_slots: int = 3

    @classmethod
    def from_settings(cls, settings: Settings) -> ReminderThresholds:
        return cls(fungal_history_days=settings.fungal_history_days)


@dataclass(frozen=True, slots=True)
class PlantContext:
    """Everything the rules need about one plant, already loaded."""

    plant_id: UUID
    user_id: UUID
    farm_id: UUID
    label: str
    health_status: str
    expected_harvest_min: date | None
    last_scan_at: datetime | None
    expected_harvest_max: date | None = None
    growth_stage: str = GrowthStage.FRUITING.value
    had_fungal_issue: bool = False


@dataclass(frozen=True, slots=True)
class PendingReminder:
    user_id: UUID
    farm_id: UUID | None
    plant_id: UUID | None
    type: ReminderType
    priority: ReminderPriority
    title: str
    body: str
    dedupe_key: str
    payload: dict[str, object] = field(default_factory=dict)
    valid_until: datetime | None = None


def local_today(now: datetime, tz_name: str) -> date:
    return now.astimezone(ZoneInfo(tz_name)).date()


def dedupe_key(reminder_type: ReminderType, target: UUID | str, day: date) -> str:
    """``<type>:<plant_id or farm_id>:<local date>`` (design 12.4)."""
    return f"{reminder_type.value}:{target}:{day.isoformat()}"


# --------------------------------------------------------------------------- #
# Pure rules
# --------------------------------------------------------------------------- #
def _is_wet(desc: str) -> bool:
    lowered = desc.lower()
    return any(word in lowered for word in _WET_WORDS)


def _is_heavy_rain_desc(desc: str) -> bool:
    lowered = desc.lower()
    return any(word in lowered for word in _HEAVY_RAIN_WORDS)


def _parse_slot(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _slots(forecast: WeatherForecast) -> list[WeatherSlot]:
    return [slot for day in forecast.days for slot in day.slots]


def is_fungal_risk(forecast: WeatherForecast, thresholds: ReminderThresholds) -> bool:
    """Humidity >= threshold for >= 48 consecutive hours AND rain or thick cloud.

    ``design.md`` 12.3. BMKG slots are every 3 hours, so the run length is
    measured from the timestamps (capped so a gap in the feed cannot fake a long
    run). The wet condition must hold *inside* the humid run, not anywhere in
    the three days, and "Cerah Berawan" (partly cloudy) does not count as thick
    cloud.
    """
    run_hours = 0.0
    run_wet = False
    previous: datetime | None = None

    for slot in _slots(forecast):
        moment = _parse_slot(slot.local_datetime)
        humidity = slot.humidity_pct
        if humidity is not None and humidity >= thresholds.fungal_humidity_pct:
            if previous is not None and moment is not None and run_hours > 0:
                delta = (moment - previous).total_seconds() / 3600
                run_hours += max(0.0, min(delta, 6.0))
            else:
                run_hours += 3.0
            run_wet = run_wet or _is_wet(slot.weather_desc)
            if run_hours >= thresholds.fungal_min_hours and run_wet:
                return True
        else:
            run_hours = 0.0
            run_wet = False
        previous = moment
    return False


def is_heavy_rain_before_harvest(
    forecast: WeatherForecast,
    harvest_min: date | None,
    thresholds: ReminderThresholds,
    *,
    today: date,
) -> bool:
    """Harvest starts within the window AND heavy rain falls before it.

    Heavy rain is either the BMKG wording itself (``Hujan Lebat``,
    ``Hujan Petir``) or a daily precipitation total at or above the "lebat"
    threshold.
    """
    if harvest_min is None:
        return False
    if (harvest_min - today).days > thresholds.heavy_rain_window_days:
        return False
    last_day = max(harvest_min, today)

    daily_mm: dict[str, float] = {}
    for day in forecast.days:
        try:
            day_date = date.fromisoformat(day.date)
        except ValueError:
            continue
        if not today <= day_date <= last_day:
            continue
        for slot in day.slots:
            if _is_heavy_rain_desc(slot.weather_desc):
                return True
            if slot.precipitation_mm is not None:
                daily_mm[day.date] = daily_mm.get(day.date, 0.0) + slot.precipitation_mm
    return any(total >= thresholds.heavy_rain_daily_mm for total in daily_mm.values())


def is_heat_stress(forecast: WeatherForecast, thresholds: ReminderThresholds) -> bool:
    """``>= 35 C`` on ``>= 3`` consecutive slots."""
    streak = 0
    for slot in _slots(forecast):
        if slot.temperature_c is not None and slot.temperature_c >= thresholds.heat_stress_c:
            streak += 1
            if streak >= thresholds.heat_stress_slots:
                return True
        else:
            streak = 0
    return False


def is_harvest_soon(plant: PlantContext, thresholds: ReminderThresholds, *, today: date) -> bool:
    """Harvest window starts within two days and has not already passed.

    Without the upper bound a stale estimate (the farmer harvested and never
    scanned again) would produce a reminder every day forever.
    """
    if plant.expected_harvest_min is None or plant.growth_stage == GrowthStage.FINISHED.value:
        return False
    window_end = plant.expected_harvest_max or plant.expected_harvest_min
    if window_end < today:
        return False
    return (plant.expected_harvest_min - today).days <= thresholds.harvest_soon_days


def is_scan_followup(plant: PlantContext, *, now: datetime, followup_days: int) -> bool:
    if plant.health_status not in {HealthStatus.SICK.value, HealthStatus.AT_RISK.value}:
        return False
    if plant.last_scan_at is None:
        return True
    return (now - plant.last_scan_at) >= timedelta(days=followup_days)


def _harvest_text(plant: PlantContext, today: date) -> str:
    start = max(((plant.expected_harvest_min or today) - today).days, 0)
    end_date = plant.expected_harvest_max or plant.expected_harvest_min or today
    end = max((end_date - today).days, start)
    if end == 0:
        return f"{plant.label} diperkirakan sudah siap panen hari ini."
    if start == end:
        return f"{plant.label} diperkirakan siap panen dalam {start} hari."
    return f"{plant.label} diperkirakan siap panen dalam {start}-{end} hari."


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def build_weather_reminders(
    *,
    plants: Sequence[PlantContext],
    forecast: WeatherForecast,
    thresholds: ReminderThresholds,
    now: datetime,
    today: date,
) -> list[PendingReminder]:
    """One reminder per rule per plant, deduplicated by the dedupe key."""
    out: list[PendingReminder] = []
    fungal = is_fungal_risk(forecast, thresholds)
    heat = is_heat_stress(forecast, thresholds)

    for plant in plants:
        if fungal:
            priority = ReminderPriority.HIGH if plant.had_fungal_issue else ReminderPriority.NORMAL
            out.append(
                PendingReminder(
                    user_id=plant.user_id,
                    farm_id=plant.farm_id,
                    plant_id=plant.plant_id,
                    type=ReminderType.FUNGAL_RISK,
                    priority=priority,
                    title="Risiko jamur naik",
                    body=(
                        f"Kelembapan tinggi beberapa hari ke depan. Periksa daun {plant.label} "
                        "dan pertimbangkan penyemprotan pencegahan."
                    ),
                    dedupe_key=dedupe_key(ReminderType.FUNGAL_RISK, plant.plant_id, today),
                    payload={"adm4_code": forecast.adm4_code},
                    valid_until=now + timedelta(days=2),
                )
            )

        if is_harvest_soon(plant, thresholds, today=today):
            out.append(
                PendingReminder(
                    user_id=plant.user_id,
                    farm_id=plant.farm_id,
                    plant_id=plant.plant_id,
                    type=ReminderType.HARVEST_SOON,
                    priority=ReminderPriority.NORMAL,
                    title="Siap panen sebentar lagi",
                    body=_harvest_text(plant, today),
                    dedupe_key=dedupe_key(ReminderType.HARVEST_SOON, plant.plant_id, today),
                    payload={
                        "expected_harvest_min": _iso(plant.expected_harvest_min),
                        "expected_harvest_max": _iso(plant.expected_harvest_max),
                    },
                    valid_until=now + timedelta(days=3),
                )
            )

        if plant.growth_stage != GrowthStage.FINISHED.value and is_heavy_rain_before_harvest(
            forecast, plant.expected_harvest_min, thresholds, today=today
        ):
            out.append(
                PendingReminder(
                    user_id=plant.user_id,
                    farm_id=plant.farm_id,
                    plant_id=plant.plant_id,
                    type=ReminderType.HEAVY_RAIN_HARVEST,
                    priority=ReminderPriority.HIGH,
                    title="Hujan lebat sebelum panen",
                    body=(
                        f"Hujan lebat diperkirakan sebelum {plant.label} siap panen. "
                        "Pertimbangkan panen lebih awal."
                    ),
                    dedupe_key=dedupe_key(ReminderType.HEAVY_RAIN_HARVEST, plant.plant_id, today),
                    payload={"adm4_code": forecast.adm4_code},
                    valid_until=now + timedelta(days=2),
                )
            )

        if heat:
            out.append(
                PendingReminder(
                    user_id=plant.user_id,
                    farm_id=plant.farm_id,
                    plant_id=plant.plant_id,
                    type=ReminderType.HEAT_STRESS,
                    priority=ReminderPriority.NORMAL,
                    title="Cuaca sangat panas",
                    body=f"Cuaca sangat panas. Pastikan {plant.label} cukup air.",
                    dedupe_key=dedupe_key(ReminderType.HEAT_STRESS, plant.plant_id, today),
                    payload={"adm4_code": forecast.adm4_code},
                    valid_until=now + timedelta(days=1),
                )
            )

    return out


def build_scan_followups(
    *,
    plants: Sequence[PlantContext],
    followup_days: int,
    now: datetime,
    today: date,
) -> list[PendingReminder]:
    out: list[PendingReminder] = []
    for plant in plants:
        if not is_scan_followup(plant, now=now, followup_days=followup_days):
            continue
        days = followup_days if plant.last_scan_at is None else (now - plant.last_scan_at).days
        condition = (
            "terdeteksi sakit"
            if plant.health_status == HealthStatus.SICK.value
            else "perlu diperiksa ulang"
        )
        out.append(
            PendingReminder(
                user_id=plant.user_id,
                farm_id=plant.farm_id,
                plant_id=plant.plant_id,
                type=ReminderType.SCAN_FOLLOWUP,
                priority=ReminderPriority.NORMAL,
                title="Cek ulang tanaman",
                body=f"Sudah {days} hari sejak daun {plant.label} {condition}. Yuk cek lagi.",
                dedupe_key=dedupe_key(ReminderType.SCAN_FOLLOWUP, plant.plant_id, today),
                valid_until=now + timedelta(days=3),
            )
        )
    return out


def is_quiet_hour(moment: datetime, *, start: int, end: int, tz_name: str) -> bool:
    """``21:00-05:00`` local quiet window (design 12.4)."""
    hour = moment.astimezone(ZoneInfo(tz_name)).hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


@dataclass(frozen=True, slots=True)
class DeliveryPrefs:
    """Opt-outs and quiet hours of one user (``/users/me/notification-settings``)."""

    disabled_types: frozenset[str]
    quiet_start: int
    quiet_end: int

    @classmethod
    def for_user(cls, user: User, settings: Settings) -> DeliveryPrefs:
        stored = user.notification_settings if isinstance(user.notification_settings, dict) else {}
        enabled = stored.get("enabled")
        disabled = (
            frozenset(str(key) for key, value in enabled.items() if value is False)
            if isinstance(enabled, dict)
            else frozenset()
        )
        quiet = stored.get("quiet_hours")
        hours = quiet if isinstance(quiet, dict) else {}
        return cls(
            disabled_types=disabled,
            quiet_start=_hour(hours.get("start"), settings.quiet_hours_start),
            quiet_end=_hour(hours.get("end"), settings.quiet_hours_end),
        )


def _hour(value: object, default: int) -> int:
    if isinstance(value, int) and 0 <= value <= 23:
        return value
    return default


def push_decision(
    *,
    priority: str,
    reminder_type: str,
    prefs: DeliveryPrefs,
    now: datetime,
    tz_name: str,
    pushes_today: int,
    max_per_day: int,
) -> PushState:
    """What to do with a pending reminder right now (design 12.4).

    ``PENDING`` means "not yet": the hourly dispatcher retries it once the quiet
    window is over. Everything else is final.
    """
    if reminder_type in prefs.disabled_types:
        return PushState.DISABLED
    if pushes_today >= max_per_day:
        return PushState.SKIPPED_CAP
    quiet = is_quiet_hour(now, start=prefs.quiet_start, end=prefs.quiet_end, tz_name=tz_name)
    if quiet and priority != ReminderPriority.HIGH.value:
        return PushState.PENDING
    return PushState.SENT


def validate_status_filter(value: str | None) -> str | None:
    if value is None:
        return None
    allowed = {member.value for member in ReminderStatus}
    if value not in allowed:
        raise ValidationError(
            "Status reminder tidak dikenal.",
            details={"field": "status", "allowed": sorted(allowed)},
        )
    return value


# --------------------------------------------------------------------------- #
# Persistence and delivery
# --------------------------------------------------------------------------- #
class ReminderService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        push: PushProvider,
    ) -> None:
        self.session = session
        self.settings = settings
        self.push = push
        self.thresholds = ReminderThresholds.from_settings(settings)

    def today(self, now: datetime) -> date:
        return local_today(now, self.settings.timezone)

    async def persist(self, candidates: Iterable[PendingReminder]) -> list[Reminder]:
        """Insert only the reminders that do not already exist.

        The unique index ``(user_id, dedupe_key)`` is the real guard; this method
        pre-filters so a normal run does not rely on catching IntegrityError.
        """
        created: list[Reminder] = []
        seen: set[tuple[UUID, str]] = set()
        for candidate in candidates:
            marker = (candidate.user_id, candidate.dedupe_key)
            if marker in seen:
                continue
            seen.add(marker)
            exists = (
                await self.session.execute(
                    select(Reminder.id).where(
                        Reminder.user_id == candidate.user_id,
                        Reminder.dedupe_key == candidate.dedupe_key,
                    )
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue

            reminder = Reminder(
                id=uuid4(),
                user_id=candidate.user_id,
                farm_id=candidate.farm_id,
                plant_id=candidate.plant_id,
                type=candidate.type.value,
                priority=candidate.priority.value,
                status=ReminderStatus.UNREAD.value,
                title=candidate.title,
                body=candidate.body,
                payload=candidate.payload,
                dedupe_key=candidate.dedupe_key,
                valid_until=candidate.valid_until,
                push_state=PushState.PENDING.value,
            )
            self.session.add(reminder)
            created.append(reminder)
            REMINDERS_CREATED.labels(type=candidate.type.value).inc()

        await self.session.commit()
        return created

    async def get(self, user_id: UUID, reminder_id: UUID) -> Reminder:
        reminder = await self.session.get(Reminder, reminder_id)
        if reminder is None or reminder.user_id != user_id:
            raise NotFound("Reminder tidak ditemukan.")
        return reminder

    async def update_status(
        self, user_id: UUID, reminder_id: UUID, status: ReminderStatus
    ) -> Reminder:
        reminder = await self.get(user_id, reminder_id)
        reminder.status = status.value
        if status is not ReminderStatus.UNREAD and reminder.read_at is None:
            reminder.read_at = datetime.now(UTC)
        await self.session.commit()
        return reminder

    async def expire_stale(self, now: datetime | None = None) -> int:
        """``valid_until`` passed -> ``dismissed`` (design 12.4)."""
        moment = now or datetime.now(UTC)
        stale = list(
            (
                await self.session.execute(
                    select(Reminder).where(
                        Reminder.valid_until.is_not(None),
                        Reminder.valid_until < moment,
                        Reminder.status.in_(
                            [ReminderStatus.UNREAD.value, ReminderStatus.READ.value]
                        ),
                    )
                )
            ).scalars()
        )
        for reminder in stale:
            reminder.status = ReminderStatus.DISMISSED.value
            if reminder.push_state == PushState.PENDING.value:
                reminder.push_state = PushState.EXPIRED.value
        if stale:
            await self.session.commit()
        return len(stale)

    async def dispatch_pending(self, *, now: datetime | None = None) -> int:
        """Push every reminder still waiting, e.g. the ones held by quiet hours."""
        moment = now or datetime.now(UTC)
        pending = list(
            (
                await self.session.execute(
                    select(Reminder)
                    .where(Reminder.push_state == PushState.PENDING.value)
                    .order_by(Reminder.created_at)
                    .limit(1000)
                )
            ).scalars()
        )
        return await self.dispatch_pushes(pending, now=moment)

    async def dispatch_pushes(
        self, reminders: Sequence[Reminder], *, now: datetime | None = None
    ) -> int:
        """Apply the delivery rules to each pending reminder and push the due ones.

        Returns the number of device pushes that FCM accepted.
        """
        moment = now or datetime.now(UTC)
        sent = 0
        users: dict[UUID, User | None] = {}
        for reminder in reminders:
            if reminder.push_state != PushState.PENDING.value:
                continue
            if reminder.status != ReminderStatus.UNREAD.value or (
                reminder.valid_until is not None and reminder.valid_until < moment
            ):
                # Already seen in the app, or no longer relevant: never push late.
                reminder.push_state = PushState.EXPIRED.value
                continue

            if reminder.user_id not in users:
                users[reminder.user_id] = await self.session.get(User, reminder.user_id)
            user = users[reminder.user_id]
            if user is None or user.deleted_at is not None:
                reminder.push_state = PushState.DISABLED.value
                continue

            decision = push_decision(
                priority=reminder.priority,
                reminder_type=reminder.type,
                prefs=DeliveryPrefs.for_user(user, self.settings),
                now=moment,
                tz_name=self.settings.timezone,
                pushes_today=await self._pushes_today(reminder.user_id, moment),
                max_per_day=self.settings.max_push_per_day,
            )
            if decision is not PushState.SENT:
                reminder.push_state = decision.value
                continue

            devices = list(
                (
                    await self.session.execute(
                        select(Device).where(Device.user_id == reminder.user_id)
                    )
                ).scalars()
            )
            if not devices:
                # The reminder still appears in the list; it just cannot be pushed.
                reminder.push_state = PushState.NO_DEVICE.value
                continue

            payload = {
                "type": "reminder",
                "reminder_id": str(reminder.id),
                "reminder_type": reminder.type,
                "priority": reminder.priority,
                "title": reminder.title,
                "body": reminder.body,
                "deeplink": f"tanami://reminders/{reminder.id}",
            }
            delivered = False
            for device in devices:
                outcome = await self.push.send(token=device.fcm_token, data=payload)
                if outcome is PushOutcome.SENT:
                    delivered = True
                    sent += 1
                elif outcome is PushOutcome.INVALID_TOKEN:
                    # The app was uninstalled or the token rotated.
                    await self.session.execute(delete(Device).where(Device.id == device.id))
            reminder.push_state = PushState.SENT.value if delivered else PushState.FAILED.value
            reminder.sent_at = moment if delivered else None
            # Make the cap count this push before the next reminder is decided.
            await self.session.flush()

        await self.session.commit()
        return sent

    async def _pushes_today(self, user_id: UUID, now: datetime) -> int:
        """Count from the database so a Redis flush cannot lift the cap."""
        tz = ZoneInfo(self.settings.timezone)
        local_midnight = datetime.combine(now.astimezone(tz).date(), time.min, tzinfo=tz)
        count = (
            await self.session.execute(
                select(func.count(Reminder.id)).where(
                    Reminder.user_id == user_id,
                    Reminder.push_state == PushState.SENT.value,
                    Reminder.sent_at >= local_midnight,
                )
            )
        ).scalar_one()
        return int(count)


async def load_plant_contexts(
    session: AsyncSession,
    *,
    thresholds: ReminderThresholds,
    now: datetime,
    farm_ids: Sequence[UUID] | None = None,
    plant_ids: Sequence[UUID] | None = None,
) -> list[PlantContext]:
    """Load every active plant of an active account with what the rules need."""
    last_scan = (
        select(Scan.plant_id, func.max(Scan.captured_at).label("last_scan_at"))
        .where(Scan.scan_type == "disease")
        .group_by(Scan.plant_id)
        .subquery()
    )

    query = (
        select(
            Plant.id,
            Plant.label,
            Plant.farm_id,
            Plant.health_status,
            Plant.expected_harvest_min,
            Plant.expected_harvest_max,
            Plant.growth_stage,
            Farm.user_id,
            last_scan.c.last_scan_at,
        )
        .join(Farm, Farm.id == Plant.farm_id)
        .join(User, User.id == Farm.user_id)
        .outerjoin(last_scan, last_scan.c.plant_id == Plant.id)
        .where(
            Plant.ended_at.is_(None),
            Farm.archived_at.is_(None),
            User.deleted_at.is_(None),
        )
    )
    if farm_ids is not None:
        query = query.where(Plant.farm_id.in_(list(farm_ids)))
    if plant_ids is not None:
        query = query.where(Plant.id.in_(list(plant_ids)))

    rows = (await session.execute(query)).all()
    if not rows:
        return []

    plant_id_list = [row.id for row in rows]
    # "Had a fungal issue recently" drives the fungal reminder priority.
    since = now - timedelta(days=thresholds.fungal_history_days)
    fungal_rows = (
        await session.execute(
            select(Scan.plant_id)
            .where(
                Scan.plant_id.in_(plant_id_list),
                Scan.captured_at >= since,
                Scan.scan_type == "disease",
                Scan.result["top"]["cause_category"].astext == "fungus",
            )
            .distinct()
        )
    ).scalars()
    fungal_plants = {row for row in fungal_rows if row is not None}

    return [
        PlantContext(
            plant_id=row.id,
            user_id=row.user_id,
            farm_id=row.farm_id,
            label=row.label,
            health_status=row.health_status,
            expected_harvest_min=row.expected_harvest_min,
            expected_harvest_max=row.expected_harvest_max,
            growth_stage=row.growth_stage,
            last_scan_at=row.last_scan_at,
            had_fungal_issue=row.id in fungal_plants,
        )
        for row in rows
    ]
