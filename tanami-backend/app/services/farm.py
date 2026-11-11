"""Farm, plant, harvest, timeline and stats business logic."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound, ValidationError
from app.domain import (
    DISEASE_LABELS,
    IRRIGATION_INTERVAL_DAYS,
    PLANT_TYPES,
    CareAction,
    GrowthStage,
    HealthStatus,
    PushState,
    ReminderStatus,
    ScanType,
    TrackingEndReason,
    outcome_for_percent,
)
from app.models.content import Region
from app.models.farm import Farm, HarvestRecord, Plant
from app.models.reminder import Reminder
from app.models.scan import Scan
from app.models.tracking import CareLog, PlantPhoto
from app.providers.storage import StorageProvider
from app.schemas.farm import (
    EndTracking,
    EstimateVsActual,
    FarmOut,
    FarmUpdate,
    HarvestCreate,
    HarvestOut,
    HealthPoint,
    PlantOut,
    PlantStats,
    PlantUpdate,
    RegionOut,
    RipenessPoint,
    TimelineEntry,
)
from app.services.scan import next_health_status

CARE_LABELS: dict[str, str] = {
    CareAction.WATERING.value: "Penyiraman",
    CareAction.FERTILIZING.value: "Pemupukan",
    CareAction.PEST_CONTROL.value: "Pengendalian hama/penyakit",
    CareAction.PRUNING.value: "Pemangkasan",
    CareAction.WEEDING.value: "Penyiangan",
    CareAction.OTHER.value: "Perawatan lain",
}
END_REASON_LABELS: dict[str, str] = {
    TrackingEndReason.HARVESTED.value: "Dipanen",
    TrackingEndReason.DIED.value: "Mati",
    TrackingEndReason.NOT_MAINTAINED.value: "Tidak dirawat lagi",
    TrackingEndReason.OTHER.value: "Alasan lain",
}


async def village_names(session: AsyncSession, codes: list[str]) -> dict[str, str]:
    """adm4 code -> village name, for the codes present in ``regions``."""
    if not codes:
        return {}
    rows = await session.execute(
        select(Region.adm4_code, Region.village).where(Region.adm4_code.in_(set(codes)))
    )
    return {row[0]: row[1] for row in rows.all()}


async def stop_plant_reminders(session: AsyncSession, plant_id: UUID) -> None:
    """Requirement 7: no reminder survives the end of tracking (or of a garden)."""
    await session.execute(
        update(Reminder)
        .where(
            Reminder.plant_id == plant_id,
            Reminder.status.in_([ReminderStatus.UNREAD.value, ReminderStatus.READ.value]),
        )
        .values(status=ReminderStatus.DISMISSED.value)
    )
    await session.execute(
        update(Reminder)
        .where(Reminder.plant_id == plant_id, Reminder.push_state == PushState.PENDING.value)
        .values(push_state=PushState.EXPIRED.value)
    )


def next_watering_on(plant: Plant, last_watered: datetime | None, tz: ZoneInfo) -> date | None:
    """The day the next watering is due according to the irrigation schedule.

    Counted from the last logged watering, or from the day tracking started.
    """
    interval = IRRIGATION_INTERVAL_DAYS.get(plant.irrigation_schedule)
    if interval is None or plant.ended_at is not None:
        return None
    base = (last_watered or plant.created_at).astimezone(tz).date()
    return base + timedelta(days=interval)


class FarmService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    # ------------------------------------------------------------------ #
    # Farms
    # ------------------------------------------------------------------ #
    async def list_farms(self, user_id: UUID, *, include_archived: bool = False) -> list[FarmOut]:
        query = select(Farm).where(Farm.user_id == user_id)
        if not include_archived:
            query = query.where(Farm.archived_at.is_(None))
        query = query.order_by(Farm.created_at)
        farms = list((await self.session.execute(query)).scalars())

        counts: dict[UUID, int] = {}
        if farms:
            rows = (
                await self.session.execute(
                    select(Plant.farm_id, func.count(Plant.id))
                    .where(
                        Plant.farm_id.in_([farm.id for farm in farms]),
                        Plant.ended_at.is_(None),
                    )
                    .group_by(Plant.farm_id)
                )
            ).all()
            counts = {farm_id: int(total) for farm_id, total in rows}

        villages = await village_names(self.session, [farm.adm4_code for farm in farms])
        return [
            self._farm_out(farm, int(counts.get(farm.id, 0)), villages.get(farm.adm4_code))
            for farm in farms
        ]

    async def get_farm(self, user_id: UUID, farm_id: UUID) -> Farm:
        farm = await self.session.get(Farm, farm_id)
        if farm is None or farm.user_id != user_id:
            raise NotFound("Lahan tidak ditemukan.")
        return farm

    async def get_farm_out(self, user_id: UUID, farm_id: UUID) -> FarmOut:
        farm = await self.get_farm(user_id, farm_id)
        count = (
            await self.session.execute(
                select(func.count(Plant.id)).where(
                    Plant.farm_id == farm.id, Plant.ended_at.is_(None)
                )
            )
        ).scalar_one()
        villages = await village_names(self.session, [farm.adm4_code])
        return self._farm_out(farm, int(count), villages.get(farm.adm4_code))

    async def create_farm(self, user_id: UUID, **fields: object) -> FarmOut:
        farm = Farm(id=uuid4(), user_id=user_id, **fields)
        self.session.add(farm)
        await self.session.commit()
        return await self.get_farm_out(user_id, farm.id)

    async def update_farm(self, user_id: UUID, farm_id: UUID, payload: FarmUpdate) -> FarmOut:
        farm = await self.get_farm(user_id, farm_id)
        data = payload.model_dump(exclude_unset=True)
        if ("lat" in data) != ("lon" in data):
            # Only one of the pair supplied: keep them consistent with the old
            # value rather than ending up with a half-moved farm.
            data.setdefault("lat", farm.lat)
            data.setdefault("lon", farm.lon)
        for key, value in data.items():
            setattr(farm, key, value)
        await self.session.commit()
        return await self.get_farm_out(user_id, farm_id)

    async def archive_farm(self, user_id: UUID, farm_id: UUID) -> None:
        farm = await self.get_farm(user_id, farm_id)
        if farm.archived_at is None:
            farm.archived_at = datetime.now(UTC)
        # Archiving a garden ends the tracking of its plants: they move to the
        # history list and stop producing reminders (requirement 7).
        now = datetime.now(UTC)
        plants = (
            await self.session.execute(
                select(Plant).where(Plant.farm_id == farm.id, Plant.ended_at.is_(None))
            )
        ).scalars()
        for plant in plants:
            plant.ended_at = now
            plant.end_reason = TrackingEndReason.OTHER.value
            plant.end_note = "Kebun diarsipkan."
            await stop_plant_reminders(self.session, plant.id)
        await self.session.commit()

    def _farm_out(self, farm: Farm, plant_count: int, village: str | None) -> FarmOut:
        return FarmOut(
            id=str(farm.id),
            name=farm.name,
            adm4_code=farm.adm4_code,
            lat=float(farm.lat) if farm.lat is not None else None,
            lon=float(farm.lon) if farm.lon is not None else None,
            area_m2=float(farm.area_m2) if farm.area_m2 is not None else None,
            placement=farm.placement,
            village=village,
            plant_count=plant_count,
            archived_at=farm.archived_at,
            created_at=farm.created_at,
            updated_at=farm.updated_at,
        )


class PlantService:
    def __init__(
        self, session: AsyncSession, settings: Settings, storage: StorageProvider | None = None
    ) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage

    # ------------------------------------------------------------------ #
    # Plants
    # ------------------------------------------------------------------ #
    async def list_plants(
        self, user_id: UUID, farm_id: UUID, *, include_archived: bool = False
    ) -> list[PlantOut]:
        farm = await self.session.get(Farm, farm_id)
        if farm is None or farm.user_id != user_id:
            raise NotFound("Lahan tidak ditemukan.")

        query = select(Plant).where(Plant.farm_id == farm_id)
        if not include_archived:
            query = query.where(Plant.ended_at.is_(None))
        plants = list((await self.session.execute(query.order_by(Plant.created_at))).scalars())
        return await self._plants_out(plants)

    async def list_user_plants(self, user_id: UUID, *, status: str) -> list[PlantOut]:
        """Every plant of the user across gardens.

        ``status=active`` is the tracking list, ``status=ended`` the history
        list (requirement 2), most recently ended first.
        """
        query = select(Plant).join(Farm, Farm.id == Plant.farm_id).where(Farm.user_id == user_id)
        if status == "ended":
            query = query.where(Plant.ended_at.is_not(None)).order_by(Plant.ended_at.desc())
        else:
            query = query.where(Plant.ended_at.is_(None)).order_by(Plant.created_at)
        plants = list((await self.session.execute(query)).scalars())
        return await self._plants_out(plants)

    async def get_plant(self, user_id: UUID, plant_id: UUID) -> Plant:
        plant = await self.session.get(Plant, plant_id)
        if plant is None:
            raise NotFound("Tanaman tidak ditemukan.")
        farm = await self.session.get(Farm, plant.farm_id)
        if farm is None or farm.user_id != user_id:
            raise NotFound("Tanaman tidak ditemukan.")
        return plant

    async def get_plant_out(self, user_id: UUID, plant_id: UUID) -> PlantOut:
        return await self._plant_out(await self.get_plant(user_id, plant_id))

    async def create_plant(self, user_id: UUID, farm_id: UUID, **fields: object) -> PlantOut:
        farm = await self.session.get(Farm, farm_id)
        if farm is None or farm.user_id != user_id:
            raise NotFound("Lahan tidak ditemukan.")
        if farm.archived_at is not None:
            raise ValidationError("Lahan ini sudah diarsipkan.", details={"field": "farm_id"})

        plant = Plant(
            id=uuid4(), farm_id=farm_id, health_status=HealthStatus.UNKNOWN.value, **fields
        )
        self.session.add(plant)
        await self.session.commit()
        return await self._plant_out(plant)

    async def get_active_plant(self, user_id: UUID, plant_id: UUID) -> Plant:
        """A plant that can still be changed: history entries are read-only."""
        plant = await self.get_plant(user_id, plant_id)
        if plant.ended_at is not None:
            raise ValidationError(
                "Tracking tanaman ini sudah diakhiri.", details={"field": "plant_id"}
            )
        return plant

    async def update_plant(self, user_id: UUID, plant_id: UUID, payload: PlantUpdate) -> PlantOut:
        plant = await self.get_active_plant(user_id, plant_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(plant, key, value)
        await self.session.commit()
        return await self._plant_out(plant)

    async def end_tracking(self, user_id: UUID, plant_id: UUID, payload: EndTracking) -> PlantOut:
        """Requirement 1: end tracking; the plant moves to the history list.

        Its unread reminders are dismissed and no new ones are generated
        (requirement 7, "Penghentian Notifikasi"); its data stays.
        """
        plant = await self.get_active_plant(user_id, plant_id)
        plant.ended_at = datetime.now(UTC)
        plant.end_reason = payload.reason.value
        plant.end_note = payload.note
        plant.yield_percent = payload.yield_percent
        result = payload.final_result
        if result is None and payload.yield_percent is not None:
            result = outcome_for_percent(float(payload.yield_percent))
        plant.final_result = result.value if result else None
        if payload.reason is TrackingEndReason.HARVESTED:
            plant.growth_stage = GrowthStage.FINISHED.value
        plant.expected_harvest_min = None
        plant.expected_harvest_max = None
        await stop_plant_reminders(self.session, plant.id)
        await self.session.commit()
        return await self._plant_out(plant)

    async def record_harvest(
        self, user_id: UUID, plant_id: UUID, payload: HarvestCreate
    ) -> HarvestOut:
        plant = await self.get_active_plant(user_id, plant_id)
        harvest = HarvestRecord(
            id=uuid4(),
            plant_id=plant.id,
            recorded_by=user_id,
            harvested_at=payload.harvested_at.astimezone(UTC),
            quality_note=payload.quality_note,
            quantity_kg=payload.quantity_kg,
        )
        self.session.add(harvest)
        plant.growth_stage = (
            GrowthStage.FINISHED.value if payload.is_final else GrowthStage.HARVESTING.value
        )
        if payload.is_final:
            # Nothing left to ripen: stop the harvest_soon reminders.
            plant.expected_harvest_min = None
            plant.expected_harvest_max = None
        await self.session.commit()

        return HarvestOut(
            id=str(harvest.id),
            plant_id=str(harvest.plant_id),
            harvested_at=harvest.harvested_at,
            quality_note=harvest.quality_note,
            quantity_kg=float(harvest.quantity_kg) if harvest.quantity_kg is not None else None,
            created_at=harvest.created_at,
        )

    # ------------------------------------------------------------------ #
    # Timeline and stats
    # ------------------------------------------------------------------ #
    async def timeline(self, user_id: UUID, plant_id: UUID) -> list[TimelineEntry]:
        plant = await self.get_plant(user_id, plant_id)
        entries: list[TimelineEntry] = []

        scans = (
            await self.session.execute(
                select(Scan).where(Scan.plant_id == plant.id).order_by(Scan.captured_at.desc())
            )
        ).scalars()
        for scan in scans:
            if scan.scan_type == ScanType.DISEASE.value:
                top = scan.result.get("top")
                code = top.get("disease_code") if isinstance(top, dict) else None
                title = (
                    f"Scan daun: {DISEASE_LABELS.get(str(code), 'Tidak teridentifikasi')}"
                    if code
                    else "Scan daun: belum bisa dipastikan"
                )
            else:
                stage = scan.result.get("stage_label") or "Belum bisa dipastikan"
                title = f"Scan buah: {stage}"
            entries.append(
                TimelineEntry(
                    kind="scan",
                    occurred_at=scan.captured_at,
                    id=str(scan.id),
                    title=title,
                    subtitle=scan.status,
                    payload={"scan_type": scan.scan_type, "status": scan.status},
                )
            )

        harvests = (
            await self.session.execute(
                select(HarvestRecord)
                .where(HarvestRecord.plant_id == plant.id)
                .order_by(HarvestRecord.harvested_at.desc())
            )
        ).scalars()
        for harvest in harvests:
            quantity = (
                f"{float(harvest.quantity_kg):g} kg" if harvest.quantity_kg is not None else None
            )
            entries.append(
                TimelineEntry(
                    kind="harvest",
                    occurred_at=harvest.harvested_at,
                    id=str(harvest.id),
                    title="Panen dicatat",
                    subtitle=quantity,
                    payload={},
                )
            )

        reminders = (
            await self.session.execute(
                select(Reminder)
                .where(
                    Reminder.plant_id == plant.id,
                    Reminder.status != ReminderStatus.DISMISSED.value,
                )
                .order_by(Reminder.created_at.desc())
            )
        ).scalars()
        for reminder in reminders:
            entries.append(
                TimelineEntry(
                    kind="reminder",
                    occurred_at=reminder.created_at,
                    id=str(reminder.id),
                    title=reminder.title,
                    subtitle=reminder.type,
                    payload={"priority": reminder.priority},
                )
            )

        # Sorted on the same (time, id) key the cursor compares, so two events
        # at the same instant can never fall between two pages.
        photos = (
            await self.session.execute(select(PlantPhoto).where(PlantPhoto.plant_id == plant.id))
        ).scalars()
        for photo in photos:
            entries.append(
                TimelineEntry(
                    kind="photo",
                    occurred_at=photo.taken_at,
                    id=str(photo.id),
                    title="Foto perkembangan",
                    subtitle=photo.caption,
                    payload={
                        "image_url": self.storage.public_url(photo.image_key)
                        if self.storage
                        else None
                    },
                )
            )

        care_logs = (
            await self.session.execute(select(CareLog).where(CareLog.plant_id == plant.id))
        ).scalars()
        for log in care_logs:
            entries.append(
                TimelineEntry(
                    kind="care",
                    occurred_at=log.performed_at,
                    id=str(log.id),
                    title=CARE_LABELS.get(log.action, log.action),
                    subtitle=log.note,
                    payload={"action": log.action},
                )
            )

        if plant.ended_at is not None:
            entries.append(
                TimelineEntry(
                    kind="ended",
                    occurred_at=plant.ended_at,
                    id=str(plant.id),
                    title="Tracking diakhiri",
                    subtitle=END_REASON_LABELS.get(plant.end_reason or "", plant.end_reason),
                    payload={"final_result": plant.final_result, "note": plant.end_note},
                )
            )

        # Sorted on the same (time, id) key the cursor compares, so two events
        # at the same instant can never fall between two pages.
        entries.sort(key=lambda entry: (entry.occurred_at, entry.id), reverse=True)
        return entries

    async def stats(
        self, user_id: UUID, plant_id: UUID, *, date_from: date | None, date_to: date | None
    ) -> PlantStats:
        plant = await self.get_plant(user_id, plant_id)
        start = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC) if date_from else None
        end = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC) if date_to else None

        scan_query = select(Scan).where(Scan.plant_id == plant.id).order_by(Scan.captured_at)
        if start:
            scan_query = scan_query.where(Scan.captured_at >= start)
        if end:
            scan_query = scan_query.where(Scan.captured_at <= end)
        scans = list((await self.session.execute(scan_query)).scalars())

        # The same state machine that sets ``plants.health_status`` (design 8.2),
        # replayed point by point, so the chart and the badge never disagree.
        health_series: list[HealthPoint] = []
        current = HealthStatus.UNKNOWN.value
        for scan in scans:
            if scan.scan_type != ScanType.DISEASE.value:
                continue
            top = scan.result.get("top")
            cause = top.get("cause_category") if isinstance(top, dict) else None
            severity = scan.result.get("severity")
            current = next_health_status(
                current,
                status=scan.status,
                cause=str(cause) if cause is not None else None,
                severity=str(severity) if severity is not None else None,
            )
            health_series.append(
                HealthPoint(date=scan.captured_at.date(), health_status=HealthStatus(current))
            )

        ripeness_series: list[RipenessPoint] = []
        for scan in scans:
            if scan.scan_type != ScanType.RIPENESS.value:
                continue
            stage = scan.result.get("stage")
            if not isinstance(stage, str):
                continue
            days_min = scan.result.get("estimated_days_min")
            days_max = scan.result.get("estimated_days_max")
            ripeness_series.append(
                RipenessPoint(
                    date=scan.captured_at.date(),
                    stage=stage,
                    estimated_days_min=days_min if isinstance(days_min, int) else None,
                    estimated_days_max=days_max if isinstance(days_max, int) else None,
                )
            )

        harvests = list(
            (
                await self.session.execute(
                    select(HarvestRecord)
                    .where(HarvestRecord.plant_id == plant.id)
                    .order_by(HarvestRecord.harvested_at)
                )
            ).scalars()
        )

        estimate_vs_actual: list[EstimateVsActual] = []
        # Pair each harvest with the last ripeness estimate taken before it.
        for harvest in harvests:
            prior = [
                scan
                for scan in scans
                if scan.scan_type == ScanType.RIPENESS.value
                and scan.captured_at <= harvest.harvested_at
                and isinstance(scan.result.get("estimated_harvest_date_min"), str)
            ]
            if not prior:
                continue
            last = prior[-1]
            est_min = date.fromisoformat(str(last.result["estimated_harvest_date_min"]))
            est_max = date.fromisoformat(str(last.result["estimated_harvest_date_max"]))
            actual = harvest.harvested_at.date()
            estimate_vs_actual.append(
                EstimateVsActual(
                    estimated_date_min=est_min,
                    estimated_date_max=est_max,
                    harvested_at=harvest.harvested_at,
                    within_range=est_min <= actual <= est_max,
                )
            )

        return PlantStats(
            health_series=health_series,
            ripeness_series=ripeness_series,
            estimate_vs_actual=estimate_vs_actual,
        )

    async def _extras(self, plants: list[Plant]) -> dict[UUID, dict[str, object]]:
        """Everything ``PlantOut`` needs beyond the row, in a few batched queries."""
        ids = [plant.id for plant in plants]
        if not ids:
            return {}
        scan_rows = await self.session.execute(
            select(Scan.plant_id, func.max(Scan.captured_at))
            .where(Scan.plant_id.in_(ids))
            .group_by(Scan.plant_id)
        )
        last_scan: dict[UUID | None, datetime] = {row[0]: row[1] for row in scan_rows.all()}
        water_rows = await self.session.execute(
            select(CareLog.plant_id, func.max(CareLog.performed_at))
            .where(CareLog.plant_id.in_(ids), CareLog.action == CareAction.WATERING.value)
            .group_by(CareLog.plant_id)
        )
        last_water: dict[UUID, datetime] = {row[0]: row[1] for row in water_rows.all()}
        latest_photo = (
            select(PlantPhoto.plant_id, PlantPhoto.image_key)
            .where(PlantPhoto.plant_id.in_(ids))
            .distinct(PlantPhoto.plant_id)
            .order_by(PlantPhoto.plant_id, PlantPhoto.taken_at.desc())
        )
        covers: dict[UUID, str] = {
            row[0]: row[1] for row in (await self.session.execute(latest_photo)).all()
        }
        farms = {
            farm.id: farm
            for farm in (
                await self.session.execute(
                    select(Farm).where(Farm.id.in_({plant.farm_id for plant in plants}))
                )
            ).scalars()
        }
        villages = await village_names(self.session, [farm.adm4_code for farm in farms.values()])
        return {
            plant.id: {
                "last_scan": last_scan.get(plant.id),
                "last_water": last_water.get(plant.id),
                "cover": covers.get(plant.id),
                "farm": farms[plant.farm_id],
                "village": villages.get(farms[plant.farm_id].adm4_code),
            }
            for plant in plants
        }

    async def _plants_out(self, plants: list[Plant]) -> list[PlantOut]:
        extras = await self._extras(plants)
        return [self._plant_out_with(plant, extras[plant.id]) for plant in plants]

    async def _plant_out(self, plant: Plant) -> PlantOut:
        return (await self._plants_out([plant]))[0]

    def _plant_out_with(self, plant: Plant, extra: dict[str, object]) -> PlantOut:
        farm = extra["farm"]
        assert isinstance(farm, Farm)  # noqa: S101 - built by _extras
        last_scan = extra["last_scan"] if isinstance(extra["last_scan"], datetime) else None
        last_water = extra["last_water"] if isinstance(extra["last_water"], datetime) else None
        cover = extra["cover"] if isinstance(extra["cover"], str) else None
        village = extra["village"] if isinstance(extra["village"], str) else None
        tz = ZoneInfo(self.settings.timezone)
        end_day = (plant.ended_at or datetime.now(UTC)).astimezone(tz).date()
        return PlantOut(
            id=str(plant.id),
            farm_id=str(plant.farm_id),
            label=plant.label,
            commodity_code=plant.commodity_code,
            commodity_label=PLANT_TYPES.get(plant.commodity_code, plant.commodity_code),
            variety=plant.variety,
            planted_at=plant.planted_at,
            age_days=max((end_day - plant.planted_at).days, 0),
            growth_stage=plant.growth_stage,
            health_status=plant.health_status,
            health_status_reason=self._health_reason(plant, last_scan),
            expected_harvest_min=plant.expected_harvest_min,
            expected_harvest_max=plant.expected_harvest_max,
            irrigation_schedule=plant.irrigation_schedule,
            last_watered_at=last_water,
            next_watering_on=next_watering_on(plant, last_water, tz),
            cover_photo_url=self.storage.public_url(cover) if cover and self.storage else None,
            last_scan_at=last_scan,
            farm_name=farm.name,
            placement=farm.placement,
            adm4_code=farm.adm4_code,
            village=village,
            status="ended" if plant.ended_at else "active",
            ended_at=plant.ended_at,
            end_reason=plant.end_reason,
            end_note=plant.end_note,
            final_result=plant.final_result,
            yield_percent=float(plant.yield_percent) if plant.yield_percent is not None else None,
            created_at=plant.created_at,
            updated_at=plant.updated_at,
        )

    def _health_reason(self, plant: Plant, last_scan: datetime | None) -> str | None:
        _ = plant
        if last_scan is None:
            return "Belum ada scan."
        age = datetime.now(UTC) - last_scan
        if age > timedelta(days=self.settings.plant_status_stale_days):
            return f"Tidak ada scan dalam {self.settings.plant_status_stale_days} hari terakhir."
        return None


class RegionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, query: str, *, limit: int = 20) -> list[RegionOut]:
        cleaned = query.strip()
        if len(cleaned) < 2:
            raise ValidationError("Ketik minimal 2 huruf nama desa.", details={"field": "q"})
        rows = (
            await self.session.execute(
                select(Region)
                .where(
                    or_(
                        Region.village.ilike(f"%{cleaned}%"),
                        Region.district.ilike(f"%{cleaned}%"),
                        Region.regency.ilike(f"%{cleaned}%"),
                    )
                )
                .order_by(Region.province, Region.regency, Region.village)
                .limit(limit)
            )
        ).scalars()
        return [self._out(region) for region in rows]

    async def resolve(self, lat: float, lon: float) -> RegionOut:
        """Nearest seeded village by squared degree distance.

        Good enough for choosing a weather location: the error is at most the
        distance to the next village centroid, and BMKG forecasts are per village
        anyway. A proper PostGIS query would need an extension the stack does not
        mandate.
        """
        region = (
            await self.session.execute(
                select(Region)
                .where(Region.lat.is_not(None), Region.lon.is_not(None))
                .order_by(
                    (Region.lat - lat) * (Region.lat - lat)
                    + (Region.lon - lon) * (Region.lon - lon)
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if region is None:
            raise NotFound("Wilayah untuk koordinat ini belum tersedia.")
        return self._out(region)

    def _out(self, region: Region) -> RegionOut:
        return RegionOut(
            adm4_code=region.adm4_code,
            village=region.village,
            district=region.district,
            regency=region.regency,
            province=region.province,
        )
