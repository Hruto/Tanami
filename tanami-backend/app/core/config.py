"""Runtime configuration.

Every field is settable through ``TANAMI_<FIELD>``. Validation is deliberately
strict: a service that starts with a weak secret or a missing production
dependency fails at boot, not on the first user request (TQA 9).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "staging", "production"]
StorageBackend = Literal["s3", "memory"]


class Settings(BaseSettings):
    """Runtime configuration for the backend."""

    model_config = SettingsConfigDict(
        env_prefix="TANAMI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    app_env: Environment = "local"
    service_name: str = "tanami-backend"
    timezone: str = "Asia/Jakarta"

    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/tanami"
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=100)
    db_echo: bool = False

    redis_url: str = "redis://127.0.0.1:6379/0"

    jwt_secret: str = "dev-only-secret-change-me-0123456789abcdef"  # noqa: S105
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "tanami-backend"
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    refresh_token_ttl_seconds: int = Field(default=2_592_000, ge=3_600, le=7_776_000)

    vision_base_url: str = "http://127.0.0.1:8001"
    vision_service_token: str = ""
    vision_timeout_seconds: float = Field(default=6.0, gt=2.0, le=30.0)
    vision_retries: int = Field(default=2, ge=0, le=5)

    max_scan_upload_bytes: int = Field(default=2_097_152, ge=1024, le=52_428_800)
    max_image_side: int = Field(default=1280, ge=224, le=8192)
    max_image_pixels: int = Field(default=40_000_000, ge=10_000)

    storage_backend: StorageBackend = "memory"
    s3_endpoint_url: str = ""
    s3_bucket: str = "tanami"
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_public_base_url: str = ""
    s3_presign_ttl_seconds: int = Field(default=3600, ge=60, le=604_800)

    bmkg_base_url: str = "https://api.bmkg.go.id"
    weather_cache_ttl_seconds: int = Field(default=21_600, ge=600, le=86_400)
    weather_timeout_seconds: float = Field(default=5.0, gt=0, le=30.0)

    # BMKG allows 60 requests/minute/IP (design 12.1); stay safely below it.
    bmkg_min_interval_seconds: float = Field(default=1.1, ge=0, le=60)

    quiet_hours_start: int = Field(default=21, ge=0, le=23)
    quiet_hours_end: int = Field(default=5, ge=0, le=23)
    max_push_per_day: int = Field(default=3, ge=0, le=50)
    scan_followup_days: int = Field(default=5, ge=1, le=90)
    plant_status_stale_days: int = Field(default=14, ge=1, le=365)
    fungal_history_days: int = Field(default=30, ge=1, le=365)

    # design 10.3 [USULAN]
    login_rate_limit_per_minute: int = Field(default=5, ge=0, le=1000)
    # Looser than login: carrier-grade NAT puts many farmers behind one IP, and
    # a group leader may sign up several members from one phone.
    register_rate_limit_per_minute: int = Field(default=20, ge=0, le=1000)
    scan_rate_limit_per_minute: int = Field(default=20, ge=0, le=1000)
    global_rate_limit_per_minute: int = Field(default=120, ge=0, le=100_000)
    # Only true behind a reverse proxy that overwrites X-Forwarded-For; otherwise
    # the header is attacker-controlled and would bypass the login limit.
    trust_forwarded_for: bool = False

    # design 13 [USULAN]: unique reporters that hide content until reviewed.
    forum_reports_to_hide: int = Field(default=3, ge=1, le=100)
    # tqa 9: deleted accounts are purged (rows and photos) after this many days.
    account_purge_days: int = Field(default=30, ge=0, le=365)

    jobs_enabled: bool = False
    cors_origins: str = ""
    log_level: str = "INFO"
    log_json: bool = True
    seed_on_startup: bool = True

    # FCM HTTP v1. The legacy ``/fcm/send`` API was shut down by Google in 2024,
    # so a service account is the only working credential. Either a path to the
    # JSON key file or the JSON itself (handy for container secrets).
    fcm_credentials_file: str = ""
    fcm_credentials_json: str = ""

    # Bootstrap the first administrator (design 13: experts are verified by the
    # PM, moderators are appointed). Comma-separated emails/phones that are
    # promoted to ``admin`` when they register.
    bootstrap_admins: str = ""

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        if not value:
            msg = "TANAMI_DATABASE_URL wajib diisi"
            raise ValueError(msg)
        if "+asyncpg" not in value:
            msg = "TANAMI_DATABASE_URL harus memakai driver asyncpg (+asyncpg)"
            raise ValueError(msg)
        return value

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            msg = f"timezone tidak dikenal: {value}"
            raise ValueError(msg) from exc
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            msg = f"log_level tidak valid: {value}"
            raise ValueError(msg)
        return level

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def bootstrap_admin_set(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower() for item in self.bootstrap_admins.split(",") if item.strip()
        )

    @property
    def sync_database_url(self) -> str:
        """Alembic and tooling connect synchronously with psycopg."""
        return self.database_url.replace("+asyncpg", "+psycopg")

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app_env != "production":
            return self

        problems: list[str] = []
        if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("dev-only"):
            problems.append("TANAMI_JWT_SECRET minimal 32 karakter dan bukan nilai contoh")
        if not self.vision_service_token:
            problems.append("TANAMI_VISION_SERVICE_TOKEN wajib diisi")
        if self.storage_backend != "s3":
            problems.append("TANAMI_STORAGE_BACKEND harus s3 di produksi")
        if not self.seed_on_startup:
            problems.append("TANAMI_SEED_ON_STARTUP harus true agar basis penyakit terisi")
        if problems:
            msg = "konfigurasi produksi tidak aman: " + "; ".join(problems)
            raise ValueError(msg)
        return self

    def public_image_url(self, key: str) -> str:
        if self.s3_public_base_url:
            return f"{self.s3_public_base_url.rstrip('/')}/{key}"
        if self.s3_endpoint_url:
            return f"{self.s3_endpoint_url.rstrip('/')}/{self.s3_bucket}/{key}"
        return f"/media/{key}"
