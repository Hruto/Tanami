"""Reminder routes and the home summary (``design.md`` 10.8)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import and_, func, or_, select

from app.api.deps import (
    CurrentUser,
    ReminderServiceDep,
    SessionDep,
    WeatherServiceDep,
)
from app.core.errors import AppError
from app.core.pagination import encode_cursor, page_request
from app.models.farm import Farm, Plant
from app.models.reminder import Reminder
from app.providers.weather import WeatherForecast
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.reminder import (
    HomeOut,
    PlantAttention,
    ReminderOut,
    ReminderUpdate,
    WeatherDayOut,
    WeatherOut,
    WeatherSlotOut,
)
from app.services.reminder import validate_status_filter

router = APIRouter(tags=["reminders"])

# Display names for ``weather_snapshots.source`` (design 10.8 shows "BMKG").
_SOURCE_LABELS = {"bmkg": "BMKG", "open_meteo": "Open-Meteo", "manual": "Manual"}

# Plants that deserve a nudge on the home screen.
_ATTENTION_STATUSES = ("sick", "at_risk")


def reminder_out(reminder: Reminder) -> ReminderOut:
    return ReminderOut(
        id=str(reminder.id),
        type=reminder.type,
        priority=reminder.priority,
        status=reminder.status,
        title=reminder.title,
        body=reminder.body,
        payload=dict(reminder.payload),
        plant_id=str(reminder.plant_id) if reminder.plant_id else None,
        farm_id=str(reminder.farm_id) if reminder.farm_id else None,
        valid_until=reminder.valid_until,
        sent_at=reminder.sent_at,
        read_at=reminder.read_at,
        created_at=reminder.created_at,
    )


def weather_out(forecast: WeatherForecast) -> WeatherOut:
    """Project the provider dataclass onto the wire shape.

    The provider keeps BMKG's short field names (``t``, ``hu``, ``ws``); the
    rename happens exactly once, here, so no other route has to remember it.
    """
    return WeatherOut(
        adm4_code=forecast.adm4_code,
        source=_SOURCE_LABELS.get(forecast.source, forecast.source),
        fetched_at=forecast.fetched_at,
        attribution=forecast.attribution,
        is_stale=forecast.is_stale,
        days=[
            WeatherDayOut(
                date=day.date,
                slots=[
                    WeatherSlotOut(
                        local_datetime=slot.local_datetime,
                        t=slot.temperature_c,
                        hu=slot.humidity_pct,
                        weather_desc=slot.weather_desc,
                        ws=slot.wind_speed,
                        wd=slot.wind_direction,
                        tp=slot.precipitation_mm,
                    )
                    for slot in day.slots
                ],
            )
            for day in forecast.days
        ],
    )


@router.get("/reminders")
async def list_reminders(
    user: CurrentUser,
    session: SessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> ListEnvelope[ReminderOut]:
    page = page_request(limit, cursor)
    validate_status_filter(status_filter)

    query = select(Reminder).where(Reminder.user_id == user.id)
    if status_filter:
        query = query.where(Reminder.status == status_filter)
    if page.cursor is not None:
        query = query.where(
            or_(
                Reminder.created_at < page.cursor.created_at,
                and_(
                    Reminder.created_at == page.cursor.created_at,
                    Reminder.id < page.cursor.last_id,
                ),
            )
        )
    query = query.order_by(Reminder.created_at.desc(), Reminder.id.desc()).limit(page.limit + 1)

    rows = list((await session.execute(query)).scalars())
    has_more = len(rows) > page.limit
    rows = rows[: page.limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, UUID(str(last.id)))

    return ListEnvelope(
        data=[reminder_out(row) for row in rows],
        meta=PaginationMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/reminders/{reminder_id}")
async def get_reminder(
    reminder_id: UUID, user: CurrentUser, service: ReminderServiceDep
) -> Envelope[ReminderOut]:
    return Envelope(data=reminder_out(await service.get(UUID(str(user.id)), reminder_id)))


@router.patch("/reminders/{reminder_id}")
async def update_reminder(
    reminder_id: UUID,
    payload: ReminderUpdate,
    user: CurrentUser,
    service: ReminderServiceDep,
) -> Envelope[ReminderOut]:
    updated = await service.update_status(UUID(str(user.id)), reminder_id, payload.status)
    return Envelope(data=reminder_out(updated))


@router.get("/home")
async def home(
    user: CurrentUser,
    session: SessionDep,
    weather: WeatherServiceDep,
) -> Envelope[HomeOut]:
    """Everything the Beranda screen needs in one round trip.

    A weather outage must not blank the screen, so the forecast is optional
    here; the app shows the rest and labels the weather panel as unavailable.
    """
    user_id = UUID(str(user.id))

    farms = list(
        (
            await session.execute(
                select(Farm)
                .where(Farm.user_id == user_id, Farm.archived_at.is_(None))
                .order_by(Farm.created_at)
            )
        ).scalars()
    )

    forecast = None
    for farm in farms:
        try:
            forecast = await weather.for_adm4(farm.adm4_code)
        except AppError:
            forecast = None
        if forecast is not None:
            break

    reminders = list(
        (
            await session.execute(
                select(Reminder)
                .where(
                    Reminder.user_id == user_id,
                    Reminder.status.in_(("unread", "read")),
                )
                .order_by(Reminder.created_at.desc())
                .limit(5)
            )
        ).scalars()
    )

    unread = (
        await session.execute(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id, Reminder.status == "unread"
            )
        )
    ).scalar_one()

    attention_rows = list(
        (
            await session.execute(
                select(Plant, Farm)
                .join(Farm, Farm.id == Plant.farm_id)
                .where(
                    Farm.user_id == user_id,
                    Farm.archived_at.is_(None),
                    Plant.ended_at.is_(None),
                    Plant.health_status.in_(_ATTENTION_STATUSES),
                )
                .order_by(Plant.updated_at.desc())
                .limit(5)
            )
        ).all()
    )

    attention = [
        PlantAttention(
            id=str(plant.id),
            label=plant.label,
            farm_id=str(farm.id),
            health_status=plant.health_status,
            reason=(
                "Terindikasi penyakit pada scan terakhir."
                if plant.health_status == "sick"
                else "Perlu diperiksa ulang."
            ),
        )
        for plant, farm in attention_rows
    ]

    return Envelope(
        data=HomeOut(
            weather=weather_out(forecast) if forecast is not None else None,
            reminders=[reminder_out(row) for row in reminders],
            plants_needing_attention=attention,
            unread_reminder_count=int(unread),
        )
    )
