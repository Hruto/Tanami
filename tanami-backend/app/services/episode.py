"""Disease episodes: confirming a scan, resolving, and closing (design 8.5).

An episode is opened only by the user ("Ya, tanaman ini sakit") on a
``confident`` disease scan, never by the model alone. Confirming the same disease
again attaches to the open episode instead of adding another delay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound, ValidationError
from app.domain import (
    CauseCategory,
    EpisodeCloseReason,
    EpisodeStatus,
    ResultStatus,
)
from app.models.content import Disease
from app.models.episode import DiseaseEpisode
from app.models.farm import Plant
from app.models.scan import Scan
from app.schemas.farm import EpisodeOut, NextHarvestOut
from app.schemas.scan import ConfirmationOut
from app.services import harvest as rules
from app.services.estimate import (
    MAX_DELAY_DAYS_PER_CYCLE,
    Estimator,
    episode_span,
    next_harvest_out,
)


@dataclass(frozen=True)
class ConfirmResult:
    episode: DiseaseEpisode
    plant: Plant
    is_new: bool


class EpisodeService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.estimator = Estimator(session, settings)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def get_owned(self, user_id: UUID, episode_id: UUID) -> DiseaseEpisode:
        episode = await self.session.get(DiseaseEpisode, episode_id)
        plant = await self.session.get(Plant, episode.plant_id) if episode else None
        if episode is None or plant is None or plant.user_id != user_id:
            raise NotFound("Episode penyakit tidak ditemukan.")
        return episode

    async def list_out(self, plant: Plant, *, status: str | None = None) -> list[EpisodeOut]:
        query = select(DiseaseEpisode).where(DiseaseEpisode.plant_id == plant.id)
        if status is not None:
            query = query.where(DiseaseEpisode.status == status)
        episodes = list(
            (await self.session.execute(query.order_by(DiseaseEpisode.opened_at.desc()))).scalars()
        )
        return await self.to_out(episodes)

    async def to_out(self, episodes: list[DiseaseEpisode]) -> list[EpisodeOut]:
        if not episodes:
            return []
        names = await self.estimator.disease_names([e.disease_code for e in episodes])
        scan_rows = await self.session.execute(
            select(Scan.disease_episode_id, Scan.id)
            .where(Scan.disease_episode_id.in_([e.id for e in episodes]))
            .order_by(Scan.captured_at)
        )
        scans: dict[UUID, list[str]] = {}
        for episode_id, scan_id in scan_rows.all():
            scans.setdefault(episode_id, []).append(str(scan_id))
        return [
            EpisodeOut(
                id=str(e.id),
                plant_id=str(e.plant_id),
                disease_code=e.disease_code,
                label=names.get(e.disease_code, e.disease_code),
                status="open" if e.status == EpisodeStatus.OPEN.value else "resolved",
                opened_at=e.opened_at,
                last_seen_at=e.last_seen_at,
                delay_days=e.delay_days,
                resolved_at=e.resolved_at,
                close_reason=e.close_reason,
                scan_ids=scans.get(e.id, []),
            )
            for e in episodes
        ]

    async def next_harvest_for(self, plant: Plant) -> NextHarvestOut | None:
        """The plant's current estimate, for responses that just changed it."""
        facts = await self.estimator.facts_for(plant)
        delays = facts.next_harvest.delays if facts.next_harvest else ()
        names = await self.estimator.disease_names([item.disease_code for item in delays])
        return next_harvest_out(facts.next_harvest, names)

    async def confirmation_for(
        self, scan: Scan, plant: Plant, disease: Disease | None
    ) -> ConfirmationOut:
        """The block that rides on a scan response (design 10.6)."""
        confirmable = (
            scan.status == ResultStatus.CONFIDENT.value
            and disease is not None
            and disease.cause_category != CauseCategory.HEALTHY.value
            and plant.ended_at is None
        )
        if not confirmable or disease is None:
            return ConfirmationOut(can_confirm=False)

        facts = await self.estimator.facts_for(plant)
        existing = next(
            (
                episode
                for episode in facts.episodes
                if episode.disease_code == disease.code and episode.status == "open"
            ),
            None,
        )
        preview = rules.delay_preview_days(
            disease_delay_days=disease.harvest_delay_days,
            episodes=[episode_span(episode, self.estimator.tz) for episode in facts.episodes],
            disease_code=disease.code,
            cycle_start_on=rules.cycle_start(plant.planted_at, facts.last_harvest),
            max_delay_days=MAX_DELAY_DAYS_PER_CYCLE,
        )
        return ConfirmationOut(
            can_confirm=True,
            existing_episode_id=str(existing.id) if existing else None,
            delay_preview_days=preview,
        )

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    async def confirm(self, user_id: UUID, scan_id: UUID) -> ConfirmResult:
        scan = await self.session.get(Scan, scan_id)
        if scan is None or scan.user_id != user_id:
            raise NotFound("Scan tidak ditemukan.")
        plant = await self.session.get(Plant, scan.plant_id)
        if plant is None:  # pragma: no cover - scans.plant_id is NOT NULL with a FK
            raise NotFound("Tanaman tidak ditemukan.")

        if scan.disease_episode_id is not None:  # already confirmed: same answer again
            episode = await self.session.get(DiseaseEpisode, scan.disease_episode_id)
            if episode is not None:
                return ConfirmResult(episode, plant, is_new=False)

        if plant.ended_at is not None:
            raise ValidationError(
                "Tracking tanaman ini sudah diakhiri.", details={"field": "scan_id"}
            )
        disease = (
            await self.session.execute(select(Disease).where(Disease.code == scan.disease_code))
        ).scalar_one_or_none()
        if (
            scan.status != ResultStatus.CONFIDENT.value
            or disease is None
            or disease.cause_category == CauseCategory.HEALTHY.value
        ):
            raise ValidationError(
                "Hanya hasil scan yang yakin dan menyebut penyakit yang bisa dikonfirmasi.",
                details={"field": "scan_id"},
            )

        existing = await self._open_episode(plant.id, disease.code)
        if existing is not None:
            return await self._attach(scan, plant, existing)

        episode = DiseaseEpisode(
            id=uuid4(),
            plant_id=plant.id,
            disease_code=disease.code,
            status=EpisodeStatus.OPEN.value,
            opened_at=scan.captured_at,
            opened_by_scan_id=scan.id,
            last_seen_at=scan.captured_at,
            delay_days=disease.harvest_delay_days,
        )
        self.session.add(episode)
        try:
            await self.session.flush()
        except IntegrityError:
            # A parallel confirmation opened it first; join that one instead.
            await self.session.rollback()
            scan = await self.session.get(Scan, scan_id) or scan
            plant = await self.session.get(Plant, plant.id) or plant
            winner = await self._open_episode(plant.id, disease.code)
            if winner is None:
                raise
            return await self._attach(scan, plant, winner)
        scan.disease_episode_id = episode.id
        await self.session.commit()
        return ConfirmResult(episode, plant, is_new=True)

    async def resolve(self, user_id: UUID, episode_id: UUID) -> DiseaseEpisode:
        episode = await self.get_owned(user_id, episode_id)
        if episode.status == EpisodeStatus.OPEN.value:
            episode.status = EpisodeStatus.RESOLVED.value
            episode.resolved_at = datetime.now(UTC)
            episode.close_reason = EpisodeCloseReason.USER_MARKED_HEALED.value
            await self.session.commit()
        return episode

    async def close_open(
        self,
        plant_id: UUID,
        reason: EpisodeCloseReason,
        *,
        at: datetime | None = None,
        opened_before: datetime | None = None,
    ) -> list[UUID]:
        """Close open episodes of a plant; returns the ids that were closed.

        ``opened_before`` limits it to episodes opened at or before that moment, so
        an old healthy photo delivered late by the offline queue cannot close an
        episode that started after it.
        """
        moment = at or datetime.now(UTC)
        conditions = [
            DiseaseEpisode.plant_id == plant_id,
            DiseaseEpisode.status == EpisodeStatus.OPEN.value,
        ]
        if opened_before is not None:
            conditions.append(DiseaseEpisode.opened_at <= opened_before)
        rows = await self.session.execute(
            update(DiseaseEpisode)
            .where(*conditions)
            .values(
                status=EpisodeStatus.RESOLVED.value,
                resolved_at=moment,
                close_reason=reason.value,
            )
            .returning(DiseaseEpisode.id)
        )
        return [row[0] for row in rows.all()]

    # ------------------------------------------------------------------ #
    async def _open_episode(self, plant_id: UUID, disease_code: str) -> DiseaseEpisode | None:
        return (
            await self.session.execute(
                select(DiseaseEpisode).where(
                    DiseaseEpisode.plant_id == plant_id,
                    DiseaseEpisode.disease_code == disease_code,
                    DiseaseEpisode.status == EpisodeStatus.OPEN.value,
                )
            )
        ).scalar_one_or_none()

    async def _attach(self, scan: Scan, plant: Plant, episode: DiseaseEpisode) -> ConfirmResult:
        scan.disease_episode_id = episode.id
        episode.last_seen_at = max(episode.last_seen_at, scan.captured_at)
        await self.session.commit()
        return ConfirmResult(episode, plant, is_new=False)
