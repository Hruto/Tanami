"""Farm, plant, history and region routes (``design.md`` 10.5, 10.7)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import (
    CurrentUser,
    FarmServiceDep,
    PlantServiceDep,
    RegionServiceDep,
    TrackingServiceDep,
)
from app.domain import DETECTION_COMMODITIES, PLANT_TYPES, CareAction, TrackingEndReason
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.farm import (
    CareLogCreate,
    CareLogOut,
    EndTracking,
    FarmCreate,
    FarmOut,
    FarmUpdate,
    HarvestCreate,
    HarvestOut,
    PhotoOut,
    PlantCreate,
    PlantOut,
    PlantStats,
    PlantTypeOut,
    PlantUpdate,
    RegionOut,
    TimelineEntry,
)

router = APIRouter(tags=["farms"])


def _list(data: list[object]) -> ListEnvelope[object]:
    return ListEnvelope(data=data, meta=PaginationMeta(next_cursor=None, has_more=False))


# --------------------------------------------------------------------------- #
# Farms
# --------------------------------------------------------------------------- #
@router.get("/farms")
async def list_farms(
    user: CurrentUser,
    service: FarmServiceDep,
    include_archived: bool = False,
) -> ListEnvelope[FarmOut]:
    farms = await service.list_farms(user.id, include_archived=include_archived)
    return ListEnvelope(data=farms, meta=PaginationMeta(next_cursor=None, has_more=False))


@router.post("/farms", status_code=status.HTTP_201_CREATED)
async def create_farm(
    payload: FarmCreate, user: CurrentUser, service: FarmServiceDep
) -> Envelope[FarmOut]:
    farm = await service.create_farm(user.id, **payload.model_dump())
    return Envelope(data=farm)


@router.get("/farms/{farm_id}")
async def get_farm(farm_id: UUID, user: CurrentUser, service: FarmServiceDep) -> Envelope[FarmOut]:
    return Envelope(data=await service.get_farm_out(user.id, farm_id))


@router.patch("/farms/{farm_id}")
async def update_farm(
    farm_id: UUID, payload: FarmUpdate, user: CurrentUser, service: FarmServiceDep
) -> Envelope[FarmOut]:
    return Envelope(data=await service.update_farm(user.id, farm_id, payload))


@router.delete("/farms/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_farm(farm_id: UUID, user: CurrentUser, service: FarmServiceDep) -> Response:
    await service.archive_farm(user.id, farm_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Plants
# --------------------------------------------------------------------------- #
@router.get("/farms/{farm_id}/plants")
async def list_plants(
    farm_id: UUID,
    user: CurrentUser,
    service: PlantServiceDep,
    include_archived: bool = False,
) -> ListEnvelope[PlantOut]:
    plants = await service.list_plants(
        user.id,
        farm_id,
        include_archived=include_archived,
    )
    return ListEnvelope(data=plants, meta=PaginationMeta(next_cursor=None, has_more=False))


@router.post("/farms/{farm_id}/plants", status_code=status.HTTP_201_CREATED)
async def create_plant(
    farm_id: UUID,
    payload: PlantCreate,
    user: CurrentUser,
    service: PlantServiceDep,
) -> Envelope[PlantOut]:
    plant = await service.create_plant(user.id, farm_id, **payload.model_dump())
    return Envelope(data=plant)


@router.get("/plants/{plant_id}")
async def get_plant(
    plant_id: UUID, user: CurrentUser, service: PlantServiceDep
) -> Envelope[PlantOut]:
    return Envelope(data=await service.get_plant_out(user.id, plant_id))


@router.patch("/plants/{plant_id}")
async def update_plant(
    plant_id: UUID, payload: PlantUpdate, user: CurrentUser, service: PlantServiceDep
) -> Envelope[PlantOut]:
    return Envelope(data=await service.update_plant(user.id, plant_id, payload))


@router.delete("/plants/{plant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_plant(plant_id: UUID, user: CurrentUser, service: PlantServiceDep) -> Response:
    """Shorthand for ending tracking with reason ``other`` (design 10.5)."""
    await service.end_tracking(user.id, plant_id, EndTracking(reason=TrackingEndReason.OTHER))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/plant-types")
async def plant_types() -> ListEnvelope[PlantTypeOut]:
    """Dropdown of plant types (requirement 1); detection works for some only."""
    data = [
        PlantTypeOut(code=code, label=label, detection_supported=code in DETECTION_COMMODITIES)
        for code, label in PLANT_TYPES.items()
    ]
    return ListEnvelope(data=data, meta=PaginationMeta())


@router.get("/plants")
async def list_my_plants(
    user: CurrentUser,
    service: PlantServiceDep,
    plant_status: Annotated[Literal["active", "ended"], Query(alias="status")] = "active",
) -> ListEnvelope[PlantOut]:
    """``status=active``: Tracking Tanaman. ``status=ended``: History Tracking."""
    plants = await service.list_user_plants(user.id, status=plant_status)
    return ListEnvelope(data=plants, meta=PaginationMeta())


@router.post("/plants/{plant_id}/end")
async def end_tracking(
    plant_id: UUID, payload: EndTracking, user: CurrentUser, service: PlantServiceDep
) -> Envelope[PlantOut]:
    """Requirement 1: end tracking; reminders for this plant stop."""
    return Envelope(data=await service.end_tracking(user.id, plant_id, payload))


@router.post("/plants/{plant_id}/photos", status_code=status.HTTP_201_CREATED)
async def add_photo(
    plant_id: UUID,
    user: CurrentUser,
    service: TrackingServiceDep,
    image: Annotated[UploadFile, File()],
    caption: Annotated[str | None, Form(max_length=280)] = None,
    taken_at: Annotated[datetime | None, Form()] = None,
) -> Envelope[PhotoOut]:
    """Growth photo (requirement 1); EXIF and GPS are stripped like scans."""
    raw = await image.read()
    photo = await service.add_photo(user.id, plant_id, raw=raw, caption=caption, taken_at=taken_at)
    return Envelope(data=photo)


@router.get("/plants/{plant_id}/photos")
async def list_photos(
    plant_id: UUID, user: CurrentUser, service: TrackingServiceDep
) -> ListEnvelope[PhotoOut]:
    return ListEnvelope(data=await service.list_photos(user.id, plant_id), meta=PaginationMeta())


@router.delete("/plants/{plant_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    plant_id: UUID, photo_id: UUID, user: CurrentUser, service: TrackingServiceDep
) -> Response:
    await service.delete_photo(user.id, plant_id, photo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/plants/{plant_id}/care-logs", status_code=status.HTTP_201_CREATED)
async def add_care_log(
    plant_id: UUID, payload: CareLogCreate, user: CurrentUser, service: TrackingServiceDep
) -> Envelope[CareLogOut]:
    """A care action; ``action=watering`` is the watering history (requirement 2)."""
    return Envelope(data=await service.add_care_log(user.id, plant_id, payload))


@router.get("/plants/{plant_id}/care-logs")
async def list_care_logs(
    plant_id: UUID,
    user: CurrentUser,
    service: TrackingServiceDep,
    action: Annotated[CareAction | None, Query()] = None,
) -> ListEnvelope[CareLogOut]:
    logs = await service.list_care_logs(user.id, plant_id, action=action)
    return ListEnvelope(data=logs, meta=PaginationMeta())


@router.delete("/plants/{plant_id}/care-logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_care_log(
    plant_id: UUID, log_id: UUID, user: CurrentUser, service: TrackingServiceDep
) -> Response:
    await service.delete_care_log(user.id, plant_id, log_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/plants/{plant_id}/harvests", status_code=status.HTTP_201_CREATED)
async def record_harvest(
    plant_id: UUID, payload: HarvestCreate, user: CurrentUser, service: PlantServiceDep
) -> Envelope[HarvestOut]:
    harvest = await service.record_harvest(user.id, plant_id, payload)
    return Envelope(data=harvest)


@router.get("/plants/{plant_id}/timeline")
async def plant_timeline(
    plant_id: UUID,
    user: CurrentUser,
    service: PlantServiceDep,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ListEnvelope[TimelineEntry]:
    """Merged, newest-first events for one plant.

    The events come from three tables, so the cursor is applied to the merged
    in-memory list rather than to a single SQL query. ``limit`` bounds the page.
    """
    from app.core.pagination import decode_cursor, encode_cursor

    entries = await service.timeline(user.id, plant_id)
    if cursor:
        decoded = decode_cursor(cursor)
        entries = [
            entry
            for entry in entries
            if (entry.occurred_at, str(entry.id)) < (decoded.created_at, str(decoded.last_id))
        ]

    page = entries[:limit]
    has_more = len(entries) > limit
    next_cursor = (
        encode_cursor(page[-1].occurred_at, UUID(page[-1].id)) if has_more and page else None
    )
    return ListEnvelope(data=page, meta=PaginationMeta(next_cursor=next_cursor, has_more=has_more))


@router.get("/plants/{plant_id}/stats")
async def plant_stats(
    plant_id: UUID,
    user: CurrentUser,
    service: PlantServiceDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Envelope[PlantStats]:
    stats = await service.stats(
        user.id,
        plant_id,
        date_from=date_from,
        date_to=date_to,
    )
    return Envelope(data=stats)


# --------------------------------------------------------------------------- #
# Regions
# --------------------------------------------------------------------------- #
@router.get("/regions/search")
async def search_regions(
    service: RegionServiceDep,
    q: Annotated[str, Query(min_length=2, max_length=80)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ListEnvelope[RegionOut]:
    regions = await service.search(q, limit=limit)
    return ListEnvelope(data=regions, meta=PaginationMeta(next_cursor=None, has_more=False))


@router.get("/regions/resolve")
async def resolve_region(
    service: RegionServiceDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> Envelope[RegionOut]:
    return Envelope(data=await service.resolve(lat, lon))
