from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.errors import ModelLoadError, ServiceUnavailable
from app.domain import ScanType
from app.inference.manifest import load_manifest, resolve_artifact
from app.services.registry import ModelRegistry
from tests.conftest import (
    LABELS_BY_COMMODITY,
    MODEL_VERSIONS,
    SHADOW_VERSIONS,
    make_settings,
    write_manifest,
)

COMMODITIES = tuple(MODEL_VERSIONS)


@pytest.mark.parametrize("commodity", COMMODITIES)
def test_loads_a_valid_manifest(tmp_path: Path, commodity: str) -> None:
    version = MODEL_VERSIONS[commodity]
    write_manifest(
        tmp_path,
        commodity_code=commodity,
        version=version,
        labels=LABELS_BY_COMMODITY[commodity],
    )
    manifest = load_manifest(tmp_path, version, commodity)
    assert manifest.scan_type is ScanType.DISEASE
    assert manifest.commodity_code == commodity
    assert manifest.input_size == 224
    assert set(manifest.labels) == set(LABELS_BY_COMMODITY[commodity])


def test_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelLoadError, match="tidak ditemukan"):
        load_manifest(tmp_path, "nope", "mango")


def test_corrupt_manifest_raises(tmp_path: Path) -> None:
    target = tmp_path / "broken"
    target.mkdir()
    (target / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ModelLoadError, match="tidak dapat dibaca"):
        load_manifest(tmp_path, "broken", "mango")


def test_manifest_with_unknown_scan_type_raises(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        commodity_code="mango",
        version="v1",
        labels=LABELS_BY_COMMODITY["mango"],
        scan_type="invalid",
    )
    with pytest.raises(ModelLoadError, match="tidak dikenal"):
        load_manifest(tmp_path, "v1", "mango")


def test_manifest_commodity_mismatch_raises(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        commodity_code="mango",
        version="v1",
        labels=LABELS_BY_COMMODITY["mango"],
    )
    with pytest.raises(ModelLoadError, match="tetapi diminta sebagai 'citrus'"):
        load_manifest(tmp_path, "v1", "citrus")


def test_manifest_with_wrong_labels_raises(tmp_path: Path) -> None:
    write_manifest(tmp_path, commodity_code="mango", version="v1", labels=["mango_anthracnose"])
    with pytest.raises(ModelLoadError, match="tidak sesuai kontrak"):
        load_manifest(tmp_path, "v1", "mango")


def test_manifest_with_another_commodity_labels_raises(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        commodity_code="citrus",
        version="v1",
        labels=LABELS_BY_COMMODITY["citrus"],
    )
    with pytest.raises(ModelLoadError, match="tetapi diminta sebagai"):
        load_manifest(tmp_path, "v1", "mango")


def test_manifest_with_missing_required_field_raises(tmp_path: Path) -> None:
    target = tmp_path / "v1"
    target.mkdir()
    payload = {
        "model_version": "v1",
        "scan_type": "disease",
        "commodity_code": "mango",
        "artifact": "model.onnx",
        "labels": LABELS_BY_COMMODITY["mango"],
        "input_name": "input",
        "output_name": "logits",
    }
    (target / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="input_size"):
        load_manifest(tmp_path, "v1", "mango")


def test_manifest_artifact_may_not_escape_the_version_dir(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        commodity_code="mango",
        version="v1",
        labels=LABELS_BY_COMMODITY["mango"],
    )
    path = tmp_path / "v1" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifact"] = "../../etc/passwd"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="relatif"):
        load_manifest(tmp_path, "v1", "mango")


def test_absolute_artifact_path_raises(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        commodity_code="mango",
        version="v1",
        labels=LABELS_BY_COMMODITY["mango"],
    )
    path = tmp_path / "v1" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifact"] = "C:\\models\\model.onnx"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="relatif"):
        load_manifest(tmp_path, "v1", "mango")


def test_unknown_normalization_raises(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        commodity_code="mango",
        version="v1",
        labels=LABELS_BY_COMMODITY["mango"],
    )
    path = tmp_path / "v1" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["normalization"] = "weird"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="normalization"):
        load_manifest(tmp_path, "v1", "mango")


def test_unknown_activation_raises(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        commodity_code="mango",
        version="v1",
        labels=LABELS_BY_COMMODITY["mango"],
    )
    path = tmp_path / "v1" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["output_activation"] = "sigmoid"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="output_activation"):
        load_manifest(tmp_path, "v1", "mango")


def test_resolve_artifact_reports_missing_file(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        commodity_code="mango",
        version="v1",
        labels=LABELS_BY_COMMODITY["mango"],
    )
    manifest = load_manifest(tmp_path, "v1", "mango")
    with pytest.raises(ModelLoadError, match="artefak"):
        resolve_artifact(manifest, tmp_path)


def test_registry_loads_all_three_primary_models(settings) -> None:  # type: ignore[no-untyped-def]
    registry = ModelRegistry(settings)
    registry.load()
    assert registry.is_ready is True
    for commodity, version in MODEL_VERSIONS.items():
        assert registry.primary(commodity).version == version
        assert registry.primary(commodity).commodity_code == commodity
    assert registry.load_errors == []


def test_registry_is_not_ready_when_one_model_is_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    for commodity in ("mango", "citrus"):
        write_manifest(
            settings.model_dir,
            commodity_code=commodity,
            version=MODEL_VERSIONS[commodity],
            labels=LABELS_BY_COMMODITY[commodity],
        )
    registry = ModelRegistry(settings)
    registry.load()
    assert registry.is_ready is False
    assert len(registry.load_errors) == 1


def test_registry_shadow_failure_is_not_fatal(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, shadow_model_versions={"mango": "does-not-exist"})
    for commodity, version in MODEL_VERSIONS.items():
        write_manifest(
            settings.model_dir,
            commodity_code=commodity,
            version=version,
            labels=LABELS_BY_COMMODITY[commodity],
        )
    registry = ModelRegistry(settings)
    registry.load()
    assert registry.is_ready is True
    assert registry.shadow("mango") is None


def test_registry_loads_shadow_when_present(tmp_path: Path) -> None:
    shadow = SHADOW_VERSIONS["citrus"]
    settings = make_settings(tmp_path, shadow_model_versions={"citrus": shadow})
    for commodity, version in (*MODEL_VERSIONS.items(), ("citrus", shadow)):
        write_manifest(
            settings.model_dir,
            commodity_code=commodity,
            version=version,
            labels=LABELS_BY_COMMODITY[commodity],
        )
    registry = ModelRegistry(settings)
    registry.load()
    loaded = registry.shadow("citrus")
    assert loaded is not None
    assert loaded.is_shadow is True
    assert loaded.version == shadow
    assert registry.shadow("mango") is None


def test_primary_raises_when_model_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    registry = ModelRegistry(settings)
    registry.load()
    with pytest.raises(ServiceUnavailable) as excinfo:
        registry.primary("mango")
    assert excinfo.value.status_code == 503
