"""Model registry: loads artifacts once at startup and serves them by commodity.

Loading is eager and fail-fast. A service that starts without a working model
would answer 500 on the first request instead of being caught by the health
check at deploy time (TQA 8.4, rollback within 30 minutes).

Every commodity has its own primary (and optional shadow) model. ``is_ready``
is true only when all supported commodities have a primary loaded.
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
    def commodity_code(self) -> str:
        return self.manifest.commodity_code

    @property
    def version(self) -> str:
        return self.manifest.model_version


class ModelRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._primary: dict[str, LoadedModel] = {}
        self._shadow: dict[str, LoadedModel] = {}
        self._load_errors: list[str] = []

    @property
    def load_errors(self) -> list[str]:
        return list(self._load_errors)

    @property
    def is_ready(self) -> bool:
        return all(code in self._primary for code in self._settings.supported_commodities)

    def load(self) -> None:
        self._primary.clear()
        self._shadow.clear()
        self._load_errors.clear()

        for code in self._settings.supported_commodities:
            version = self._settings.model_version_for(code)
            try:
                self._primary[code] = self._load_one(code, version, is_shadow=False)
            except ModelLoadError as exc:
                MODELS_LOADED.labels(scan_type=ScanType.DISEASE.value, result="error").inc()
                self._load_errors.append(str(exc))
                logger.error("model_load_failed", commodity_code=code, error=str(exc))

        for code in self._settings.supported_commodities:
            shadow_version = self._settings.shadow_version_for(code)
            if not shadow_version:
                continue
            try:
                self._shadow[code] = self._load_one(code, shadow_version, is_shadow=True)
            except ModelLoadError as exc:
                # A shadow model must never take the service down.
                MODELS_LOADED.labels(scan_type=ScanType.DISEASE.value, result="shadow_error").inc()
                logger.warning("shadow_model_load_failed", commodity_code=code, error=str(exc))

    def _load_one(self, commodity_code: str, version: str, *, is_shadow: bool) -> LoadedModel:
        manifest = load_manifest(self._settings.model_dir, version, commodity_code)
        predictor = build_predictor(
            manifest,
            Path(self._settings.model_dir),
            backend=self._settings.model_backend,
            intra_op_threads=self._settings.onnx_intra_op_threads,
        )
        MODELS_LOADED.labels(scan_type=ScanType.DISEASE.value, result="ok").inc()
        logger.info(
            "model_loaded",
            commodity_code=commodity_code,
            scan_type=ScanType.DISEASE.value,
            model_version=manifest.model_version,
            backend=self._settings.model_backend,
            is_shadow=is_shadow,
        )
        return LoadedModel(manifest=manifest, predictor=predictor, is_shadow=is_shadow)

    def primary(self, commodity_code: str) -> LoadedModel:
        model = self._primary.get(commodity_code)
        if model is None:
            raise ServiceUnavailable(
                "Model belum tersedia. Coba lagi nanti.",
                details={"commodity_code": commodity_code},
            )
        return model

    def shadow(self, commodity_code: str) -> LoadedModel | None:
        return self._shadow.get(commodity_code)

    def all_models(self) -> list[LoadedModel]:
        return [*self._primary.values(), *self._shadow.values()]
