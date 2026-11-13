"""Scans (design 10.6, 11): idempotency, validation, health derivation.

Design v2: every stored scan belongs to an active plant from the start (the
``PATCH /scans/{id}`` attach route is gone), ``type`` is always ``disease``
(``ripeness`` was dropped with the ML ripeness model) and a "Cek cepat" without
``plant_id`` needs ``commodity_code`` and is never stored.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.errors import ServiceUnavailable
from app.core.state import AppState
from app.domain import ScanType
from app.providers.storage import MemoryStorage
from httpx import AsyncClient

from tests.helpers import (
    FakeVision,
    auth_headers,
    create_farm,
    create_plant,
    disease_result,
    image_bytes,
    register,
    text_bytes,
    upload_scan,
    vision_payload,
)


async def setup(client: AsyncClient) -> tuple[dict[str, str], dict[str, Any]]:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    return headers, await create_plant(client, headers, farm["id"])


def leaf(
    code: str, cause: str, status: str = "confident", severity: str | None = "moderate"
) -> Any:
    result = disease_result(code=code, cause=cause, status=status)
    result["severity"] = severity
    return vision_payload(ScanType.DISEASE, result=result, status=status)


async def health(client: AsyncClient, headers: dict[str, str], plant_id: str) -> str:
    plant = (await client.get(f"/api/v1/plants/{plant_id}", headers=headers)).json()["data"]
    return str(plant["health_status"])


async def test_resend_is_idempotent_and_returns_200(
    client: AsyncClient, vision: FakeVision, state: AppState
) -> None:
    headers, plant = await setup(client)
    key = str(uuid4())
    first = await upload_scan(client, headers, client_uuid=key, plant_id=plant["id"])
    again = await upload_scan(client, headers, client_uuid=key, plant_id=plant["id"])
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["data"]["id"] == first.json()["data"]["id"]
    assert again.json()["data"]["is_duplicate"] is True
    assert len(vision.calls) == 1
    assert isinstance(state.storage, MemoryStorage) and len(state.storage.keys) == 1

    # A "Cek cepat" answers 200 and saves nothing (design 10.6).
    quick = await upload_scan(client, headers, commodity_code="mango")
    assert quick.status_code == 200
    body = quick.json()["data"]
    assert (body["saved"], body["id"], body["plant_id"]) == (False, None, None)
    assert isinstance(state.storage, MemoryStorage) and len(state.storage.keys) == 1


async def test_header_and_form_uuid_must_agree(client: AsyncClient) -> None:
    headers, plant = await setup(client)
    response = await client.post(
        "/api/v1/scans",
        data={"type": "disease", "client_uuid": str(uuid4()), "plant_id": plant["id"]},
        files={"image": ("a.jpg", image_bytes(), "image/jpeg")},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    missing = await client.post(
        "/api/v1/scans",
        data={"type": "disease", "plant_id": plant["id"]},
        files={"image": ("a.jpg", image_bytes(), "image/jpeg")},
        headers=headers,
    )
    assert missing.status_code == 400
    # A quick check without a commodity has nothing to look up either.
    no_commodity = await client.post(
        "/api/v1/scans",
        data={"type": "disease"},
        files={"image": ("a.jpg", image_bytes(), "image/jpeg")},
        headers=headers,
    )
    assert no_commodity.status_code == 400


async def test_bad_files_are_rejected_before_inference(
    client: AsyncClient, vision: FakeVision
) -> None:
    headers, plant = await setup(client)
    not_image = await upload_scan(client, headers, image=text_bytes(), plant_id=plant["id"])
    gif = await upload_scan(client, headers, image=image_bytes(fmt="GIF"), plant_id=plant["id"])
    assert (not_image.status_code, not_image.json()["error"]["code"]) == (422, "invalid_image")
    assert (gif.status_code, gif.json()["error"]["code"]) == (415, "unsupported_media_type")
    huge = await upload_scan(client, headers, image=b"0" * (3 * 1024 * 1024), plant_id=plant["id"])
    assert huge.status_code == 413
    assert vision.calls == []


async def test_vision_outage_is_503_and_leaves_no_image(
    client: AsyncClient, vision: FakeVision, state: AppState
) -> None:
    headers, plant = await setup(client)
    vision.enqueue_error(ServiceUnavailable("sibuk"))
    response = await upload_scan(client, headers, plant_id=plant["id"])
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert isinstance(state.storage, MemoryStorage) and state.storage.keys == []


async def test_unknown_disease_code_is_stored_without_advice(
    client: AsyncClient, vision: FakeVision
) -> None:
    headers, plant = await setup(client)
    vision.enqueue_result(leaf("new_class_from_model", "fungus"))
    response = await upload_scan(client, headers, plant_id=plant["id"])
    assert response.status_code == 201, response.text
    assert response.json()["data"]["result"]["advice"] is None


async def test_advice_comes_from_reviewed_knowledge_base(client: AsyncClient) -> None:
    headers, plant = await setup(client)
    scan = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]
    advice = scan["result"]["advice"]
    assert advice["summary"].startswith("Daun tampak terkena")
    assert advice["first_aid"] and advice["reviewed_by"] and advice["reviewed_at"]
    # Design v2: prevention and the full treatment list travel with the result.
    assert advice["prevention"] and advice["treatments"]


async def test_sick_recovering_healthy_cycle(client: AsyncClient, vision: FakeVision) -> None:
    headers, plant = await setup(client)
    pid = plant["id"]
    vision.enqueue_result(leaf("anthracnose", "fungus"))
    await upload_scan(client, headers, plant_id=pid)
    assert await health(client, headers, pid) == "sick"

    vision.enqueue_result(leaf("healthy", "healthy", severity=None))
    await upload_scan(client, headers, plant_id=pid)
    assert await health(client, headers, pid) == "recovering"

    vision.enqueue_result(leaf("healthy", "healthy", severity=None))
    await upload_scan(client, headers, plant_id=pid)
    assert await health(client, headers, pid) == "healthy"


async def test_mild_disease_and_uncertain_mean_at_risk(
    client: AsyncClient, vision: FakeVision
) -> None:
    headers, plant = await setup(client)
    vision.enqueue_result(leaf("cercospora_leaf_spot", "fungus", severity="mild"))
    await upload_scan(client, headers, plant_id=plant["id"])
    assert await health(client, headers, plant["id"]) == "at_risk"


async def test_late_offline_upload_does_not_override_newer_scan(
    client: AsyncClient, vision: FakeVision
) -> None:
    headers, plant = await setup(client)
    vision.enqueue_result(leaf("healthy", "healthy", severity=None))
    await upload_scan(client, headers, plant_id=plant["id"])
    # A photo taken two days ago arrives from the offline queue just now.
    vision.enqueue_result(leaf("anthracnose", "fungus"))
    old = datetime.now(UTC) - timedelta(days=2)
    await upload_scan(client, headers, plant_id=plant["id"], captured_at=old)
    # Replayed in capture order (sick two days ago, healthy now) the plant is
    # recovering. Applying the late photo as "newest" would wrongly say sick.
    assert await health(client, headers, plant["id"]) == "recovering"


async def test_ripeness_type_is_ignored(client: AsyncClient) -> None:
    """Design 10.6 v2: ``type`` is always ``disease``, so a v0.3 client still works."""
    headers, plant = await setup(client)
    response = await upload_scan(client, headers, scan_type="ripeness", plant_id=plant["id"])
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["type"] == "disease"
    assert body["result"]["top"]["disease_code"]


async def test_delete_recomputes_plant_and_removes_image(
    client: AsyncClient, vision: FakeVision, state: AppState
) -> None:
    headers, plant = await setup(client)
    response = await upload_scan(client, headers, plant_id=plant["id"])
    scan_id = response.json()["data"]["id"]
    assert await health(client, headers, plant["id"]) == "sick"
    assert (await client.delete(f"/api/v1/scans/{scan_id}", headers=headers)).status_code == 204
    assert await health(client, headers, plant["id"]) == "unknown"
    assert isinstance(state.storage, MemoryStorage) and state.storage.keys == []


async def test_feedback_detail_and_isolation(client: AsyncClient) -> None:
    headers, plant = await setup(client)
    other = auth_headers(await register(client))
    scan_id = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]["id"]
    url = f"/api/v1/scans/{scan_id}"

    feedback = {"value": "incorrect", "comment": "Ini bercak lain"}
    assert (await client.put(f"{url}/feedback", json=feedback, headers=headers)).status_code == 200
    replaced = await client.put(f"{url}/feedback", json={"value": "correct"}, headers=headers)
    assert replaced.json()["data"]["value"] == "correct"

    detail = (await client.get(url, headers=headers)).json()["data"]
    assert detail["feedback"]["value"] == "correct"
    assert detail["commodity_code"] == "mango"
    assert detail["plant_id"] == plant["id"]

    assert (await client.get(url, headers=other)).status_code == 404
    foreign = await client.put(f"{url}/feedback", json={"value": "correct"}, headers=other)
    assert foreign.status_code == 404


async def test_list_pagination_and_filters(client: AsyncClient) -> None:
    headers, plant = await setup(client)
    for _ in range(4):
        await upload_scan(client, headers, plant_id=plant["id"])
    first = (await client.get("/api/v1/scans?limit=2", headers=headers)).json()
    assert len(first["data"]) == 2 and first["meta"]["has_more"] is True
    rest = await client.get(
        f"/api/v1/scans?limit=2&cursor={first['meta']['next_cursor']}", headers=headers
    )
    ids = {row["id"] for row in first["data"]} | {row["id"] for row in rest.json()["data"]}
    assert len(ids) == 4
    mango = (await client.get("/api/v1/scans?commodity_code=mango", headers=headers)).json()["data"]
    assert len(mango) == 4
    by_plant = (await client.get(f"/api/v1/scans?plant_id={plant['id']}", headers=headers)).json()[
        "data"
    ]
    assert {row["plant_id"] for row in by_plant} == {plant["id"]}
    citrus = (await client.get("/api/v1/scans?commodity_code=citrus", headers=headers)).json()
    assert citrus["data"] == []


async def test_media_route_serves_uploaded_photo(client: AsyncClient) -> None:
    headers, plant = await setup(client)
    url = (await upload_scan(client, headers, plant_id=plant["id"])).json()["data"]["image_url"]
    photo = await client.get(url)
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
