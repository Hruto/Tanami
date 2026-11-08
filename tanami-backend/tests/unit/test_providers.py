"""HTTP providers against ``httpx.MockTransport``: no network, real clients."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.core.config import Settings
from app.core.errors import InvalidImage, ServiceUnavailable
from app.providers.push import FcmV1PushProvider, PushOutcome
from app.providers.vision import VisionClient
from app.providers.weather import BmkgWeatherProvider
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, vision_retries=2, **overrides)  # type: ignore[call-arg]


def credentials() -> dict[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {"project_id": "tanami-test", "client_email": "svc@test.iam", "private_key": pem}


async def test_fcm_v1_sends_and_caches_token() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        body = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer tok"
        assert body["message"]["data"]["reminder_id"] == "r1"
        return httpx.Response(200, json={"name": "projects/x/messages/1"})

    provider = FcmV1PushProvider(credentials(), transport=httpx.MockTransport(handler))
    assert await provider.send(token="device", data={"reminder_id": "r1"}) is PushOutcome.SENT
    assert await provider.send(token="device", data={"reminder_id": "r1"}) is PushOutcome.SENT
    assert calls.count("/token") == 1
    await provider.aclose()


async def test_fcm_v1_reports_unregistered_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(
            404,
            json={"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}},
        )

    provider = FcmV1PushProvider(credentials(), transport=httpx.MockTransport(handler))
    assert await provider.send(token="gone", data={}) is PushOutcome.INVALID_TOKEN


async def test_fcm_v1_server_error_is_failed_not_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})

    provider = FcmV1PushProvider(credentials(), transport=httpx.MockTransport(handler))
    assert await provider.send(token="t", data={}) is PushOutcome.FAILED


def vision_ok() -> dict[str, Any]:
    return {
        "data": {
            "type": "disease",
            "status": "confident",
            "model_version": "disease-chili-v0.1.0",
            "commodity_code": "chili",
            "confidence": 0.9,
            "quality": {"blur": "ok", "brightness": "ok"},
            "result": {"top": None, "alternatives": [], "is_healthy": None, "severity": None},
            "inference_ms": 10,
        }
    }


async def predict(client: VisionClient) -> Any:
    return await client.predict(
        scan_type="disease",
        image=b"x",
        content_type="image/jpeg",
        client_uuid="u",
        commodity_code="chili",
    )


async def test_vision_retries_503_then_succeeds() -> None:
    attempts = iter([503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(attempts)
        return httpx.Response(status, json=vision_ok() if status == 200 else {})

    client = VisionClient(settings(), transport=httpx.MockTransport(handler))
    assert (await predict(client)).model_version == "disease-chili-v0.1.0"


async def test_vision_4xx_is_not_retried() -> None:
    seen = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen += 1
        return httpx.Response(422, json={"error": {"code": "invalid_image"}})

    client = VisionClient(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(InvalidImage):
        await predict(client)
    assert seen == 1


async def test_vision_exhausted_and_bad_payload_are_503() -> None:
    down = VisionClient(settings(), transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(ServiceUnavailable):
        await predict(down)
    garbled = VisionClient(
        settings(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"x": 1}))
    )
    with pytest.raises(ServiceUnavailable):
        await predict(garbled)


async def test_bmkg_provider_maps_failures_to_503() -> None:
    provider = BmkgWeatherProvider(
        settings(), transport=httpx.MockTransport(lambda r: httpx.Response(500))
    )
    with pytest.raises(ServiceUnavailable):
        await provider.fetch("31.71.03.1001")
    empty = BmkgWeatherProvider(
        settings(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []}))
    )
    with pytest.raises(ServiceUnavailable):
        await empty.fetch("31.71.03.1001")
