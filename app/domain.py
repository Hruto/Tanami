"""Domain vocabulary shared by the inference layer and the HTTP layer.

Every value here is copied verbatim from design.md section 8.2 and 11.5. If the
public contract changes, this module changes first and `contracts/API.md` is
bumped in the same pull request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScanType(StrEnum):
    DISEASE = "disease"
    RIPENESS = "ripeness"


class ResultStatus(StrEnum):
    CONFIDENT = "confident"
    UNCERTAIN = "uncertain"
    UNKNOWN = "unknown"
    INVALID_IMAGE = "invalid_image"


class CauseCategory(StrEnum):
    HEALTHY = "healthy"
    FUNGUS = "fungus"
    BACTERIA = "bacteria"
    VIRUS = "virus"
    PEST = "pest"
    NUTRIENT_DEFICIENCY = "nutrient_deficiency"
    UNKNOWN = "unknown"


class RipenessStage(StrEnum):
    UNRIPE = "unripe"
    TURNING = "turning"
    RIPE = "ripe"
    OVERRIPE = "overripe"


class QualityStatus(StrEnum):
    OK = "ok"
    TOO_BLURRY = "too_blurry"
    TOO_DARK = "too_dark"
    TOO_BRIGHT = "too_bright"


class EstimateConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Severity(StrEnum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


@dataclass(frozen=True, slots=True)
class DiseaseLabel:
    code: str
    label_id: str
    cause_category: CauseCategory


DISEASE_LABELS: dict[str, DiseaseLabel] = {
    "healthy": DiseaseLabel("healthy", "Sehat", CauseCategory.HEALTHY),
    "anthracnose": DiseaseLabel("anthracnose", "Antraknosa", CauseCategory.FUNGUS),
    "cercospora_leaf_spot": DiseaseLabel(
        "cercospora_leaf_spot", "Bercak Daun Cercospora", CauseCategory.FUNGUS
    ),
    "bacterial_wilt": DiseaseLabel("bacterial_wilt", "Layu Bakteri", CauseCategory.BACTERIA),
    "leaf_curl_virus": DiseaseLabel(
        "leaf_curl_virus", "Keriting Daun (Virus)", CauseCategory.VIRUS
    ),
    "pest_damage": DiseaseLabel("pest_damage", "Kerusakan Akibat Hama", CauseCategory.PEST),
    "nutrient_deficiency": DiseaseLabel(
        "nutrient_deficiency", "Kekurangan Hara", CauseCategory.NUTRIENT_DEFICIENCY
    ),
}

RIPENESS_LABELS: dict[str, str] = {
    RipenessStage.UNRIPE.value: "Mentah",
    RipenessStage.TURNING.value: "Mengkal",
    RipenessStage.RIPE.value: "Matang",
    RipenessStage.OVERRIPE.value: "Terlalu Matang",
}

# Day ranges per ripeness stage. [USULAN] Values must be validated by an
# agronomist before the beta release (TQA 8.2). The service only returns a
# range; the backend turns it into absolute dates using the scan timestamp.
RIPENESS_DAY_POLICY: dict[str, tuple[int, int]] = {
    RipenessStage.UNRIPE.value: (12, 18),
    RipenessStage.TURNING.value: (4, 7),
    RipenessStage.RIPE.value: (0, 2),
    RipenessStage.OVERRIPE.value: (0, 0),
}

RIPENESS_NOTE = "Perkiraan kasar; dipengaruhi cuaca dan varietas."


def known_labels(scan_type: ScanType) -> tuple[str, ...]:
    if scan_type is ScanType.DISEASE:
        return tuple(DISEASE_LABELS)
    return tuple(RIPENESS_LABELS)
