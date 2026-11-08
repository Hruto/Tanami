"""Farms, plants, harvests, timeline, stats, regions (design 10.5, 10.7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.helpers import auth_headers, create_farm, create_plant, register


async def test_farm_crud_and_ownership(client: AsyncClient) -> None:
    owner = auth_headers(await register(client))
    stranger = auth_headers(await register(client))
    farm = await create_farm(client, owner, name="  Kebun   Belakang ")
    assert farm["name"] == "Kebun Belakang" and farm["plant_count"] == 0

    url = f"/api/v1/farms/{farm['id']}"
    assert (await client.get(url, headers=stranger)).status_code == 404
    assert (await client.patch(url, json={"name": "X"}, headers=stranger)).status_code == 404

    renamed = await client.patch(url, json={"name": "Kebun Depan", "area_m2": 500}, headers=owner)
    assert renamed.status_code == 200 and renamed.json()["data"]["area_m2"] == 500.0

    assert (await client.patch(url, json={"name": None}, headers=owner)).status_code == 400
    assert (await client.patch(url, json={"lat": -6.2}, headers=owner)).status_code == 400

    bad = await client.post(
        "/api/v1/farms", json={"name": "X", "adm4_code": "31-71"}, headers=owner
    )
    assert bad.status_code == 400 and bad.json()["error"]["details"]["field"] == "adm4_code"


async def test_archiving_a_farm_archives_its_plants(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    plant = await create_plant(client, headers, farm["id"])
    assert (await client.delete(f"/api/v1/farms/{farm['id']}", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/farms", headers=headers)).json()["data"] == []
    archived = await client.get("/api/v1/farms?include_archived=true", headers=headers)
    assert len(archived.json()["data"]) == 1
    plant_now = (await client.get(f"/api/v1/plants/{plant['id']}", headers=headers)).json()
    assert plant_now["data"]["status"] == "ended"
    assert plant_now["data"]["end_reason"] == "other"
    blocked = await client.post(
        f"/api/v1/farms/{farm['id']}/plants",
        json={"label": "Baru", "planted_at": "2026-10-01"},
        headers=headers,
    )
    assert blocked.status_code == 400


async def test_plant_validation_and_patch(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    plants_url = f"/api/v1/farms/{farm['id']}/plants"
    future = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    assert (
        await client.post(plants_url, json={"label": "A", "planted_at": future}, headers=headers)
    ).status_code == 400
    tomato = {"label": "A", "planted_at": "2026-10-01", "commodity_code": "durian"}
    assert (await client.post(plants_url, json=tomato, headers=headers)).status_code == 400

    plant = await create_plant(client, headers, farm["id"])
    assert plant["health_status"] == "unknown"
    assert plant["health_status_reason"] == "Belum ada scan."
    url = f"/api/v1/plants/{plant['id']}"
    assert (await client.patch(url, json={"label": None}, headers=headers)).status_code == 400
    assert (
        await client.patch(url, json={"growth_stage": None}, headers=headers)
    ).status_code == 400
    ok = await client.patch(url, json={"growth_stage": "flowering"}, headers=headers)
    assert ok.json()["data"]["growth_stage"] == "flowering"
    listed = (await client.get(plants_url, headers=headers)).json()["data"]
    assert [item["id"] for item in listed] == [plant["id"]]


async def test_harvests_are_repeatable_until_final(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    plant = await create_plant(client, headers, farm["id"])
    url = f"/api/v1/plants/{plant['id']}/harvests"
    picked = datetime.now(UTC) - timedelta(days=1)

    first = await client.post(
        url, json={"harvested_at": picked.isoformat(), "quantity_kg": 12.5}, headers=headers
    )
    assert first.status_code == 201
    state = (await client.get(f"/api/v1/plants/{plant['id']}", headers=headers)).json()["data"]
    assert state["growth_stage"] == "harvesting"

    final = await client.post(
        url, json={"harvested_at": picked.isoformat(), "is_final": True}, headers=headers
    )
    assert final.status_code == 201
    state = (await client.get(f"/api/v1/plants/{plant['id']}", headers=headers)).json()["data"]
    assert state["growth_stage"] == "finished"

    naive = await client.post(url, json={"harvested_at": "2026-11-01T08:00:00"}, headers=headers)
    assert naive.status_code == 400
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    assert (
        await client.post(url, json={"harvested_at": future}, headers=headers)
    ).status_code == 400

    timeline = (
        await client.get(f"/api/v1/plants/{plant['id']}/timeline?limit=1", headers=headers)
    ).json()
    assert timeline["meta"]["has_more"] is True
    second_page = await client.get(
        f"/api/v1/plants/{plant['id']}/timeline?limit=1&cursor={timeline['meta']['next_cursor']}",
        headers=headers,
    )
    assert second_page.json()["data"][0]["id"] != timeline["data"][0]["id"]


async def test_region_search_and_resolve(client: AsyncClient) -> None:
    found = await client.get("/api/v1/regions/search?q=gambir")
    assert found.status_code == 200
    assert any(row["adm4_code"] == "31.71.03.1001" for row in found.json()["data"])
    nearest = await client.get("/api/v1/regions/resolve?lat=-6.1761&lon=106.8271")
    assert nearest.json()["data"]["adm4_code"] == "31.71.03.1001"
    assert (await client.get("/api/v1/regions/search?q=a")).status_code == 400
