from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.errors import ModelLoadError
from app.domain import ScanType
from app.inference.manifest import load_manifest, resolve_artifact
from app.services.registry import ModelRegistry
from tests.conftest import (
    DISEASE_LABELS,
    MODEL_VERSIONS,
    RIPENESS_LABELS,
    make_settings,
    write_manifest,
)


def test_loads_a_valid_manifest(tmp_path: Path) -> None:
    write_manifest(
        tmp_path, scan_type="disease", version="disease-chili-v0.1.0", labels=DISEASE_LABELS
    )
    manifest = load_manifest(tmp_path, "disease-chili-v0.1.0", ScanType.DISEASE)
    assert manifest.scan_type is ScanType.DISEASE
    assert manifest.input_size == 224
    assert set(manifest.labels) == set(DISEASE_LABELS)


def test_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelLoadError, match="tidak ditemukan"):
        load_manifest(tmp_path, "nope", ScanType.DISEASE)


def test_corrupt_manifest_raises(tmp_path: Path) -> None:
    target = tmp_path / "broken"
    target.mkdir()
    (target / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ModelLoadError, match="tidak dapat dibaca"):
        load_manifest(tmp_path, "broken", ScanType.DISEASE)


def test_manifest_scan_type_mismatch_raises(tmp_path: Path) -> None:
    write_manifest(tmp_path, scan_type="disease", version="v1", labels=DISEASE_LABELS)
    with pytest.raises(ModelLoadError, match="bertipe disease"):
        load_manifest(tmp_path, "v1", ScanType.RIPENESS)


def test_manifest_with_wrong_labels_raises(tmp_path: Path) -> None:
    write_manifest(tmp_path, scan_type="disease", version="v1", labels=["anthracnose"])
    with pytest.raises(ModelLoadError, match="tidak sesuai kontrak"):
        load_manifest(tmp_path, "v1", ScanType.DISEASE)


def test_manifest_with_missing_label_raises(tmp_path: Path) -> None:
    write_manifest(
        tmp_path, scan_type="disease", version="v1", labels=[*DISEASE_LABELS[:-1], "healthy"]
    )
    with pytest.raises(ModelLoadError, match="tidak sesuai kontrak"):
        load_manifest(tmp_path, "v1", ScanType.DISEASE)


def test_manifest_with_missing_required_field_raises(tmp_path: Path) -> None:
    target = tmp_path / "v1"
    target.mkdir()
    payload = {
        "model_version": "v1",
        "scan_type": "disease",
        "commodity_code": "chili",
        "artifact": "model.onnx",
        "labels": DISEASE_LABELS,
        "input_name": "input",
        "output_name": "logits",
    }
    (target / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="input_size"):
        load_manifest(tmp_path, "v1", ScanType.DISEASE)


def test_manifest_artifact_may_not_escape_the_version_dir(tmp_path: Path) -> None:
    write_manifest(tmp_path, scan_type="disease", version="v1", labels=DISEASE_LABELS)
    path = tmp_path / "v1" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifact"] = "../../etc/passwd"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="relatif"):
        load_manifest(tmp_path, "v1", ScanType.DISEASE)


def test_absolute_artifact_path_raises(tmp_path: Path) -> None:
    write_manifest(tmp_path, scan_type="disease", version="v1", labels=DISEASE_LABELS)
    path = tmp_path / "v1" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifact"] = "C:\\models\\model.onnx"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="relatif"):
        load_manifest(tmp_path, "v1", ScanType.DISEASE)


def test_unknown_normalization_raises(tmp_path: Path) -> None:
    write_manifest(tmp_path, scan_type="disease", version="v1", labels=DISEASE_LABELS)
    path = tmp_path / "v1" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["normalization"] = "weird"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="normalization"):
        load_manifest(tmp_path, "v1", ScanType.DISEASE)


def test_unknown_activation_raises(tmp_path: Path) -> None:
    write_manifest(tmp_path, scan_type="disease", version="v1", labels=DISEASE_LABELS)
    path = tmp_path / "v1" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["output_activation"] = "sigmoid"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="output_activation"):
        load_manifest(tmp_path, "v1", ScanType.DISEASE)


def test_resolve_artifact_reports_missing_file(tmp_path: Path) -> None:
    write_manifest(tmp_path, scan_type="disease", version="v1", labels=DISEASE_LABELS)
    manifest = load_manifest(tmp_path, "v1", ScanType.DISEASE)
    with pytest.raises(ModelLoadError, match="artefak"):
        resolve_artifact(manifest, tmp_path)


def test_registry_loads_both_primary_models(settings) -> None:  # type: ignore[no-untyped-def]
    registry = ModelRegistry(settings)
    registry.load()
    assert registry.is_ready is True
    assert registry.primary(ScanType.DISEASE).version == MODEL_VERSIONS["disease"]
    assert registry.primary(ScanType.RIPENESS).version == MODEL_VERSIONS["ripeness"]
    assert registry.load_errors == []


def test_registry_is_not_ready_when_one_model_is_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_manifest(
        settings.model_dir,
        scan_type="disease",
        version=MODEL_VERSIONS["disease"],
        labels=DISEASE_LABELS,
    )
    registry = ModelRegistry(settings)
    registry.load()
    assert registry.is_ready is False
    assert len(registry.load_errors) == 1


def test_registry_shadow_failure_is_not_fatal(settings) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import Settings

    shadow_settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="local",
        model_backend="stub",
        model_dir=settings.model_dir,
        shadow_disease_model_version="does-not-exist",
    )
    registry = ModelRegistry(shadow_settings)
    registry.load()
    assert registry.is_ready is True
    assert registry.shadow(ScanType.DISEASE) is None


def test_registry_loads_shadow_when_present(tmp_path: Path) -> None:
    from app.core.config import Settings

    settings = make_settings(tmp_path)
    for scan_type, version, labels in (
        ("disease", MODEL_VERSIONS["disease"], DISEASE_LABELS),
        ("ripeness", MODEL_VERSIONS["ripeness"], RIPENESS_LABELS),
        ("disease", "disease-chili-v0.2.0-rc1", DISEASE_LABELS),
    ):
        write_manifest(settings.model_dir, scan_type=scan_type, version=version, labels=labels)

    shadow_settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="local",
        model_backend="stub",
        model_dir=tmp_path / "models",
        shadow_disease_model_version="disease-chili-v0.2.0-rc1",
    )
    registry = ModelRegistry(shadow_settings)
    registry.load()
    shadow = registry.shadow(ScanType.DISEASE)
    assert shadow is not None
    assert shadow.is_shadow is True
    assert shadow.version == "disease-chili-v0.2.0-rc1"


def test_primary_raises_when_model_missing(tmp_path: Path) -> None:
    from app.core.errors import ServiceUnavailable

    settings = make_settings(tmp_path)
    registry = ModelRegistry(settings)
    registry.load()
    with pytest.raises(ServiceUnavailable) as excinfo:
        registry.primary(ScanType.DISEASE)
    assert excinfo.value.status_code == 503
