"""Version 1 of the API.

Every route module exposes ``router``; this module mounts them under
``/api/v1`` and keeps the operational endpoints (health, metrics) outside that
prefix so infrastructure config does not depend on the API version.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    diseases,
    farms,
    forum,
    reminders,
    scans,
    staff,
    weather,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(farms.router)
api_router.include_router(scans.router)
api_router.include_router(reminders.router)
api_router.include_router(weather.router)
api_router.include_router(diseases.router)
api_router.include_router(forum.router)
api_router.include_router(staff.router)

__all__ = ["api_router"]
