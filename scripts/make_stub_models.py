"""Create manifest-only stub model folders for local development and CI.

The `stub` backend needs a manifest (labels, input size, version) but no ONNX
file. Run this once after cloning, or let the Makefile/CI do it.

    python scripts/make_stub_models.py --model-dir models
    python scripts/make_stub_models.py --model-dir models --with-shadow
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.domain import DISEASE_LABELS_BY_COMMODITY, ScanType, known_labels

# design.md 11.5 / TQA 8.4 naming: disease-<komoditas>-v<semver>.
DEFAULT_VERSIONS: dict[str, str] = {
    "mango": "disease-mango-v0.1.0",
    "citrus": "disease-citrus-v0.1.0",
    "tomato": "disease-tomato-v0.1.0",
}

SHADOW_VERSIONS: dict[str, str] = {
    commodity: version.replace("v0.1.0", "v0.2.0-rc1")
    for commodity, version in DEFAULT_VERSIONS.items()
}

SUPPORTED = tuple(DISEASE_LABELS_BY_COMMODITY)


def write_manifest(model_dir: Path, version: str, commodity_code: str) -> Path:
    if commodity_code not in SUPPORTED:
        msg = f"komoditas '{commodity_code}' tidak didukung"
        raise ValueError(msg)

    target = model_dir / version
    target.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model_version": version,
        "scan_type": ScanType.DISEASE.value,
        "commodity_code": commodity_code,
        "artifact": "model.onnx",
        "labels": list(known_labels(ScanType.DISEASE, commodity_code)),
        "input_size": 224,
        "input_name": "input",
        "output_name": "logits",
        "normalization": "zero_one",
        "output_activation": "softmax",
        "sha256": "",
        "metrics": {"source": "stub", "macro_f1": 0.0},
    }
    path = target / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    parser.add_argument(
        "--with-shadow",
        action="store_true",
        help="Juga tulis versi shadow per komoditas, untuk eksperimen staging.",
    )
    args = parser.parse_args()

    written = [
        write_manifest(args.model_dir, version, commodity)
        for commodity, version in DEFAULT_VERSIONS.items()
    ]
    if args.with_shadow:
        written.extend(
            write_manifest(args.model_dir, version, commodity)
            for commodity, version in SHADOW_VERSIONS.items()
        )

    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
