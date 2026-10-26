from __future__ import annotations

import pytest
from app.core.errors import ServiceUnavailable
from app.domain import ResultStatus, ScanType
from app.services.predict import PredictCommand, PredictService
from tests.conftest import blurred_image, dark_image, encode, noise_image


def _command(payload: bytes, scan_type: str = "disease") -> PredictCommand:
    return PredictCommand(
        scan_type=ScanType(scan_type),
        image_bytes=payload,
        content_type="image/jpeg",
        commodity_code="chili",
    )


async def test_disease_prediction_shape(settings, registry) -> None:  # type: ignore[no-untyped-def]
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(noise_image())))

    assert data.type == "disease"
    assert data.model_version == "disease-chili-v0.1.0"
    assert data.commodity_code == "chili"
    assert data.status in set(ResultStatus)
    assert data.inference_ms >= 0
    assert data.quality.blur == "ok"

    result = data.result
    assert hasattr(result, "top")
    if data.status in {ResultStatus.CONFIDENT, ResultStatus.UNCERTAIN}:
        assert result.top is not None  # type: ignore[union-attr]
        assert result.top.confidence is not None  # type: ignore[union-attr]
    else:
        assert result.top is None  # type: ignore[union-attr]


async def test_ripeness_prediction_shape(settings, registry) -> None:  # type: ignore[no-untyped-def]
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(noise_image()), scan_type="ripeness"))
    assert data.type == "ripeness"
    assert data.model_version == "ripeness-chili-v0.1.0"
    result = data.result
    assert hasattr(result, "stage")
    if data.status is ResultStatus.CONFIDENT or data.status is ResultStatus.UNCERTAIN:
        assert result.stage is not None  # type: ignore[union-attr]
        assert result.estimated_days_min is not None  # type: ignore[union-attr]
        assert result.estimated_days_max is not None  # type: ignore[union-attr]


async def test_blurry_image_yields_invalid_image(settings, registry) -> None:  # type: ignore[no-untyped-def]
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(blurred_image())))
    assert data.status is ResultStatus.INVALID_IMAGE
    assert data.result.top is None  # type: ignore[union-attr]
    assert data.quality.blur == "too_blurry"


async def test_dark_image_yields_invalid_image(settings, registry) -> None:  # type: ignore[no-untyped-def]
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(dark_image())))
    assert data.status is ResultStatus.INVALID_IMAGE
    assert data.quality.brightness == "too_dark"


async def test_ripeness_invalid_image_nulls_stage(settings, registry) -> None:  # type: ignore[no-untyped-def]
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(blurred_image()), scan_type="ripeness"))
    assert data.status is ResultStatus.INVALID_IMAGE
    assert data.result.stage is None  # type: ignore[union-attr]
    assert data.result.estimated_days_min is None  # type: ignore[union-attr]


async def test_missing_model_raises_service_unavailable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.services.registry import ModelRegistry
    from tests.conftest import make_settings

    settings = make_settings(tmp_path)
    registry = ModelRegistry(settings)
    registry.load()
    service = PredictService(settings, registry)
    with pytest.raises(ServiceUnavailable):
        await service.predict(_command(encode(noise_image())))


async def test_model_load_error_during_inference_raises_service_unavailable(
    settings, registry, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """A broken artifact must surface as 503 with a model_error metric."""
    from app.core.errors import ModelLoadError

    model = registry.primary(ScanType.DISEASE)

    def boom(_image):  # type: ignore[no-untyped-def]
        raise ModelLoadError("ONNX session mati")

    monkeypatch.setattr(model.predictor, "predict", boom)
    service = PredictService(settings, registry)

    with pytest.raises(ServiceUnavailable) as excinfo:
        await service.predict(_command(encode(noise_image())))
    assert excinfo.value.status_code == 503
    assert excinfo.value.details is None


async def test_shadow_failure_does_not_break_the_primary_result(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import Settings
    from app.core.errors import ModelLoadError
    from app.services.registry import ModelRegistry
    from tests.conftest import (
        DISEASE_LABELS,
        MODEL_VERSIONS,
        RIPENESS_LABELS,
        make_settings,
        write_manifest,
    )

    base = make_settings(tmp_path)
    for scan_type, version, labels in (
        ("disease", MODEL_VERSIONS["disease"], DISEASE_LABELS),
        ("ripeness", MODEL_VERSIONS["ripeness"], RIPENESS_LABELS),
        ("disease", "disease-chili-v0.2.0-rc1", DISEASE_LABELS),
    ):
        write_manifest(base.model_dir, scan_type=scan_type, version=version, labels=labels)

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="local",
        model_backend="stub",
        model_dir=tmp_path / "models",
        shadow_disease_model_version="disease-chili-v0.2.0-rc1",
        inference_timeout_seconds=30.0,
    )
    registry = ModelRegistry(settings)
    registry.load()
    shadow = registry.shadow(ScanType.DISEASE)
    assert shadow is not None

    def boom(_image):  # type: ignore[no-untyped-def]
        raise ModelLoadError("shadow crash")

    from unittest.mock import patch

    with patch.object(shadow.predictor, "predict", boom):
        service = PredictService(settings, registry)
        data = await service.predict(_command(encode(noise_image())))

    assert data.shadow_model_version is None
    assert data.shadow_status is None
    assert data.model_version == MODEL_VERSIONS["disease"]


async def test_shadow_is_reported_when_configured(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import Settings
    from app.services.registry import ModelRegistry
    from tests.conftest import (
        DISEASE_LABELS,
        MODEL_VERSIONS,
        RIPENESS_LABELS,
        make_settings,
        write_manifest,
    )

    base = make_settings(tmp_path)
    for scan_type, version, labels in (
        ("disease", MODEL_VERSIONS["disease"], DISEASE_LABELS),
        ("ripeness", MODEL_VERSIONS["ripeness"], RIPENESS_LABELS),
        ("disease", "disease-chili-v0.2.0-rc1", DISEASE_LABELS),
    ):
        write_manifest(base.model_dir, scan_type=scan_type, version=version, labels=labels)

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="local",
        model_backend="stub",
        model_dir=tmp_path / "models",
        shadow_disease_model_version="disease-chili-v0.2.0-rc1",
    )
    registry = ModelRegistry(settings)
    registry.load()
    service = PredictService(settings, registry)
    data = await service.predict(_command(encode(noise_image())))
    assert data.shadow_model_version == "disease-chili-v0.2.0-rc1"
    assert data.shadow_status is not None
    # The primary result must never be replaced by the shadow one.
    assert data.model_version == MODEL_VERSIONS["disease"]
