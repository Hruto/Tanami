"""Weather, home, reminders and the scheduled jobs (design 10.8, 12)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.state import AppState
from app.jobs.scheduler import (
    run_account_purge,
    run_health_decay,
    run_push_dispatch,
    run_reminder_expiry,
    run_reminder_generation,
    run_scan_followup,
    run_weather_refresh,
)
from app.providers.push import LogPushProvider
from app.providers.storage import MemoryStorage
from app.providers.weather import WeatherDay
from httpx import AsyncClient

from tests.helpers import (
    FakeWeather,
    auth_headers,
    create_farm,
    create_plant,
    forecast,
    hourly_slots,
    register,
    upload_scan,
)

DAY = date(2026, 11, 7)
MORNING = datetime(2026, 11, 7, 3, 0, tzinfo=UTC)  # 10:00 WIB
LATE = datetime(2026, 11, 7, 15, 0, tzinfo=UTC)  # 22:00 WIB, quiet hours


def humid_three_days(weather: FakeWeather) -> None:
    days = [
        WeatherDay(
            date=(DAY + timedelta(days=i)).isoformat(),
            slots=hourly_slots((DAY + timedelta(days=i)).isoformat()),
        )
        for i in range(3)
    ]
    weather.default = forecast(days=days)


async def farmer(client: AsyncClient) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    plant = await create_plant(client, headers, farm["id"])
    await client.post(
        "/api/v1/devices",
        json={"fcm_token": "device-token-0001", "platform": "android"},
        headers=headers,
    )
    return headers, farm, plant


async def reminders(client: AsyncClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    return list((await client.get("/api/v1/reminders", headers=headers)).json()["data"])


async def test_weather_is_cached_attributed_and_falls_back_when_stale(
    client: AsyncClient, weather: FakeWeather, state: AppState
) -> None:
    headers, farm, _ = await farmer(client)
    url = f"/api/v1/farms/{farm['id']}/weather"
    first = (await client.get(url, headers=headers)).json()["data"]
    assert first["attribution"] == "Sumber data: BMKG" and first["is_stale"] is False
    await client.get(url, headers=headers)
    assert len(weather.calls) == 1

    await state.redis.delete(f"weather:{farm['adm4_code']}")
    weather.fail = True
    stale = (await client.get(url, headers=headers)).json()["data"]
    assert stale["is_stale"] is True

    await state.redis.delete(f"weather:{farm['adm4_code']}:last")
    archived = (await client.get(url, headers=headers)).json()["data"]
    assert archived["is_stale"] is True  # served from weather_snapshots


async def test_weather_job_refreshes_every_active_village(
    client: AsyncClient, weather: FakeWeather, state: AppState
) -> None:
    await farmer(client)
    result = await run_weather_refresh(state)
    assert result == {"villages": 1, "fetched": 1, "failed": 0}
    weather.fail = True
    assert (await run_weather_refresh(state))["failed"] == 1


async def test_generation_dedupes_and_pushes(
    client: AsyncClient, weather: FakeWeather, state: AppState, push: LogPushProvider
) -> None:
    humid_three_days(weather)
    headers, _, plant = await farmer(client)
    created = await run_reminder_generation(state, now=MORNING)
    assert created["created"] == 1 and created["pushed"] == 1
    again = await run_reminder_generation(state, now=MORNING + timedelta(hours=8))
    assert again["created"] == 0

    items = await reminders(client, headers)
    assert [item["type"] for item in items] == ["fungal_risk"]
    assert items[0]["plant_id"] == plant["id"] and items[0]["sent_at"] is not None
    assert push.sent[0]["deeplink"] == f"tanami://reminders/{items[0]['id']}"


async def test_quiet_hours_defer_then_dispatch(
    client: AsyncClient, weather: FakeWeather, state: AppState, push: LogPushProvider
) -> None:
    humid_three_days(weather)
    headers, _, _ = await farmer(client)
    await run_reminder_generation(state, now=LATE)
    assert push.sent == []
    assert (await reminders(client, headers))[0]["sent_at"] is None
    pushed = await run_push_dispatch(state, now=LATE + timedelta(hours=9))  # 07:00 WIB
    assert pushed == 1 and len(push.sent) == 1


async def test_invalid_token_is_removed(
    client: AsyncClient, weather: FakeWeather, state: AppState, push: LogPushProvider
) -> None:
    humid_three_days(weather)
    headers, _, _ = await farmer(client)
    push.invalid_tokens.add("device-token-0001")
    await run_reminder_generation(state, now=MORNING)
    assert (await client.get("/api/v1/devices", headers=headers)).json()["data"] == []


async def test_reminder_status_updates_and_filter(
    client: AsyncClient, weather: FakeWeather, state: AppState
) -> None:
    humid_three_days(weather)
    headers, _, _ = await farmer(client)
    await run_reminder_generation(state, now=MORNING)
    reminder = (await reminders(client, headers))[0]
    url = f"/api/v1/reminders/{reminder['id']}"
    read = await client.patch(url, json={"status": "read"}, headers=headers)
    assert read.json()["data"]["read_at"] is not None
    unread = await client.get("/api/v1/reminders?status=unread", headers=headers)
    assert unread.json()["data"] == []
    assert (await client.get("/api/v1/reminders?status=lol", headers=headers)).status_code == 400
    stranger = auth_headers(await register(client))
    assert (await client.get(url, headers=stranger)).status_code == 404


async def test_home_summary(client: AsyncClient, weather: FakeWeather, state: AppState) -> None:
    humid_three_days(weather)
    headers, _, plant = await farmer(client)
    await upload_scan(client, headers, plant_id=plant["id"])  # anthracnose -> sick
    await run_reminder_generation(state, now=MORNING)
    home = (await client.get("/api/v1/home", headers=headers)).json()["data"]
    assert home["weather"]["attribution"] == "Sumber data: BMKG"
    assert home["unread_reminder_count"] == 1
    assert home["plants_needing_attention"][0]["health_status"] == "sick"

    weather.fail = True
    await state.redis.flushall()
    empty = auth_headers(await register(client))
    assert (await client.get("/api/v1/home", headers=empty)).json()["data"]["weather"] is None


async def test_scan_followup_expiry_and_decay(client: AsyncClient, state: AppState) -> None:
    headers, _, plant = await farmer(client)
    six_days_ago = datetime.now(UTC) - timedelta(days=6)
    await upload_scan(client, headers, plant_id=plant["id"], captured_at=six_days_ago)
    assert await run_scan_followup(state) == 1
    items = await reminders(client, headers)
    assert items[0]["type"] == "scan_followup"

    expired = await run_reminder_expiry(state, now=datetime.now(UTC) + timedelta(days=4))
    assert expired == 1
    assert (await reminders(client, headers))[0]["status"] == "dismissed"

    assert await run_health_decay(state, now=datetime.now(UTC) + timedelta(days=9)) == 1
    plant_now = (await client.get(f"/api/v1/plants/{plant['id']}", headers=headers)).json()
    assert plant_now["data"]["health_status"] == "unknown"


async def test_deleted_account_is_purged_with_photos(client: AsyncClient, state: AppState) -> None:
    headers, _, plant = await farmer(client)
    await upload_scan(client, headers, plant_id=plant["id"])
    await client.delete("/api/v1/users/me", headers=headers)
    assert await run_account_purge(state) == 0  # grace period
    assert await run_account_purge(state, now=datetime.now(UTC) + timedelta(days=31)) == 1
    assert isinstance(state.storage, MemoryStorage) and state.storage.keys == []
    async with state.session_factory() as session:
        from app.models.farm import Farm
        from app.models.user import User
        from sqlalchemy import func, select

        assert (await session.execute(select(func.count(User.id)))).scalar_one() == 0
        assert (await session.execute(select(func.count(Farm.id)))).scalar_one() == 0
