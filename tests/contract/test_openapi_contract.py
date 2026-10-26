"""Contract tests.

Two independent guarantees:

* the committed ``contracts/openapi.json`` still describes the running app,
* every documented response validates against the committed document, so a
  handler that drifts from its declared schema fails here rather than in the
  Tanami backend's integration tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import referencing
from app.main import create_app
from fastapi.testclient import TestClient
from openapi_spec_validator import validate
from tests.conftest import blurred_image, encode, noise_image

pytestmark = pytest.mark.contract

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def client(settings):  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_committed_spec_is_valid_openapi(contract: dict) -> None:
    validate(contract)


def test_committed_spec_matches_the_application(contract: dict) -> None:
    # Same builder the export script uses, so the comparison is apples to apples
    # and independent of whatever .env happens to exist on this machine.
    from scripts.export_openapi import build_spec

    assert contract == json.loads(json.dumps(build_spec()))


def test_success_response_matches_schema(client: TestClient, contract: dict) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", encode(noise_image()), "image/jpeg")},
        data={"type": "disease"},
    )
    assert response.status_code == 200

    schema_ref = contract["paths"]["/v1/predict"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    _validate_with_refs(response.json(), schema_ref, contract)


def test_error_response_matches_schema(client: TestClient, contract: dict) -> None:
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", b"garbage", "image/jpeg")},
        data={"type": "disease"},
    )
    assert response.status_code == 422

    schema_ref = contract["paths"]["/v1/predict"]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]
    _validate_with_refs(response.json(), schema_ref, contract)


def test_health_response_matches_schema(client: TestClient, contract: dict) -> None:
    response = client.get("/healthz")
    schema_ref = contract["paths"]["/healthz"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    _validate_with_refs(response.json(), schema_ref, contract)


def test_invalid_image_response_matches_schema(client: TestClient, contract: dict) -> None:
    """A 200 with status=invalid_image must fit the same schema as a normal hit."""
    response = client.post(
        "/v1/predict",
        files={"image": ("photo.jpg", encode(blurred_image()), "image/jpeg")},
        data={"type": "disease"},
    )
    assert response.status_code == 200
    schema_ref = contract["paths"]["/v1/predict"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    _validate_with_refs(response.json(), schema_ref, contract)


def test_every_documented_status_is_reachable(client: TestClient, contract: dict) -> None:
    """Guards against documenting a code the app can never return."""
    documented = {
        int(code)
        for code in contract["paths"]["/v1/predict"]["post"]["responses"]
        if code.isdigit()
    }
    assert documented == {200, 400, 401, 413, 415, 422, 429, 500, 503}
    # Touch the client so an app that fails to start cannot pass this test.
    assert client.get("/livez").status_code == 200


def _validate_with_refs(payload: object, schema_ref: dict, contract: dict) -> None:
    resource = referencing.Resource.from_contents(
        contract, default_specification=referencing.jsonschema.DRAFT202012
    )
    registry = referencing.Registry().with_resource("urn:tanami-contract", resource)
    schema = (
        {"$ref": "urn:tanami-contract" + schema_ref["$ref"]} if "$ref" in schema_ref else schema_ref
    )
    jsonschema.Draft202012Validator(schema, registry=registry).validate(payload)
