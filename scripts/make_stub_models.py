"""Create manifest-only stub model folders for local development and CI.

The `stub` backend needs a manifest (labels, input size, version) but no ONNX
file. Run this once after cloning, or let the Makefile/CI do it.

    python scripts/make_stub_models.py --model-dir models
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.domain import ScanType, known_labels

DEFAULT_VERSIONS = {
    ScanType.DISEASE: "disease-chili-v0.1.0",
    ScanType.RIPENESS: "ripeness-chili-v0.1.0",
}

SHADOW_VERSIONS = {
    ScanType.DISEASE: "disease-chili-v0.2.0-rc1",
    ScanType.RIPENESS: "ripeness-chili-v0.2.0-rc1",
}


def write_manifest(model_dir: Path, version: str, scan_type: ScanType) -> Path:
    target = model_dir / version
    target.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model_version": version,
        "scan_type": scan_type.value,
        "commodity_code": "chili",
        "artifact": "model.onnx",
        "labels": list(known_labels(scan_type)),
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
        help="Also write a shadow version per scan type, for staging experiments.",
    )
    args = parser.parse_args()

    written = [
        write_manifest(args.model_dir, version, scan_type)
        for scan_type, version in DEFAULT_VERSIONS.items()
    ]
    if args.with_shadow:
        written.extend(
            write_manifest(args.model_dir, version, scan_type)
            for scan_type, version in SHADOW_VERSIONS.items()
        )

    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
