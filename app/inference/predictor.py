"""Predictors.

Two backends implement the same interface:

``StubPredictor``
    Deterministic, dependency-free. Produces a plausible probability vector
    from a hash of the pixels so the backend, frontend and tests can run
    end-to-end before a trained model exists. Refused in production.

``OnnxPredictor``
    Runs the exported model through ONNX Runtime. Labels come from the
    manifest, never from the model metadata, so label order is fixed by the
    versioned manifest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from app.core.errors import ModelLoadError
from app.inference.manifest import ModelManifest, resolve_artifact

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass(frozen=True, slots=True)
class RawPrediction:
    """Probability per label, aligned with ``manifest.labels``."""

    model_version: str
    probabilities: dict[str, float]
    inference_ms: float


class Predictor(Protocol):
    @property
    def manifest(self) -> ModelManifest: ...

    def predict(self, image: np.ndarray) -> RawPrediction: ...


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    result: np.ndarray = exp / np.sum(exp, axis=-1, keepdims=True)
    return result


def _normalise(image: np.ndarray, mode: str) -> np.ndarray:
    batch = np.expand_dims(image, axis=0).astype(np.float32)
    if mode == "imagenet":
        batch = (batch - _IMAGENET_MEAN) / _IMAGENET_STD
    return batch


class StubPredictor:
    """Deterministic placeholder used until a trained artifact exists."""

    def __init__(self, manifest: ModelManifest) -> None:
        self._manifest = manifest

    @property
    def manifest(self) -> ModelManifest:
        return self._manifest

    def predict(self, image: np.ndarray) -> RawPrediction:
        import time

        started = time.perf_counter()
        digest = hashlib.sha256(np.ascontiguousarray(image).tobytes()).digest()
        seed = int.from_bytes(digest[:8], "big", signed=False)
        rng = np.random.default_rng(seed)

        labels = self._manifest.labels
        # Bias the draw so the stub behaves like a real classifier: one label
        # dominates most of the time instead of a uniform spread.
        scores = rng.dirichlet(np.full(len(labels), 0.6, dtype=np.float64))
        probabilities = {label: float(score) for label, score in zip(labels, scores, strict=True)}
        return RawPrediction(
            model_version=self._manifest.model_version,
            probabilities=probabilities,
            inference_ms=round((time.perf_counter() - started) * 1000, 2),
        )


class OnnxPredictor:
    def __init__(self, manifest: ModelManifest, model_dir: Path, *, intra_op_threads: int) -> None:
        import onnxruntime as ort  # imported lazily so the stub path needs no native runtime

        artifact = resolve_artifact(manifest, model_dir)
        options = ort.SessionOptions()
        options.intra_op_num_threads = intra_op_threads
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        try:
            self._session = ort.InferenceSession(
                str(artifact), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:  # onnxruntime raises bare Exception subclasses
            msg = f"gagal memuat artefak ONNX {artifact.name}: {exc}"
            raise ModelLoadError(msg) from exc

        available_inputs = {item.name for item in self._session.get_inputs()}
        if manifest.input_name not in available_inputs:
            msg = (
                f"model {manifest.model_version} tidak memiliki input "
                f"'{manifest.input_name}' (ada: {sorted(available_inputs)})"
            )
            raise ModelLoadError(msg)

        self._manifest = manifest

    @property
    def manifest(self) -> ModelManifest:
        return self._manifest

    def predict(self, image: np.ndarray) -> RawPrediction:
        import time

        batch = _normalise(image, self._manifest.normalization)
        started = time.perf_counter()
        outputs = self._session.run(
            [self._manifest.output_name], {self._manifest.input_name: batch}
        )
        inference_ms = round((time.perf_counter() - started) * 1000, 2)

        logits = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        if logits.shape[0] != len(self._manifest.labels):
            msg = (
                f"model {self._manifest.model_version} mengembalikan {logits.shape[0]} skor "
                f"untuk {len(self._manifest.labels)} label"
            )
            raise ModelLoadError(msg)

        probabilities = (
            _softmax(logits) if self._manifest.output_activation == "softmax" else logits
        )
        mapped = {
            label: float(score)
            for label, score in zip(self._manifest.labels, probabilities, strict=True)
        }
        return RawPrediction(
            model_version=self._manifest.model_version,
            probabilities=mapped,
            inference_ms=inference_ms,
        )


def build_predictor(
    manifest: ModelManifest,
    model_dir: Path,
    *,
    backend: str,
    intra_op_threads: int,
) -> Predictor:
    if backend == "stub":
        return StubPredictor(manifest)
    return OnnxPredictor(manifest, model_dir, intra_op_threads=intra_op_threads)
