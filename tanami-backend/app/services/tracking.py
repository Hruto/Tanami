"""Growth photos and care logs of tracked plants (requirements 1-2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound, ValidationError
from app.domain import CareAction
from app.models.tracking import CareLog, PlantPhoto
from app.providers.images import new_object_key, validate_and_normalise
from app.providers.storage import StorageProvider
from app.schemas.farm import CareLogCreate, CareLogOut, PhotoOut
from app.services.farm import PlantService


class TrackingService:
    def __init__(self, session: AsyncSession, settings: Settings, storage: StorageProvider) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage
        self.plants = PlantService(session, settings, storage)

    # ------------------------------------------------------------------ #
    # Photos
    # ------------------------------------------------------------------ #
    async def add_photo(
        self,
        user_id: UUID,
        plant_id: UUID,
        *,
        raw: bytes,
        caption: str | None,
        taken_at: datetime | None,
    ) -> PhotoOut:
        plant = await self.plants.get_active_plant(user_id, plant_id)
        moment = _past_or_now(taken_at, field="taken_at")
        validated = validate_and_normalise(
            raw,
            max_bytes=self.settings.max_scan_upload_bytes,
            max_side=self.settings.max_image_side,
            max_pixels=self.settings.max_image_pixels,
        )
        key = new_object_key("plants", user_id=str(user_id), extension=validated.extension)
        await self.storage.put(key, validated.data, validated.content_type)
        photo = PlantPhoto(
            id=uuid4(),
            plant_id=plant.id,
            user_id=user_id,
            image_key=key,
            caption=(caption or "").strip() or None,
            taken_at=moment,
        )
        self.session.add(photo)
        await self.session.commit()
        return self.photo_out(photo)

    async def list_photos(self, user_id: UUID, plant_id: UUID) -> list[PhotoOut]:
        plant = await self.plants.get_plant(user_id, plant_id)
        rows = (
            await self.session.execute(
                select(PlantPhoto)
                .where(PlantPhoto.plant_id == plant.id)
                .order_by(PlantPhoto.taken_at.desc(), PlantPhoto.id.desc())
            )
        ).scalars()
        return [self.photo_out(photo) for photo in rows]

    async def delete_photo(self, user_id: UUID, plant_id: UUID, photo_id: UUID) -> None:
        plant = await self.plants.get_plant(user_id, plant_id)
        photo = await self.session.get(PlantPhoto, photo_id)
        if photo is None or photo.plant_id != plant.id:
            raise NotFound("Foto tidak ditemukan.")
        key = photo.image_key
        await self.session.delete(photo)
        await self.session.commit()
        await self.storage.delete(key)

    def photo_out(self, photo: PlantPhoto) -> PhotoOut:
        return PhotoOut(
            id=str(photo.id),
            plant_id=str(photo.plant_id),
            image_url=self.storage.public_url(photo.image_key),
            caption=photo.caption,
            taken_at=photo.taken_at,
            created_at=photo.created_at,
        )

    # ------------------------------------------------------------------ #
    # Care logs (watering history included)
    # ------------------------------------------------------------------ #
    async def add_care_log(
        self, user_id: UUID, plant_id: UUID, payload: CareLogCreate
    ) -> CareLogOut:
        plant = await self.plants.get_active_plant(user_id, plant_id)
        log = CareLog(
            id=uuid4(),
            plant_id=plant.id,
            user_id=user_id,
            action=payload.action.value,
            note=(payload.note or "").strip() or None,
            performed_at=payload.performed_at or datetime.now(UTC),
        )
        self.session.add(log)
        await self.session.commit()
        return care_log_out(log)

    async def list_care_logs(
        self, user_id: UUID, plant_id: UUID, *, action: CareAction | None
    ) -> list[CareLogOut]:
        plant = await self.plants.get_plant(user_id, plant_id)
        query = select(CareLog).where(CareLog.plant_id == plant.id)
        if action is not None:
            query = query.where(CareLog.action == action.value)
        rows = (
            await self.session.execute(
                query.order_by(CareLog.performed_at.desc(), CareLog.id.desc())
            )
        ).scalars()
        return [care_log_out(log) for log in rows]

    async def delete_care_log(self, user_id: UUID, plant_id: UUID, log_id: UUID) -> None:
        plant = await self.plants.get_active_plant(user_id, plant_id)
        log = await self.session.get(CareLog, log_id)
        if log is None or log.plant_id != plant.id:
            raise NotFound("Catatan perawatan tidak ditemukan.")
        await self.session.delete(log)
        await self.session.commit()


def care_log_out(log: CareLog) -> CareLogOut:
    return CareLogOut(
        id=str(log.id),
        plant_id=str(log.plant_id),
        action=CareAction(log.action),
        note=log.note,
        performed_at=log.performed_at,
        created_at=log.created_at,
    )


def _past_or_now(value: datetime | None, *, field: str) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value > datetime.now(UTC) + timedelta(minutes=5):
        raise ValidationError("Waktu tidak boleh di masa depan.", details={"field": field})
    return value.astimezone(UTC)
