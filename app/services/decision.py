"""Turning raw model probabilities into the contract in design.md 11.3.

Rules encoded here, all from design.md / tqa.md and deliberately kept in one
place so there is exactly one implementation of each:

* status thresholds (design.md 11.2),
* ``top`` is null for ``unknown`` / ``invalid_image`` (design.md 11.3),
* ripeness always returns a *range*, never a single number (design.md 11.3),
* no treatment advice is produced here (tqa.md 8.3) - the backend fills it
  from the reviewed ``diseases`` table.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.domain import (
    DISEASE_LABELS,
    RIPENESS_DAY_POLICY,
    RIPENESS_LABELS,
    RIPENESS_NOTE,
    CauseCategory,
    EstimateConfidence,
    ResultStatus,
    RipenessStage,
)
from app.inference.predictor import RawPrediction
from app.inference.preprocessing import QualityReport
from app.schemas.prediction import (
    DiseaseAlternative,
    DiseaseResult,
    DiseaseTop,
    RipenessResult,
)


@dataclass(frozen=True, slots=True)
class Thresholds:
    confident: float
    uncertain: float

    def __post_init__(self) -> None:
        if not 0.0 < self.uncertain < self.confident <= 1.0:
            msg = (
                "ambang keyakinan tidak valid: butuh 0 < uncertain < confident <= 1, "
                f"didapat uncertain={self.uncertain}, confident={self.confident}"
            )
            raise ValueError(msg)

    @classmethod
    def from_settings(cls, settings: Settings) -> Thresholds:
        return cls(confident=settings.confident_threshold, uncertain=settings.uncertain_threshold)


def decide_status(
    confidence: float, quality: QualityReport, thresholds: Thresholds
) -> ResultStatus:
    """Apply design.md 11.2. Image quality wins over confidence."""
    if not quality.is_usable:
        return ResultStatus.INVALID_IMAGE
    if confidence >= thresholds.confident:
        return ResultStatus.CONFIDENT
    if confidence >= thresholds.uncertain:
        return ResultStatus.UNCERTAIN
    return ResultStatus.UNKNOWN


def estimate_confidence(confidence: float) -> EstimateConfidence:
    if confidence >= 0.85:
        return EstimateConfidence.HIGH
    if confidence >= 0.60:
        return EstimateConfidence.MEDIUM
    return EstimateConfidence.LOW


def ranked(probabilities: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(probabilities.items(), key=lambda item: item[1], reverse=True)


def _alternatives(ordered: list[tuple[str, float]]) -> list[DiseaseAlternative]:
    return [
        DiseaseAlternative(
            disease_code=code,
            label=DISEASE_LABELS[code].label_id if code in DISEASE_LABELS else code,
            cause_category=(
                DISEASE_LABELS[code].cause_category
                if code in DISEASE_LABELS
                else CauseCategory.UNKNOWN
            ),
            confidence=round(score, 4),
        )
        for code, score in ordered
    ]


def build_disease_result(
    prediction: RawPrediction,
    *,
    status: ResultStatus,
    top_k: int,
) -> DiseaseResult:
    ordered = ranked(prediction.probabilities)
    if not ordered:
        msg = f"model {prediction.model_version} tidak mengembalikan skor apa pun"
        raise ValueError(msg)

    top_code, top_confidence = ordered[0]
    top_label = DISEASE_LABELS.get(top_code)
    if top_label is None:
        msg = f"model {prediction.model_version} mengembalikan label tak dikenal: {top_code}"
        raise ValueError(msg)

    if status is ResultStatus.INVALID_IMAGE:
        # The pixels were unusable, so every score is meaningless. Returning
        # candidates would invite the UI to show a diagnosis from a blurry
        # photo, which design.md 11.4 forbids.
        return DiseaseResult(top=None, alternatives=[], is_healthy=None, severity=None)

    if status is ResultStatus.UNKNOWN:
        # No single disease is named, but design.md 11.3 allows candidates so
        # the forum/expert flow has something to show. The highest-scoring
        # class therefore stays in `alternatives` instead of being dropped.
        return DiseaseResult(
            top=None,
            alternatives=_alternatives(ordered[:top_k]),
            is_healthy=None,
            severity=None,
        )

    return DiseaseResult(
        top=DiseaseTop(
            disease_code=top_label.code,
            label=top_label.label_id,
            cause_category=top_label.cause_category,
            confidence=round(top_confidence, 4),
        ),
        alternatives=_alternatives(ordered[1:top_k]),
        is_healthy=top_label.cause_category is CauseCategory.HEALTHY,
        # Severity is optional in the MVP and the first model does not predict
        # it; the backend may override this from the reviewed knowledge base.
        severity=None,
    )


def build_ripeness_result(
    prediction: RawPrediction,
    *,
    status: ResultStatus,
) -> RipenessResult:
    ordered = ranked(prediction.probabilities)
    if not ordered:
        msg = f"model {prediction.model_version} tidak mengembalikan skor apa pun"
        raise ValueError(msg)

    if status in {ResultStatus.UNKNOWN, ResultStatus.INVALID_IMAGE}:
        return RipenessResult(
            stage=None,
            stage_label=None,
            confidence=None,
            estimated_days_min=None,
            estimated_days_max=None,
            estimate_confidence=None,
            note=RIPENESS_NOTE,
        )

    stage_value, confidence = ordered[0]
    try:
        stage = RipenessStage(stage_value)
    except ValueError as exc:
        msg = f"model {prediction.model_version} mengembalikan tahap tak dikenal: {stage_value}"
        raise ValueError(msg) from exc

    days_min, days_max = RIPENESS_DAY_POLICY[stage.value]
    return RipenessResult(
        stage=stage,
        stage_label=RIPENESS_LABELS[stage.value],
        confidence=round(confidence, 4),
        estimated_days_min=days_min,
        estimated_days_max=days_max,
        estimate_confidence=estimate_confidence(confidence),
        note=RIPENESS_NOTE,
    )
