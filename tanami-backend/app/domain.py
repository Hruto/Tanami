"""Domain vocabulary.

Every enum is copied verbatim from ``design.md`` section 8.2. The user-facing
labels live next to the enums because the API returns Indonesian strings and
they must never be duplicated in two places.
"""

from __future__ import annotations

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


class GrowthStage(StrEnum):
    SEEDLING = "seedling"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    HARVESTING = "harvesting"
    FINISHED = "finished"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    SICK = "sick"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"


class ReminderType(StrEnum):
    # Requirement 7: care reminders for tracked plants.
    WATERING = "watering"
    PHOTO = "photo"
    MONITORING = "monitoring"
    # Weather and scan rules (design 12.3).
    FUNGAL_RISK = "fungal_risk"
    HEAVY_RAIN_HARVEST = "heavy_rain_harvest"
    HARVEST_SOON = "harvest_soon"
    HEAT_STRESS = "heat_stress"
    SCAN_FOLLOWUP = "scan_followup"
    GENERAL = "general"


class ReminderPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class ReminderStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    DONE = "done"
    DISMISSED = "dismissed"


class FeedbackValue(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"


class UserRole(StrEnum):
    FARMER = "farmer"
    EXPERT = "expert"
    MODERATOR = "moderator"
    ADMIN = "admin"


class PostStatus(StrEnum):
    PUBLISHED = "published"
    HIDDEN = "hidden"
    REMOVED = "removed"


class ReportReason(StrEnum):
    SPAM = "spam"
    SCAM = "scam"
    ABUSE = "abuse"
    WRONG_INFO = "wrong_info"
    OTHER = "other"


class ReportTargetType(StrEnum):
    POST = "post"
    COMMENT = "comment"


class Platform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class Severity(StrEnum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class QualityStatus(StrEnum):
    OK = "ok"
    TOO_BLURRY = "too_blurry"
    TOO_DARK = "too_dark"
    TOO_BRIGHT = "too_bright"


class EstimateConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Placement(StrEnum):
    """Where a garden is (requirement 0)."""

    INDOOR = "indoor"
    OUTDOOR = "outdoor"


class IrrigationSchedule(StrEnum):
    """Watering frequency of a tracked plant (requirement 1)."""

    DAILY = "daily"
    EVERY_3_5_DAYS = "every_3_5_days"
    WEEKLY = "weekly"
    NEVER = "never"


# Days between waterings that trigger a reminder; ``never`` has none.
IRRIGATION_INTERVAL_DAYS: dict[str, int] = {
    IrrigationSchedule.DAILY.value: 1,
    IrrigationSchedule.EVERY_3_5_DAYS.value: 3,
    IrrigationSchedule.WEEKLY.value: 7,
}


class TrackingEndReason(StrEnum):
    """Why tracking of a plant ended (requirement 1, 2)."""

    HARVESTED = "harvested"
    DIED = "died"
    NOT_MAINTAINED = "not_maintained"
    OTHER = "other"


class HarvestOutcome(StrEnum):
    """Final result of a tracked plant (requirement 1, "Hasil Akhir")."""

    FAILED = "failed"  # gagal panen, < 20% of target
    SUBOPTIMAL = "suboptimal"  # kurang optimal, 20% - 70%
    NORMAL = "normal"  # panen normal / sesuai target, 70% - 100%
    BUMPER = "bumper"  # panen raya, > 100%


def outcome_for_percent(percent: float) -> HarvestOutcome:
    """Map a yield percentage of target onto the four requirement buckets."""
    if percent < 20:
        return HarvestOutcome.FAILED
    if percent < 70:
        return HarvestOutcome.SUBOPTIMAL
    if percent <= 100:
        return HarvestOutcome.NORMAL
    return HarvestOutcome.BUMPER


class CareAction(StrEnum):
    """Care actions logged on a tracked plant (requirement 2)."""

    WATERING = "watering"
    FERTILIZING = "fertilizing"
    PEST_CONTROL = "pest_control"
    PRUNING = "pruning"
    WEEDING = "weeding"
    OTHER = "other"


class PushState(StrEnum):
    """Delivery state of the push behind a reminder (design 12.4).

    ``pending`` is the only non-final state: quiet hours keep a reminder there
    until the hourly dispatcher can send it.
    """

    PENDING = "pending"
    SENT = "sent"
    NO_DEVICE = "no_device"
    DISABLED = "disabled"
    SKIPPED_CAP = "skipped_cap"
    FAILED = "failed"
    EXPIRED = "expired"


# Plant types for the tracking dropdown (requirement 1). Tracking works for any
# of them; disease detection only for the commodities a model exists for.
PLANT_TYPES: dict[str, str] = {
    "chili": "Cabai",
    "tomato": "Tomat",
    "eggplant": "Terong",
    "shallot": "Bawang Merah",
    "cucumber": "Mentimun",
    "long_bean": "Kacang Panjang",
    "spinach": "Bayam",
    "water_spinach": "Kangkung",
    "mustard_greens": "Sawi",
    "lettuce": "Selada",
    "corn": "Jagung",
    "rice": "Padi",
    "strawberry": "Stroberi",
    "other": "Lainnya",
}
COMMODITY_LABELS: dict[str, str] = PLANT_TYPES
SUPPORTED_COMMODITIES: tuple[str, ...] = tuple(PLANT_TYPES)
# Commodities the vision service has a model for (design 11.5).
DETECTION_COMMODITIES: tuple[str, ...] = ("chili",)
# design 13: one forum category per commodity plus "Umum".
FORUM_GENERAL_CATEGORY = "general"
FORUM_CATEGORIES: tuple[str, ...] = (*SUPPORTED_COMMODITIES, FORUM_GENERAL_CATEGORY)

# Backend-owned copy of the labels used in scan results. The authoritative
# label list lives in the model manifest; this mapping only decorates stored
# results and the disease knowledge base.
DISEASE_LABELS: dict[str, str] = {
    "healthy": "Sehat",
    "anthracnose": "Antraknosa",
    "cercospora_leaf_spot": "Bercak Daun Cercospora",
    "bacterial_wilt": "Layu Bakteri",
    "leaf_curl_virus": "Keriting Daun (Virus)",
    "pest_damage": "Kerusakan Akibat Hama",
    "nutrient_deficiency": "Kekurangan Hara",
}

RIPENESS_LABELS: dict[str, str] = {
    RipenessStage.UNRIPE.value: "Mentah",
    RipenessStage.TURNING.value: "Mengkal",
    RipenessStage.RIPE.value: "Matang",
    RipenessStage.OVERRIPE.value: "Terlalu Matang",
}

CAUSE_LABELS: dict[CauseCategory, str] = {
    CauseCategory.HEALTHY: "Sehat",
    CauseCategory.FUNGUS: "Jamur",
    CauseCategory.BACTERIA: "Bakteri",
    CauseCategory.VIRUS: "Virus",
    CauseCategory.PEST: "Hama",
    CauseCategory.NUTRIENT_DEFICIENCY: "Kekurangan hara",
    CauseCategory.UNKNOWN: "Belum diketahui",
}
