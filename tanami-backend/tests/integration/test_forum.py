"""Forum, moderation, roles and feedback review (design 10.10, 13; TQA 8.4)."""

from __future__ import annotations

from typing import Any

from app.core.state import AppState
from app.models.user import User
from httpx import AsyncClient
from sqlalchemy import update

from tests.helpers import (
    auth_headers,
    create_farm,
    create_plant,
    image_bytes,
    register,
    upload_scan,
)

POST = {"commodity_code": "mango", "title": "Daun mangga bercak", "body": "Kenapa ya?"}


async def stored_scan(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    """A scan this user owns: v2 stores scans only against a plant (design 10.6)."""
    farm = await create_farm(client, headers)
    plant = await create_plant(client, headers, farm["id"])
    response = await upload_scan(client, headers, plant_id=plant["id"])
    assert response.status_code == 201, response.text
    return dict(response.json()["data"])


async def user_with_role(client: AsyncClient, state: AppState, role: str) -> dict[str, str]:
    headers = auth_headers(await register(client))
    me = (await client.get("/api/v1/users/me", headers=headers)).json()["data"]
    async with state.session_factory() as session:
        await session.execute(update(User).where(User.id == me["id"]).values(role=role))
        await session.commit()
    return headers


async def new_post(client: AsyncClient, headers: dict[str, str], **extra: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/forum/posts", json=POST | extra, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json()["data"])


async def upload_photo(client: AsyncClient, headers: dict[str, str]) -> str:
    files = {"image": ("x.jpg", image_bytes(), "image/jpeg")}
    response = await client.post("/api/v1/uploads/forum-image", files=files, headers=headers)
    assert response.status_code == 201
    return str(response.json()["data"]["image_key"])


async def test_post_with_photo_scan_and_public_listing(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    key = await upload_photo(client, headers)
    scan = await stored_scan(client, headers)
    post = await new_post(client, headers, image_keys=[key], scan_id=scan["id"])
    assert post["image_urls"][0].endswith(key)
    assert post["scan_summary"]["label"] == "Antraknosa"
    assert "plant_id" not in post["scan_summary"]

    listed = (await client.get("/api/v1/forum/posts?q=bercak")).json()
    assert [row["id"] for row in listed["data"]] == [post["id"]]
    assert (await client.get("/api/v1/forum/posts?q=100%25")).json()["data"] == []
    cats = (await client.get("/api/v1/forum/categories")).json()["data"]
    # design 10.9 v2: Mangga, Jeruk, Stroberi plus "Umum" - nothing else.
    assert [c["commodity_code"] for c in cats] == ["mango", "citrus", "strawberry", "general"]
    counts = {c["commodity_code"]: c["post_count"] for c in cats}
    assert counts == {"mango": 1, "citrus": 0, "strawberry": 0, "general": 0}


async def test_cannot_attach_someone_elses_photo_or_scan(client: AsyncClient) -> None:
    alice = auth_headers(await register(client))
    bob = auth_headers(await register(client))
    alice_key = await upload_photo(client, alice)
    alice_scan = await stored_scan(client, alice)
    stolen = await client.post(
        "/api/v1/forum/posts", json=POST | {"image_keys": [alice_key]}, headers=bob
    )
    assert stolen.status_code == 400
    scan_key = alice_scan["image_url"].removeprefix("/media/")
    private = await client.post(
        "/api/v1/forum/posts", json=POST | {"image_keys": [scan_key]}, headers=bob
    )
    assert private.status_code == 400
    other_scan = await client.post(
        "/api/v1/forum/posts", json=POST | {"scan_id": alice_scan["id"]}, headers=bob
    )
    assert other_scan.status_code == 404
    bad = await client.post(
        "/api/v1/forum/posts", json=POST | {"scan_id": "bukan-uuid"}, headers=bob
    )
    assert bad.status_code == 400
    unknown = await client.post(
        "/api/v1/forum/posts", json=POST | {"commodity_code": "durian"}, headers=bob
    )
    assert unknown.status_code == 400


async def test_comments_counters_and_deletion(client: AsyncClient) -> None:
    author = auth_headers(await register(client))
    reader = auth_headers(await register(client))
    post = await new_post(client, author)
    url = f"/api/v1/forum/posts/{post['id']}/comments"
    comment = (await client.post(url, json={"body": "Coba semprot"}, headers=reader)).json()["data"]
    assert (await client.get(f"/api/v1/forum/posts/{post['id']}")).json()["data"][
        "comment_count"
    ] == 1
    assert (
        await client.delete(f"/api/v1/forum/comments/{comment['id']}", headers=author)
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/forum/comments/{comment['id']}", headers=reader)
    ).status_code == 204
    detail = (await client.get(f"/api/v1/forum/posts/{post['id']}")).json()["data"]
    assert detail["comment_count"] == 0 and detail["comments"] == []


async def test_three_reports_hide_until_moderator_decides(
    client: AsyncClient, state: AppState
) -> None:
    author = auth_headers(await register(client))
    post = await new_post(client, author)
    report = {"target_type": "post", "target_id": post["id"], "reason": "spam"}
    first = auth_headers(await register(client))
    assert (
        await client.post("/api/v1/forum/reports", json=report, headers=first)
    ).status_code == 201
    twice = await client.post("/api/v1/forum/reports", json=report, headers=first)
    assert twice.status_code == 409
    for _ in range(2):
        reporter = auth_headers(await register(client))
        await client.post("/api/v1/forum/reports", json=report, headers=reporter)

    post_url = f"/api/v1/forum/posts/{post['id']}"
    assert (await client.get(post_url)).status_code == 404  # hidden from the public
    assert (await client.get(post_url, headers=author)).json()["data"]["status"] == "hidden"
    assert (await client.get("/api/v1/forum/posts")).json()["data"] == []

    farmer = auth_headers(await register(client))
    assert (await client.get("/api/v1/moderation/reports", headers=farmer)).status_code == 403

    moderator = await user_with_role(client, state, "moderator")
    queue = (await client.get("/api/v1/moderation/reports", headers=moderator)).json()["data"]
    assert queue[0]["report_count"] == 3 and queue[0]["reasons"] == {"spam": 3}

    resolve = f"/api/v1/moderation/reports/post/{post['id']}/resolve"
    done = await client.post(resolve, json={"action": "dismiss"}, headers=moderator)
    assert done.json()["data"] == {"resolved_reports": 3}
    assert (await client.get(post_url)).json()["data"]["status"] == "published"
    assert (await client.get("/api/v1/moderation/reports", headers=moderator)).json()["data"] == []


async def test_moderator_can_remove_and_restore(client: AsyncClient, state: AppState) -> None:
    author = auth_headers(await register(client))
    post = await new_post(client, author)
    moderator = await user_with_role(client, state, "moderator")
    url = f"/api/v1/moderation/posts/{post['id']}"
    assert (
        await client.patch(url, json={"status": "removed"}, headers=moderator)
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/forum/posts/{post['id']}", headers=author)
    ).status_code == 404
    await client.patch(url, json={"status": "published"}, headers=moderator)
    assert (await client.get(f"/api/v1/forum/posts/{post['id']}")).status_code == 200


async def test_admin_roles_and_broadcast(client: AsyncClient, state: AppState) -> None:
    admin = await user_with_role(client, state, "admin")
    farmer_tokens = await register(client)
    farmer = auth_headers(farmer_tokens)
    farmer_id = (await client.get("/api/v1/users/me", headers=farmer)).json()["data"]["id"]

    expert = await client.patch(
        f"/api/v1/admin/users/{farmer_id}/role", json={"role": "expert"}, headers=admin
    )
    assert expert.json()["data"]["role"] == "expert"
    assert (
        await client.patch(
            f"/api/v1/admin/users/{farmer_id}/role", json={"role": "admin"}, headers=farmer
        )
    ).status_code == 403

    sent = await client.post(
        "/api/v1/admin/reminders/general",
        json={"title": "Fitur baru Tanami", "body": "Sekarang ada grafik panen."},
        headers=admin,
    )
    assert sent.json()["data"]["created"] == 2
    items = (await client.get("/api/v1/reminders", headers=farmer)).json()["data"]
    assert items[0]["type"] == "general" and items[0]["farm_id"] is None


async def test_expert_reviews_incorrect_feedback(client: AsyncClient, state: AppState) -> None:
    farmer = auth_headers(await register(client))
    scan_id = (await stored_scan(client, farmer))["id"]
    await client.put(
        f"/api/v1/scans/{scan_id}/feedback", json={"value": "incorrect"}, headers=farmer
    )

    assert (await client.get("/api/v1/review/feedback", headers=farmer)).status_code == 403
    expert = await user_with_role(client, state, "expert")
    queue = (await client.get("/api/v1/review/feedback", headers=expert)).json()["data"]
    assert len(queue) == 1 and queue[0]["consent_training_data"] is False
    url = f"/api/v1/review/feedback/{queue[0]['id']}"
    assert (
        await client.patch(url, json={"correct_label": "durian"}, headers=expert)
    ).status_code == 400
    reviewed = await client.patch(url, json={"correct_label": "healthy"}, headers=expert)
    assert reviewed.json()["data"]["reviewed_at"] is not None
    assert (await client.get("/api/v1/review/feedback", headers=expert)).json()["data"] == []
