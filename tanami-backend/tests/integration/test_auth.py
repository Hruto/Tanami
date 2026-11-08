"""Auth, profile, devices (design 10.4) and the error envelope (10.1, 10.2)."""

from __future__ import annotations

from app.core.state import AppState
from httpx import AsyncClient

from tests.helpers import auth_headers, login, register, register_payload

BAD_LOGIN = {"email": "x@example.com", "password": "salah-123"}


async def test_register_login_refresh_rotates_and_logout(client: AsyncClient) -> None:
    tokens = await register(client, email="budi@example.com")
    assert tokens["token_type"] == "bearer" and tokens["expires_in"] > 0

    again = await login(client, email="BUDI@example.com")
    body = {"refresh_token": again["refresh_token"]}
    refreshed = await client.post("/api/v1/auth/refresh", json=body)
    assert refreshed.status_code == 200
    # Rotation: the old refresh token is now spent.
    reused = await client.post("/api/v1/auth/refresh", json=body)
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "unauthorized"

    new = refreshed.json()["data"]
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": new["refresh_token"]})
    assert out.status_code == 204
    assert (await client.get("/api/v1/users/me", headers=auth_headers(new))).status_code == 401


async def test_duplicate_registration_is_conflict(client: AsyncClient) -> None:
    await register(client, email="sari@example.com")
    payload = register_payload(email="sari@example.com")
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"field": "email"}


async def test_validation_errors_use_the_envelope(client: AsyncClient) -> None:
    both = register_payload(email="a@example.com") | {"phone": "08123456789"}
    response = await client.post("/api/v1/auth/register", json=both)
    body = response.json()
    assert response.status_code == 400
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]

    short = await client.post("/api/v1/auth/register", json=register_payload() | {"password": "1"})
    assert short.status_code == 400
    assert short.json()["error"]["details"]["fields"][0]["field"] == "password"


async def test_wrong_password_and_unknown_account_look_identical(client: AsyncClient) -> None:
    await register(client, email="tani@example.com")
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "tani@example.com", "password": "salah-123"}
    )
    ghost = await client.post("/api/v1/auth/login", json=BAD_LOGIN)
    assert wrong.status_code == ghost.status_code == 401
    assert wrong.json()["error"]["message"] == ghost.json()["error"]["message"]


# The limiter uses fixed one-minute windows, so a burst can straddle a window
# boundary. Twelve attempts guarantee at least six land in one window.
async def test_login_rate_limit_returns_retry_after(client: AsyncClient) -> None:
    responses = [await client.post("/api/v1/auth/login", json=BAD_LOGIN) for _ in range(12)]
    blocked = [r for r in responses if r.status_code == 429]
    assert blocked, [r.status_code for r in responses]
    assert int(blocked[0].headers["Retry-After"]) >= 1
    assert blocked[0].json()["error"]["code"] == "rate_limited"


async def test_spoofed_forwarded_for_does_not_bypass_login_limit(client: AsyncClient) -> None:
    statuses = [
        (
            await client.post(
                "/api/v1/auth/login", json=BAD_LOGIN, headers={"X-Forwarded-For": f"10.0.0.{i}"}
            )
        ).status_code
        for i in range(12)
    ]
    assert 429 in statuses


async def test_password_change_logs_out_other_devices(client: AsyncClient) -> None:
    first = await register(client, email="ganti@example.com")
    second = await login(client, email="ganti@example.com")
    url = "/api/v1/users/me/password"
    wrong = await client.post(
        url,
        json={"current_password": "salah-123", "new_password": "sandi-baru-456"},
        headers=auth_headers(first),
    )
    assert wrong.status_code == 400
    changed = await client.post(
        url,
        json={"current_password": "sandi-keren-123", "new_password": "sandi-baru-456"},
        headers=auth_headers(first),
    )
    assert changed.status_code == 200
    assert (await client.get("/api/v1/users/me", headers=auth_headers(second))).status_code == 401
    fresh = changed.json()["data"]
    assert (await client.get("/api/v1/users/me", headers=auth_headers(fresh))).status_code == 200
    relogin = await client.post(
        "/api/v1/auth/login", json={"email": "ganti@example.com", "password": "sandi-baru-456"}
    )
    assert relogin.status_code == 200


async def test_profile_update_and_identifier_conflict(client: AsyncClient) -> None:
    await register(client, email="dipakai@example.com", username="dipakai")
    headers = auth_headers(await register(client, email="saya@example.com"))
    ok = await client.patch(
        "/api/v1/users/me",
        json={"full_name": "  Bu   Sari ", "username": "Bu.Sari", "consent_training_data": True},
        headers=headers,
    )
    assert ok.status_code == 200
    me = ok.json()["data"]
    assert (me["full_name"], me["username"]) == ("Bu Sari", "bu.sari")
    assert me["consent_at"] is not None
    for field, value in (("email", "dipakai@example.com"), ("username", "dipakai")):
        taken = await client.patch("/api/v1/users/me", json={field: value}, headers=headers)
        assert taken.status_code == 409, field
    bad = await client.patch("/api/v1/users/me", json={"username": "a b"}, headers=headers)
    assert bad.status_code == 400
    by_username = await client.post(
        "/api/v1/auth/login", json={"username": "BU.SARI", "password": "sandi-keren-123"}
    )
    assert by_username.status_code == 200


async def test_delete_account_revokes_every_session(client: AsyncClient) -> None:
    first = await register(client, email="hapus@example.com")
    second = await login(client, email="hapus@example.com")
    response = await client.delete("/api/v1/users/me", headers=auth_headers(first))
    assert response.status_code == 202
    assert response.json()["data"]["scheduled_removal_days"] == 30
    for tokens in (first, second):
        me = await client.get("/api/v1/users/me", headers=auth_headers(tokens))
        assert me.status_code == 401
    relogin = await client.post(
        "/api/v1/auth/login", json={"email": "hapus@example.com", "password": "sandi-keren-123"}
    )
    assert relogin.status_code == 401


async def test_notification_settings_roundtrip(client: AsyncClient) -> None:
    headers = auth_headers(await register(client))
    url = "/api/v1/users/me/notification-settings"
    default = (await client.get(url, headers=headers)).json()["data"]
    assert default["quiet_hours"] == {"start": 21, "end": 5}
    assert all(default["enabled"].values())
    patched = await client.patch(
        url, json={"enabled": {"heat_stress": False}, "quiet_hours_start": 22}, headers=headers
    )
    assert patched.json()["data"]["enabled"]["heat_stress"] is False
    assert patched.json()["data"]["quiet_hours"] == {"start": 22, "end": 5}


async def test_device_registration_moves_token_between_accounts(client: AsyncClient) -> None:
    alice = auth_headers(await register(client))
    bob = auth_headers(await register(client))
    payload = {"fcm_token": "fcm-token-shared-123", "platform": "android"}
    assert (await client.post("/api/v1/devices", json=payload, headers=alice)).status_code == 201
    moved = await client.post("/api/v1/devices", json=payload, headers=bob)
    assert moved.status_code == 201
    assert (await client.get("/api/v1/devices", headers=alice)).json()["data"] == []
    device_id = moved.json()["data"]["id"]
    url = f"/api/v1/devices/{device_id}"
    assert (await client.delete(url, headers=alice)).status_code == 404
    assert (await client.delete("/api/v1/devices/bukan-uuid", headers=bob)).status_code == 400
    assert (await client.delete(url, headers=bob)).status_code == 204


async def test_bootstrap_admin_role(client: AsyncClient, state: AppState) -> None:
    state.settings.bootstrap_admins = "boss@example.com"
    tokens = await register(client, email="boss@example.com")
    me = await client.get("/api/v1/users/me", headers=auth_headers(tokens))
    assert me.json()["data"]["role"] == "admin"


async def test_missing_or_garbage_token_is_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/users/me")).status_code == 401
    garbage = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer x.y.z"})
    assert garbage.status_code == 401
    assert garbage.json()["error"]["code"] == "unauthorized"
