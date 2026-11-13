"""Farm, plant, harvest, timeline and stats business logic (design v2)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound, ValidationError
from app.domain import (
    COMMODITY_LABELS_V2,
    DEFAULT_MATERIAL,
    DISEASE_LABELS,
    IRRIGATION_INTERVAL_DAYS,
    MATERIALS_BY_COMMODITY,
    PLANT_CODE_PREFIX,
    CareAction,
    EpisodeCloseReason,
    HealthStatus,
    PushState,
    ReminderStatus,
    TrackingEndReason,
)
from app.models.content import Disease, Region
from app.models.episode import DiseaseEpisode
from app.models.farm import Farm, HarvestRecord, Plant
from app.models.reminder import Reminder
from app.models.scan import Scan
from app.models.tracking import CareLog, PlantPhoto
from app.models.user import User
from app.providers.storage import StorageProvider
from app.schemas.farm import (
    EndedDiseaseOut,
    EndTracking,
    EstimateVsActual,
    FarmOut,
    FarmUpdate,
    HarvestCreate,
    HarvestOut,
    HarvestPoint,
    HarvestUpdate,
    HealthPoint,
    NextHarvestOut,
    PlantCreate,
    PlantOut,
    PlantStats,
    PlantUpdate,
    RegionOut,
    TimelineEntry,
)
from app.services import harvest as rules
from app.services.episode import EpisodeService
from app.services.estimate import (
    MAX_DELAY_DAYS_PER_CYCLE,
    Estimator,
    PlantFacts,
    episode_span,
    local_date,
    next_harvest_out,
    noon_utc,
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
    TrackingEndReason.PRODUCTIVE_PERIOD_OVER.value: "Masa produktif selesai",
    TrackingEndReason.DISEASE.value: "Mati atau dibongkar karena penyakit",
    TrackingEndReason.CUT_DOWN.value: "Ditebang atau dibongkar",
    TrackingEndReason.DIED_OTHER.value: "Mati bukan karena penyakit",
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


async def end_plant(
    session: AsyncSession,
    settings: Settings,
    plant: Plant,
    *,
    reason: str,
    note: str | None = None,
    disease_codes: Sequence[str] | None = None,
    cause_note: str | None = None,
    now: datetime | None = None,
) -> None:
    """End tracking: status akhir, close open episodes, stop reminders (design 8.6).

    The one place that ends a plant, whether the user did it, the farm was
    archived, or the productive period ran out. It does not commit.
    """
    moment = now or datetime.now(UTC)
    harvest_count = int(
        (
            await session.execute(
                select(func.count(HarvestRecord.id)).where(HarvestRecord.plant_id == plant.id)
            )
        ).scalar_one()
    )
    plant.ended_at = moment
    plant.end_reason = reason
    plant.end_note = note
    plant.end_disease_codes = (
        list(disease_codes) if reason == TrackingEndReason.DISEASE.value and disease_codes else None
    )
    plant.end_cause_note = (cause_note or "").strip() or None
    plant.outcome = rules.tracking_outcome(reason, harvest_count).value
    await EpisodeService(session, settings).close_open(
        plant.id, EpisodeCloseReason.TRACKING_ENDED, at=moment
    )
    await stop_plant_reminders(session, plant.id)


async def complete_productive_period(
    session: AsyncSession, settings: Settings, *, today: date
) -> list[Plant]:
    """Daily job: end tracking of plants whose productive period is over (design 5.6)."""
    plants = list(
        (
            await session.execute(
                select(Plant).where(Plant.ended_at.is_(None), Plant.productive_until <= today)
            )
        ).scalars()
    )
    for plant in plants:
        await end_plant(
            session, settings, plant, reason=TrackingEndReason.PRODUCTIVE_PERIOD_OVER.value
        )
    await session.commit()
    return plants


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
            await end_plant(
                self.session,
                self.settings,
                plant,
                reason=TrackingEndReason.OTHER.value,
                note="Kebun diarsipkan.",
                now=now,
            )
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
        self.estimator = Estimator(session, settings)
        self.tz = ZoneInfo(settings.timezone)

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

    async def list_user_plants(
        self,
        user_id: UUID,
        *,
        status: str,
        commodity_code: str | None = None,
        outcome: str | None = None,
    ) -> list[PlantOut]:
        """Every plant of the user across gardens.

        ``status=active`` is the tracking list, ``status=ended`` Riwayat Tanaman,
        most recently ended first (design 5.7).
        """
        query = select(Plant).where(Plant.user_id == user_id)
        if commodity_code is not None:
            query = query.where(Plant.commodity_code == commodity_code)
        if status == "ended":
            query = query.where(Plant.ended_at.is_not(None))
            if outcome is not None:
                query = query.where(Plant.outcome == outcome)
            query = query.order_by(Plant.ended_at.desc())
        else:
            query = query.where(Plant.ended_at.is_(None)).order_by(Plant.created_at)
        plants = list((await self.session.execute(query)).scalars())
        return await self._plants_out(plants)

    async def get_plant(self, user_id: UUID, plant_id: UUID) -> Plant:
        plant = await self.session.get(Plant, plant_id)
        if plant is None or plant.user_id != user_id:
            # Same answer for "missing" and "someone else's".
            raise NotFound("Tanaman tidak ditemukan.")
        return plant

    async def get_plant_out(self, user_id: UUID, plant_id: UUID) -> PlantOut:
        return await self._plant_out(await self.get_plant(user_id, plant_id))

    async def get_active_plant(self, user_id: UUID, plant_id: UUID) -> Plant:
        """A plant that can still be changed: history entries are read-only."""
        plant = await self.get_plant(user_id, plant_id)
        if plant.ended_at is not None:
            raise ValidationError(
                "Tracking tanaman ini sudah diakhiri.", details={"field": "plant_id"}
            )
        return plant

    async def create_plant(self, user_id: UUID, farm_id: UUID, payload: PlantCreate) -> PlantOut:
        farm = await self.session.get(Farm, farm_id)
        if farm is None or farm.user_id != user_id:
            raise NotFound("Lahan tidak ditemukan.")
        if farm.archived_at is not None:
            raise ValidationError("Lahan ini sudah diarsipkan.", details={"field": "farm_id"})

        material = (
            payload.planting_material.value
            if payload.planting_material
            else DEFAULT_MATERIAL[payload.commodity_code]
        )
        until = await self._productive_until(payload.commodity_code, material, payload.planted_at)

        plant = Plant(
            id=uuid4(),
            farm_id=farm_id,
            user_id=user_id,
            code=await self._next_code(user_id, payload.commodity_code),
            commodity_code=payload.commodity_code,
            planting_material=material,
            variety=payload.variety,
            label=payload.label,
            planted_at=payload.planted_at,
            quantity=payload.quantity,
            productive_until=until,
            health_status=HealthStatus.UNKNOWN.value,
            irrigation_schedule=payload.irrigation_schedule.value,
        )
        self.session.add(plant)
        await self.session.commit()
        return await self._plant_out(plant)

    async def update_plant(self, user_id: UUID, plant_id: UUID, payload: PlantUpdate) -> PlantOut:
        plant = await self.get_active_plant(user_id, plant_id)
        data = payload.model_dump(exclude_unset=True)
        if "planting_material" in data:
            material = data["planting_material"].value
            if material not in MATERIALS_BY_COMMODITY[plant.commodity_code]:
                raise ValidationError(
                    "Jenis bibit ini tidak dipakai untuk tanaman tersebut.",
                    details={"field": "planting_material"},
                )
            data["planting_material"] = material
        if "irrigation_schedule" in data:
            data["irrigation_schedule"] = data["irrigation_schedule"].value

        if "planted_at" in data or "planting_material" in data:
            planted_at = data.get("planted_at", plant.planted_at)
            first = (
                await self.session.execute(
                    select(func.min(HarvestRecord.harvested_at)).where(
                        HarvestRecord.plant_id == plant.id
                    )
                )
            ).scalar_one()
            if first is not None and planted_at > local_date(first, self.tz):
                raise ValidationError(
                    "Tanggal tanam tidak boleh setelah panen pertama.",
                    details={"field": "planted_at"},
                )
            plant.productive_until = await self._productive_until(
                plant.commodity_code,
                data.get("planting_material", plant.planting_material),
                planted_at,
            )
        for key, value in data.items():
            setattr(plant, key, value)
        await self.session.commit()
        return await self._plant_out(plant)

    async def end_tracking(self, user_id: UUID, plant_id: UUID, payload: EndTracking) -> PlantOut:
        """End tracking before the productive period is over (design 8.6)."""
        plant = await self.get_active_plant(user_id, plant_id)
        reason = payload.reason.value
        codes = list(dict.fromkeys(payload.disease_codes))
        problem = rules.end_request_error(
            reason=reason, disease_codes=codes, cause_note=payload.cause_note, note=payload.note
        )
        if problem:
            raise ValidationError(problem, details={"field": "reason"})
        if codes:
            known = set(
                (
                    await self.session.execute(
                        select(Disease.code).where(
                            Disease.code.in_(codes), Disease.commodity_code == plant.commodity_code
                        )
                    )
                ).scalars()
            )
            unknown = [code for code in codes if code not in known]
            if unknown:
                raise ValidationError(
                    "Ada penyakit yang tidak dikenal untuk jenis tanaman ini.",
                    details={"field": "disease_codes", "unknown": unknown},
                )
        await end_plant(
            self.session,
            self.settings,
            plant,
            reason=reason,
            note=payload.note,
            disease_codes=codes,
            cause_note=payload.cause_note,
        )
        await self.session.commit()
        return await self._plant_out(plant)

    # ------------------------------------------------------------------ #
    # Harvests (panen ke-n)
    # ------------------------------------------------------------------ #
    async def list_harvests(self, user_id: UUID, plant_id: UUID) -> list[HarvestOut]:
        plant = await self.get_plant(user_id, plant_id)
        return [self._harvest_out(row, None) for row in await self._harvest_rows(plant.id)]

    async def record_harvest(
        self, user_id: UUID, plant_id: UUID, payload: HarvestCreate
    ) -> HarvestOut:
        plant = await self.get_active_plant(user_id, plant_id)
        rows = await self._harvest_rows(plant.id)
        day = self._harvest_day(payload.harvested_at)
        previous = local_date(rows[-1].harvested_at, self.tz) if rows else None
        self._check_harvest_day(day, plant, previous=previous, following=None)

        record = HarvestRecord(
            id=uuid4(),
            plant_id=plant.id,
            recorded_by=user_id,
            harvested_at=noon_utc(day, self.tz),
            sequence=len(rows) + 1,
            quality_note=payload.quality_note,
            quantity_kg=payload.quantity_kg,
        )
        self.session.add(record)
        await self.session.commit()
        return await self._harvest_out_with_estimate(plant, record)

    async def update_harvest(
        self, user_id: UUID, plant_id: UUID, harvest_id: UUID, payload: HarvestUpdate
    ) -> HarvestOut:
        plant = await self.get_active_plant(user_id, plant_id)
        rows = await self._harvest_rows(plant.id)
        record = next((row for row in rows if row.id == harvest_id), None)
        if record is None:
            raise NotFound("Catatan panen tidak ditemukan.")
        data = payload.model_dump(exclude_unset=True)
        if data.get("harvested_at") is not None:
            day = self._harvest_day(data["harvested_at"])
            index = rows.index(record)
            previous = local_date(rows[index - 1].harvested_at, self.tz) if index > 0 else None
            following = (
                local_date(rows[index + 1].harvested_at, self.tz) if index + 1 < len(rows) else None
            )
            self._check_harvest_day(day, plant, previous=previous, following=following)
            record.harvested_at = noon_utc(day, self.tz)
        if "quality_note" in data:
            record.quality_note = data["quality_note"]
        if "quantity_kg" in data:
            record.quantity_kg = data["quantity_kg"]
        await self.session.flush()
        await self._renumber(plant.id)
        await self.session.commit()
        return await self._harvest_out_with_estimate(plant, record)

    async def delete_harvest(self, user_id: UUID, plant_id: UUID, harvest_id: UUID) -> None:
        plant = await self.get_active_plant(user_id, plant_id)
        record = await self.session.get(HarvestRecord, harvest_id)
        if record is None or record.plant_id != plant.id:
            raise NotFound("Catatan panen tidak ditemukan.")
        await self.session.delete(record)
        await self.session.flush()
        await self._renumber(plant.id)
        await self.session.commit()

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
            top = scan.result.get("top")
            code = top.get("disease_code") if isinstance(top, dict) else None
            label = (top.get("label") if isinstance(top, dict) else None) or DISEASE_LABELS.get(
                str(code), "Tidak teridentifikasi"
            )
            title = f"Scan daun: {label}" if code else "Scan daun: belum bisa dipastikan"
            entries.append(
                TimelineEntry(
                    kind="scan",
                    occurred_at=scan.captured_at,
                    id=str(scan.id),
                    title=title,
                    subtitle=scan.status,
                    payload={
                        "status": scan.status,
                        "disease_code": scan.disease_code,
                        "disease_episode_id": str(scan.disease_episode_id)
                        if scan.disease_episode_id
                        else None,
                    },
                )
            )

        for harvest in await self._harvest_rows(plant.id):
            quantity = (
                f"{float(harvest.quantity_kg):g} kg" if harvest.quantity_kg is not None else None
            )
            entries.append(
                TimelineEntry(
                    kind="harvest",
                    occurred_at=harvest.harvested_at,
                    id=str(harvest.id),
                    title=f"Panen ke-{harvest.sequence}",
                    subtitle=quantity,
                    payload={"sequence": harvest.sequence},
                )
            )

        episode_list = list(
            (
                await self.session.execute(
                    select(DiseaseEpisode).where(DiseaseEpisode.plant_id == plant.id)
                )
            ).scalars()
        )
        names = await self.estimator.disease_names([e.disease_code for e in episode_list])
        for episode in episode_list:
            name = names.get(episode.disease_code, episode.disease_code)
            entries.append(
                TimelineEntry(
                    kind="episode_opened",
                    occurred_at=episode.opened_at,
                    id=str(episode.id),
                    title=f"Penyakit dikonfirmasi: {name}",
                    subtitle=(
                        f"Perkiraan panen mundur {episode.delay_days} hari"
                        if episode.delay_days
                        else None
                    ),
                    payload={
                        "disease_code": episode.disease_code,
                        "delay_days": episode.delay_days,
                    },
                )
            )
            if episode.resolved_at is not None:
                entries.append(
                    TimelineEntry(
                        kind="episode_resolved",
                        occurred_at=episode.resolved_at,
                        # A different id from the "opened" entry keeps the paging key unique.
                        id=str(uuid5(NAMESPACE_URL, f"episode-resolved:{episode.id}")),
                        title=f"Penyakit sembuh: {name}",
                        subtitle=episode.close_reason,
                        payload={"episode_id": str(episode.id)},
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
                    payload={"outcome": plant.outcome, "note": plant.end_note},
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

        # The same state machine that sets ``plants.health_status`` (design 8.7),
        # replayed point by point, so the chart and the badge never disagree.
        health_series: list[HealthPoint] = []
        current = HealthStatus.UNKNOWN.value
        for scan in scans:
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

        harvests = await self._harvest_rows(plant.id)
        harvest_series = [
            HarvestPoint(
                date=local_date(row.harvested_at, self.tz),
                sequence=row.sequence,
                quantity_kg=float(row.quantity_kg) if row.quantity_kg is not None else None,
            )
            for row in harvests
        ]

        facts = await self.estimator.facts_for(plant)
        estimate_vs_actual: list[EstimateVsActual] = []
        if facts.profile is not None:
            for index, row in enumerate(harvests):
                actual = local_date(row.harvested_at, self.tz)
                # What was expected at the time: only what was known on that day.
                spans = [
                    rules.EpisodeSpan(
                        span.episode_id,
                        span.disease_code,
                        span.opened_on,
                        span.resolved_on
                        if span.resolved_on and span.resolved_on <= actual
                        else None,
                        span.delay_days,
                    )
                    for span in (episode_span(e, self.tz) for e in facts.episodes)
                    if span.opened_on <= actual
                ]
                window = rules.next_harvest(
                    planted_at=plant.planted_at,
                    harvest_dates=[
                        local_date(prior.harvested_at, self.tz) for prior in harvests[:index]
                    ],
                    episodes=spans,
                    profile=facts.profile,
                    today=actual,
                    max_delay_days=MAX_DELAY_DAYS_PER_CYCLE,
                )
                estimate_vs_actual.append(
                    EstimateVsActual(
                        sequence=row.sequence,
                        estimated_date_min=window.start if window else None,
                        estimated_date_max=window.end if window else None,
                        harvested_at=actual,
                        within_range=(window.start <= actual <= window.end) if window else None,
                    )
                )

        return PlantStats(
            health_series=health_series,
            harvest_series=harvest_series,
            estimate_vs_actual=estimate_vs_actual,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _productive_until(
        self, commodity_code: str, planting_material: str, planted_at: date
    ) -> date:
        profile = await self.estimator.profile_for(commodity_code, planting_material)
        if profile is None:
            raise ValidationError(
                "Profil tanaman untuk jenis dan bibit ini belum tersedia.",
                details={"field": "planting_material"},
            )
        until = rules.productive_until(planted_at, profile.productive_years)
        if until <= self.estimator.today():
            raise ValidationError(
                "Tanaman dengan tanggal tanam ini sudah melewati masa produktif.",
                details={"field": "planted_at", "productive_until": until.isoformat()},
            )
        return until

    async def _next_code(self, user_id: UUID, commodity_code: str) -> str:
        """``MGA-001``: the per-user counter is locked and never reused (design 8.2)."""
        user = (
            await self.session.execute(select(User).where(User.id == user_id).with_for_update())
        ).scalar_one()
        counters = dict(user.plant_code_seq or {})
        number = int(counters.get(commodity_code, 0)) + 1
        counters[commodity_code] = number
        user.plant_code_seq = counters
        return f"{PLANT_CODE_PREFIX[commodity_code]}-{number:03d}"

    async def _harvest_rows(self, plant_id: UUID) -> list[HarvestRecord]:
        rows = await self.session.execute(
            select(HarvestRecord)
            .where(HarvestRecord.plant_id == plant_id)
            .order_by(HarvestRecord.harvested_at, HarvestRecord.created_at, HarvestRecord.id)
        )
        return list(rows.scalars())

    async def _renumber(self, plant_id: UUID) -> None:
        """Panen ke-n follows the harvest date; the unique key is checked at commit."""
        for number, row in enumerate(await self._harvest_rows(plant_id), start=1):
            if row.sequence != number:
                row.sequence = number

    def _harvest_day(self, value: date | datetime | None) -> date:
        if value is None:
            return self.estimator.today()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValidationError(
                    "harvested_at wajib memakai zona waktu atau berupa tanggal (YYYY-MM-DD).",
                    details={"field": "harvested_at"},
                )
            return value.astimezone(self.tz).date()
        return value

    def _check_harvest_day(
        self, day: date, plant: Plant, *, previous: date | None, following: date | None
    ) -> None:
        problem = rules.harvest_date_error(
            day, planted_at=plant.planted_at, today=self.estimator.today(), previous=previous
        )
        if problem is None and following is not None and day > following:
            problem = "Tanggal panen tidak boleh setelah panen berikutnya."
        if problem:
            raise ValidationError(problem, details={"field": "harvested_at"})

    def _harvest_out(self, row: HarvestRecord, estimate: NextHarvestOut | None) -> HarvestOut:
        return HarvestOut(
            id=str(row.id),
            plant_id=str(row.plant_id),
            sequence=row.sequence,
            harvested_at=local_date(row.harvested_at, self.tz),
            quality_note=row.quality_note,
            quantity_kg=float(row.quantity_kg) if row.quantity_kg is not None else None,
            created_at=row.created_at,
            next_harvest=estimate,
        )

    async def _harvest_out_with_estimate(self, plant: Plant, row: HarvestRecord) -> HarvestOut:
        facts = await self.estimator.facts_for(plant)
        delays = facts.next_harvest.delays if facts.next_harvest else ()
        names = await self.estimator.disease_names([item.disease_code for item in delays])
        return self._harvest_out(row, next_harvest_out(facts.next_harvest, names))

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
        facts = await self.estimator.facts(plants)
        wanted: set[str] = set()
        for plant in plants:
            item = facts[plant.id]
            wanted.update(plant.end_disease_codes or [])
            if item.next_harvest:
                wanted.update(delay.disease_code for delay in item.next_harvest.delays)
        names = await self.estimator.disease_names(sorted(wanted))
        return [
            self._plant_out_with(plant, extras[plant.id], facts[plant.id], names)
            for plant in plants
        ]

    async def _plant_out(self, plant: Plant) -> PlantOut:
        return (await self._plants_out([plant]))[0]

    def _plant_out_with(
        self, plant: Plant, extra: dict[str, object], facts: PlantFacts, names: dict[str, str]
    ) -> PlantOut:
        farm = extra["farm"]
        assert isinstance(farm, Farm)  # noqa: S101 - built by _extras
        last_scan = extra["last_scan"] if isinstance(extra["last_scan"], datetime) else None
        last_water = extra["last_water"] if isinstance(extra["last_water"], datetime) else None
        cover = extra["cover"] if isinstance(extra["cover"], str) else None
        village = extra["village"] if isinstance(extra["village"], str) else None
        end_day = (plant.ended_at or datetime.now(UTC)).astimezone(self.tz).date()
        return PlantOut(
            id=str(plant.id),
            code=plant.code,
            farm_id=str(plant.farm_id),
            label=plant.label,
            commodity_code=plant.commodity_code,
            commodity_label=COMMODITY_LABELS_V2.get(plant.commodity_code, plant.commodity_code),
            variety=plant.variety,
            planting_material=plant.planting_material,
            quantity=plant.quantity,
            planted_at=plant.planted_at,
            age_days=rules.age_days(plant.planted_at, end_day),
            lifecycle_phase=facts.phase,
            productive_until=plant.productive_until,
            health_status=plant.health_status,
            health_status_reason=self._health_reason(plant, last_scan),
            harvest_count=facts.harvest_count,
            last_harvest_at=facts.last_harvest,
            next_harvest=next_harvest_out(facts.next_harvest, names),
            open_episode_count=facts.open_episode_count,
            irrigation_schedule=plant.irrigation_schedule,
            last_watered_at=last_water,
            next_watering_on=next_watering_on(plant, last_water, self.tz),
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
            end_diseases=[
                EndedDiseaseOut(code=code, label=names.get(code, code))
                for code in (plant.end_disease_codes or [])
            ],
            end_cause_note=plant.end_cause_note,
            outcome=plant.outcome,
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
