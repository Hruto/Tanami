# Contributing to tanami-backend

## Ground rules

- Match the existing conventions: Indonesian user-facing error strings, `snake_case` JSON, UUID ids, ISO 8601 UTC timestamps, response envelopes `{ "data": ... }` / `{ "data": [...], "meta": {...} }`.
- Keep the business logic in `services/`; routes in `api/v1/` stay thin (parse, call service, wrap in envelope).
- Constraints and CHECKs belong in the SQLAlchemy models (`models/`) so Alembic autogenerates them. Do not hand-edit migrations for anything the model already declares.
- `mypy` runs in strict mode (`pyproject.toml` `[tool.mypy] strict = true, warn_unreachable = true`). Every `# type: ignore` must carry a specific code (`[arg-type]`, `[import-untyped]`, ...) and be removed the moment it becomes unused (`warn_unused_ignores = true`).

## Local setup

See `README.md`. Short version:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

## The verification loop (run before every commit)

```powershell
ruff check app tests scripts migrations
ruff format --check app tests scripts migrations
mypy app scripts
python scripts/export_openapi.py      # then commit contracts/openapi.json if it changed
pytest -q --cov=app --cov-fail-under=80
```

`pytest` needs no running services: it starts a throwaway PostgreSQL 16 with `pgserver` (or uses `TANAMI_TEST_DATABASE_URL`), migrates it with the real Alembic chain, and uses fakeredis plus in-memory fakes for storage, vision, weather and push.

`pyproject.toml` defines the exact tool versions; do not bump them without a reason recorded in the PR.

## Database workflow

1. Change the model in `app/models/`.
2. Generate the migration: `alembic revision --autogenerate -m "short description"`.
3. Read the generated file in `migrations/versions/` before applying. Autogenerate is good at tables/columns/constraints but will not detect renames (it emits drop + create) and may miss server defaults.
4. Apply: `alembic upgrade head`.
5. Verify zero drift: re-run `alembic revision --autogenerate` and confirm it produces an empty migration (`pass` only).
6. Test the downgrade: `alembic downgrade -1` then `alembic upgrade head`. Every migration must be reversible.

Use `pgserver` (in `[dev]`) to get a throwaway Postgres 16 cluster without installing anything:

```powershell
python -c "from pgserver import get_server; from pathlib import Path; s=get_server(Path('C:/temp/tanami-pg')); print(s.get_uri())"
```

## Testing expectations

- Unit tests for the pure rule engines (`services/reminder.py` rules, `services/scan.py` internals) need no database.
- Integration tests use a real Postgres (marker `db`) and an in-memory storage backend (`TANAMI_STORAGE_BACKEND=memory`); fakeredis covers Redis.
- Contract tests compare the live OpenAPI document against `design.md` (marker `contract`).
- Coverage floor is 80% (`pyproject.toml` `[tool.coverage.report]`); `app/jobs/scheduler.py` is excluded because it is environment-gated.
- New endpoints must ship with at least one happy-path and one error-path test.

## Style notes

- User-facing strings are Indonesian and must be safe to show verbatim (`message` is displayed by the frontend based on `code`, never parsed).
- Errors are raised as `AppError` subclasses in services; routes never build HTTP responses by hand except `Response(status_code=...)` for 204.
- Rate limits follow `design.md` 10.3: login 5/min/IP, scans 20/min/user, everything else 120/min/user (all configurable). `X-Forwarded-For` is ignored unless `TANAMI_TRUST_FORWARDED_FOR=true`.
- Plant `health_status` is never set directly: `ScanService.refresh_plant` replays the leaf scans in capture order through `next_health_status` (design 8.2). Call it after any change to a plant's scans.
- Times written to the database are timezone-aware UTC; "today" for reminders is the local date (`ReminderService.today`).
- Scan uploads go through `providers/images.py` (content sniffing + re-encode + EXIF strip) before storage. Never store raw bytes.
- `treatments` in `diseases` carry no dose and always a `safety_note` (TQA 8.3).

## Common pitfalls

- `redis.ping()` is typed `Awaitable[bool] | bool` by redis-py; on the asyncio client it is awaitable. Cast with `cast(Awaitable[bool], ...)` (see `main.py`, `ops.py`).
- `AsyncEngine.pool` is typed as the abstract `Pool`; size counters live on `QueuePool`. Use `getattr` (see `db/session.py::engine_info`).
- `session.execute(...)` returns `Result`, not `CursorResult`; only the latter has `rowcount`. Cast: `cast(CursorResult[Any], result)`.
- Keyset pagination must not use tuple comparison `(col_a, col_b) < (x, y)` against instrumented attributes; write it as an explicit `OR` (see `services/forum.py`, `api/v1/reminders.py`).
- `dict(mapped_column_value)` fails mypy when the column is typed `dict[str, object]` but arrives as `object`; guard with `isinstance(..., dict)` first.
- `is_fungal_risk` accumulates humidity run in **hours**, not slots; reset `run_hours` to `0.0` on a dry slot.
- Seed functions must stay idempotent (`on_conflict_do_nothing` / `on_conflict_do_update`); never truncate reference tables on startup.

## Commit / PR

- One logical change per commit. Commit messages in the imperative mood, referencing the design section when relevant (e.g. `feat(scans): idempotent upload per design 10.6`).
- Do not commit `.env`, `__pycache__`, `.coverage`, or `*.pyc`.
- Before opening a PR, paste the output of the four verification commands into the PR description.
