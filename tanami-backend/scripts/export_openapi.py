"""Write the OpenAPI document to ``contracts/openapi.json``.

The frontend generates its API types from this file (TQA 5.3), and the
contract test fails when it is stale. No database or network is needed.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = Settings(
        _env_file=None,
        app_env="local",
        database_url="postgresql+asyncpg://unused:unused@127.0.0.1:1/unused",
        log_json=False,
    )
    schema = create_app(settings).openapi()
    target = ROOT / "contracts" / "openapi.json"
    target.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {target.relative_to(ROOT)} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
