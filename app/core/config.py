from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "staging", "production"]
ModelBackend = Literal["stub", "onnx"]


class Settings(BaseSettings):
    """Runtime configuration. Every field is settable via ``VISION_<FIELD>``."""

    model_config = SettingsConfigDict(
        env_prefix="VISION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    app_env: Environment = "local"
    service_name: str = "tanami-vision"

    model_backend: ModelBackend = "stub"
    model_dir: Path = Path("models")
    commodity_code: str = "chili"
    supported_commodities: tuple[str, ...] = ("chili",)

    disease_model_version: str = "disease-chili-v0.1.0"
    ripeness_model_version: str = "ripeness-chili-v0.1.0"
    shadow_disease_model_version: str = ""
    shadow_ripeness_model_version: str = ""

    max_upload_bytes: int = Field(default=8 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    max_image_side: int = Field(default=4096, gt=0)
    min_image_side: int = Field(default=224, gt=0)

    # Result status thresholds (design.md 11.2). Kept in configuration so they
    # can be tuned without a code change, but validated to stay ordered.
    confident_threshold: float = Field(default=0.75, gt=0, le=1)
    uncertain_threshold: float = Field(default=0.50, gt=0, le=1)

    # Quality gate thresholds. [USULAN] Calibrate against the field dataset.
    blur_min_variance: float = Field(default=45.0, ge=0)
    brightness_min: float = Field(default=0.15, ge=0, le=1)
    brightness_max: float = Field(default=0.92, ge=0, le=1)

    top_k: int = Field(default=3, ge=1, le=10)
    max_concurrent_inference: int = Field(default=4, ge=1)
    inference_timeout_seconds: float = Field(default=2.0, gt=0)
    onnx_intra_op_threads: int = Field(default=2, ge=1)

    admin_token: str = ""
    service_token: str = ""

    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("admin_token", "service_token")
    @classmethod
    def _strip_token(cls, value: str) -> str:
        return value.strip()

    @field_validator("supported_commodities")
    @classmethod
    def _require_commodities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            msg = "supported_commodities tidak boleh kosong."
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_consistency(self) -> Settings:
        if self.uncertain_threshold >= self.confident_threshold:
            msg = (
                "VISION_UNCERTAIN_THRESHOLD harus lebih kecil dari "
                "VISION_CONFIDENT_THRESHOLD (design.md 11.2)."
            )
            raise ValueError(msg)
        if self.brightness_min >= self.brightness_max:
            msg = "VISION_BRIGHTNESS_MIN harus lebih kecil dari VISION_BRIGHTNESS_MAX."
            raise ValueError(msg)
        if self.commodity_code not in self.supported_commodities:
            msg = (
                f"commodity_code '{self.commodity_code}' tidak ada di supported_commodities "
                f"{list(self.supported_commodities)}."
            )
            raise ValueError(msg)
        if self.is_production and self.model_backend == "stub":
            msg = (
                "VISION_MODEL_BACKEND=stub tidak diizinkan di production: "
                "stub bukan model terlatih."
            )
            raise ValueError(msg)
        if self.is_production and not self.admin_token:
            msg = "VISION_ADMIN_TOKEN wajib diisi di production."
            raise ValueError(msg)
        if self.is_production and not self.service_token:
            msg = "VISION_SERVICE_TOKEN wajib diisi di production."
            raise ValueError(msg)
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        return not self.is_production

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_token)
