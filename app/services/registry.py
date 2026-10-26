"""Model registry: loads artifacts once at startup and serves them by scan type.

Loading is eager and fail-fast. A service that starts without a working model
would answer 500 on the first request instead of being caught by the health
check at deploy time (TQA 8.4, rollback within 30 minutes).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.errors import ModelLoadError, ServiceUnavailable
from app.core.logging import get_logger
from app.core.metrics import MODELS_LOADED
from app.domain import ScanType
from app.inference.manifest import ModelManifest, load_manifest
from app.inference.predictor import Predictor, build_predictor

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LoadedModel:
    manifest: ModelManifest
    predictor: Predictor
    is_shadow: bool

    @property
    def scan_type(self) -> ScanType:
        return self.manifest.scan_type

    @property
    def version(self) -> str:
        return self.manifest.model_version


class ModelRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._primary: dict[ScanType, LoadedModel] = {}
        self._shadow: dict[ScanType, LoadedModel] = {}
        self._load_errors: list[str] = []

    @property
    def load_errors(self) -> list[str]:
        return list(self._load_errors)

    @property
    def is_ready(self) -> bool:
        return all(scan_type in self._primary for scan_type in ScanType)

    def load(self) -> None:
        self._primary.clear()
        self._shadow.clear()
        self._load_errors.clear()

        requested = {
            ScanType.DISEASE: self._settings.disease_model_version,
            ScanType.RIPENESS: self._settings.ripeness_model_version,
        }
        shadow_requested = {
            ScanType.DISEASE: self._settings.shadow_disease_model_version,
            ScanType.RIPENESS: self._settings.shadow_ripeness_model_version,
        }

        for scan_type, version in requested.items():
            try:
                self._primary[scan_type] = self._load_one(scan_type, version, is_shadow=False)
            except ModelLoadError as exc:
                MODELS_LOADED.labels(scan_type=scan_type.value, result="error").inc()
                self._load_errors.append(str(exc))
                logger.error("model_load_failed", scan_type=scan_type.value, error=str(exc))

        for scan_type, version in shadow_requested.items():
            if not version:
                continue
            try:
                self._shadow[scan_type] = self._load_one(scan_type, version, is_shadow=True)
            except ModelLoadError as exc:
                # A shadow model must never take the service down.
                MODELS_LOADED.labels(scan_type=scan_type.value, result="shadow_error").inc()
                logger.warning(
                    "shadow_model_load_failed", scan_type=scan_type.value, error=str(exc)
                )

    def _load_one(self, scan_type: ScanType, version: str, *, is_shadow: bool) -> LoadedModel:
        manifest = load_manifest(self._settings.model_dir, version, scan_type)
        predictor = build_predictor(
            manifest,
            Path(self._settings.model_dir),
            backend=self._settings.model_backend,
            intra_op_threads=self._settings.onnx_intra_op_threads,
        )
        MODELS_LOADED.labels(scan_type=scan_type.value, result="ok").inc()
        logger.info(
            "model_loaded",
            scan_type=scan_type.value,
            model_version=manifest.model_version,
            backend=self._settings.model_backend,
            is_shadow=is_shadow,
        )
        return LoadedModel(manifest=manifest, predictor=predictor, is_shadow=is_shadow)

    def primary(self, scan_type: ScanType) -> LoadedModel:
        model = self._primary.get(scan_type)
        if model is None:
            raise ServiceUnavailable(
                "Model belum tersedia. Coba lagi nanti.",
                details={"scan_type": scan_type.value},
            )
        return model

    def shadow(self, scan_type: ScanType) -> LoadedModel | None:
        return self._shadow.get(scan_type)

    def all_models(self) -> list[LoadedModel]:
        return [*self._primary.values(), *self._shadow.values()]
