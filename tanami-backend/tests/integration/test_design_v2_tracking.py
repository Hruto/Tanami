"""design v2: plants with codes, harvests, estimates, disease episodes, scan history.

These tests pin the behaviour of ``docs/design.md`` sections 5, 8 and 10.5-10.6
through the real API against a real PostgreSQL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from app.core.config import Settings
from app.models.content import Disease
from app.models.farm import Plant
from app.services.farm import complete_productive_period
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.helpers import (
    FakeVision,
    auth_headers,
    create_farm,
    disease_result,
    image_bytes,
    register,
    upload_scan,
    vision_payload,
)

TODAY = datetime.now(UTC).date()

# (code, commodity, name, cause, delay days)
DISEASES = (
    ("mango_anthracnose", "mango", "Antraknosa", "fungus", 14),
    ("mango_sooty_mould", "mango", "Embun Jelaga", "fungus", 7),
    ("citrus_greening", "citrus", "CVPD (Greening)", "bacteria", 30),
)


@pytest.fixture
async def diseases(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[None]:
    """Reviewed knowledge-base rows for the mango and citrus codes the tests use."""
    async with session_factory() as db:
        for code, commodity, name, cause, delay in DISEASES:
            found = await db.execute(select(Disease).where(Disease.code == code))
            if found.scalar_one_or_none():
                continue
            db.add(
                Disease(
                    code=code,
                    commodity_code=commodity,
                    name_id=name,
                    cause_category=cause,
                    symptoms="Bercak pada daun.",
                    causes_text="Cendawan.",
                    prevention="Pangkas tajuk agar tidak lembap. Bersihkan daun gugur.",
                    treatments={"first_aid": ["Pangkas daun bergejala."]},
                    harvest_delay_days=delay,
                    reviewed_by="Tim Agronomi",
                    reviewed_at=TODAY,
                    is_active=True,
                )
            )
        await db.commit()
    yield


async def start(client: AsyncClient) -> tuple[dict[str, str], dict[str, Any]]:
    headers = auth_headers(await register(client))
    return headers, await create_farm(client, headers)


async def start_other(client: AsyncClient) -> tuple[dict[str, str], dict[str, Any]]:
    headers = auth_headers(await register(client, email="lain@example.com", username="lain"))
    return headers, await create_farm(client, headers)


async def new_plant(
    client: AsyncClient, headers: dict[str, str], farm_id: str, **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": "Mangga Depan Rumah",
        "commodity_code": "mango",
        "planted_at": (TODAY - timedelta(days=2000)).isoformat(),
    }
    payload.update(overrides)
    response = await client.post(f"/api/v1/farms/{farm_id}/plants", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def get_plant(client: AsyncClient, headers: dict[str, str], plant_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/plants/{plant_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def harvest(
    client: AsyncClient, headers: dict[str, str], plant_id: str, day: date | None = None, **kw: Any
) -> Any:
    payload = {"harvested_at": day.isoformat()} if day else {}
    return await client.post(
        f"/api/v1/plants/{plant_id}/harvests", json={**payload, **kw}, headers=headers
    )


def result_for(code: str, cause: str = "fungus", status: str = "confident") -> Any:
    return vision_payload(result=disease_result(code=code, cause=cause), status=status)


# --------------------------------------------------------------------------- #
# Plant types, creation, codes
# --------------------------------------------------------------------------- #


async def test_plant_types_are_the_three_fruits_with_materials(client: AsyncClient) -> None:
    rows = (await client.get("/api/v1/plant-types")).json()["data"]
    assert [row["code"] for row in rows] == ["mango", "citrus", "strawberry"]
    strawberry = rows[2]
    assert {m["code"] for m in strawberry["materials"]} == {"runner", "seed", "other"}
    assert [m["code"] for m in strawberry["materials"] if m["is_default"]] == ["runner"]
    assert rows[0]["detection_supported"] is True


async def test_crop_profiles_are_listed(client: AsyncClient) -> None:
    rows = (await client.get("/api/v1/crop-profiles")).json()["data"]
    assert len(rows) == 6
    assert {row["commodity_code"] for row in rows} == {"mango", "citrus", "strawberry"}


async def test_plant_codes_count_per_commodity_and_are_never_reused(client: AsyncClient) -> None:
    headers, farm = await start(client)
    first = await new_plant(client, headers, farm["id"])
    second = await new_plant(client, headers, farm["id"], label="Mangga 2")
    citrus = await new_plant(client, headers, farm["id"], label="Jeruk", commodity_code="citrus")
    assert [first["code"], second["code"], citrus["code"]] == ["MGA-001", "MGA-002", "JRK-001"]

    await client.delete(f"/api/v1/plants/{second['id']}", headers=headers)
    third = await new_plant(client, headers, farm["id"], label="Mangga 3")
    assert third["code"] == "MGA-003"

    other_headers, other_farm = await start_other(client)
    assert (await new_plant(client, other_headers, other_farm["id"]))["code"] == "MGA-001"


async def test_new_plant_defaults_and_estimate(client: AsyncClient) -> None:
    headers, farm = await start(client)
    planted = TODAY - timedelta(days=100)
    plant = await new_plant(client, headers, farm["id"], planted_at=planted.isoformat())
    assert plant["planting_material"] == "grafted"
    assert plant["quantity"] == 1
    assert plant["lifecycle_phase"] == "juvenile"
    assert plant["age_days"] == 100
    assert plant["productive_until"] == planted.replace(year=planted.year + 40).isoformat()
    nxt = plant["next_harvest"]
    assert nxt["start"] == (planted + timedelta(days=1095)).isoformat()
    assert nxt["end"] == (planted + timedelta(days=1460)).isoformat()
    assert nxt["is_estimate"] is True and nxt["is_overdue"] is False


async def test_strawberry_defaults_to_runner_and_can_be_a_group(client: AsyncClient) -> None:
    headers, farm = await start(client)
    plant = await new_plant(
        client,
        headers,
        farm["id"],
        commodity_code="strawberry",
        planted_at=(TODAY - timedelta(days=30)).isoformat(),
        quantity=200,
        label="Bedengan A",
    )
    assert plant["planting_material"] == "runner" and plant["quantity"] == 200
    assert plant["code"] == "STB-001"
    assert plant["lifecycle_phase"] == "juvenile"


@pytest.mark.parametrize(
    "overrides",
    [
        {"commodity_code": "chili"},  # no longer supported
        {"planting_material": "runner"},  # runner is strawberry-only
        {"planted_at": (TODAY + timedelta(days=1)).isoformat()},
        {"planted_at": (TODAY - timedelta(days=365 * 41)).isoformat()},  # past the productive end
        {"quantity": 0},
    ],
)
async def test_invalid_plants_are_rejected(client: AsyncClient, overrides: dict[str, Any]) -> None:
    headers, farm = await start(client)
    response = await client.post(
        f"/api/v1/farms/{farm['id']}/plants",
        json={
            "label": "X",
            "commodity_code": "mango",
            "planted_at": (TODAY - timedelta(days=2000)).isoformat(),
            **overrides,
        },
        headers=headers,
    )
    assert response.status_code == 400, response.text


# --------------------------------------------------------------------------- #
# Harvests
# --------------------------------------------------------------------------- #


async def test_harvests_are_numbered_and_move_the_estimate(client: AsyncClient) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    day1, day2 = TODAY - timedelta(days=400), TODAY - timedelta(days=30)

    first = (await harvest(client, headers, plant["id"], day1, quantity_kg=12.5)).json()["data"]
    assert first["sequence"] == 1 and first["harvested_at"] == day1.isoformat()
    second = (await harvest(client, headers, plant["id"], day2)).json()["data"]
    assert second["sequence"] == 2
    assert second["next_harvest"]["start"] == (day2 + timedelta(days=330)).isoformat()
    assert second["next_harvest"]["end"] == (day2 + timedelta(days=400)).isoformat()

    detail = await get_plant(client, headers, plant["id"])
    assert detail["harvest_count"] == 2 and detail["last_harvest_at"] == day2.isoformat()
    assert detail["lifecycle_phase"] == "productive"

    listing = (await client.get(f"/api/v1/plants/{plant['id']}/harvests", headers=headers)).json()
    assert [row["sequence"] for row in listing["data"]] == [1, 2]


async def test_harvest_date_rules(client: AsyncClient) -> None:
    headers, farm = await start(client)
    planted = TODAY - timedelta(days=2000)
    plant = await new_plant(client, headers, farm["id"], planted_at=planted.isoformat())
    future = await harvest(client, headers, plant["id"], TODAY + timedelta(days=1))
    assert future.status_code == 400
    before = await harvest(client, headers, plant["id"], planted - timedelta(days=1))
    assert before.status_code == 400
    await harvest(client, headers, plant["id"], TODAY - timedelta(days=10))
    earlier = await harvest(client, headers, plant["id"], TODAY - timedelta(days=20))
    assert earlier.status_code == 400  # not before the previous harvest
    assert (await harvest(client, headers, plant["id"])).status_code == 201  # no date: today


async def test_deleting_a_harvest_renumbers_and_editing_keeps_order(client: AsyncClient) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    ids = []
    for days_ago in (300, 200, 100):
        created = await harvest(client, headers, plant["id"], TODAY - timedelta(days=days_ago))
        ids.append(created.json()["data"]["id"])

    url = f"/api/v1/plants/{plant['id']}/harvests"
    assert (await client.delete(f"{url}/{ids[0]}", headers=headers)).status_code == 204
    rows = (await client.get(url, headers=headers)).json()["data"]
    assert [(r["sequence"], r["id"]) for r in rows] == [(1, ids[1]), (2, ids[2])]

    too_late = await client.patch(
        f"{url}/{ids[1]}",
        json={"harvested_at": (TODAY - timedelta(days=50)).isoformat()},
        headers=headers,
    )
    assert too_late.status_code == 400  # would pass the next harvest
    fine = await client.patch(
        f"{url}/{ids[1]}",
        json={"harvested_at": (TODAY - timedelta(days=150)).isoformat(), "quantity_kg": 9},
        headers=headers,
    )
    assert fine.status_code == 200 and fine.json()["data"]["quantity_kg"] == 9


# --------------------------------------------------------------------------- #
# Scans, confirmation and episodes
# --------------------------------------------------------------------------- #


async def test_confirming_a_disease_pushes_the_estimate_once(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    last = TODAY - timedelta(days=20)
    await harvest(client, headers, plant["id"], last)
    base_start = last + timedelta(days=330)

    vision.enqueue_result(result_for("mango_anthracnose"))
    scan = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    assert scan["saved"] is True and scan["plant_code"] == plant["code"]
    assert scan["confirmation"] == {
        "can_confirm": True,
        "existing_episode_id": None,
        "delay_preview_days": 14,
    }
    assert scan["result"]["advice"]["prevention"].startswith("Pangkas tajuk")
    # A scan alone changes nothing about the estimate.
    assert (await get_plant(client, headers, plant["id"]))["next_harvest"]["delay_days"] == 0

    confirmed = await client.post(f"/api/v1/scans/{scan['id']}/confirm-disease", headers=headers)
    assert confirmed.status_code == 201
    body = confirmed.json()["data"]
    assert body["is_new"] is True and body["episode"]["delay_days"] == 14
    assert body["next_harvest"]["delay_days"] == 14
    assert body["next_harvest"]["start"] == (base_start + timedelta(days=14)).isoformat()
    assert body["next_harvest"]["delays"][0]["label"] == "Antraknosa"

    # Scanning the same leaf again and confirming joins the open episode: no extra delay.
    vision.enqueue_result(result_for("mango_anthracnose"))
    again = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    assert again["confirmation"]["existing_episode_id"] == body["episode"]["id"]
    assert again["confirmation"]["delay_preview_days"] == 0
    second = await client.post(f"/api/v1/scans/{again['id']}/confirm-disease", headers=headers)
    assert second.status_code == 200 and second.json()["data"]["is_new"] is False
    assert second.json()["data"]["next_harvest"]["delay_days"] == 14
    # Confirming the very same scan twice is harmless.
    repeat = await client.post(f"/api/v1/scans/{again['id']}/confirm-disease", headers=headers)
    assert repeat.status_code == 200

    episodes = (
        await client.get(f"/api/v1/plants/{plant['id']}/disease-episodes", headers=headers)
    ).json()["data"]
    assert len(episodes) == 1 and len(episodes[0]["scan_ids"]) == 2

    # A different disease adds its own delay.
    vision.enqueue_result(result_for("mango_sooty_mould"))
    sooty = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    third = await client.post(f"/api/v1/scans/{sooty['id']}/confirm-disease", headers=headers)
    assert third.json()["data"]["next_harvest"]["delay_days"] == 21


async def test_only_confident_diseases_can_be_confirmed(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])

    vision.enqueue_result(result_for("mango_anthracnose", status="uncertain"))
    uncertain = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    assert uncertain["confirmation"]["can_confirm"] is False
    url = f"/api/v1/scans/{uncertain['id']}/confirm-disease"
    assert (await client.post(url, headers=headers)).status_code == 400

    vision.enqueue_result(result_for("healthy", cause="healthy"))
    healthy = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    assert healthy["confirmation"]["can_confirm"] is False
    url = f"/api/v1/scans/{healthy['id']}/confirm-disease"
    assert (await client.post(url, headers=headers)).status_code == 400


async def test_a_healthy_scan_closes_open_episodes_and_keeps_the_delay(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    await harvest(client, headers, plant["id"], TODAY - timedelta(days=20))

    vision.enqueue_result(result_for("mango_anthracnose"))
    sick = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    confirmed = await client.post(f"/api/v1/scans/{sick['id']}/confirm-disease", headers=headers)
    episode = confirmed.json()["data"]["episode"]

    vision.enqueue_result(result_for("healthy", cause="healthy"))
    healthy = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    assert healthy["closed_episode_ids"] == [episode["id"]]

    detail = await get_plant(client, headers, plant["id"])
    assert detail["open_episode_count"] == 0
    # The days already added to the running cycle are not given back.
    assert detail["next_harvest"]["delay_days"] == 14
    assert detail["next_harvest"]["delays"][0]["status"] == "resolved"


async def test_user_can_mark_an_episode_healed(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    vision.enqueue_result(result_for("mango_anthracnose"))
    scan = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    confirmed = await client.post(f"/api/v1/scans/{scan['id']}/confirm-disease", headers=headers)
    episode = confirmed.json()["data"]["episode"]

    url = f"/api/v1/disease-episodes/{episode['id']}"
    healed = await client.patch(url, json={"status": "resolved"}, headers=headers)
    assert healed.status_code == 200
    assert healed.json()["data"]["close_reason"] == "user_marked_healed"
    assert (await get_plant(client, headers, plant["id"]))["open_episode_count"] == 0

    stranger_headers, _ = await start_other(client)
    hidden = await client.patch(url, json={"status": "resolved"}, headers=stranger_headers)
    assert hidden.status_code == 404


async def test_quick_scan_is_answered_but_never_stored(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, _ = await start(client)
    vision.enqueue_result(result_for("mango_anthracnose"))
    response = await client.post(
        "/api/v1/scans",
        data={"commodity_code": "mango"},
        files={"image": ("foto.jpg", image_bytes(), "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["saved"] is False and data["id"] is None and data["plant_id"] is None
    assert data["image_url"] is None and data["confirmation"] is None
    assert data["result"]["top"]["disease_code"] == "mango_anthracnose"
    assert vision.calls[-1]["commodity_code"] == "mango"
    assert (await client.get("/api/v1/scans", headers=headers)).json()["data"] == []

    missing = await client.post(
        "/api/v1/scans",
        files={"image": ("foto.jpg", image_bytes(), "image/jpeg")},
        headers=headers,
    )
    assert missing.status_code == 400


async def test_scans_send_the_plants_commodity_to_vision(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"], commodity_code="citrus")
    vision.enqueue_result(result_for("citrus_greening", cause="bacteria"))
    response = await upload_scan(client, headers, plant_id=plant["id"])
    assert response.status_code == 201, response.text
    assert vision.calls[-1]["commodity_code"] == "citrus"


async def test_scan_history_filters(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    mango = await new_plant(client, headers, farm["id"])
    citrus = await new_plant(client, headers, farm["id"], commodity_code="citrus", label="Jeruk")

    vision.enqueue_result(result_for("mango_anthracnose"))
    await upload_scan(client, headers, plant_id=mango["id"])
    vision.enqueue_result(result_for("mango_sooty_mould"))
    await upload_scan(client, headers, plant_id=mango["id"])
    vision.enqueue_result(result_for("citrus_greening", cause="bacteria"))
    await upload_scan(client, headers, plant_id=citrus["id"])
    vision.enqueue_result(result_for("mango_anthracnose", status="unknown"))
    await upload_scan(client, headers, plant_id=mango["id"])

    async def codes(query: str = "") -> list[str | None]:
        rows = (await client.get(f"/api/v1/scans{query}", headers=headers)).json()["data"]
        return [row["disease_code"] for row in rows]

    assert len(await codes()) == 4
    assert await codes("?commodity_code=citrus") == ["citrus_greening"]
    assert sorted(await codes(f"?plant_id={mango['id']}&status=confident")) == [
        "mango_anthracnose",
        "mango_sooty_mould",
    ]
    assert await codes("?disease_code=mango_sooty_mould") == ["mango_sooty_mould"]
    assert await codes("?status=unknown") == [None]
    assert await codes(f"?from={TODAY + timedelta(days=1)}") == []
    assert len(await codes(f"?from={TODAY}&to={TODAY}")) == 4

    query = "?disease_code=mango_anthracnose&status=confident"
    row = (await client.get(f"/api/v1/scans{query}", headers=headers)).json()["data"][0]
    assert row["plant_code"] == "MGA-001" and row["confidence_percent"] == 93
    assert row["disease_label"] == "Antraknosa" and row["cause_category"] == "fungus"
    assert row["prevention_summary"] == "Pangkas tajuk agar tidak lembap."


async def test_scans_need_an_active_plant_that_is_yours(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    stranger_headers, _ = await start_other(client)
    stranger = await upload_scan(client, stranger_headers, plant_id=plant["id"])
    assert stranger.status_code == 404

    await client.delete(f"/api/v1/plants/{plant['id']}", headers=headers)
    assert (await upload_scan(client, headers, plant_id=plant["id"])).status_code == 400


# --------------------------------------------------------------------------- #
# Ending tracking
# --------------------------------------------------------------------------- #


async def test_ending_for_disease_needs_a_disease_or_a_note(
    client: AsyncClient, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"], commodity_code="citrus", label="Jeruk")
    url = f"/api/v1/plants/{plant['id']}/end"

    assert (await client.post(url, json={"reason": "disease"}, headers=headers)).status_code == 400
    wrong = await client.post(
        url, json={"reason": "disease", "disease_codes": ["mango_anthracnose"]}, headers=headers
    )
    assert wrong.status_code == 400
    system_only = await client.post(url, json={"reason": "productive_period_over"}, headers=headers)
    assert system_only.status_code == 400
    assert (await client.post(url, json={"reason": "other"}, headers=headers)).status_code == 400

    ended = await client.post(
        url,
        json={"reason": "disease", "disease_codes": ["citrus_greening"], "cause_note": "Belang"},
        headers=headers,
    )
    assert ended.status_code == 200, ended.text
    data = ended.json()["data"]
    assert data["status"] == "ended" and data["outcome"] == "failed"
    assert data["end_diseases"] == [{"code": "citrus_greening", "label": "CVPD (Greening)"}]
    assert data["end_cause_note"] == "Belang"
    assert data["next_harvest"] is None


async def test_outcome_depends_on_harvests_and_history_is_filterable(
    client: AsyncClient, diseases: None
) -> None:
    headers, farm = await start(client)
    early = await new_plant(client, headers, farm["id"], label="Sudah panen")
    never = await new_plant(client, headers, farm["id"], label="Belum panen")
    await harvest(client, headers, early["id"], TODAY - timedelta(days=100))

    cut = await client.post(
        f"/api/v1/plants/{early['id']}/end", json={"reason": "cut_down"}, headers=headers
    )
    assert cut.json()["data"]["outcome"] == "ended_early"
    died = await client.post(
        f"/api/v1/plants/{never['id']}/end",
        json={"reason": "died_other", "cause_note": "Banjir"},
        headers=headers,
    )
    assert died.json()["data"]["outcome"] == "failed"

    async def labels(query: str) -> list[str]:
        rows = (await client.get(f"/api/v1/plants?status=ended{query}", headers=headers)).json()
        return sorted(row["label"] for row in rows["data"])

    assert await labels("") == ["Belum panen", "Sudah panen"]
    assert await labels("&outcome=failed") == ["Belum panen"]
    assert await labels("&outcome=ended_early") == ["Sudah panen"]
    assert await labels("&commodity_code=citrus") == []
    assert (await client.get("/api/v1/plants?status=active", headers=headers)).json()["data"] == []


async def test_an_ended_plant_is_read_only(client: AsyncClient) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    url = f"/api/v1/plants/{plant['id']}"
    await client.post(f"{url}/end", json={"reason": "cut_down"}, headers=headers)

    assert (await harvest(client, headers, plant["id"], TODAY)).status_code == 400
    assert (await client.patch(url, json={"label": "Baru"}, headers=headers)).status_code == 400
    again = await client.post(f"{url}/end", json={"reason": "cut_down"}, headers=headers)
    assert again.status_code == 400
    # History keeps working.
    assert (await get_plant(client, headers, plant["id"]))["outcome"] == "failed"
    timeline = (await client.get(f"{url}/timeline", headers=headers)).json()
    assert timeline["data"][0]["kind"] == "ended"


async def test_ending_closes_open_episodes(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    vision.enqueue_result(result_for("mango_anthracnose"))
    scan = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    await client.post(f"/api/v1/scans/{scan['id']}/confirm-disease", headers=headers)

    await client.post(
        f"/api/v1/plants/{plant['id']}/end",
        json={"reason": "disease", "disease_codes": ["mango_anthracnose"]},
        headers=headers,
    )
    url = f"/api/v1/plants/{plant['id']}/disease-episodes"
    episodes = (await client.get(url, headers=headers)).json()["data"]
    assert episodes[0]["status"] == "resolved" and episodes[0]["close_reason"] == "tracking_ended"


async def test_productive_period_ends_tracking_by_itself(
    client: AsyncClient,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers, farm = await start(client)
    # Strawberry is productive for two years (design 8.3), so the plant has to be
    # young enough to register; the job is then driven by moving productive_until.
    plant = await new_plant(
        client,
        headers,
        farm["id"],
        commodity_code="strawberry",
        planted_at=(TODAY - timedelta(days=400)).isoformat(),
        label="Bedengan A",
    )
    await harvest(client, headers, plant["id"], TODAY - timedelta(days=5))
    async with session_factory() as db:
        row = await db.get(Plant, UUID(plant["id"]))
        assert row is not None
        row.productive_until = TODAY
        await db.commit()
    async with session_factory() as db:
        ended = await complete_productive_period(db, settings, today=TODAY)
    assert [p.code for p in ended] == ["STB-001"]

    data = await get_plant(client, headers, plant["id"])
    assert data["status"] == "ended"
    assert data["end_reason"] == "productive_period_over" and data["outcome"] == "completed"


async def test_timeline_and_stats_cover_harvests_and_episodes(
    client: AsyncClient, vision: FakeVision, diseases: None
) -> None:
    headers, farm = await start(client)
    plant = await new_plant(client, headers, farm["id"])
    await harvest(client, headers, plant["id"], TODAY - timedelta(days=400))
    vision.enqueue_result(result_for("mango_anthracnose"))
    scan = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    await client.post(f"/api/v1/scans/{scan['id']}/confirm-disease", headers=headers)
    await harvest(client, headers, plant["id"], TODAY - timedelta(days=1))

    url = f"/api/v1/plants/{plant['id']}"
    entries = (await client.get(f"{url}/timeline", headers=headers)).json()["data"]
    assert {"harvest", "scan", "episode_opened"} <= {entry["kind"] for entry in entries}
    assert any(entry["title"] == "Panen ke-2" for entry in entries)
    assert len({entry["id"] for entry in entries}) == len(entries)

    stats = (await client.get(f"{url}/stats", headers=headers)).json()["data"]
    assert [point["sequence"] for point in stats["harvest_series"]] == [1, 2]
    assert [row["sequence"] for row in stats["estimate_vs_actual"]] == [1, 2]
    assert stats["health_series"][0]["health_status"] == "sick"
