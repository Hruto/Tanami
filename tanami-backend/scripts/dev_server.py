"""Run the API locally without Docker, with demo data for the staff dashboard.

    python scripts/dev_server.py             # http://127.0.0.1:8000, demo data
    python scripts/dev_server.py --no-demo   # same, empty database

PostgreSQL is an embedded ``pgserver`` cluster in ``.devdata/``, Redis is
fakeredis, photos live in memory and the vision model is a deterministic stub.
The ``tanami_dev`` database is recreated on every start because the photos it
would point at are gone once the process exits. Local development only.

Demo accounts (password ``tanami-demo-123``): ``admin``, ``ahli`` (expert),
``moderator``, plus farmers.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.rate_limit import RateLimiter  # noqa: E402
from app.core.state import AppState  # noqa: E402
from app.data.seed import seed_reference_data  # noqa: E402
from app.db.session import create_engine, create_session_factory  # noqa: E402
from app.domain import DISEASE_LABELS, CauseCategory  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.providers.push import LogPushProvider  # noqa: E402
from app.providers.storage import MemoryStorage  # noqa: E402
from app.providers.vision import VisionResult  # noqa: E402
from app.providers.weather import build_weather_provider  # noqa: E402
from fakeredis import FakeAsyncRedis  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from sqlalchemy import text, update  # noqa: E402

DEMO_PASSWORD = "tanami-demo-123"  # noqa: S105 - local demo only
DEV_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

STAFF = (
    ("admin", "Rina Wulandari", "admin"),
    ("ahli", "Dr. Sekar Ayu Pramesti", "expert"),
    ("moderator", "Bayu Saputra", "moderator"),
)
FARMERS = (
    "Slamet Riyadi",
    "Wati Ningsih",
    "Darto Sumarno",
    "Komang Ayu",
    "Yusuf Hidayat",
    "Siti Aminah",
    "Made Wirawan",
    "Tini Rahayu",
    "Hendra Gunawan",
    "Nur Fadilah",
    "Agus Prasetyo",
    "Lilis Suryani",
    "Rudi Hartono",
    "Sri Mulyani",
)
REGIONS = (
    "35.07.02.2001",
    "35.25.03.2001",
    "51.02.02.2001",
    "51.03.01.2001",
    "13.05.02.2001",
    "32.73.05.1001",
    "31.71.03.1001",
)
CAUSES = {
    "healthy": CauseCategory.HEALTHY.value,
    "anthracnose": "fungus",
    "cercospora_leaf_spot": "fungus",
    "bacterial_wilt": "bacteria",
    "leaf_curl_virus": "virus",
    "pest_damage": "pest",
    "nutrient_deficiency": "nutrient_deficiency",
}
WEIGHTED_CODES = (
    ["healthy"] * 5
    + ["anthracnose"] * 4
    + ["cercospora_leaf_spot"] * 3
    + ["leaf_curl_virus"] * 2
    + ["bacterial_wilt", "pest_damage", "nutrient_deficiency"]
)


class DemoVision:
    """Deterministic stand-in for the vision service, good enough for demos."""

    def __init__(self, seed: int = 7) -> None:
        self.rng = random.Random(seed)  # noqa: S311 - not security relevant
        self.forced: list[str] = []

    async def predict(
        self,
        *,
        scan_type: str,
        image: bytes,  # noqa: ARG002 - protocol signature
        content_type: str,  # noqa: ARG002 - protocol signature
        client_uuid: str,  # noqa: ARG002 - protocol signature
        commodity_code: str,  # noqa: ARG002 - protocol signature
    ) -> VisionResult:
        if scan_type == "ripeness":
            stage = self.rng.choice(["unripe", "turning", "ripe"])
            low = {"unripe": 10, "turning": 4, "ripe": 0}[stage]
            result: dict[str, object] = {
                "stage": stage,
                "stage_label": None,
                "confidence": round(self.rng.uniform(0.7, 0.96), 2),
                "estimated_days_min": low,
                "estimated_days_max": low + 4,
                "estimate_confidence": "medium",
                "note": f"Perkiraan panen {low}-{low + 4} hari lagi.",
            }
            return self._wrap("ripeness", "confident", result, 0.88)

        code = self.forced.pop(0) if self.forced else self.rng.choice(WEIGHTED_CODES)
        roll = self.rng.random()
        status = "confident" if roll < 0.7 else "uncertain" if roll < 0.92 else "unknown"
        confidence = round(
            self.rng.uniform(0.78, 0.97) if status == "confident" else self.rng.uniform(0.45, 0.7),
            2,
        )
        top = None
        if status != "unknown":
            top = {
                "disease_code": code,
                "label": DISEASE_LABELS[code],
                "cause_category": CAUSES[code],
                "confidence": confidence,
            }
        result = {
            "top": top,
            "alternatives": [],
            "is_healthy": None if top is None else code == "healthy",
            "severity": None if top is None or code == "healthy" else "moderate",
        }
        return self._wrap("disease", status, result, None if top is None else confidence)

    @staticmethod
    def _wrap(
        scan_type: str, status: str, result: dict[str, object], confidence: float | None
    ) -> VisionResult:
        return VisionResult(
            scan_type=scan_type,
            status=status,
            model_version=f"{scan_type}-chili-demo",
            commodity_code="chili",
            confidence=confidence,
            quality={"exposure": "ok", "blur": "ok"},
            result=result,
            inference_ms=40.0,
        )


def leaf_photo(rng: random.Random, *, sick: bool) -> bytes:
    """A small drawn chili leaf so the review screen has something to look at."""
    image = Image.new("RGB", (480, 360), (226, 221, 200))
    draw = ImageDraw.Draw(image)
    green = (rng.randint(50, 80), rng.randint(110, 140), rng.randint(50, 70))
    draw.ellipse((70, 95, 410, 265), fill=green)
    draw.line((80, 180, 400, 180), fill=(170, 190, 120), width=4)
    for _ in range(rng.randint(5, 12) if sick else 0):
        x, y = rng.randint(120, 360), rng.randint(120, 240)
        r = rng.randint(6, 16)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(96, 70, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def start_database() -> str:
    """Start the embedded cluster and return a fresh ``tanami_dev`` URL."""
    from pgserver import get_server  # type: ignore[attr-defined]

    data_dir = ROOT / ".devdata" / "pg"
    data_dir.mkdir(parents=True, exist_ok=True)
    server = get_server(data_dir, cleanup_mode="stop")
    admin_uri = server.get_uri()
    with psycopg.connect(admin_uri, autocommit=True) as connection:
        connection.execute("DROP DATABASE IF EXISTS tanami_dev WITH (FORCE)")
        connection.execute("CREATE DATABASE tanami_dev")
    base = admin_uri.rsplit("/", 1)[0]
    url = base.replace("postgresql://", "postgresql+asyncpg://", 1) + "/tanami_dev"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("+asyncpg", "+psycopg"))
    command.upgrade(config, "head")
    return url


def dev_settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="local",
        database_url=database_url,
        storage_backend="memory",
        seed_on_startup=True,
        jwt_secret="dev-only-local-dashboard-0123456789abcdef",  # noqa: S106
        cors_origins=DEV_ORIGINS,
        jobs_enabled=False,
        log_json=False,
        log_level="INFO",
        register_rate_limit_per_minute=0,
        scan_rate_limit_per_minute=0,
        global_rate_limit_per_minute=0,
    )


def dev_state(settings: Settings) -> AppState:
    engine = create_engine(settings)
    redis = FakeAsyncRedis(decode_responses=True)
    return AppState(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        redis=redis,
        storage=MemoryStorage(),
        vision=DemoVision(),  # type: ignore[arg-type]
        weather=build_weather_provider(settings),
        push=LogPushProvider(),
        rate_limiter=RateLimiter(redis),
    )


async def _account(
    http: AsyncClient, username: str, full_name: str, *, consent: bool = False
) -> tuple[str, dict[str, str]]:
    response = await http.post(
        "/api/v1/auth/register",
        json={
            "email": f"{username}@demo.tanami.id",
            "username": username,
            "full_name": full_name,
            "password": DEMO_PASSWORD,
            "consent_training_data": consent,
        },
    )
    if response.status_code != 201:
        raise RuntimeError(f"register {username}: {response.text}")
    headers = {"Authorization": f"Bearer {response.json()['data']['access_token']}"}
    me = (await http.get("/api/v1/users/me", headers=headers)).json()["data"]
    return str(me["id"]), headers


async def _ok(response: Any) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RuntimeError(f"{response.request.url}: {response.status_code} {response.text}")
    return dict(response.json()["data"]) if response.content else {}


async def populate(state: AppState) -> None:
    """Fill the dashboard with a believable two weeks of activity."""
    rng = random.Random(42)  # noqa: S311
    vision = state.vision
    now = datetime.now(UTC)
    app = create_app(state=state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://dev") as http:
        staff: dict[str, dict[str, str]] = {}
        for username, name, role in STAFF:
            user_id, headers = await _account(http, username, name)
            async with state.session_factory() as session:
                await session.execute(update(User).where(User.id == user_id).values(role=role))
                await session.commit()
            staff[role] = headers

        farmers: list[tuple[str, dict[str, str]]] = []
        scans: list[tuple[str, dict[str, str], datetime]] = []
        for index, name in enumerate(FARMERS):
            username = name.split()[0].lower() + f"_{index + 1}"
            user_id, headers = await _account(http, username, name, consent=index % 3 != 0)
            farmers.append((user_id, headers))
            farm = await _ok(
                await http.post(
                    "/api/v1/farms",
                    json={
                        "name": rng.choice(["Kebun Belakang", "Lahan Sawah Timur", "Pekarangan"]),
                        "adm4_code": rng.choice(REGIONS),
                        "placement": "outdoor" if index % 4 else "indoor",
                    },
                    headers=headers,
                )
            )
            for number in range(rng.randint(1, 3)):
                planted = date.today() - timedelta(days=rng.randint(25, 120))
                plant = await _ok(
                    await http.post(
                        f"/api/v1/farms/{farm['id']}/plants",
                        json={
                            "label": f"Cabai rawit {number + 1}",
                            "commodity_code": "chili",
                            "planted_at": planted.isoformat(),
                            "growth_stage": "fruiting",
                        },
                        headers=headers,
                    )
                )
                for _ in range(rng.randint(0, 3)):
                    sick = rng.random() < 0.6
                    if isinstance(vision, DemoVision):
                        vision.forced.append(
                            rng.choice([c for c in WEIGHTED_CODES if (c != "healthy") == sick])
                        )
                    captured = now - timedelta(days=rng.randint(0, 13), hours=rng.randint(0, 9))
                    scan = await _ok(
                        await http.post(
                            "/api/v1/scans",
                            data={
                                "type": "disease",
                                "client_uuid": str(uuid4()),
                                "plant_id": plant["id"],
                                "captured_at": captured.isoformat(),
                            },
                            files={"image": ("daun.jpg", leaf_photo(rng, sick=sick), "image/jpeg")},
                            headers=headers,
                        )
                    )
                    scans.append((scan["id"], headers, captured))
                if rng.random() < 0.35:
                    await _ok(
                        await http.post(
                            f"/api/v1/plants/{plant['id']}/end",
                            json={
                                "reason": "harvested",
                                "yield_percent": rng.choice([12, 45, 64, 82, 95, 118]),
                            },
                            headers=headers,
                        )
                    )
        await _feedback_forum_broadcasts(http, rng, staff, farmers, scans)

    async with state.session_factory() as session:
        for scan_id, _, captured in scans:
            await session.execute(
                text("UPDATE scans SET created_at = :at WHERE id = :id"),
                {"at": captured, "id": scan_id},
            )
        for offset, (user_id, _) in enumerate(farmers):
            joined = now - timedelta(days=4 + offset * 4, hours=offset)
            await session.execute(
                text("UPDATE users SET created_at = :at WHERE id = :id"),
                {"at": joined, "id": user_id},
            )
        await session.commit()


POSTS = (
    ("Daun cabai menguning dari bawah", "Sudah dua minggu daun bawah menguning. Apa kurang pupuk?"),
    ("Bercak hitam di buah menjelang panen", "Buah yang hampir merah ada lekukan hitam basah."),
    ("Jadwal siram saat kemarau", "Kebun saya di Gianyar, sekarang siram tiap hari. Kebanyakan?"),
    ("Jual bibit unggul murah, hubungi WA", "Bibit super panen 3x lipat, transfer dulu ya."),
    ("Pengalaman pakai mulsa jerami", "Hasilnya tanah lebih lembap dan gulma berkurang."),
)


async def _feedback_forum_broadcasts(
    http: AsyncClient,
    rng: random.Random,
    staff: dict[str, dict[str, str]],
    farmers: list[tuple[str, dict[str, str]]],
    scans: list[tuple[str, dict[str, str], datetime]],
) -> None:
    for scan_id, headers, _ in rng.sample(scans, k=min(len(scans), 14)):
        verdict = "incorrect" if rng.random() < 0.6 else "correct"
        note = rng.choice([None, "Menurut saya ini kurang air, bukan penyakit.", "Benar, mirip."])
        await _ok(
            await http.put(
                f"/api/v1/scans/{scan_id}/feedback",
                json={"value": verdict, "comment": note},
                headers=headers,
            )
        )

    posts = []
    for (title, body), (_, headers) in zip(POSTS, farmers, strict=False):
        posts.append(
            await _ok(
                await http.post(
                    "/api/v1/forum/posts",
                    json={"commodity_code": "chili", "title": title, "body": body},
                    headers=headers,
                )
            )
        )
    comment = await _ok(
        await http.post(
            f"/api/v1/forum/posts/{posts[1]['id']}/comments",
            json={"body": "Itu antraknosa, buang saja semua buahnya dan bakar, dasar bodoh."},
            headers=farmers[6][1],
        )
    )
    for _, headers in farmers[7:10]:
        await _ok(
            await http.post(
                "/api/v1/forum/reports",
                json={"target_type": "post", "target_id": posts[3]["id"], "reason": "scam"},
                headers=headers,
            )
        )
    await _ok(
        await http.post(
            "/api/v1/forum/reports",
            json={"target_type": "comment", "target_id": comment["id"], "reason": "abuse"},
            headers=farmers[1][1],
        )
    )
    await _ok(
        await http.post(
            "/api/v1/forum/reports",
            json={
                "target_type": "post",
                "target_id": posts[0]["id"],
                "reason": "wrong_info",
                "note": "Judulnya menyesatkan.",
            },
            headers=farmers[11][1],
        )
    )

    await _ok(
        await http.post(
            "/api/v1/admin/reminders/general",
            json={
                "title": "Musim hujan mulai minggu ini",
                "body": "Periksa saluran air kebun dan kurangi penyiraman bila tanah masih basah.",
            },
            headers=staff["admin"],
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split(chr(10))[0])
    parser.add_argument("--no-demo", action="store_true", help="start with an empty database")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    settings = dev_settings(start_database())
    state = dev_state(settings)

    async def prepare() -> None:
        async with state.session_factory() as session:
            await seed_reference_data(session)
        if not args.no_demo:
            await populate(state)
        await state.engine.dispose()

    asyncio.run(prepare())
    print(f"Tanami API lokal: http://127.0.0.1:{args.port}/docs")
    if not args.no_demo:
        print(f"Akun demo: admin / ahli / moderator, sandi {DEMO_PASSWORD}")
    uvicorn.run(create_app(state=state), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
