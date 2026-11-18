from __future__ import annotations

import io
import random
from pathlib import Path

import pytest
from app.core.config import Settings
from app.domain import DISEASE_LABELS_BY_COMMODITY, ScanType, known_labels
from app.main import create_app
from app.services.registry import ModelRegistry
from PIL import Image, ImageFilter

MODEL_VERSIONS: dict[str, str] = {
    "mango": "disease-mango-v0.1.0",
    "citrus": "disease-citrus-v0.1.0",
    "strawberry": "disease-strawberry-v0.1.0",
}

SHADOW_VERSIONS: dict[str, str] = {
    commodity: version.replace("v0.1.0", "v0.2.0-rc1")
    for commodity, version in MODEL_VERSIONS.items()
}


def labels_for(commodity: str) -> list[str]:
    return list(known_labels(ScanType.DISEASE, commodity))


MANGO_LABELS = labels_for("mango")
CITRUS_LABELS = labels_for("citrus")
STRAWBERRY_LABELS = labels_for("strawberry")
LABELS_BY_COMMODITY = {
    commodity: labels_for(commodity) for commodity in DISEASE_LABELS_BY_COMMODITY
}


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "local",
        "model_backend": "stub",
        "model_dir": tmp_path / "models",
        "service_token": "",
        "admin_token": "",
        "log_json": False,
        # The production default (2s) is a latency budget, not a test budget: a
        # loaded CI box can exceed it and turn a success-path test into a 503.
        # Tests that care about the timeout set it explicitly.
        "inference_timeout_seconds": 30.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def write_manifest(
    model_dir: Path,
    *,
    commodity_code: str,
    version: str,
    labels: list[str],
    scan_type: str = "disease",
    input_size: int = 224,
) -> Path:
    import json

    target = model_dir / version
    target.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model_version": version,
        "scan_type": scan_type,
        "commodity_code": commodity_code,
        "artifact": "model.onnx",
        "labels": labels,
        "input_size": input_size,
        "input_name": "input",
        "output_name": "logits",
        "normalization": "zero_one",
        "output_activation": "softmax",
        "sha256": "",
        "metrics": {"macro_f1": "n/a"},
    }
    path = target / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def write_primary_models(model_dir: Path) -> None:
    """Write the three primary manifests used by the shared fixtures."""
    for commodity, version in MODEL_VERSIONS.items():
        write_manifest(
            model_dir,
            commodity_code=commodity,
            version=version,
            labels=LABELS_BY_COMMODITY[commodity],
        )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    resolved = make_settings(tmp_path)
    resolved.model_dir.mkdir(parents=True, exist_ok=True)
    write_primary_models(resolved.model_dir)
    return resolved


@pytest.fixture
def registry(settings: Settings) -> ModelRegistry:
    reg = ModelRegistry(settings)
    reg.load()
    return reg


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(settings: Settings):
    from fastapi.testclient import TestClient

    with TestClient(create_app(settings)) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# Image helpers
# --------------------------------------------------------------------------- #
def noise_image(size: int = 320, seed: int = 7) -> Image.Image:
    """High-variance image so the blur gate passes."""
    rng = random.Random(seed)
    image = Image.new("RGB", (size, size))
    pixels = [
        (rng.randrange(60, 220), rng.randrange(60, 220), rng.randrange(60, 220))
        for _ in range(size * size)
    ]
    image.putdata(pixels)
    return image


def blurred_image(size: int = 320) -> Image.Image:
    flat = Image.new("RGB", (size, size), (128, 128, 128))
    return flat.filter(ImageFilter.GaussianBlur(radius=12))


def dark_image(size: int = 320) -> Image.Image:
    rng = random.Random(3)
    image = Image.new("RGB", (size, size))
    image.putdata([(rng.randrange(0, 12),) * 3 for _ in range(size * size)])
    return image


def encode(image: Image.Image, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def predict_files(image_bytes: bytes, scan_type: str = "disease", **form: str) -> dict[str, object]:
    files = {"image": ("photo.jpg", image_bytes, "image/jpeg")}
    data = {"type": scan_type, **form}
    return {"files": files, "data": data}
