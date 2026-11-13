"""Loads what the pure harvest rules need and applies them to plants.

``app/services/harvest.py`` holds the rules; this module only fetches rows (crop
profiles, harvest dates, episodes) in a few batched queries and feeds them in, so
a list of fifty plants costs three queries, not a hundred and fifty.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain import LifecyclePhase, profile_material
from app.models.content import CropProfile, Disease
from app.models.episode import DiseaseEpisode
from app.models.farm import HarvestRecord, Plant
from app.schemas.farm import DelayItemOut, NextHarvestOut
from app.services import harvest as rules

# The ceiling on how far diseases can push one cycle back (design 8.4) [USULAN].
MAX_DELAY_DAYS_PER_CYCLE = rules.DEFAULT_MAX_DELAY_DAYS_PER_CYCLE


@dataclass
class PlantFacts:
    """Everything derived for one plant."""

    harvest_dates: list[date] = field(default_factory=list)
    episodes: list[DiseaseEpisode] = field(default_factory=list)
    profile: rules.CropProfile | None = None
    phase: LifecyclePhase = LifecyclePhase.JUVENILE
    next_harvest: rules.NextHarvest | None = None

    @property
    def harvest_count(self) -> int:
        return len(self.harvest_dates)

    @property
    def last_harvest(self) -> date | None:
        return max(self.harvest_dates) if self.harvest_dates else None

    @property
    def open_episode_count(self) -> int:
        return sum(1 for episode in self.episodes if episode.status == "open")


def row_to_profile(row: CropProfile) -> rules.CropProfile:
    return rules.CropProfile(
        first_harvest_min_days=row.first_harvest_min_days,
        first_harvest_max_days=row.first_harvest_max_days,
        harvest_cycle_min_days=row.harvest_cycle_min_days,
        harvest_cycle_max_days=row.harvest_cycle_max_days,
        productive_years=row.productive_years,
    )


def local_date(moment: datetime, tz: ZoneInfo) -> date:
    return moment.astimezone(tz).date()


def noon_utc(day: date, tz: ZoneInfo) -> datetime:
    """A harvest is a day, stored as local noon so no timezone can move it to another day."""
    return datetime.combine(day, time(12, 0), tzinfo=tz).astimezone(UTC)


def episode_span(episode: DiseaseEpisode, tz: ZoneInfo) -> rules.EpisodeSpan:
    return rules.EpisodeSpan(
        episode_id=str(episode.id),
        disease_code=episode.disease_code,
        opened_on=local_date(episode.opened_at, tz),
        resolved_on=local_date(episode.resolved_at, tz) if episode.resolved_at else None,
        delay_days=episode.delay_days,
    )


class Estimator:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.tz = ZoneInfo(settings.timezone)
        self._profiles: dict[tuple[str, str], rules.CropProfile] | None = None

    def today(self) -> date:
        return datetime.now(self.tz).date()

    async def profiles(self) -> dict[tuple[str, str], rules.CropProfile]:
        if self._profiles is None:
            rows = (await self.session.execute(select(CropProfile))).scalars()
            self._profiles = {
                (row.commodity_code, row.planting_material): row_to_profile(row) for row in rows
            }
        return self._profiles

    async def profile_for(
        self, commodity_code: str, planting_material: str
    ) -> rules.CropProfile | None:
        profiles = await self.profiles()
        return profiles.get((commodity_code, profile_material(commodity_code, planting_material)))

    async def facts(self, plants: Sequence[Plant]) -> dict[UUID, PlantFacts]:
        """Facts for many plants; the estimate is only computed for active ones."""
        ids = [plant.id for plant in plants]
        facts = {plant.id: PlantFacts() for plant in plants}
        if not ids:
            return facts

        harvests = await self.session.execute(
            select(HarvestRecord.plant_id, HarvestRecord.harvested_at).where(
                HarvestRecord.plant_id.in_(ids)
            )
        )
        for plant_id, moment in harvests.all():
            facts[plant_id].harvest_dates.append(local_date(moment, self.tz))
        episodes = await self.session.execute(
            select(DiseaseEpisode)
            .where(DiseaseEpisode.plant_id.in_(ids))
            .order_by(DiseaseEpisode.opened_at)
        )
        for episode in episodes.scalars():
            facts[episode.plant_id].episodes.append(episode)

        today = self.today()
        for plant in plants:
            item = facts[plant.id]
            item.harvest_dates.sort()
            item.profile = await self.profile_for(plant.commodity_code, plant.planting_material)
            if item.profile is None:
                continue
            item.phase = rules.lifecycle_phase(
                plant.planted_at, today, item.harvest_count, item.profile
            )
            if plant.ended_at is None:
                item.next_harvest = rules.next_harvest(
                    planted_at=plant.planted_at,
                    harvest_dates=item.harvest_dates,
                    episodes=[episode_span(episode, self.tz) for episode in item.episodes],
                    profile=item.profile,
                    today=today,
                    max_delay_days=MAX_DELAY_DAYS_PER_CYCLE,
                )
        return facts

    async def facts_for(self, plant: Plant) -> PlantFacts:
        return (await self.facts([plant]))[plant.id]

    async def disease_names(self, codes: Sequence[str]) -> dict[str, str]:
        if not codes:
            return {}
        rows = await self.session.execute(
            select(Disease.code, Disease.name_id).where(Disease.code.in_(set(codes)))
        )
        return dict(rows.tuples().all())


def next_harvest_out(
    value: rules.NextHarvest | None, names: dict[str, str]
) -> NextHarvestOut | None:
    """The API shape of an estimate; ``names`` maps disease codes to display names."""
    if value is None:
        return None
    return NextHarvestOut(
        base_start=value.base_start,
        base_end=value.base_end,
        delay_days=value.delay_days,
        start=value.start,
        end=value.end,
        delays=[
            DelayItemOut(
                episode_id=item.episode_id,
                disease_code=item.disease_code,
                label=names.get(item.disease_code, item.disease_code),
                days=item.days,
                status="open" if item.is_open else "resolved",
            )
            for item in value.delays
        ],
        is_overdue=value.is_overdue,
        delay_capped=value.delay_capped,
    )
