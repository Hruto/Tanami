from __future__ import annotations

import numpy as np
import pytest
from app.core.errors import ModelLoadError
from app.domain import ScanType
from app.inference.manifest import load_manifest
from app.inference.predictor import OnnxPredictor, StubPredictor, build_predictor
from tests.conftest import DISEASE_LABELS, write_manifest


def _manifest(tmp_path, **kwargs):  # type: ignore[no-untyped-def]
    write_manifest(
        tmp_path,
        scan_type=kwargs.get("scan_type", "disease"),
        version="disease-chili-v0.1.0",
        labels=DISEASE_LABELS,
    )
    return load_manifest(tmp_path, "disease-chili-v0.1.0", ScanType.DISEASE)


def test_stub_is_deterministic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    manifest = _manifest(tmp_path)
    predictor = StubPredictor(manifest)
    image = np.linspace(0, 1, 224 * 224 * 3, dtype=np.float32).reshape(224, 224, 3)

    first = predictor.predict(image)
    second = predictor.predict(image)

    assert first.probabilities == second.probabilities
    assert set(first.probabilities) == set(DISEASE_LABELS)


def test_stub_distribution_sums_to_one(tmp_path) -> None:  # type: ignore[no-untyped-def]
    manifest = _manifest(tmp_path)
    predictor = StubPredictor(manifest)
    image = np.random.default_rng(1).random((224, 224, 3), dtype=np.float32)
    prediction = predictor.predict(image)
    assert sum(prediction.probabilities.values()) == pytest.approx(1.0, abs=1e-6)


def test_stub_is_sensitive_to_pixels(tmp_path) -> None:  # type: ignore[no-untyped-def]
    manifest = _manifest(tmp_path)
    predictor = StubPredictor(manifest)
    rng = np.random.default_rng(2)
    a = predictor.predict(rng.random((224, 224, 3), dtype=np.float32))
    b = predictor.predict(rng.random((224, 224, 3), dtype=np.float32))
    assert a.probabilities != b.probabilities


def test_build_predictor_respects_backend(tmp_path) -> None:  # type: ignore[no-untyped-def]
    manifest = _manifest(tmp_path)
    stub = build_predictor(manifest, tmp_path, backend="stub", intra_op_threads=1)
    assert isinstance(stub, StubPredictor)


def test_missing_artifact_raises_for_onnx_backend(tmp_path) -> None:  # type: ignore[no-untyped-def]
    manifest = _manifest(tmp_path)
    with pytest.raises(ModelLoadError, match="artefak"):
        build_predictor(manifest, tmp_path, backend="onnx", intra_op_threads=1)


def _write_fixture_model(tmp_path, *, input_name: str = "input"):  # type: ignore[no-untyped-def]
    from scripts.make_fixture_onnx import build_fixture_onnx

    version = "disease-chili-v0.1.0"
    target = tmp_path / version
    build_fixture_onnx(target / "model.onnx", labels=DISEASE_LABELS, input_size=224)
    import json

    manifest_payload = {
        "model_version": version,
        "scan_type": "disease",
        "commodity_code": "chili",
        "artifact": "model.onnx",
        "labels": DISEASE_LABELS,
        "input_size": 224,
        "input_name": input_name,
        "output_name": "output",
        "normalization": "zero_one",
        "output_activation": "softmax",
        "sha256": "",
        "metrics": {},
    }
    (target / "manifest.json").write_text(json.dumps(manifest_payload), encoding="utf-8")
    return load_manifest(tmp_path, version, ScanType.DISEASE)


def test_onnx_predictor_runs_the_fixture_model(tmp_path) -> None:  # type: ignore[no-untyped-def]
    manifest = _write_fixture_model(tmp_path)
    predictor = OnnxPredictor(manifest, tmp_path, intra_op_threads=1)
    image = np.random.default_rng(0).random((224, 224, 3), dtype=np.float32)
    prediction = predictor.predict(image)

    assert prediction.model_version == manifest.model_version
    assert set(prediction.probabilities) == set(DISEASE_LABELS)
    assert sum(prediction.probabilities.values()) == pytest.approx(1.0, abs=1e-5)
    assert prediction.inference_ms >= 0


def test_onnx_predictor_validates_input_name(tmp_path) -> None:  # type: ignore[no-untyped-def]
    manifest = _write_fixture_model(tmp_path, input_name="not_the_input")
    with pytest.raises(ModelLoadError, match="input"):
        OnnxPredictor(manifest, tmp_path, intra_op_threads=1)


def test_onnx_predictor_rejects_corrupt_artifact(tmp_path) -> None:  # type: ignore[no-untyped-def]
    version = "disease-chili-v0.1.0"
    target = tmp_path / version
    target.mkdir(parents=True)
    (target / "model.onnx").write_bytes(b"not an onnx file")
    import json

    payload = {
        "model_version": version,
        "scan_type": "disease",
        "commodity_code": "chili",
        "artifact": "model.onnx",
        "labels": DISEASE_LABELS,
        "input_size": 224,
        "input_name": "input",
        "output_name": "output",
    }
    (target / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    manifest = load_manifest(tmp_path, version, ScanType.DISEASE)
    with pytest.raises(ModelLoadError, match="gagal memuat"):
        OnnxPredictor(manifest, tmp_path, intra_op_threads=1)
