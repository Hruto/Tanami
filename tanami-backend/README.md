# Tanami Backend

FastAPI service behind the Tanami mobile app. It implements the product requirements R0-R7 (gardens, plant tracking and its history, the disease-detection list and its history, forum, profile, reminders) plus fruit-ripeness scans, BMKG weather, moderation and the disease knowledge base. It is the single owner of persistent state; the `tanami-vision` service (repo root) is stateless and only serves inference.

Contract: `design.md` v0.2 (sections 8, 10, 11, 12 are the source of truth) and `tqa.md`. The generated OpenAPI lives in `contracts/openapi.json`; the frontend generates its types from it.

## Stack

| Layer | Choice |
|---|---|
| Runtime | Python 3.12, FastAPI 0.162, Uvicorn |
| ORM / DB | SQLAlchemy 2.0 (async, asyncpg), Alembic 1.18, PostgreSQL 16 |
| Cache / sessions | Redis 7 (refresh-token sessions, weather cache, rate limits) |
| Auth | JWT (HS256) access tokens + rotating opaque refresh tokens in Redis, Argon2id |
| Storage | S3-compatible (R2/MinIO) or in-memory for local/tests |
| Push | FCM HTTP v1 (service account) |
| Weather | BMKG `api.bmkg.go.id`, cached 6 h, archived in `weather_snapshots` |
| Jobs | APScheduler, single instance (`TANAMI_JOBS_ENABLED`) |
| Observability | structlog JSON with `request_id`, Prometheus `/metrics` |

## Setup

```powershell
cd tanami-backend
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env      # set TANAMI_JWT_SECRET (>= 32 chars)
alembic upgrade head        # 0001 -> 0004
uvicorn app.asgi:app --reload --port 8000
```

No system PostgreSQL? `pgserver` (in `[dev]`) starts one:

```powershell
python -c "from pgserver import get_server; from pathlib import Path; print(get_server(Path('C:/temp/tanami-pg')).get_uri())"
# use that URI with +asyncpg as TANAMI_DATABASE_URL
```

`tanami-vision` must run on `:8001` for scans (`uvicorn app.asgi:app --port 8001` at the repo root, stub models are fine). Everything else works without it. With `TANAMI_STORAGE_BACKEND=memory` uploaded photos are served from `/media/...` (local only).

Docs: <http://127.0.0.1:8000/docs>. Probes outside `/api/v1`: `/health`, `/readyz` (database, Redis, and vision as a soft check), `/metrics`.

## API surface

Everything in `design.md` section 10 is implemented and checked by `tests/contract`. By requirement:

| Requirement | Endpoints |
|---|---|
| R0 Tambah Kebun | `POST/GET/PATCH/DELETE /farms...` (`placement`: `indoor`/`outdoor`), `/regions/search`, `/regions/resolve` |
| R1 Tracking | `GET /plant-types`, `POST /farms/{id}/plants`, `GET/PATCH /plants/{id}` (`age_days`, `next_watering_on`), `/plants/{id}/photos`, `/plants/{id}/care-logs`, `POST /plants/{id}/end` |
| R2 History Tracking | `GET /plants?status=ended`, `GET /plants/{id}`, `GET /plants/{id}/timeline` |
| R3 Deteksi | `POST /detection-plants`, `POST /scans` with `detection_plant_id`, `GET /detection-plants/{id}`, `POST /detection-plants/{id}/end` |
| R4 History Deteksi | `GET /detection-plants?status=ended`, `GET /scans/{id}`, `POST /detection-plants/{id}/reactivate` |
| R5 Forum | `/forum/posts...`, `PUT/DELETE /forum/posts/{id}/like`, comments, reports |
| R6 Profil | `GET/PATCH /users/me` (email, username, full name), `POST /users/me/password`, `/users/me/notification-settings` (`photo_reminder_days`, `monitoring_reminder_days`), `POST /auth/logout`, `DELETE /users/me` |
| R7 Pengingat | jobs `care_reminders` (watering/photo/monitoring), `GET /reminders`, `GET /home` |

Staff and extra endpoints:

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /users/me/password` | user | Change password; other devices are logged out, a fresh token pair is returned |
| `GET/DELETE /devices...` | user | List / remove push devices |
| `DELETE /forum/comments/{id}` | author, moderator | Remove a comment |
| `GET /moderation/reports` | moderator, admin | Reported content awaiting review |
| `POST /moderation/reports/{post\|comment}/{id}/resolve` | moderator, admin | `dismiss` / `hide` / `remove`, closes every open report |
| `PATCH /moderation/posts/{id}`, `/moderation/comments/{id}` | moderator, admin | Set `published` / `hidden` / `removed` |
| `PATCH /admin/users/{id}/role` | admin | Verify an expert, appoint a moderator |
| `POST /admin/reminders/general` | admin | Team broadcast (`general` reminder) to one user or everyone |
| `GET/PATCH /review/feedback...` | expert, admin | Review "incorrect" scan feedback and set the correct label (TQA 8.4) |

The first admin comes from `TANAMI_BOOTSTRAP_ADMINS` (promoted at registration).

Behaviour worth knowing:

* `POST /scans` returns **201** for a new scan and **200** for a resend with the same `client_uuid` (design 10.6).
* Plant `health_status` is recomputed by replaying the leaf scans in capture order (design 8.2), so a late offline upload or a deleted scan cannot leave a wrong status. A plant without a leaf scan for 14 days becomes `unknown` (nightly job).
* `advice` in a disease result is built only from the reviewed `diseases` row (summary, first aid, reviewer, review date). A class the model knows but the knowledge base does not is stored without a disease link and without advice.
* Forum reads are public; hidden posts are visible to their author and moderators only. `image_keys` must come from the caller's own `/uploads/forum-image`.

## Scheduled jobs (`TANAMI_JOBS_ENABLED=true` on exactly one replica)

| Job | When (WIB) | What |
|---|---|---|
| `fetch_weather` | 06:00, 18:00 | Fresh BMKG forecast per village with an active farm, spaced to stay under 60 req/min |
| `generate_reminders` | 06:15, 18:15 | `fungal_risk`, `harvest_soon`, `heavy_rain_harvest`, `heat_stress` (outdoor gardens only) |
| `care_reminders` | 06:30 | `watering` (irrigation schedule), `photo` (user period), `monitoring` (no activity) for active tracked plants |
| `scan_followup` | 07:00 | Sick/at-risk plants not rescanned for 5 days |
| `dispatch_pushes` | hourly :05 | Pushes deferred by quiet hours |
| `expire_reminders` | 00:15 | `valid_until` passed -> `dismissed` |
| `decay_health` | 00:30 | No leaf scan for 14 days -> `unknown` |
| `purge_accounts` | 03:00 | Accounts deleted 30+ days ago: photos and rows removed |

Delivery rules (design 12.4): dedupe per type/plant/local day, quiet hours from the user settings (high priority still goes), max 3 pushes per user per local day, per-type opt-out, invalid FCM tokens are deleted.

## Configuration

Every setting is `TANAMI_<FIELD>` (see `.env.example`). Production refuses to boot with a weak JWT secret, no vision token, or non-S3 storage. Set `TANAMI_TRUST_FORWARDED_FOR=true` only behind a proxy that overwrites `X-Forwarded-For`.

## Verification

```powershell
ruff check app tests scripts migrations
ruff format --check app tests scripts migrations
mypy app scripts
python scripts/export_openapi.py
pytest -q --cov=app --cov-fail-under=80
```

The suite (unit, integration against a real PostgreSQL 16, contract) starts its own database; see `CONTRIBUTING.md`. CI: `.github/workflows/backend-ci.yml`. The audit that produced the current state is in `docs/backend-audit.md`.

## Layout

```
app/
  api/v1/        routes: auth, farms (+ tracking), detections, scans, reminders, weather,
                 diseases, forum, staff
  core/          config, security, errors, middleware, logging, pagination, rate limit
  models/        SQLAlchemy models (constraints live here)
  schemas/       Pydantic request/response models (the API contract)
  services/      business logic (scan, farm, tracking, detection, reminder, care_reminders,
                 weather, forum, admin, maintenance)
  providers/     vision client, storage, images, push (FCM v1), weather (BMKG)
  jobs/          APScheduler jobs
  data/          seed data (diseases, regions)
migrations/      Alembic (0001-0004)
contracts/       openapi.json (generated)
tests/           unit / integration / contract
```
