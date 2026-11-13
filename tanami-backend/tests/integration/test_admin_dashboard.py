"""Endpoints behind the staff dashboard (tanami-admin)."""

from __future__ import annotations

from datetime import date

from app.core.state import AppState
from app.data.seed import seed_diseases
from app.models.content import Disease
from httpx import AsyncClient
from sqlalchemy import select, update

from tests.helpers import auth_headers, create_farm, create_plant, register, upload_scan
from tests.integration.test_forum import new_post, user_with_role


async def test_overview_counts_and_access(client: AsyncClient, state: AppState) -> None:
    farmer = auth_headers(await register(client))
    farm = await create_farm(client, farmer)
    plant = await create_plant(client, farmer, farm["id"])
    active = await create_plant(client, farmer, farm["id"])
    # design 8.6: the user picks a v2 reason; no harvest yet -> ``failed``.
    ended = await client.post(
        f"/api/v1/plants/{plant['id']}/end",
        json={"reason": "cut_down", "cause_note": "Lahan dipakai untuk komoditas lain"},
        headers=farmer,
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["data"]["outcome"] == "failed"
    scan_id = (await upload_scan(client, farmer, plant_id=active["id"])).json()["data"]["id"]
    await client.put(
        f"/api/v1/scans/{scan_id}/feedback", json={"value": "incorrect"}, headers=farmer
    )
    post = await new_post(client, farmer)
    reporter = auth_headers(await register(client))
    report = {"target_type": "post", "target_id": post["id"], "reason": "spam"}
    assert (
        await client.post("/api/v1/forum/reports", json=report, headers=reporter)
    ).status_code == 201

    assert (await client.get("/api/v1/admin/overview", headers=farmer)).status_code == 403
    moderator = await user_with_role(client, state, "moderator")
    response = await client.get("/api/v1/admin/overview", headers=moderator)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["users"]["total"] == 3
    assert data["users"]["by_role"] == {"farmer": 2, "expert": 0, "moderator": 1, "admin": 0}
    assert data["tracking"] == {
        "active_plants": 1,
        "ended_plants": 1,
        "outcomes": {"completed": 0, "ended_early": 0, "failed": 1},
    }
    assert data["detection"]["scans_total"] == 1
    assert data["detection"]["scans_7d"] == 1
    assert data["queues"] == {"open_reports": 1, "feedback_pending": 1}
    assert len(data["scans_daily"]) == 14
    assert sum(day["disease"] for day in data["scans_daily"]) == 1
    assert data["scans_daily"][-1]["disease"] == 1
    assert sum(data["scan_status_30d"].values()) == 1


async def test_admin_user_search_and_pagination(client: AsyncClient, state: AppState) -> None:
    admin = await user_with_role(client, state, "admin")
    for index in range(3):
        await register(client, full_name=f"Ibu Sari {index}")
    expert = auth_headers(await register(client, full_name="Pak Agronom"))
    expert_id = (await client.get("/api/v1/users/me", headers=expert)).json()["data"]["id"]
    await client.patch(
        f"/api/v1/admin/users/{expert_id}/role", json={"role": "expert"}, headers=admin
    )

    assert (await client.get("/api/v1/admin/users", headers=expert)).status_code == 403

    page = await client.get("/api/v1/admin/users?q=sari&limit=2", headers=admin)
    body = page.json()
    assert [user["full_name"] for user in body["data"]] == ["Ibu Sari 2", "Ibu Sari 1"]
    assert body["meta"]["has_more"] is True
    rest = await client.get(
        f"/api/v1/admin/users?q=sari&limit=2&cursor={body['meta']['next_cursor']}",
        headers=admin,
    )
    assert [user["full_name"] for user in rest.json()["data"]] == ["Ibu Sari 0"]

    experts = (await client.get("/api/v1/admin/users?role=expert", headers=admin)).json()
    assert [user["id"] for user in experts["data"]] == [expert_id]
    # LIKE wildcards in the search box are literal characters, not patterns.
    wildcard = await client.get("/api/v1/admin/users", params={"q": "%"}, headers=admin)
    assert wildcard.json()["data"] == []


async def test_broadcast_history(client: AsyncClient, state: AppState) -> None:
    admin = await user_with_role(client, state, "admin")
    farmer_tokens = await register(client)
    farmer = auth_headers(farmer_tokens)
    farmer_id = (await client.get("/api/v1/users/me", headers=farmer)).json()["data"]["id"]

    await client.post(
        "/api/v1/admin/reminders/general",
        json={"title": "Musim hujan tiba", "body": "Periksa saluran air kebun."},
        headers=admin,
    )
    await client.post(
        "/api/v1/admin/reminders/general",
        json={"title": "Halo dari tim Tanami", "body": "Terima kasih.", "user_id": farmer_id},
        headers=admin,
    )
    reminder = (await client.get("/api/v1/reminders", headers=farmer)).json()["data"][0]
    await client.patch(
        f"/api/v1/reminders/{reminder['id']}", json={"status": "read"}, headers=farmer
    )

    history = (await client.get("/api/v1/admin/reminders/general", headers=admin)).json()
    assert [(item["title"], item["audience"], item["recipients"]) for item in history["data"]] == [
        ("Halo dari tim Tanami", "user", 1),
        ("Musim hujan tiba", "all", 2),
    ]
    assert history["data"][0]["read"] == 1
    assert (await client.get("/api/v1/admin/reminders/general", headers=farmer)).status_code == 403


async def test_expert_edits_disease_and_seed_keeps_the_edit(
    client: AsyncClient, state: AppState
) -> None:
    expert = await user_with_role(client, state, "expert")
    farmer = auth_headers(await register(client))
    url = "/api/v1/admin/diseases/anthracnose"
    assert (await client.get("/api/v1/admin/diseases", headers=farmer)).status_code == 403

    catalogue = (await client.get("/api/v1/admin/diseases", headers=expert)).json()["data"]
    original = next(item for item in catalogue if item["code"] == "anthracnose")
    assert original["is_active"] is True

    unsafe = dict(original["treatments"], safety_note="")
    rejected = await client.patch(url, json={"treatments": unsafe}, headers=expert)
    assert rejected.status_code == 400
    assert rejected.json()["error"]["details"]["field"] == "treatments.safety_note"
    assert (await client.patch(url, json={"symptoms": None}, headers=expert)).status_code == 400

    new_symptoms = "Bercak cekung kehitaman pada buah, melebar saat musim hujan."
    try:
        edited = await client.patch(url, json={"symptoms": new_symptoms}, headers=expert)
        assert edited.status_code == 200, edited.text
        data = edited.json()["data"]
        assert data["symptoms"] == new_symptoms
        assert data["reviewed_by"] == "Pak Budi"
        assert data["reviewed_at"] > original["reviewed_at"]

        # The startup seed must not undo an expert's newer review.
        async with state.session_factory() as session:
            await seed_diseases(session)
        public = await client.get(url.replace("/admin", ""), headers=farmer)
        assert public.json()["data"]["symptoms"] == new_symptoms

        hidden = await client.patch(url, json={"is_active": False}, headers=expert)
        assert hidden.json()["data"]["is_active"] is False
        assert (await client.get(url.replace("/admin", ""), headers=farmer)).status_code == 404
    finally:
        # Reference data survives between tests: put the seeded text back.
        async with state.session_factory() as session:
            await session.execute(
                update(Disease)
                .where(Disease.code == "anthracnose")
                .values(reviewed_at=date(2000, 1, 1), is_active=True)
            )
            await session.commit()
            await seed_diseases(session)
            restored = await session.scalar(
                select(Disease.symptoms).where(Disease.code == "anthracnose")
            )
    assert restored == original["symptoms"]


async def test_review_queue_lists_allowed_labels(client: AsyncClient, state: AppState) -> None:
    farmer = auth_headers(await register(client))
    farm = await create_farm(client, farmer)
    plant = await create_plant(client, farmer, farm["id"])
    # design 10.6: a stored scan always belongs to a plant in v2.
    scan_id = (await upload_scan(client, farmer, plant_id=plant["id"])).json()["data"]["id"]
    await client.put(
        f"/api/v1/scans/{scan_id}/feedback", json={"value": "incorrect"}, headers=farmer
    )
    admin = await user_with_role(client, state, "admin")
    queue = (await client.get("/api/v1/review/feedback", headers=admin)).json()["data"]
    assert "cercospora_leaf_spot" in queue[0]["allowed_labels"]
    assert "healthy" in queue[0]["allowed_labels"]
