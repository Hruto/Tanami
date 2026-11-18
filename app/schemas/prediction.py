"""Pydantic schemas: the wire contract of this service.

The shapes mirror design.md section 11.3 exactly, wrapped in the success
envelope from design.md 10.1 so the backend can forward a response untouched.

v2 returns a single ``DiseaseResult`` shape for every commodity.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain import CauseCategory, QualityStatus, ResultStatus, ScanType, Severity


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# --------------------------------------------------------------------------- #
# Predictions
# --------------------------------------------------------------------------- #
class DiseaseTop(ApiModel):
    disease_code: str
    label: str
    cause_category: CauseCategory
    confidence: float = Field(ge=0, le=1)


class DiseaseAlternative(ApiModel):
    disease_code: str
    label: str
    cause_category: CauseCategory
    confidence: float = Field(ge=0, le=1)


class DiseaseResult(ApiModel):
    top: DiseaseTop | None
    alternatives: list[DiseaseAlternative]
    is_healthy: bool | None
    severity: Severity | None


class QualityInfo(ApiModel):
    blur: QualityStatus
    brightness: QualityStatus


class PredictionData(ApiModel):
    """Response body for ``POST /v1/predict``.

    ``result`` is always a ``DiseaseResult``; the commodity-specific label set
    is chosen by ``commodity_code`` (design.md 11.5).
    """

    model_config = ConfigDict(extra="forbid")

    type: ScanType
    status: ResultStatus
    model_version: str
    commodity_code: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    quality: QualityInfo
    result: DiseaseResult
    shadow_model_version: str | None = None
    shadow_status: ResultStatus | None = None
    inference_ms: float = Field(ge=0)


class PredictionResponse(ApiModel):
    data: PredictionData


# --------------------------------------------------------------------------- #
# Health and models
# --------------------------------------------------------------------------- #
class ModelInfo(ApiModel):
    scan_type: ScanType
    model_version: str
    commodity_code: str
    backend: Literal["stub", "onnx"]
    labels: list[str]
    input_size: int
    metrics: dict[str, float | str | int]
    is_shadow: bool


class HealthData(ApiModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: Literal["local", "staging", "production"]
    uptime_seconds: float
    models: list[ModelInfo]


class HealthResponse(ApiModel):
    data: HealthData


class ReadyData(ApiModel):
    ready: bool
    missing: list[str]


class ReadyResponse(ApiModel):
    data: ReadyData


# --------------------------------------------------------------------------- #
# Errors (design.md 10.1)
# --------------------------------------------------------------------------- #
class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, object] | None = None
    request_id: str


class ErrorResponse(ApiModel):
    error: ErrorBody
