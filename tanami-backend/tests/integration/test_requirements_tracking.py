"""Requirements 0-2 and 7: gardens, plant tracking, history, care reminders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.state import AppState
from app.jobs.scheduler import run_care_reminders
from httpx import AsyncClient

from tests.helpers import auth_headers, create_farm, create_plant, image_bytes, register


async def garden(client: AsyncClient, **farm: Any) -> tuple[dict[str, str], dict[str, Any]]:
    headers = auth_headers(await register(client))
    return headers, await create_farm(client, headers, **farm)


async def test_indoor_garden_and_plant_type_dropdown(client: AsyncClient) -> None:
    headers, farm = await garden(client, placement="indoor")
    assert farm["placement"] == "indoor" and farm["village"] == "Gambir"
    types = (await client.get("/api/v1/plant-types")).json()["data"]
    by_code = {row["code"]: row for row in types}
    assert by_code["chili"]["detection_supported"] is True
    assert by_code["tomato"] == {"code": "tomato", "label": "Tomat", "detection_supported": False}
    bad = await client.post(
        "/api/v1/farms",
        json={"name": "X", "adm4_code": "31.71.03.1001", "placement": "roof"},
        headers=headers,
    )
    assert bad.status_code == 400


async def test_tracking_photos_care_logs_and_age(client: AsyncClient) -> None:
    headers, farm = await garden(client)
    planted = (datetime.now(UTC) - timedelta(days=30)).date().isoformat()
    plant = await create_plant(
        client,
        headers,
        farm["id"],
        commodity_code="tomato",
        planted_at=planted,
        irrigation_schedule="daily",
    )
    assert plant["age_days"] in (29, 30, 31)
    assert plant["commodity_label"] == "Tomat" and plant["status"] == "active"
    url = f"/api/v1/plants/{plant['id']}"

    files = {"image": ("p.jpg", image_bytes(), "image/jpeg")}
    photo = await client.post(
        f"{url}/photos", files=files, data={"caption": "Minggu ke-4"}, headers=headers
    )
    assert photo.status_code == 201, photo.text
    assert (await client.get(f"{url}/photos", headers=headers)).json()["data"][0][
        "caption"
    ] == "Minggu ke-4"

    watered = await client.post(f"{url}/care-logs", json={"action": "watering"}, headers=headers)
    assert watered.status_code == 201
    await client.post(
        f"{url}/care-logs", json={"action": "fertilizing", "note": "NPK"}, headers=headers
    )
    only_water = (await client.get(f"{url}/care-logs?action=watering", headers=headers)).json()
    assert [row["action"] for row in only_water["data"]] == ["watering"]

    detail = (await client.get(url, headers=headers)).json()["data"]
    assert detail["last_watered_at"] is not None
    assert detail["cover_photo_url"] == photo.json()["data"]["image_url"]
    assert detail["next_watering_on"] is not None

    kinds = {
        row["kind"] for row in (await client.get(f"{url}/timeline", headers=headers)).json()["data"]
    }
    assert {"photo", "care"} <= kinds


async def test_end_tracking_moves_to_history_and_freezes_the_plant(
    client: AsyncClient, state: AppState
) -> None:
    headers, farm = await garden(client)
    plant = await create_plant(client, headers, farm["id"])
    url = f"/api/v1/plants/{plant['id']}"
    await run_care_reminders(state, now=datetime.now(UTC) + timedelta(days=8))
    assert (await client.get("/api/v1/reminders?status=unread", headers=headers)).json()["data"]

    missing = await client.post(f"{url}/end", json={"reason": "harvested"}, headers=headers)
    assert missing.status_code == 400
    ended = await client.post(
        f"{url}/end",
        json={"reason": "harvested", "yield_percent": 85, "note": "Lumayan"},
        headers=headers,
    )
    body = ended.json()["data"]
    assert (body["status"], body["final_result"], body["growth_stage"]) == (
        "ended",
        "normal",
        "finished",
    )

    active = (await client.get("/api/v1/plants", headers=headers)).json()["data"]
    history = (await client.get("/api/v1/plants?status=ended", headers=headers)).json()["data"]
    assert active == [] and history[0]["id"] == plant["id"]
    assert history[0]["farm_name"] == farm["name"] and history[0]["end_note"] == "Lumayan"

    assert (await client.get("/api/v1/reminders?status=unread", headers=headers)).json()[
        "data"
    ] == []
    assert await run_care_reminders(state, now=datetime.now(UTC) + timedelta(days=9)) == 0
    blocked = await client.post(f"{url}/care-logs", json={"action": "watering"}, headers=headers)
    assert blocked.status_code == 400
    assert (
        await client.post(f"{url}/end", json={"reason": "died"}, headers=headers)
    ).status_code == 400
    assert (await client.get(f"{url}/timeline", headers=headers)).json()["data"][0][
        "kind"
    ] == "ended"


async def test_care_reminders_respect_user_periods(client: AsyncClient, state: AppState) -> None:
    headers, farm = await garden(client)
    await create_plant(client, headers, farm["id"], irrigation_schedule="never")
    await client.patch(
        "/api/v1/users/me/notification-settings",
        json={"photo_reminder_days": 0, "monitoring_reminder_days": 5},
        headers=headers,
    )
    settings = (await client.get("/api/v1/users/me/notification-settings", headers=headers)).json()
    assert settings["data"]["photo_reminder_days"] == 0
    await run_care_reminders(state, now=datetime.now(UTC) + timedelta(days=6))
    items = (await client.get("/api/v1/reminders", headers=headers)).json()["data"]
    assert [item["type"] for item in items] == ["monitoring"]
