"""Domain vocabulary shared by the inference layer and the HTTP layer.

Every value here is copied verbatim from design.md sections 8.2 and 11.5. If the
public contract changes, this module changes first and `contracts/API.md` is
bumped in the same pull request.

v2 supports exactly three fruit commodities and one scan type (``disease``).
Label sets follow design.md 11.5.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScanType(StrEnum):
    DISEASE = "disease"


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


# Sumber: design.md 11.5. Kode penyakit unik global berprefiks komoditas;
# kelas sehat memakai kode bersama `healthy` pada setiap komoditas.
DISEASE_LABELS_BY_COMMODITY: dict[str, dict[str, DiseaseLabel]] = {
    "mango": {
        "healthy": DiseaseLabel("healthy", "Sehat", CauseCategory.HEALTHY),
        "mango_anthracnose": DiseaseLabel("mango_anthracnose", "Antraknosa", CauseCategory.FUNGUS),
        "mango_bacterial_canker": DiseaseLabel(
            "mango_bacterial_canker", "Kanker bakteri", CauseCategory.BACTERIA
        ),
        "mango_die_back": DiseaseLabel("mango_die_back", "Mati pucuk", CauseCategory.FUNGUS),
        "mango_powdery_mildew": DiseaseLabel(
            "mango_powdery_mildew", "Embun tepung", CauseCategory.FUNGUS
        ),
        "mango_sooty_mould": DiseaseLabel(
            "mango_sooty_mould", "Embun jelaga", CauseCategory.FUNGUS
        ),
        "mango_gall_midge": DiseaseLabel(
            "mango_gall_midge", "Puru daun (lalat puru)", CauseCategory.PEST
        ),
        "mango_cutting_weevil": DiseaseLabel(
            "mango_cutting_weevil", "Kumbang pemotong pucuk", CauseCategory.PEST
        ),
    },
    "citrus": {
        "healthy": DiseaseLabel("healthy", "Sehat", CauseCategory.HEALTHY),
        "citrus_canker": DiseaseLabel("citrus_canker", "Kanker jeruk", CauseCategory.BACTERIA),
        "citrus_greening": DiseaseLabel(
            "citrus_greening", "CVPD (Greening/HLB)", CauseCategory.BACTERIA
        ),
        "citrus_black_spot": DiseaseLabel(
            "citrus_black_spot", "Bercak hitam", CauseCategory.FUNGUS
        ),
        "citrus_melanose": DiseaseLabel("citrus_melanose", "Melanosa", CauseCategory.FUNGUS),
    },
    "strawberry": {
        "healthy": DiseaseLabel("healthy", "Sehat", CauseCategory.HEALTHY),
        "strawberry_leaf_scorch": DiseaseLabel(
            "strawberry_leaf_scorch", "Hangus daun", CauseCategory.FUNGUS
        ),
        "strawberry_leaf_spot": DiseaseLabel(
            "strawberry_leaf_spot", "Bercak daun", CauseCategory.FUNGUS
        ),
        "strawberry_angular_leaf_spot": DiseaseLabel(
            "strawberry_angular_leaf_spot", "Bercak daun bersudut", CauseCategory.BACTERIA
        ),
        "strawberry_powdery_mildew": DiseaseLabel(
            "strawberry_powdery_mildew", "Embun tepung", CauseCategory.FUNGUS
        ),
    },
}

# Union of every commodity's labels, kept for callers that only need to know
# whether a code is a valid disease label somewhere in the contract.
DISEASE_LABELS: dict[str, DiseaseLabel] = {
    code: label for labels in DISEASE_LABELS_BY_COMMODITY.values() for code, label in labels.items()
}


def known_labels(scan_type: ScanType, commodity_code: str) -> tuple[str, ...]:
    """Return the exact, ordered label codes for one commodity.

    Only ``ScanType.DISEASE`` exists in v2; the argument is kept so callers can
    be explicit about the scan they are validating.
    """
    if scan_type.value != ScanType.DISEASE.value:
        msg = f"jenis scan '{scan_type.value}' tidak didukung; hanya disease yang tersedia"
        raise ValueError(msg)
    labels = DISEASE_LABELS_BY_COMMODITY.get(commodity_code)
    if labels is None:
        msg = f"komoditas '{commodity_code}' tidak memiliki label penyakit yang dikenal"
        raise ValueError(msg)
    return tuple(labels)
