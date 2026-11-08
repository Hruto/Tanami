"""Weather route (``design.md`` 10.8, 12.1).

The response always carries ``attribution``: the BMKG licence requires the app to
display the source, so the field is part of the payload rather than optional.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, WeatherServiceDep
from app.api.v1.reminders import weather_out
from app.schemas.base import Envelope
from app.schemas.reminder import WeatherOut

router = APIRouter(tags=["weather"])


@router.get("/farms/{farm_id}/weather")
async def farm_weather(
    farm_id: UUID, user: CurrentUser, service: WeatherServiceDep
) -> Envelope[WeatherOut]:
    forecast = await service.for_farm(UUID(str(user.id)), farm_id)
    return Envelope(data=weather_out(forecast))
