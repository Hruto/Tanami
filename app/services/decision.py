"""Turning raw model probabilities into the contract in design.md 11.3.

Rules encoded here, all from design.md / tqa.md and deliberately kept in one
place so there is exactly one implementation of each:

* status thresholds (design.md 11.2),
* ``top`` is null for ``unknown`` / ``invalid_image`` (design.md 11.3),
* labels and cause categories come from the per-commodity table in design.md 11.5,
* no treatment advice is produced here (tqa.md 8.3) - the backend fills it
  from the reviewed ``diseases`` table.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.domain import (
    DISEASE_LABELS_BY_COMMODITY,
    CauseCategory,
    DiseaseLabel,
    ResultStatus,
)
from app.inference.predictor import RawPrediction
from app.inference.preprocessing import QualityReport
from app.schemas.prediction import DiseaseAlternative, DiseaseResult, DiseaseTop


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


def ranked(probabilities: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(probabilities.items(), key=lambda item: item[1], reverse=True)


def _labels_for(commodity_code: str) -> dict[str, DiseaseLabel]:
    labels = DISEASE_LABELS_BY_COMMODITY.get(commodity_code)
    if labels is None:
        msg = f"komoditas '{commodity_code}' tidak memiliki label penyakit yang dikenal"
        raise ValueError(msg)
    return labels


def _alternatives(
    ordered: list[tuple[str, float]], labels: dict[str, DiseaseLabel]
) -> list[DiseaseAlternative]:
    result: list[DiseaseAlternative] = []
    for code, score in ordered:
        label = labels.get(code)
        result.append(
            DiseaseAlternative(
                disease_code=code,
                label=label.label_id if label is not None else code,
                cause_category=label.cause_category if label is not None else CauseCategory.UNKNOWN,
                confidence=round(score, 4),
            )
        )
    return result


def build_disease_result(
    prediction: RawPrediction,
    *,
    commodity_code: str,
    status: ResultStatus,
    top_k: int,
) -> DiseaseResult:
    """Build the always-disease result using ``commodity_code``'s label table."""
    labels = _labels_for(commodity_code)
    ordered = ranked(prediction.probabilities)
    if not ordered:
        msg = f"model {prediction.model_version} tidak mengembalikan skor apa pun"
        raise ValueError(msg)

    top_code, top_confidence = ordered[0]
    top_label = labels.get(top_code)
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
            alternatives=_alternatives(ordered[:top_k], labels),
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
        alternatives=_alternatives(ordered[1:top_k], labels),
        is_healthy=top_label.cause_category is CauseCategory.HEALTHY,
        # Severity is optional in the MVP and the first model does not predict
        # it; the backend may override this from the reviewed knowledge base.
        severity=None,
    )
