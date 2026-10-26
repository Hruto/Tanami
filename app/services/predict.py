"""The prediction orchestration.

This module owns the whole lifecycle of one inference request: lookup, decode,
blocking inference on a worker thread, thresholding, and metrics. Routes stay
thin so the logic is testable without HTTP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import anyio
from anyio import CapacityLimiter

from app.core.config import Settings
from app.core.errors import ModelLoadError, ServiceUnavailable
from app.core.logging import get_logger
from app.core.metrics import INFERENCE_ERRORS, PREDICTION_LATENCY, PREDICTIONS_TOTAL
from app.domain import ResultStatus, ScanType
from app.inference.predictor import RawPrediction
from app.inference.preprocessing import PreparedImage, decode_and_prepare
from app.schemas.prediction import (
    DiseaseResult,
    PredictionData,
    QualityInfo,
    RipenessResult,
)
from app.services.decision import (
    Thresholds,
    build_disease_result,
    build_ripeness_result,
    decide_status,
)
from app.services.registry import LoadedModel, ModelRegistry

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PredictCommand:
    scan_type: ScanType
    image_bytes: bytes
    content_type: str | None
    commodity_code: str
    client_uuid: str | None = None


class PredictService:
    def __init__(self, settings: Settings, registry: ModelRegistry) -> None:
        self._settings = settings
        self._registry = registry
        self._thresholds = Thresholds.from_settings(settings)
        self._limiter = CapacityLimiter(settings.max_concurrent_inference)

    def _run_blocking(
        self,
        model: LoadedModel,
        payload: bytes,
        content_type: str | None,
    ) -> tuple[PreparedImage, RawPrediction]:
        prepared = decode_and_prepare(
            payload,
            content_type=content_type,
            settings=self._settings,
            target_size=model.manifest.input_size,
        )
        return prepared, model.predictor.predict(prepared.array)

    async def predict(self, command: PredictCommand) -> PredictionData:
        started = time.perf_counter()
        model = self._registry.primary(command.scan_type)

        try:
            with anyio.fail_after(self._settings.inference_timeout_seconds):
                prepared, prediction = await anyio.to_thread.run_sync(
                    self._run_blocking,
                    model,
                    command.image_bytes,
                    command.content_type,
                    limiter=self._limiter,
                    abandon_on_cancel=True,
                )
        except TimeoutError as exc:
            INFERENCE_ERRORS.labels(reason="timeout").inc()
            raise ServiceUnavailable(
                "Model tidak merespons tepat waktu. Coba lagi.",
            ) from exc
        except ModelLoadError as exc:
            INFERENCE_ERRORS.labels(reason="model_error").inc()
            logger.error(
                "inference_failed",
                scan_type=command.scan_type.value,
                model_version=model.version,
                error=str(exc),
            )
            raise ServiceUnavailable("Model gagal memproses gambar.") from exc

        ordered = sorted(prediction.probabilities.items(), key=lambda item: item[1], reverse=True)
        top_confidence = ordered[0][1] if ordered else 0.0
        status = decide_status(top_confidence, prepared.quality, self._thresholds)

        result = self._build_result(command.scan_type, prediction, status)

        shadow_version, shadow_status = self._run_shadow(command, prepared)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        PREDICTION_LATENCY.labels(scan_type=command.scan_type.value).observe(duration_ms / 1000)
        PREDICTIONS_TOTAL.labels(scan_type=command.scan_type.value, status=status.value).inc()

        return PredictionData(
            type=command.scan_type,
            status=status,
            model_version=prediction.model_version,
            commodity_code=command.commodity_code,
            confidence=round(top_confidence, 4),
            quality=QualityInfo(blur=prepared.quality.blur, brightness=prepared.quality.brightness),
            result=result,
            shadow_model_version=shadow_version,
            shadow_status=shadow_status,
            # Model time only. Decode, resize and the quality gate are reported
            # by the request latency metrics instead, so this number keeps its
            # promise when it lands in `scans.result`.
            inference_ms=prediction.inference_ms,
        )

    def _build_result(
        self,
        scan_type: ScanType,
        prediction: RawPrediction,
        status: ResultStatus,
    ) -> DiseaseResult | RipenessResult:
        if scan_type is ScanType.DISEASE:
            return build_disease_result(prediction, status=status, top_k=self._settings.top_k)
        return build_ripeness_result(prediction, status=status)

    def _run_shadow(
        self, command: PredictCommand, prepared: PreparedImage
    ) -> tuple[str | None, ResultStatus | None]:
        """Score the shadow model in-line but never let it affect the response.

        Recording both statuses is what makes the staging comparison in
        TQA 8.4 possible. Failures are logged and swallowed.
        """
        shadow = self._registry.shadow(command.scan_type)
        if shadow is None:
            return None, None

        try:
            prediction = shadow.predictor.predict(prepared.array)
            top_confidence = max(prediction.probabilities.values(), default=0.0)
            status = decide_status(top_confidence, prepared.quality, self._thresholds)
        except Exception as exc:  # a shadow failure must never break the request
            logger.warning(
                "shadow_inference_failed",
                scan_type=command.scan_type.value,
                model_version=shadow.version,
                error=str(exc),
            )
            INFERENCE_ERRORS.labels(reason="shadow_error").inc()
            return None, None

        return shadow.version, status
