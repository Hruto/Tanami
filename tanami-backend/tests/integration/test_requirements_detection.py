"""Requirements 3-5 in design v2: scan history per plant, ending tracking, forum likes.

The separate "Daftar Tanaman Deteksi" was removed in v2 (``design.md`` 10.6 and
"Apa yang berubah" #4): a saved scan always belongs to a registered plant, so
the plant's own history *is* the detection history and every
``/detection-plants*`` route is gone.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from app.models.content import Disease
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.helpers import (
    FakeVision,
    auth_headers,
    create_farm,
    create_plant,
    disease_result,
    image_bytes,
    register,
    upload_scan,
    vision_payload,
)

TODAY = datetime.now(UTC).date()


@pytest.fixture
async def mango_anthracnose(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """The reviewed knowledge-base row behind the canned mango result (design 11.5).

    Upserted rather than inserted-if-missing: other suites seed the same code with
    different text, and this test asserts on the text it asked for.
    """
    fields: dict[str, Any] = {
        "commodity_code": "mango",
        "name_id": "Antraknosa",
        "cause_category": "fungus",
        "symptoms": "Bercak cokelat kehitaman yang melebar pada daun.",
        "causes_text": "Infeksi jamur Colletotrichum.",
        "prevention": "Pangkas tajuk agar tidak lembap. Bersihkan daun gugur.",
        "treatments": {
            "first_aid": ["Pangkas dan musnahkan daun bergejala."],
            "safety_note": "Gunakan sarung tangan dan masker.",
        },
        "harvest_delay_days": 14,
        "reviewed_by": "Tim Agronomi",
        "reviewed_at": TODAY,
        "is_active": True,
    }
    async with session_factory() as db:
        row = (
            await db.execute(select(Disease).where(Disease.code == "mango_anthracnose"))
        ).scalar_one_or_none()
        if row is None:
            db.add(Disease(code="mango_anthracnose", **fields))
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        await db.commit()
    yield


def mango_leaf() -> Any:
    """A confident mango anthracnose result at the helpers' 93 % confidence."""
    return vision_payload(result=disease_result(code="mango_anthracnose"))


async def test_scan_history_replaces_detection_plants_and_ending_is_final(
    client: AsyncClient, vision: FakeVision, mango_anthracnose: None
) -> None:
    headers = auth_headers(await register(client))

    # design 10.6: every ``/detection-plants*`` route was removed in v2.
    assert (
        await client.post(
            "/api/v1/detection-plants",
            json={"name": "Tomat", "commodity_code": "tomato"},
            headers=headers,
        )
    ).status_code == 404
    assert (await client.get("/api/v1/detection-plants", headers=headers)).status_code == 404
    # A "cek cepat" is the only scan without a plant, and it still only accepts
    # the three v2 commodities (design 8.2, 10.6).
    unsupported = await client.post(
        "/api/v1/scans",
        data={"commodity_code": "tomato"},
        files={"image": ("d.jpg", image_bytes(), "image/jpeg")},
        headers=headers,
    )
    assert unsupported.status_code == 400

    farm = await create_farm(client, headers)
    plant = await create_plant(client, headers, farm["id"])
    vision.enqueue_result(mango_leaf())
    scan = await upload_scan(client, headers, plant_id=plant["id"])
    assert scan.status_code == 201, scan.text
    data = scan.json()["data"]
    result = data["result"]
    assert result["confidence_percent"] == 93
    advice = result["advice"]
    assert (
        advice["disease_name"] == "Antraknosa"
        and advice["symptoms"]
        and advice["treatments"]["safety_note"]
    )
    # The scan is stored, attached to the registered plant, with its code.
    assert (data["saved"], data["plant_id"], data["plant_code"]) == (True, plant["id"], "MGA-001")
    assert data["confirmation"]["can_confirm"] is True
    assert data["confirmation"]["delay_preview_days"] == 14

    # "Ya, tanaman ini sakit" opens an episode from that scan (design 8.5).
    confirmed = await client.post(f"/api/v1/scans/{data['id']}/confirm-disease", headers=headers)
    assert confirmed.status_code == 201, confirmed.text
    episode = confirmed.json()["data"]["episode"]
    assert episode["delay_days"] == 14 and episode["scan_ids"] == [data["id"]]

    ended = await client.post(
        f"/api/v1/plants/{plant['id']}/end", json={"reason": "cut_down"}, headers=headers
    )
    assert ended.status_code == 200, ended.text
    assert (ended.json()["data"]["status"], ended.json()["data"]["outcome"]) == ("ended", "failed")

    # design 8.6: an ended plant is read-only, and v2 has no "aktifkan kembali"
    # (10.6) — the history entry stays closed.
    assert (await upload_scan(client, headers, plant_id=plant["id"])).status_code == 400
    assert (
        await client.post(f"/api/v1/plants/{plant['id']}/reactivate", headers=headers)
    ).status_code == 404
    assert (await client.get("/api/v1/plants", headers=headers)).json()["data"] == []
    history = (await client.get("/api/v1/plants?status=ended", headers=headers)).json()["data"]
    assert [row["id"] for row in history] == [plant["id"]]

    # Riwayat Scan keeps the scan (design principle 7), flagged as an ended plant.
    rows = (await client.get(f"/api/v1/scans?plant_id={plant['id']}", headers=headers)).json()[
        "data"
    ]
    assert len(rows) == 1
    assert (rows[0]["plant_code"], rows[0]["plant_ended"]) == ("MGA-001", True)
    assert (rows[0]["disease_label"], rows[0]["confidence_percent"]) == ("Antraknosa", 93)
    assert rows[0]["prevention_summary"].startswith("Pangkas tajuk")
    # Ending tracking closes the open episode instead of leaving it dangling.
    episodes = (
        await client.get(f"/api/v1/plants/{plant['id']}/disease-episodes", headers=headers)
    ).json()["data"]
    assert (episodes[0]["status"], episodes[0]["close_reason"]) == ("resolved", "tracking_ended")

    stranger = auth_headers(await register(client))
    assert (await client.get(f"/api/v1/plants/{plant['id']}", headers=stranger)).status_code == 404
    assert (await upload_scan(client, stranger, plant_id=plant["id"])).status_code == 404


async def test_scan_on_a_tracked_plant_shows_in_its_history(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    tracked = await create_plant(client, headers, farm["id"])
    scan = await upload_scan(client, headers, plant_id=tracked["id"])
    assert scan.status_code == 201, scan.text

    plant = (await client.get(f"/api/v1/plants/{tracked['id']}", headers=headers)).json()["data"]
    assert plant["health_status"] == "sick"
    timeline = (
        await client.get(f"/api/v1/plants/{tracked['id']}/timeline", headers=headers)
    ).json()
    assert timeline["data"][0]["kind"] == "scan"
    listed = (await client.get(f"/api/v1/scans?plant_id={tracked['id']}", headers=headers)).json()
    assert [row["id"] for row in listed["data"]] == [scan.json()["data"]["id"]]


async def test_forum_likes_are_idempotent(client: AsyncClient) -> None:
    author = auth_headers(await register(client))
    reader = auth_headers(await register(client))
    post = (
        await client.post(
            "/api/v1/forum/posts",
            json={"title": "Panen mangga pertama", "body": "Alhamdulillah"},
            headers=author,
        )
    ).json()["data"]
    assert post["author"]["username"].startswith("petani_")
    url = f"/api/v1/forum/posts/{post['id']}/like"
    for _ in range(2):
        liked = (await client.put(url, headers=reader)).json()["data"]
    assert (liked["like_count"], liked["liked_by_me"]) == (1, True)
    listed = (await client.get("/api/v1/forum/posts", headers=reader)).json()["data"][0]
    assert listed["liked_by_me"] is True
    anonymous = (await client.get(f"/api/v1/forum/posts/{post['id']}")).json()["data"]
    assert (anonymous["like_count"], anonymous["liked_by_me"]) == (1, False)
    unliked = (await client.delete(url, headers=reader)).json()["data"]
    assert unliked["like_count"] == 0
    assert (await client.put(url)).status_code == 401
