from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from tests.conftest import blurred_image, dark_image, encode, noise_image


def predict(client: TestClient, **overrides: object):  # type: ignore[no-untyped-def]
    payload = {
        "files": {"image": ("photo.jpg", encode(noise_image()), "image/jpeg")},
        "data": {"type": "disease"},
    }
    payload.update(overrides)  # type: ignore[arg-type]
    return client.post("/v1/predict", **payload)  # type: ignore[arg-type]


def test_healthz_reports_loaded_models(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "ok"
    assert {model["scan_type"] for model in body["models"]} == {"disease", "ripeness"}


def test_readyz_is_ready(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["data"] == {"ready": True, "missing": []}


def test_livez_ignores_models(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app
    from tests.conftest import make_settings

    with TestClient(create_app(make_settings(tmp_path))) as test_client:
        assert test_client.get("/livez").status_code == 200
        assert test_client.get("/readyz").status_code == 503


def test_degraded_health_returns_503(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app
    from tests.conftest import make_settings

    with TestClient(create_app(make_settings(tmp_path))) as test_client:
        response = test_client.get("/healthz")
        assert response.status_code == 503
        assert response.json()["data"]["status"] == "degraded"


def test_metrics_endpoint_is_prometheus_text(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "vision_predictions_total" in response.text


def test_openapi_is_served_outside_production(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Tanami Vision"


def test_request_id_header_is_echoed(client: TestClient) -> None:
    response = client.get("/livez", headers={"X-Request-Id": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/livez", headers={"X-Request-Id": "bad id with spaces"})
    assert response.headers["x-request-id"] != "bad id with spaces"


def test_predict_disease_success(client: TestClient) -> None:
    response = predict(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["type"] == "disease"
    assert data["status"] in {"confident", "uncertain", "unknown"}
    assert "result" in data
    assert data["quality"] == {"blur": "ok", "brightness": "ok"}


def test_predict_ripeness_success(client: TestClient) -> None:
    response = predict(client, data={"type": "ripeness"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["type"] == "ripeness"
    assert "stage" in data["result"]


def test_predict_accepts_commodity_code(client: TestClient) -> None:
    response = predict(client, data={"type": "disease", "commodity_code": "chili"})
    assert response.status_code == 200
    assert response.json()["data"]["commodity_code"] == "chili"


def test_predict_rejects_unknown_commodity(client: TestClient) -> None:
    response = predict(client, data={"type": "disease", "commodity_code": "tomato"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["field"] == "commodity_code"


def test_predict_rejects_unknown_scan_type(client: TestClient) -> None:
    response = predict(client, data={"type": "soil"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_predict_requires_image(client: TestClient) -> None:
    response = client.post("/v1/predict", data={"type": "disease"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_predict_rejects_non_image(client: TestClient) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("note.txt", b"hello", "text/plain")},
        data={"type": "disease"},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_predict_rejects_garbage_image(client: TestClient) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", b"garbage", "image/jpeg")},
        data={"type": "disease"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"


def test_predict_rejects_oversized_body(client: TestClient) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", b"x" * (9 * 1024 * 1024), "image/jpeg")},
        data={"type": "disease"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_predict_accepts_idempotency_key(client: TestClient) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", encode(noise_image()), "image/jpeg")},
        data={"type": "disease", "client_uuid": "11111111-1111-1111-1111-111111111111"},
        headers={"Idempotency-Key": "11111111-1111-1111-1111-111111111111"},
    )
    assert response.status_code == 200


def test_blurry_upload_returns_invalid_image_status(client: TestClient) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", encode(blurred_image()), "image/jpeg")},
        data={"type": "disease"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "invalid_image"
    assert data["result"]["top"] is None
    assert data["result"]["alternatives"] == []


def test_dark_upload_returns_invalid_image_status(client: TestClient) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", encode(dark_image()), "image/jpeg")},
        data={"type": "disease"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "invalid_image"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "request_id" in body["error"]


# --------------------------------------------------------------------------- #
# Concurrency and timeout wiring
# --------------------------------------------------------------------------- #
def test_route_uses_the_shared_predict_service(client: TestClient) -> None:
    """The route must resolve the service from app state, not build one.

    A per-request ``PredictService`` also built a per-request CapacityLimiter,
    which silently turned VISION_MAX_CONCURRENT_INFERENCE into a no-op.
    """

    class Spy:
        def __init__(self, inner):  # type: ignore[no-untyped-def]
            self.inner = inner
            self.calls = 0

        async def predict(self, command):  # type: ignore[no-untyped-def]
            self.calls += 1
            return await self.inner.predict(command)

    state = client.app.state.tanami  # type: ignore[attr-defined]
    spy = Spy(state.predict_service)
    state.predict_service = spy

    assert predict(client).status_code == 200
    assert predict(client).status_code == 200
    assert spy.calls == 2


def test_inference_timeout_returns_503(settings) -> None:  # type: ignore[no-untyped-def]
    """A slow model must surface as 503, not as a hung request or a 500.

    The model is made to sleep rather than relying on a tiny timeout: with a
    microsecond budget the work could finish first, so the test would fail or
    pass depending on machine load.

    Uses the ``settings`` fixture so the manifests exist: without them the 503
    would come from the registry and this test would pass for the wrong reason.
    """
    import time

    from app.domain import ScanType
    from app.main import create_app

    timed_out = settings.model_copy(update={"inference_timeout_seconds": 0.05})
    app = create_app(timed_out)
    with TestClient(app) as test_client:
        model = test_client.app.state.tanami.registry.primary(ScanType.DISEASE)  # type: ignore[attr-defined]

        def slow(_image):  # type: ignore[no-untyped-def]
            time.sleep(0.5)
            raise AssertionError("the timeout should have abandoned this call")

        with pytest.MonkeyPatch.context() as patcher:
            patcher.setattr(model.predictor, "predict", slow)
            response = predict(test_client)

    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "service_unavailable"
    assert "tepat waktu" in body["message"]


def test_wrong_method_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/v1/predict")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "validation_error"


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@pytest.fixture
def secured_client(tmp_path) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    from app.core.config import Settings
    from app.main import create_app
    from tests.conftest import (
        DISEASE_LABELS,
        MODEL_VERSIONS,
        RIPENESS_LABELS,
        make_settings,
        write_manifest,
    )

    base = make_settings(tmp_path)
    write_manifest(
        base.model_dir,
        scan_type="disease",
        version=MODEL_VERSIONS["disease"],
        labels=DISEASE_LABELS,
    )
    write_manifest(
        base.model_dir,
        scan_type="ripeness",
        version=MODEL_VERSIONS["ripeness"],
        labels=RIPENESS_LABELS,
    )
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="local",
        model_backend="stub",
        model_dir=base.model_dir,
        service_token="s3cret",
        admin_token="adm1n",
        log_json=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_predict_without_token_is_unauthorized(secured_client: TestClient) -> None:
    response = predict(secured_client)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"


def test_predict_with_wrong_token_is_unauthorized(secured_client: TestClient) -> None:
    response = secured_client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", encode(noise_image()), "image/jpeg")},
        data={"type": "disease"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_predict_with_token_succeeds(secured_client: TestClient) -> None:
    response = secured_client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", encode(noise_image()), "image/jpeg")},
        data={"type": "disease"},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert response.status_code == 200


def test_healthz_does_not_require_token(secured_client: TestClient) -> None:
    assert secured_client.get("/healthz").status_code == 200


def test_models_endpoint_does_not_require_token(secured_client: TestClient) -> None:
    assert secured_client.get("/v1/models").status_code == 200


def test_reload_requires_admin_token(secured_client: TestClient) -> None:
    assert secured_client.post("/v1/models/reload").status_code == 401
    response = secured_client.post("/v1/models/reload", headers={"Authorization": "Bearer s3cret"})
    assert response.status_code == 401


def test_reload_with_admin_token_succeeds(secured_client: TestClient) -> None:
    response = secured_client.post("/v1/models/reload", headers={"Authorization": "Bearer adm1n"})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_reload_is_disabled_without_admin_token(client: TestClient) -> None:
    response = client.post("/v1/models/reload", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --------------------------------------------------------------------------- #
# Content type handling on the wire
# --------------------------------------------------------------------------- #
def test_png_upload_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.png", encode(noise_image(), "PNG"), "image/png")},
        data={"type": "disease"},
    )
    assert response.status_code == 200


def test_empty_filename_yields_clean_validation_error(client: TestClient) -> None:
    """A malformed multipart body must not surface as a 500."""
    payload = io.BytesIO(encode(noise_image()))
    response = client.post(
        "/v1/predict",
        files={"image": ("", payload, "image/jpeg")},
        data={"type": "disease"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_image_sent_as_plain_field_is_rejected_cleanly(client: TestClient) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": (None, "not-a-file")},
        data={"type": "disease"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


# --------------------------------------------------------------------------- #
# Failure isolation
# --------------------------------------------------------------------------- #
def test_unexpected_error_returns_envelope_not_a_traceback(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """An unhandled exception must still produce the design.md 10.1 envelope."""
    from app.main import create_app
    from tests.conftest import make_settings

    app = create_app(make_settings(tmp_path))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/boom")
    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "internal_error"
    assert "kaboom" not in response.text


def test_asgi_module_exposes_an_app() -> None:
    """The uvicorn entrypoint (``app.asgi:app``) must import and build."""
    from app.asgi import app
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    assert app.title == "Tanami Vision"
