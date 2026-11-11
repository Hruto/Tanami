"""Disease detection plant list and its history (requirements 3-4).

Flow: create a detection plant (just a name), then ``POST /scans`` with
``detection_plant_id`` and the photo. Every later ``POST /scans`` for the same
plant is a manual re-check. Ending moves it to ``?status=ended``; reactivating
keeps every earlier result.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DetectionServiceDep
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.detection import (
    DetectionEnd,
    DetectionPlantCreate,
    DetectionPlantDetailOut,
    DetectionPlantOut,
    DetectionPlantUpdate,
)

router = APIRouter(tags=["detections"])


@router.get("/detection-plants")
async def list_detection_plants(
    user: CurrentUser,
    service: DetectionServiceDep,
    plant_status: Annotated[Literal["active", "ended"], Query(alias="status")] = "active",
) -> ListEnvelope[DetectionPlantOut]:
    """``active``: Daftar Tanaman Deteksi. ``ended``: History Deteksi Penyakit."""
    items = await service.list_plants(user.id, status=plant_status)
    return ListEnvelope(data=items, meta=PaginationMeta())


@router.post("/detection-plants", status_code=status.HTTP_201_CREATED)
async def create_detection_plant(
    payload: DetectionPlantCreate, user: CurrentUser, service: DetectionServiceDep
) -> Envelope[DetectionPlantOut]:
    return Envelope(data=await service.create(user.id, payload))


@router.get("/detection-plants/{detection_id}")
async def get_detection_plant(
    detection_id: UUID, user: CurrentUser, service: DetectionServiceDep
) -> Envelope[DetectionPlantDetailOut]:
    """Detail with every check (photo, disease, confidence, symptoms, advice)."""
    return Envelope(data=await service.detail(user.id, detection_id))


@router.patch("/detection-plants/{detection_id}")
async def update_detection_plant(
    detection_id: UUID,
    payload: DetectionPlantUpdate,
    user: CurrentUser,
    service: DetectionServiceDep,
) -> Envelope[DetectionPlantOut]:
    return Envelope(data=await service.update(user.id, detection_id, payload))


@router.post("/detection-plants/{detection_id}/end")
async def end_detection(
    detection_id: UUID, payload: DetectionEnd, user: CurrentUser, service: DetectionServiceDep
) -> Envelope[DetectionPlantOut]:
    return Envelope(data=await service.end(user.id, detection_id, payload.note))


@router.post("/detection-plants/{detection_id}/reactivate")
async def reactivate_detection(
    detection_id: UUID, user: CurrentUser, service: DetectionServiceDep
) -> Envelope[DetectionPlantOut]:
    return Envelope(data=await service.reactivate(user.id, detection_id))
