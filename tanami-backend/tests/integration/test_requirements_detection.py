"""Requirements 3-5: detection plant list, detection history, forum likes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from httpx import AsyncClient

from tests.helpers import (
    auth_headers,
    create_farm,
    create_plant,
    image_bytes,
    register,
)


async def detect(client: AsyncClient, headers: dict[str, str], detection_id: str) -> Any:
    key = str(uuid4())
    return await client.post(
        "/api/v1/scans",
        data={"type": "disease", "client_uuid": key, "detection_plant_id": detection_id},
        files={"image": ("d.jpg", image_bytes(), "image/jpeg")},
        headers={**headers, "Idempotency-Key": key},
    )


async def test_detection_list_result_end_and_reactivate(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    unsupported = await client.post(
        "/api/v1/detection-plants",
        json={"name": "Tomat", "commodity_code": "tomato"},
        headers=headers,
    )
    assert unsupported.status_code == 400
    created = await client.post(
        "/api/v1/detection-plants", json={"name": "  Cabai   tetangga "}, headers=headers
    )
    plant = created.json()["data"]
    assert (plant["name"], plant["status"], plant["scan_count"]) == ("Cabai tetangga", "active", 0)

    scan = await detect(client, headers, plant["id"])
    assert scan.status_code == 201, scan.text
    result = scan.json()["data"]["result"]
    assert result["confidence_percent"] == 93
    advice = result["advice"]
    assert (
        advice["disease_name"] == "Antraknosa"
        and advice["symptoms"]
        and advice["treatments"]["safety_note"]
    )
    assert scan.json()["data"]["detection_plant_id"] == plant["id"]

    url = f"/api/v1/detection-plants/{plant['id']}"
    ended = await client.post(f"{url}/end", json={"note": "Sudah dicabut"}, headers=headers)
    assert ended.json()["data"]["status"] == "ended"
    assert (await detect(client, headers, plant["id"])).status_code == 400
    assert (await client.get("/api/v1/detection-plants", headers=headers)).json()["data"] == []
    history = (await client.get("/api/v1/detection-plants?status=ended", headers=headers)).json()[
        "data"
    ]
    assert (
        history[0]["cover_image_url"] and history[0]["last_result"]["disease_name"] == "Antraknosa"
    )

    await client.post(f"{url}/reactivate", headers=headers)
    assert (await detect(client, headers, plant["id"])).status_code == 201
    detail = (await client.get(url, headers=headers)).json()["data"]
    assert detail["status"] == "active" and detail["scan_count"] == 2 and len(detail["scans"]) == 2
    filtered = await client.get(f"/api/v1/scans?detection_plant_id={plant['id']}", headers=headers)
    assert len(filtered.json()["data"]) == 2

    stranger = auth_headers(await register(client))
    assert (await client.get(url, headers=stranger)).status_code == 404
    assert (await detect(client, stranger, plant["id"])).status_code == 404


async def test_detection_linked_to_tracked_plant_shows_in_its_history(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    tracked = await create_plant(client, headers, farm["id"])
    detection = (
        await client.post(
            "/api/v1/detection-plants",
            json={"name": "Cabai blok A", "plant_id": tracked["id"]},
            headers=headers,
        )
    ).json()["data"]
    await detect(client, headers, detection["id"])
    plant = (await client.get(f"/api/v1/plants/{tracked['id']}", headers=headers)).json()["data"]
    assert plant["health_status"] == "sick"
    timeline = (
        await client.get(f"/api/v1/plants/{tracked['id']}/timeline", headers=headers)
    ).json()
    assert timeline["data"][0]["kind"] == "scan"


async def test_forum_likes_are_idempotent(client: AsyncClient) -> None:
    author = auth_headers(await register(client))
    reader = auth_headers(await register(client))
    post = (
        await client.post(
            "/api/v1/forum/posts",
            json={"title": "Panen tomat pertama", "body": "Alhamdulillah"},
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
