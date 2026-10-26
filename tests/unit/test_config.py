from __future__ import annotations

import pytest
from app.core.config import Settings


def test_defaults_match_contract_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.supported_commodities == ("chili",)
    assert settings.confident_threshold == 0.75
    assert settings.uncertain_threshold == 0.50
    assert settings.disease_model_version == "disease-chili-v0.1.0"
    assert settings.ripeness_model_version == "ripeness-chili-v0.1.0"


def test_env_prefix_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISION_COMMODITY_CODE", "chili")
    monkeypatch.setenv("VISION_TOP_K", "5")
    monkeypatch.setenv("VISION_SUPPORTED_COMMODITIES", '["chili","tomato"]')
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.top_k == 5
    assert settings.supported_commodities == ("chili", "tomato")


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="UNCERTAIN_THRESHOLD"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            confident_threshold=0.5,
            uncertain_threshold=0.6,
        )


def test_thresholds_may_not_be_equal() -> None:
    with pytest.raises(ValueError, match="UNCERTAIN_THRESHOLD"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            confident_threshold=0.7,
            uncertain_threshold=0.7,
        )


def test_brightness_bounds_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="BRIGHTNESS_MIN"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            brightness_min=0.9,
            brightness_max=0.2,
        )


def test_commodity_must_be_supported() -> None:
    with pytest.raises(ValueError, match="tidak ada di supported_commodities"):
        Settings(_env_file=None, commodity_code="tomato")  # type: ignore[call-arg]


def test_stub_backend_refused_in_production() -> None:
    with pytest.raises(ValueError, match="stub"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            app_env="production",
            model_backend="stub",
            admin_token="admin",
            service_token="svc",
        )


def test_production_requires_tokens() -> None:
    with pytest.raises(ValueError, match="ADMIN_TOKEN"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            app_env="production",
            model_backend="onnx",
        )


def test_production_requires_service_token() -> None:
    with pytest.raises(ValueError, match="SERVICE_TOKEN"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            app_env="production",
            model_backend="onnx",
            admin_token="admin",
        )


def test_tokens_are_stripped() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, service_token="  abc  ", admin_token=" x "
    )
    assert settings.service_token == "abc"
    assert settings.admin_token == "x"
    assert settings.admin_enabled is True


def test_docs_disabled_in_production() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="production",
        model_backend="onnx",
        admin_token="a",
        service_token="s",
    )
    assert settings.docs_enabled is False
