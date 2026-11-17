"""Perubahan pasca-rapat: varietas bebas, umur pembibitan, indoor, panen, irigasi."""

from __future__ import annotations

from datetime import date, timedelta

from httpx import AsyncClient

from tests.helpers import auth_headers, create_farm, image_bytes, register

TODAY = date.today()


async def test_add_tanaman_memakai_varietas_bebas_dan_tanggal_pembibitan(
    client: AsyncClient,
) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    response = await client.post(
        f"/api/v1/farms/{farm['id']}/plants",
        json={
            "label": "Pohon Mangga",
            "variety": "Mangga Arumanis",
            "nursery_started_at": (TODAY - timedelta(days=30)).isoformat(),
            "placement": "indoor",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    plant = response.json()["data"]
    assert plant["variety"] == "Mangga Arumanis"
    assert plant["commodity_label"] == "Mangga"
    assert plant["placement"] == "indoor"
    assert plant["age_days"] == 30
    assert plant["planted_at"] == plant["nursery_started_at"]


async def test_endpoint_archive_sudah_dihapus(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    response = await client.post(
        f"/api/v1/farms/{farm['id']}/plants",
        json={
            "label": "Jeruk Siam",
            "variety": "Jeruk Siam",
            "nursery_started_at": (TODAY - timedelta(days=10)).isoformat(),
        },
        headers=headers,
    )
    plant_id = response.json()["data"]["id"]
    assert (await client.delete(f"/api/v1/plants/{plant_id}", headers=headers)).status_code == 405
    assert (await client.delete(f"/api/v1/farms/{farm['id']}", headers=headers)).status_code == 405


async def test_panen_menghasilkan_persen_dan_kategori_kualitas(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    plant = (
        await client.post(
            f"/api/v1/farms/{farm['id']}/plants",
            json={
                "label": "Mangga 1",
                "variety": "Mangga Arumanis",
                "nursery_started_at": (TODAY - timedelta(days=800)).isoformat(),
            },
            headers=headers,
        )
    ).json()["data"]
    url = f"/api/v1/plants/{plant['id']}/harvests"
    bad = await client.post(url, json={"quality": "Istimewa"}, headers=headers)
    assert bad.status_code == 400
    ok = await client.post(url, json={"quantity_kg": 15}, headers=headers)
    assert ok.status_code == 201, ok.text
    record = ok.json()["data"]
    assert record["quality"] in {"gagal", "kurang_optimal", "normal", "panen_raya"}
    assert record["success_pct"] is not None


async def test_irigasi_bisa_diubah_dan_riwayatnya_tersimpan(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    plant = (
        await client.post(
            f"/api/v1/farms/{farm['id']}/plants",
            json={
                "label": "Stroberi 1",
                "variety": "Stroberi Frigo",
                "nursery_started_at": (TODAY - timedelta(days=20)).isoformat(),
            },
            headers=headers,
        )
    ).json()["data"]
    url = f"/api/v1/plants/{plant['id']}/irrigation"
    changed = await client.patch(
        url, json={"schedule": "daily", "reason": "cuaca panas"}, headers=headers
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["irrigation_schedule"] == "daily"
    history = await client.get(f"{url}/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["data"][0]["from_schedule"] == "every_3_5_days"
    assert history.json()["data"][0]["to_schedule"] == "daily"


async def test_endpoint_progress_dan_saran_irigasi_indoor(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    plant = (
        await client.post(
            f"/api/v1/farms/{farm['id']}/plants",
            json={
                "label": "Mangga 2",
                "variety": "Mangga Arumanis",
                "nursery_started_at": (TODAY - timedelta(days=100)).isoformat(),
                "placement": "indoor",
            },
            headers=headers,
        )
    ).json()["data"]
    progress = await client.get(f"/api/v1/plants/{plant['id']}/progress", headers=headers)
    assert progress.status_code == 200, progress.text
    body = progress.json()["data"]
    assert body["age_days"] == 100
    assert 0 <= body["percent_to_first_harvest"] <= 100
    assert "estimated_first_harvest" in body

    advice = await client.get(f"/api/v1/plants/{plant['id']}/irrigation-advice", headers=headers)
    assert advice.status_code == 200, advice.text
    assert advice.json()["data"]["weather_used"] is False


async def test_create_tanaman_dengan_thumbnail_satu_panggilan(client: AsyncClient) -> None:
    """Form Tambah Tanaman: satu kirim, foto langsung jadi thumbnail."""
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    response = await client.post(
        f"/api/v1/farms/{farm['id']}/plants/with-photo",
        data={
            "label": "Pohon Mangga",
            "variety": "Mangga Arumanis",
            "nursery_started_at": (TODAY - timedelta(days=7)).isoformat(),
            "placement": "indoor",
            "irrigation_schedule": "daily",
        },
        files={"photo": ("thumb.jpg", image_bytes(), "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    plant = response.json()["data"]
    assert plant["cover_photo_url"] is not None
    photos = await client.get(f"/api/v1/plants/{plant['id']}/photos", headers=headers)
    assert len(photos.json()["data"]) == 1


async def test_thumbnail_rusak_tidak_membuat_tanaman(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    farm = await create_farm(client, headers)
    response = await client.post(
        f"/api/v1/farms/{farm['id']}/plants/with-photo",
        data={
            "label": "Pohon Mangga",
            "variety": "Mangga Arumanis",
            "nursery_started_at": (TODAY - timedelta(days=7)).isoformat(),
        },
        files={"photo": ("rusak.jpg", b"bukan gambar", "image/jpeg")},
        headers=headers,
    )
    assert response.status_code in (400, 422), response.text
    plants = await client.get(f"/api/v1/farms/{farm['id']}/plants", headers=headers)
    assert plants.json()["data"] == []
