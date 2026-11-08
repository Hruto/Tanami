"""Probes, cross-cutting HTTP behaviour, and model/migration agreement."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.base import Base
from app.models import *  # noqa: F403 - register every table on the metadata
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers import auth_headers, register


async def test_probes(client: AsyncClient) -> None:
    assert (await client.get("/health")).json()["status"] == "ok"
    ready = await client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"
    assert ready.json()["checks"]["redis"] == "ok"
    metrics = await client.get("/metrics")
    assert "backend_scans_total" in metrics.text


async def test_request_id_is_echoed_and_unknown_routes_use_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nope", headers={"X-Request-ID": "abc-123"})
    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "abc-123"
    error = response.json()["error"]
    assert (error["code"], error["request_id"]) == ("not_found", "abc-123")
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def test_wrong_method_and_bad_uuid(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    assert (await client.put("/api/v1/farms", headers=headers)).status_code == 405
    bad = await client.get("/api/v1/farms/not-a-uuid", headers=headers)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "validation_error"


async def test_disease_knowledge_base(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    listing = (await client.get("/api/v1/diseases?commodity_code=chili", headers=headers)).json()
    codes = {row["code"] for row in listing["data"]}
    assert {"healthy", "anthracnose", "bacterial_wilt"} <= codes
    detail = (await client.get("/api/v1/diseases/anthracnose", headers=headers)).json()["data"]
    assert detail["treatments"]["safety_note"] and detail["reviewed_by"]
    assert (await client.get("/api/v1/diseases/zzz", headers=headers)).status_code == 404


async def test_models_and_migrations_agree(engine: AsyncEngine) -> None:
    """Zero autogenerate drift: every model change ships with its migration."""

    def diff(connection: object) -> list[object]:
        context = MigrationContext.configure(
            connection,  # type: ignore[arg-type]
            opts={"compare_type": True, "compare_server_default": True},
        )
        return list(compare_metadata(context, Base.metadata))

    async with engine.connect() as connection:
        changes = await connection.run_sync(diff)
    assert changes == [], changes
