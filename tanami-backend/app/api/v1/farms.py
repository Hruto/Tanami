"""Farm, plant, history and region routes (``design.md`` 10.5, 10.7)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import (
    CurrentUser,
    EpisodeServiceDep,
    FarmServiceDep,
    PlantServiceDep,
    RegionServiceDep,
    SessionDep,
    TrackingServiceDep,
)
from app.domain import (
    COMMODITIES_V2,
    COMMODITY_LABELS_V2,
    DEFAULT_MATERIAL,
    DETECTION_COMMODITIES,
    MATERIALS_BY_COMMODITY,
    CareAction,
    TrackingEndReason,
)
from app.models.content import CropProfile
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.farm import (
    CareLogCreate,
    CareLogOut,
    CropProfileOut,
    EndTracking,
    EpisodeOut,
    EpisodeUpdate,
    FarmCreate,
    FarmOut,
    FarmUpdate,
    HarvestCreate,
    HarvestOut,
    HarvestUpdate,
    PhotoOut,
    PlantCreate,
    PlantMaterialOut,
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
    plant = await service.create_plant(user.id, farm_id, payload)
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
    await service.end_tracking(
        user.id,
        plant_id,
        EndTracking(reason=TrackingEndReason.OTHER, note="Dihentikan oleh pengguna."),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_MATERIAL_LABELS = {
    "grafted": "Okulasi/sambung",
    "seed": "Biji",
    "runner": "Anakan (stolon)",
    "other": "Lainnya",
}


@router.get("/plant-types")
async def plant_types(session: SessionDep) -> ListEnvelope[PlantTypeOut]:
    """Dropdown of plant types (mango, citrus, strawberry) with the planting materials allowed."""
    profiles = {
        (row.commodity_code, row.planting_material): row
        for row in (await session.execute(select(CropProfile))).scalars()
    }
    data = []
    for code in COMMODITIES_V2:
        default = DEFAULT_MATERIAL[code]
        row = profiles.get((code, default))
        data.append(
            PlantTypeOut(
                code=code,
                label=COMMODITY_LABELS_V2[code],
                detection_supported=code in DETECTION_COMMODITIES,
                materials=[
                    PlantMaterialOut(
                        code=material,
                        label=_MATERIAL_LABELS[material],
                        is_default=material == default,
                    )
                    for material in MATERIALS_BY_COMMODITY[code]
                ],
                profile_summary=(
                    f"Mulai berbuah sekitar {row.first_harvest_min_days}-"
                    f"{row.first_harvest_max_days} hari setelah tanam"
                    if row
                    else None
                ),
            )
        )
    return ListEnvelope(data=data, meta=PaginationMeta())


@router.get("/crop-profiles")
async def crop_profiles(session: SessionDep) -> ListEnvelope[CropProfileOut]:
    """The agronomic numbers behind the harvest estimate, with their source (design 10.8)."""
    rows = (
        await session.execute(
            select(CropProfile).order_by(CropProfile.commodity_code, CropProfile.planting_material)
        )
    ).scalars()
    return ListEnvelope(
        data=[
            CropProfileOut(
                commodity_code=row.commodity_code,
                planting_material=row.planting_material,
                first_harvest_min_days=row.first_harvest_min_days,
                first_harvest_max_days=row.first_harvest_max_days,
                harvest_cycle_min_days=row.harvest_cycle_min_days,
                harvest_cycle_max_days=row.harvest_cycle_max_days,
                productive_years=row.productive_years,
                harvest_pattern_note=row.harvest_pattern_note,
                source=row.source,
                reviewed_by=row.reviewed_by,
                reviewed_at=row.reviewed_at,
            )
            for row in rows
        ],
        meta=PaginationMeta(),
    )


@router.get("/plants")
async def list_my_plants(
    user: CurrentUser,
    service: PlantServiceDep,
    plant_status: Annotated[Literal["active", "ended"], Query(alias="status")] = "active",
    commodity_code: Annotated[str | None, Query()] = None,
    outcome: Annotated[Literal["completed", "ended_early", "failed"] | None, Query()] = None,
) -> ListEnvelope[PlantOut]:
    """``status=active``: Tracking. ``status=ended``: Riwayat Tanaman (filter ``outcome``)."""
    plants = await service.list_user_plants(
        user.id, status=plant_status, commodity_code=commodity_code, outcome=outcome
    )
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


@router.get("/plants/{plant_id}/harvests")
async def list_harvests(
    plant_id: UUID, user: CurrentUser, service: PlantServiceDep
) -> ListEnvelope[HarvestOut]:
    """Every harvest of the plant, numbered "panen ke-n"."""
    return ListEnvelope(data=await service.list_harvests(user.id, plant_id), meta=PaginationMeta())


@router.post("/plants/{plant_id}/harvests", status_code=status.HTTP_201_CREATED)
async def record_harvest(
    plant_id: UUID, payload: HarvestCreate, user: CurrentUser, service: PlantServiceDep
) -> Envelope[HarvestOut]:
    """Record a harvest; the response carries the recomputed ``next_harvest``."""
    harvest = await service.record_harvest(user.id, plant_id, payload)
    return Envelope(data=harvest)


@router.patch("/plants/{plant_id}/harvests/{harvest_id}")
async def update_harvest(
    plant_id: UUID,
    harvest_id: UUID,
    payload: HarvestUpdate,
    user: CurrentUser,
    service: PlantServiceDep,
) -> Envelope[HarvestOut]:
    return Envelope(data=await service.update_harvest(user.id, plant_id, harvest_id, payload))


@router.delete("/plants/{plant_id}/harvests/{harvest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_harvest(
    plant_id: UUID, harvest_id: UUID, user: CurrentUser, service: PlantServiceDep
) -> Response:
    await service.delete_harvest(user.id, plant_id, harvest_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/plants/{plant_id}/disease-episodes")
async def list_episodes(
    plant_id: UUID,
    user: CurrentUser,
    plants: PlantServiceDep,
    episodes: EpisodeServiceDep,
    episode_status: Annotated[Literal["open", "resolved"] | None, Query(alias="status")] = None,
) -> ListEnvelope[EpisodeOut]:
    """The plant's disease episodes, newest first, each with the scans that back it."""
    plant = await plants.get_plant(user.id, plant_id)
    return ListEnvelope(
        data=await episodes.list_out(plant, status=episode_status), meta=PaginationMeta()
    )


@router.patch("/disease-episodes/{episode_id}")
async def update_episode(
    episode_id: UUID,
    payload: EpisodeUpdate,
    user: CurrentUser,
    episodes: EpisodeServiceDep,
) -> Envelope[EpisodeOut]:
    """ "Tandai sembuh". It never gives back days already added to the running cycle."""
    _ = payload  # the only allowed transition is open -> resolved
    episode = await episodes.resolve(user.id, episode_id)
    return Envelope(data=(await episodes.to_out([episode]))[0])


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
