"""The published contract matches ``design.md`` section 10 and stays committed.

Every endpoint the design lists must exist with the documented method, and
``contracts/openapi.json`` must be regenerated whenever the API changes
(``python scripts/export_openapi.py``) so the frontend can generate its types
from it (TQA 5.3, 6.1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.main import create_app

from tests.conftest import make_settings

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]

# (method, path) straight from design.md section 10.
DESIGN_ENDPOINTS: list[tuple[str, str]] = [
    ("post", "/auth/register"),
    ("post", "/auth/login"),
    ("post", "/auth/refresh"),
    ("post", "/auth/logout"),
    ("get", "/users/me"),
    ("patch", "/users/me"),
    ("delete", "/users/me"),
    ("post", "/devices"),
    ("get", "/farms"),
    ("post", "/farms"),
    ("get", "/farms/{farm_id}"),
    ("patch", "/farms/{farm_id}"),
    ("delete", "/farms/{farm_id}"),
    ("get", "/farms/{farm_id}/plants"),
    ("post", "/farms/{farm_id}/plants"),
    ("get", "/plants/{plant_id}"),
    ("patch", "/plants/{plant_id}"),
    ("delete", "/plants/{plant_id}"),
    ("post", "/plants/{plant_id}/harvests"),
    ("get", "/regions/search"),
    ("get", "/regions/resolve"),
    ("post", "/scans"),
    ("get", "/scans"),
    ("get", "/scans/{scan_id}"),
    ("delete", "/scans/{scan_id}"),
    ("put", "/scans/{scan_id}/feedback"),
    ("patch", "/scans/{scan_id}"),
    ("get", "/plants/{plant_id}/timeline"),
    ("get", "/plants/{plant_id}/stats"),
    ("get", "/home"),
    ("get", "/farms/{farm_id}/weather"),
    ("get", "/reminders"),
    ("get", "/reminders/{reminder_id}"),
    ("patch", "/reminders/{reminder_id}"),
    ("get", "/users/me/notification-settings"),
    ("patch", "/users/me/notification-settings"),
    ("get", "/diseases"),
    ("get", "/diseases/{code}"),
    ("get", "/forum/categories"),
    ("get", "/forum/posts"),
    ("post", "/forum/posts"),
    ("get", "/forum/posts/{post_id}"),
    ("delete", "/forum/posts/{post_id}"),
    ("get", "/forum/posts/{post_id}/comments"),
    ("post", "/forum/posts/{post_id}/comments"),
    ("post", "/forum/reports"),
    ("post", "/uploads/forum-image"),
    # Requirements v1 (design.md 0.2)
    ("post", "/users/me/password"),
    ("get", "/devices"),
    ("get", "/plant-types"),
    ("get", "/plants"),
    ("post", "/plants/{plant_id}/end"),
    ("get", "/plants/{plant_id}/photos"),
    ("post", "/plants/{plant_id}/photos"),
    ("delete", "/plants/{plant_id}/photos/{photo_id}"),
    ("get", "/plants/{plant_id}/care-logs"),
    ("post", "/plants/{plant_id}/care-logs"),
    ("delete", "/plants/{plant_id}/care-logs/{log_id}"),
    ("get", "/detection-plants"),
    ("post", "/detection-plants"),
    ("get", "/detection-plants/{detection_id}"),
    ("patch", "/detection-plants/{detection_id}"),
    ("post", "/detection-plants/{detection_id}/end"),
    ("post", "/detection-plants/{detection_id}/reactivate"),
    ("put", "/forum/posts/{post_id}/like"),
    ("delete", "/forum/posts/{post_id}/like"),
    ("delete", "/forum/comments/{comment_id}"),
]


@pytest.fixture(scope="module")
def schema() -> dict[str, object]:
    settings = make_settings("postgresql+asyncpg://unused:unused@127.0.0.1:1/unused")
    return create_app(settings).openapi()


@pytest.mark.parametrize(("method", "path"), DESIGN_ENDPOINTS)
def test_design_endpoint_exists(schema: dict[str, object], method: str, path: str) -> None:
    paths = schema["paths"]
    assert isinstance(paths, dict)
    assert method in paths.get(f"/api/v1{path}", {}), f"{method.upper()} {path} missing"


def test_every_api_route_answers_with_an_envelope(schema: dict[str, object]) -> None:
    paths = schema["paths"]
    assert isinstance(paths, dict)
    for path, operations in paths.items():
        if not path.startswith("/api/v1"):
            continue
        for method, operation in operations.items():
            ok = {
                code: spec for code, spec in operation["responses"].items() if code.startswith("2")
            }
            for code, spec in ok.items():
                if code == "204" or "content" not in spec:
                    continue
                ref = spec["content"]["application/json"]["schema"].get("$ref", "")
                assert "Envelope" in ref, f"{method.upper()} {path} returns {ref or 'raw JSON'}"


def test_committed_contract_is_current(schema: dict[str, object]) -> None:
    committed = ROOT / "contracts" / "openapi.json"
    assert committed.exists(), "run: python scripts/export_openapi.py"
    assert json.loads(committed.read_text(encoding="utf-8")) == json.loads(
        json.dumps(schema, sort_keys=True)
    ), "contracts/openapi.json is stale; run: python scripts/export_openapi.py"
