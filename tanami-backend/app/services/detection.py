"""The disease-detection plant list (requirements 3-4).

Separate from tracked plants on purpose: a farmer can check a neighbour plant
or a plant they never track. Ending a detection plant moves it to the history
list; its scans stay, and it can be reactivated without losing them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound, ValidationError
from app.models.scan import Scan
from app.models.tracking import DetectionPlant
from app.providers.storage import StorageProvider
from app.schemas.detection import (
    DetectionPlantCreate,
    DetectionPlantDetailOut,
    DetectionPlantOut,
    DetectionPlantUpdate,
)
from app.schemas.scan import ScanOut
from app.services.farm import PlantService


class DetectionService:
    def __init__(self, session: AsyncSession, settings: Settings, storage: StorageProvider) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage

    async def get(self, user_id: UUID, detection_id: UUID) -> DetectionPlant:
        row = await self.session.get(DetectionPlant, detection_id)
        if row is None or row.user_id != user_id:
            raise NotFound("Tanaman deteksi tidak ditemukan.")
        return row

    async def get_active(self, user_id: UUID, detection_id: UUID) -> DetectionPlant:
        row = await self.get(user_id, detection_id)
        if row.ended_at is not None:
            raise ValidationError(
                "Deteksi tanaman ini sudah diakhiri. Aktifkan kembali untuk memeriksa lagi.",
                details={"field": "detection_plant_id"},
            )
        return row

    async def list_plants(self, user_id: UUID, *, status: str) -> list[DetectionPlantOut]:
        query = select(DetectionPlant).where(DetectionPlant.user_id == user_id)
        if status == "ended":
            query = query.where(DetectionPlant.ended_at.is_not(None)).order_by(
                DetectionPlant.ended_at.desc()
            )
        else:
            query = query.where(DetectionPlant.ended_at.is_(None)).order_by(
                DetectionPlant.created_at.desc()
            )
        rows = list((await self.session.execute(query)).scalars())
        return await self._many_out(rows)

    async def create(self, user_id: UUID, payload: DetectionPlantCreate) -> DetectionPlantOut:
        if payload.plant_id is not None:
            await PlantService(self.session, self.settings).get_plant(user_id, payload.plant_id)
        row = DetectionPlant(
            id=uuid4(),
            user_id=user_id,
            name=payload.name,
            commodity_code=payload.commodity_code,
            plant_id=payload.plant_id,
        )
        self.session.add(row)
        await self.session.commit()
        return (await self._many_out([row]))[0]

    async def update(
        self, user_id: UUID, detection_id: UUID, payload: DetectionPlantUpdate
    ) -> DetectionPlantOut:
        row = await self.get(user_id, detection_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data:
            row.name = data["name"]
        if "plant_id" in data:
            if data["plant_id"] is not None:
                await PlantService(self.session, self.settings).get_plant(user_id, data["plant_id"])
            row.plant_id = data["plant_id"]
        await self.session.commit()
        return (await self._many_out([row]))[0]

    async def end(self, user_id: UUID, detection_id: UUID, note: str | None) -> DetectionPlantOut:
        row = await self.get_active(user_id, detection_id)
        row.ended_at = datetime.now(UTC)
        row.end_note = (note or "").strip() or None
        await self.session.commit()
        return (await self._many_out([row]))[0]

    async def reactivate(self, user_id: UUID, detection_id: UUID) -> DetectionPlantOut:
        row = await self.get(user_id, detection_id)
        row.ended_at = None
        row.end_note = None
        await self.session.commit()
        return (await self._many_out([row]))[0]

    async def detail(self, user_id: UUID, detection_id: UUID) -> DetectionPlantDetailOut:
        from app.services.scan import scan_fields

        row = await self.get(user_id, detection_id)
        scans = list(
            (
                await self.session.execute(
                    select(Scan)
                    .where(Scan.detection_plant_id == row.id)
                    .order_by(Scan.captured_at.desc(), Scan.id.desc())
                )
            ).scalars()
        )
        base = (await self._many_out([row]))[0]
        return DetectionPlantDetailOut(
            **base.model_dump(),
            scans=[ScanOut(**scan_fields(scan, self.storage)) for scan in scans],
        )

    async def _many_out(self, rows: list[DetectionPlant]) -> list[DetectionPlantOut]:
        ids = [row.id for row in rows]
        counts: dict[UUID | None, int] = {}
        latest: dict[UUID | None, Scan] = {}
        if ids:
            count_rows = await self.session.execute(
                select(Scan.detection_plant_id, func.count(Scan.id))
                .where(Scan.detection_plant_id.in_(ids))
                .group_by(Scan.detection_plant_id)
            )
            counts = {row[0]: int(row[1]) for row in count_rows.all()}
            latest_rows = await self.session.execute(
                select(Scan)
                .where(Scan.detection_plant_id.in_(ids))
                .distinct(Scan.detection_plant_id)
                .order_by(Scan.detection_plant_id, Scan.captured_at.desc())
            )
            latest = {scan.detection_plant_id: scan for scan in latest_rows.scalars()}
        return [self._out(row, counts.get(row.id, 0), latest.get(row.id)) for row in rows]

    def _out(self, row: DetectionPlant, count: int, last: Scan | None) -> DetectionPlantOut:
        return DetectionPlantOut(
            id=str(row.id),
            name=row.name,
            commodity_code=row.commodity_code,
            plant_id=str(row.plant_id) if row.plant_id else None,
            status="ended" if row.ended_at else "active",
            ended_at=row.ended_at,
            end_note=row.end_note,
            cover_image_url=self.storage.public_url(last.image_key) if last else None,
            scan_count=count,
            last_result=_headline(last),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _headline(scan: Scan | None) -> dict[str, Any] | None:
    if scan is None:
        return None
    result = scan.result if isinstance(scan.result, dict) else {}
    raw_top = result.get("top")
    top = raw_top if isinstance(raw_top, dict) else {}
    return {
        "scan_id": str(scan.id),
        "status": scan.status,
        "disease_code": top.get("disease_code"),
        "disease_name": top.get("label"),
        "cause_category": top.get("cause_category"),
        "confidence_percent": result.get("confidence_percent"),
        "captured_at": scan.captured_at.isoformat(),
    }
