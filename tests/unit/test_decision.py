from __future__ import annotations

import pytest
from app.domain import CauseCategory, QualityStatus, ResultStatus
from app.inference.predictor import RawPrediction
from app.inference.preprocessing import QualityReport
from app.services.decision import (
    Thresholds,
    build_disease_result,
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
        model_version="disease-mango-v0.1.0", probabilities=scores, inference_ms=1.0
    )


def test_confident_disease_result_has_top_and_alternatives() -> None:
    prediction = _prediction(mango_anthracnose=0.87, healthy=0.08, mango_gall_midge=0.05)
    result = build_disease_result(
        prediction, commodity_code="mango", status=ResultStatus.CONFIDENT, top_k=3
    )

    assert result.top is not None
    assert result.top.disease_code == "mango_anthracnose"
    assert result.top.label == "Antraknosa"
    assert result.top.cause_category is CauseCategory.FUNGUS
    assert result.top.confidence == 0.87
    assert result.is_healthy is False
    assert [alt.disease_code for alt in result.alternatives] == ["healthy", "mango_gall_midge"]


def test_top_k_limits_alternatives() -> None:
    prediction = _prediction(a=0.0, healthy=0.2, mango_anthracnose=0.5, mango_gall_midge=0.1)
    result = build_disease_result(
        prediction, commodity_code="mango", status=ResultStatus.CONFIDENT, top_k=2
    )
    assert len(result.alternatives) == 1


def test_healthy_result_sets_healthy_flag() -> None:
    prediction = _prediction(healthy=0.95, mango_anthracnose=0.05)
    result = build_disease_result(
        prediction, commodity_code="mango", status=ResultStatus.CONFIDENT, top_k=3
    )
    assert result.is_healthy is True
    assert result.top is not None
    assert result.top.cause_category is CauseCategory.HEALTHY
    assert result.top.disease_code == "healthy"


def test_unknown_keeps_candidates_but_hides_top() -> None:
    """design.md 11.3: unknown may still list candidates, but names no disease."""
    prediction = _prediction(mango_anthracnose=0.4, healthy=0.35, mango_gall_midge=0.25)
    result = build_disease_result(
        prediction, commodity_code="mango", status=ResultStatus.UNKNOWN, top_k=3
    )

    assert result.top is None
    assert result.is_healthy is None
    assert result.severity is None
    assert [alt.disease_code for alt in result.alternatives] == [
        "mango_anthracnose",
        "healthy",
        "mango_gall_midge",
    ]


def test_invalid_image_returns_no_candidates() -> None:
    """Unusable pixels make every score meaningless, so none are surfaced."""
    prediction = _prediction(mango_anthracnose=0.4, healthy=0.35, mango_gall_midge=0.25)
    result = build_disease_result(
        prediction, commodity_code="mango", status=ResultStatus.INVALID_IMAGE, top_k=3
    )

    assert result.top is None
    assert result.is_healthy is None
    assert result.severity is None
    assert result.alternatives == []


def test_unknown_label_in_model_output_raises() -> None:
    prediction = _prediction(mystery_disease=0.9)
    with pytest.raises(ValueError, match="tak dikenal"):
        build_disease_result(
            prediction, commodity_code="mango", status=ResultStatus.CONFIDENT, top_k=3
        )


def test_label_from_another_commodity_is_rejected() -> None:
    prediction = _prediction(mango_anthracnose=0.9, healthy=0.1)
    with pytest.raises(ValueError, match="tak dikenal"):
        build_disease_result(
            prediction, commodity_code="citrus", status=ResultStatus.CONFIDENT, top_k=3
        )


@pytest.mark.parametrize(
    ("commodity", "code", "label", "category"),
    [
        ("citrus", "citrus_canker", "Kanker jeruk", CauseCategory.BACTERIA),
        ("citrus", "citrus_greening", "CVPD (Greening/HLB)", CauseCategory.BACTERIA),
        (
            "tomato",
            "tomato_bacterial_spot",
            "Bercak bakteri",
            CauseCategory.BACTERIA,
        ),
        ("tomato", "tomato_early_blight", "Bercak daun awal", CauseCategory.FUNGUS),
        ("mango", "mango_gall_midge", "Puru daun (lalat puru)", CauseCategory.PEST),
    ],
)
def test_labels_and_categories_follow_design_11_5(
    commodity: str, code: str, label: str, category: CauseCategory
) -> None:
    prediction = RawPrediction(model_version="v", probabilities={code: 0.9}, inference_ms=0.0)
    result = build_disease_result(
        prediction, commodity_code=commodity, status=ResultStatus.CONFIDENT, top_k=3
    )
    assert result.top is not None
    assert result.top.disease_code == code
    assert result.top.label == label
    assert result.top.cause_category is category


def test_empty_prediction_raises() -> None:
    empty = RawPrediction(model_version="v", probabilities={}, inference_ms=0.0)
    with pytest.raises(ValueError, match="tidak mengembalikan"):
        build_disease_result(empty, commodity_code="mango", status=ResultStatus.CONFIDENT, top_k=3)
