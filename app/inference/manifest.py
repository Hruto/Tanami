"""Model manifests and artifact resolution.

A manifest is written next to the exported artifact by the training pipeline
(`tanami-ml`). The service refuses to load a model whose manifest disagrees
with the contract, because a silent label-order mismatch produces confident
but wrong diagnoses (TQA 8.4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.errors import ModelLoadError
from app.domain import ScanType, known_labels


@dataclass(frozen=True, slots=True)
class ModelManifest:
    model_version: str
    scan_type: ScanType
    commodity_code: str
    artifact: str
    labels: tuple[str, ...]
    input_size: int
    input_name: str
    output_name: str
    normalization: str
    output_activation: str
    sha256: str
    metrics: dict[str, Any] = field(default_factory=dict)


def _require(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        msg = f"manifest tidak memiliki field wajib '{key}'"
        raise ModelLoadError(msg)
    return data[key]


def load_manifest(model_dir: Path, model_version: str, scan_type: ScanType) -> ModelManifest:
    manifest_path = model_dir / model_version / "manifest.json"
    if not manifest_path.is_file():
        msg = f"manifest model tidak ditemukan: {manifest_path}"
        raise ModelLoadError(msg)

    try:
        raw: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"manifest model tidak dapat dibaca: {manifest_path}"
        raise ModelLoadError(msg) from exc

    try:
        manifest_scan_type = ScanType(str(_require(raw, "scan_type")))
    except ValueError as exc:
        msg = f"scan_type pada manifest {model_version} tidak dikenal"
        raise ModelLoadError(msg) from exc

    if manifest_scan_type is not scan_type:
        msg = (
            f"manifest {model_version} bertipe {manifest_scan_type.value}, "
            f"tetapi diminta sebagai {scan_type.value}"
        )
        raise ModelLoadError(msg)

    labels = tuple(str(item) for item in _require(raw, "labels"))
    expected = known_labels(scan_type)
    if sorted(labels) != sorted(expected):
        msg = f"label pada manifest {model_version} tidak sesuai kontrak: {list(labels)}"
        raise ModelLoadError(msg)

    input_size = int(_require(raw, "input_size"))
    if input_size <= 0:
        msg = f"input_size pada manifest {model_version} tidak valid"
        raise ModelLoadError(msg)

    artifact = str(_require(raw, "artifact"))
    artifact_parts = Path(artifact).parts
    if Path(artifact).is_absolute() or ".." in artifact_parts:
        msg = f"artifact pada manifest {model_version} harus berupa path relatif"
        raise ModelLoadError(msg)

    normalization = str(raw.get("normalization", "zero_one"))
    if normalization not in {"zero_one", "imagenet"}:
        msg = f"normalization '{normalization}' pada manifest {model_version} tidak didukung"
        raise ModelLoadError(msg)

    output_activation = str(raw.get("output_activation", "softmax"))
    if output_activation not in {"softmax", "none"}:
        msg = (
            f"output_activation '{output_activation}' pada manifest {model_version} tidak didukung"
        )
        raise ModelLoadError(msg)

    return ModelManifest(
        model_version=str(_require(raw, "model_version")),
        scan_type=manifest_scan_type,
        commodity_code=str(_require(raw, "commodity_code")),
        artifact=artifact,
        labels=labels,
        input_size=input_size,
        input_name=str(_require(raw, "input_name")),
        output_name=str(_require(raw, "output_name")),
        normalization=normalization,
        output_activation=output_activation,
        sha256=str(raw.get("sha256", "")),
        metrics=dict(raw.get("metrics", {})),
    )


def resolve_artifact(manifest: ModelManifest, model_dir: Path) -> Path:
    path = model_dir / manifest.model_version / manifest.artifact
    if not path.is_file():
        msg = f"artefak model tidak ditemukan: {path}"
        raise ModelLoadError(msg)
    return path
