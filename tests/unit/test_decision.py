from __future__ import annotations

import pytest
from app.domain import CauseCategory, EstimateConfidence, QualityStatus, ResultStatus, RipenessStage
from app.inference.predictor import RawPrediction
from app.inference.preprocessing import QualityReport
from app.services.decision import (
    Thresholds,
    build_disease_result,
    build_ripeness_result,
    decide_status,
)

GOOD_QUALITY = QualityReport(blur=QualityStatus.OK, brightness=QualityStatus.OK)
BLURRY = QualityReport(blur=QualityStatus.TOO_BLURRY, brightness=QualityStatus.OK)
DARK = QualityReport(blur=QualityStatus.OK, brightness=QualityStatus.TOO_DARK)
THRESHOLDS = Thresholds(confident=0.75, uncertain=0.50)


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (1.0, ResultStatus.CONFIDENT),
        (0.75, ResultStatus.CONFIDENT),  # boundary is inclusive (design.md 11.2)
        (0.7499, ResultStatus.UNCERTAIN),
        (0.50, ResultStatus.UNCERTAIN),  # boundary is inclusive
        (0.4999, ResultStatus.UNKNOWN),
        (0.0, ResultStatus.UNKNOWN),
    ],
)
def test_status_thresholds(confidence: float, expected: ResultStatus) -> None:
    assert decide_status(confidence, GOOD_QUALITY, THRESHOLDS) is expected


@pytest.mark.parametrize("quality", [BLURRY, DARK])
def test_bad_quality_overrides_high_confidence(quality: QualityReport) -> None:
    assert decide_status(0.99, quality, THRESHOLDS) is ResultStatus.INVALID_IMAGE


def test_thresholds_reject_inverted_values() -> None:
    with pytest.raises(ValueError, match="ambang"):
        Thresholds(confident=0.4, uncertain=0.6)


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_thresholds_reject_degenerate_values(value: float) -> None:
    with pytest.raises(ValueError):
        Thresholds(confident=value, uncertain=value)


def _prediction(**scores: float) -> RawPrediction:
    return RawPrediction(
        model_version="disease-chili-v0.1.0", probabilities=scores, inference_ms=1.0
    )


def test_confident_disease_result_has_top_and_alternatives() -> None:
    prediction = _prediction(anthracnose=0.87, healthy=0.08, pest_damage=0.05)
    result = build_disease_result(prediction, status=ResultStatus.CONFIDENT, top_k=3)

    assert result.top is not None
    assert result.top.disease_code == "anthracnose"
    assert result.top.label == "Antraknosa"
    assert result.top.cause_category is CauseCategory.FUNGUS
    assert result.top.confidence == 0.87
    assert result.is_healthy is False
    assert [alt.disease_code for alt in result.alternatives] == ["healthy", "pest_damage"]


def test_top_k_limits_alternatives() -> None:
    prediction = _prediction(a=0.0, healthy=0.2, anthracnose=0.5, pest_damage=0.1)
    result = build_disease_result(prediction, status=ResultStatus.CONFIDENT, top_k=2)
    assert len(result.alternatives) == 1


def test_healthy_result_sets_healthy_flag() -> None:
    prediction = _prediction(healthy=0.95, anthracnose=0.05)
    result = build_disease_result(prediction, status=ResultStatus.CONFIDENT, top_k=3)
    assert result.is_healthy is True
    assert result.top is not None
    assert result.top.cause_category is CauseCategory.HEALTHY
    assert result.top.disease_code == "healthy"


def test_unknown_keeps_candidates_but_hides_top() -> None:
    """design.md 11.3: unknown may still list candidates, but names no disease."""
    prediction = _prediction(anthracnose=0.4, healthy=0.35, pest_damage=0.25)
    result = build_disease_result(prediction, status=ResultStatus.UNKNOWN, top_k=3)

    assert result.top is None
    assert result.is_healthy is None
    assert result.severity is None
    assert [alt.disease_code for alt in result.alternatives] == [
        "anthracnose",
        "healthy",
        "pest_damage",
    ]


def test_invalid_image_returns_no_candidates() -> None:
    """Unusable pixels make every score meaningless, so none are surfaced."""
    prediction = _prediction(anthracnose=0.4, healthy=0.35, pest_damage=0.25)
    result = build_disease_result(prediction, status=ResultStatus.INVALID_IMAGE, top_k=3)

    assert result.top is None
    assert result.is_healthy is None
    assert result.severity is None
    assert result.alternatives == []


def test_unknown_label_in_model_output_raises() -> None:
    prediction = _prediction(mystery_disease=0.9)
    with pytest.raises(ValueError, match="tak dikenal"):
        build_disease_result(prediction, status=ResultStatus.CONFIDENT, top_k=3)


def test_empty_prediction_raises() -> None:
    empty = RawPrediction(model_version="v", probabilities={}, inference_ms=0.0)
    with pytest.raises(ValueError, match="tidak mengembalikan"):
        build_disease_result(empty, status=ResultStatus.CONFIDENT, top_k=3)


def test_ripeness_always_returns_a_range() -> None:
    prediction = RawPrediction(
        model_version="ripeness-chili-v0.1.0",
        probabilities={"turning": 0.81, "ripe": 0.19},
        inference_ms=2.0,
    )
    result = build_ripeness_result(prediction, status=ResultStatus.CONFIDENT)
    assert result.stage is RipenessStage.TURNING
    assert result.stage_label == "Mengkal"
    assert result.estimated_days_min == 4
    assert result.estimated_days_max == 7
    assert result.estimated_days_min < result.estimated_days_max
    assert result.estimate_confidence is EstimateConfidence.MEDIUM


def test_overripe_is_zero_to_zero() -> None:
    prediction = RawPrediction(
        model_version="v", probabilities={"overripe": 0.9, "ripe": 0.1}, inference_ms=0.0
    )
    result = build_ripeness_result(prediction, status=ResultStatus.CONFIDENT)
    assert result.stage is RipenessStage.OVERRIPE
    assert (result.estimated_days_min, result.estimated_days_max) == (0, 0)


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.95, EstimateConfidence.HIGH),
        (0.85, EstimateConfidence.HIGH),
        (0.84, EstimateConfidence.MEDIUM),
        (0.60, EstimateConfidence.MEDIUM),
        (0.59, EstimateConfidence.LOW),
    ],
)
def test_estimate_confidence_bands(confidence: float, expected: EstimateConfidence) -> None:
    prediction = RawPrediction(
        model_version="v",
        probabilities={"turning": confidence, "ripe": 1 - confidence},
        inference_ms=0.0,
    )
    # confidence >= 0.5 keeps the stage populated; use confident status so the
    # stage is never suppressed by the status gate.
    result = build_ripeness_result(prediction, status=ResultStatus.CONFIDENT)
    assert result.estimate_confidence is expected


@pytest.mark.parametrize("status", [ResultStatus.UNKNOWN, ResultStatus.INVALID_IMAGE])
def test_ripeness_unknown_returns_nulls(status: ResultStatus) -> None:
    prediction = RawPrediction(
        model_version="v", probabilities={"turning": 0.3, "ripe": 0.7}, inference_ms=0.0
    )
    result = build_ripeness_result(prediction, status=status)
    assert result.stage is None
    assert result.stage_label is None
    assert result.confidence is None
    assert result.estimated_days_min is None
    assert result.estimated_days_max is None
    assert result.note


def test_ripeness_unknown_stage_raises() -> None:
    prediction = RawPrediction(model_version="v", probabilities={"rotten": 0.9}, inference_ms=0.0)
    with pytest.raises(ValueError, match="tak dikenal"):
        build_ripeness_result(prediction, status=ResultStatus.CONFIDENT)
