"""Plant health state machine (design 8.2)."""

from __future__ import annotations

from typing import Any

import pytest
from app.services.scan import next_health_status, replay_health_status


def disease(
    cause: str, status: str = "confident", severity: str | None = "moderate"
) -> tuple[str, dict[str, Any]]:
    top = None if status in {"unknown", "invalid_image"} else {"cause_category": cause}
    return status, {"top": top, "severity": severity}


HEALTHY = disease("healthy", severity=None)
FUNGUS = disease("fungus")


@pytest.mark.parametrize(
    ("previous", "status", "cause", "severity", "expected"),
    [
        ("unknown", "confident", "fungus", "moderate", "sick"),
        ("healthy", "confident", "virus", None, "sick"),
        ("healthy", "confident", "fungus", "mild", "at_risk"),
        ("healthy", "uncertain", "fungus", None, "at_risk"),
        ("unknown", "confident", "healthy", None, "healthy"),
        ("sick", "confident", "healthy", None, "recovering"),
        ("recovering", "confident", "healthy", None, "healthy"),
        ("at_risk", "confident", "healthy", None, "healthy"),
        ("sick", "unknown", None, None, "sick"),
        ("healthy", "invalid_image", None, None, "healthy"),
        ("recovering", "confident", "unknown", None, "recovering"),
    ],
)
def test_next_health_status(
    previous: str, status: str, cause: str | None, severity: str | None, expected: str
) -> None:
    assert next_health_status(previous, status=status, cause=cause, severity=severity) == expected


def test_no_scans_is_unknown() -> None:
    assert replay_health_status([]) == "unknown"


def test_recovery_needs_two_consecutive_healthy_scans() -> None:
    assert replay_health_status([FUNGUS, HEALTHY]) == "recovering"
    assert replay_health_status([FUNGUS, HEALTHY, HEALTHY]) == "healthy"


def test_relapse_during_recovery_is_sick_again() -> None:
    assert replay_health_status([FUNGUS, HEALTHY, FUNGUS]) == "sick"


def test_unusable_photo_does_not_reset_recovery() -> None:
    assert replay_health_status([FUNGUS, HEALTHY, disease("", "unknown"), HEALTHY]) == "healthy"
