"""Serve images held by ``MemoryStorage`` (local development only).

``MemoryStorage.public_url`` returns ``/media/<key>``; without this route the
URL in every scan response would 404 against a local backend. ``create_app``
mounts it only outside production and only when the memory backend is active,
so it can never expose S3 objects.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import StorageDep
from app.core.errors import NotFound
from app.providers.storage import MemoryStorage

router = APIRouter(include_in_schema=False)


@router.get("/media/{key:path}")
async def media(key: str, storage: StorageDep) -> Response:
    if not isinstance(storage, MemoryStorage):
        raise NotFound("Berkas tidak ditemukan.")
    entry = storage.entry(key)
    if entry is None:
        raise NotFound("Berkas tidak ditemukan.")
    data, content_type = entry
    return Response(content=data, media_type=content_type)
