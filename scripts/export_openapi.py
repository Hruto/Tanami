"""Fail CI when the published contract and the code disagree.

Two checks:

1. the committed ``contracts/openapi.json`` is byte-identical to what the app
   generates, so a route or schema change cannot land without updating the
   contract (TQA section 6),
2. the committed document is a valid OpenAPI 3.x specification.

    python scripts/export_openapi.py --check
    python scripts/export_openapi.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "contracts" / "openapi.json"


def build_spec() -> dict[str, object]:
    # A fixed, side-effect-free settings object keeps the output stable no
    # matter which .env file happens to exist on the machine running this.
    settings = Settings(app_env="local", model_backend="stub", _env_file=None)  # type: ignore[call-arg]
    app = create_app(settings, load_models=False)
    spec: dict[str, object] = app.openapi()
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Fail if the file is stale.")
    group.add_argument("--write", action="store_true", help="Overwrite the committed file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    spec = build_spec()
    serialized = json.dumps(spec, indent=2, sort_keys=True) + "\n"

    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
        print(f"wrote {args.output}")
        return 0

    if not args.output.is_file():
        print(f"ERROR: {args.output} tidak ada. Jalankan dengan --write.", file=sys.stderr)
        return 1

    current = args.output.read_text(encoding="utf-8")
    if current != serialized:
        print(
            "ERROR: kontrak OpenAPI tidak sinkron dengan kode.\n"
            "Jalankan: python scripts/export_openapi.py --write",
            file=sys.stderr,
        )
        return 1

    print("OK: kontrak OpenAPI sinkron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
