from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.errors import ServiceUnavailable
from app.domain import ResultStatus, ScanType
from app.services.predict import PredictCommand, PredictService
from app.services.registry import ModelRegistry
from tests.conftest import (
    LABELS_BY_COMMODITY,
    MODEL_VERSIONS,
    SHADOW_VERSIONS,
    blurred_image,
    dark_image,
    encode,
    make_settings,
    noise_image,
    write_manifest,
)

COMMODITIES = tuple(MODEL_VERSIONS)


def _command(payload: bytes, commodity_code: str = "mango") -> PredictCommand:
    return PredictCommand(
        image_bytes=payload,
        content_type="image/jpeg",
        commodity_code=commodity_code,
    )


@pytest.mark.parametrize("commodity", COMMODITIES)
async def test_disease_prediction_shape(settings, registry, commodity: str) -> None:  # type: ignore[no-untyped-def]
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(noise_image()), commodity))

    assert data.type == ScanType.DISEASE
    assert data.model_version == MODEL_VERSIONS[commodity]
    assert data.commodity_code == commodity
    assert data.status in set(ResultStatus)
    assert data.inference_ms >= 0
    assert data.quality.blur == "ok"

    # The result shape is always DiseaseResult.
    result = data.result
    assert hasattr(result, "top")
    assert not hasattr(result, "stage")
    if data.status in {ResultStatus.CONFIDENT, ResultStatus.UNCERTAIN}:
        assert result.top is not None
        assert result.top.confidence is not None
    else:
        assert result.top is None


async def test_blurry_image_yields_invalid_image(settings, registry) -> None:  # type: ignore[no-untyped-def]
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(blurred_image())))
    assert data.status is ResultStatus.INVALID_IMAGE
    assert data.result.top is None
    assert data.quality.blur == "too_blurry"


async def test_dark_image_yields_invalid_image(settings, registry) -> None:  # type: ignore[no-untyped-def]
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(dark_image())))
    assert data.status is ResultStatus.INVALID_IMAGE
    assert data.quality.brightness == "too_dark"


async def test_missing_model_raises_service_unavailable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    registry = ModelRegistry(settings)
    registry.load()
    service = PredictService(settings, registry)
    with pytest.raises(ServiceUnavailable):
        await service.predict(_command(encode(noise_image())))


async def test_model_load_error_during_inference_raises_service_unavailable(  # type: ignore[no-untyped-def]
    settings, registry, monkeypatch
) -> None:
    """A broken artifact must surface as 503 with a model_error metric."""
    from app.core.errors import ModelLoadError

    model = registry.primary("mango")

    def boom(_image):  # type: ignore[no-untyped-def]
        raise ModelLoadError("ONNX session mati")

    monkeypatch.setattr(model.predictor, "predict", boom)
    service = PredictService(settings, registry)

    with pytest.raises(ServiceUnavailable) as excinfo:
        await service.predict(_command(encode(noise_image())))
    assert excinfo.value.status_code == 503
    assert excinfo.value.details is None


def _settings_with_shadow(tmp_path: Path) -> tuple[Settings, str]:
    shadow = SHADOW_VERSIONS["mango"]
    settings = make_settings(tmp_path, shadow_model_versions={"mango": shadow})
    for commodity, version in (*MODEL_VERSIONS.items(), ("mango", shadow)):
        write_manifest(
            settings.model_dir,
            commodity_code=commodity,
            version=version,
            labels=LABELS_BY_COMMODITY[commodity],
        )
    return settings, shadow


async def test_shadow_failure_does_not_break_the_primary_result(tmp_path: Path) -> None:
    """A broken shadow must never change the primary version or status."""
    from unittest.mock import patch

    from app.core.errors import ModelLoadError

    settings, _ = _settings_with_shadow(tmp_path)
    registry = ModelRegistry(settings)
    registry.load()
    shadow = registry.shadow("mango")
    assert shadow is not None

    def boom(_image):  # type: ignore[no-untyped-def]
        raise ModelLoadError("shadow crash")

    with patch.object(shadow.predictor, "predict", boom):
        service = PredictService(settings, registry)
        data = await service.predict(_command(encode(noise_image())))

    assert data.shadow_model_version is None
    assert data.shadow_status is None
    assert data.model_version == MODEL_VERSIONS["mango"]


async def test_shadow_is_reported_when_configured(tmp_path: Path) -> None:
    settings, shadow_version = _settings_with_shadow(tmp_path)
    registry = ModelRegistry(settings)
    registry.load()
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(noise_image())))
    assert data.shadow_model_version == shadow_version
    assert data.shadow_status is not None
    # The primary result must never be replaced by the shadow one.
    assert data.model_version == MODEL_VERSIONS["mango"]
