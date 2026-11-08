"""The main journey (TQA 7 E2E list): register, farm, plant, scan, history."""

from __future__ import annotations

from httpx import AsyncClient

from tests.helpers import auth_headers, create_farm, create_plant, register, upload_scan


async def test_register_farm_plant_scan_history(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    plant = await create_plant(client, headers, farm["id"])

    response = await upload_scan(client, headers, plant_id=plant["id"])
    assert response.status_code == 201, response.text
    scan = response.json()["data"]
    assert scan["status"] == "confident"
    assert scan["result"]["advice"]["disease_detail_url"] == "/diseases/anthracnose"

    plant_now = (await client.get(f"/api/v1/plants/{plant['id']}", headers=headers)).json()
    assert plant_now["data"]["health_status"] == "sick"

    timeline = await client.get(f"/api/v1/plants/{plant['id']}/timeline", headers=headers)
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["data"][0]["kind"] == "scan"
