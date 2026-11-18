# Class diagram Tanami

Dokumen ini menjelaskan **struktur kode berorientasi objek**, bukan alur data (DFD).
Sumbernya adalah kode yang benar-benar ada di repo — bukan tebakan. Kalau ada class
baru, update diagram ini di commit yang sama.

Ringkasan hasil audit kode: **215 class di 79 file**, dengan rincian 94 turunan
`ApiModel`, 19 `Base` (SQLAlchemy), 30 `StrEnum`, 10 `AppError`, 3 `Protocol`,
dan 15 file `@dataclass`.

## 1. Lapisan yang ada

```
HTTP / Flutter / Admin
        │
        ▼
API router (app/api/v1/*.py) ──► Pydantic schema (app/schemas/*.py)
        │
        ▼
Service (app/services/*.py) ──► Provider (app/providers/*.py)
        │
        ▼
ORM model (app/models/*.py) ──► PostgreSQL
```

Class diagram berikut dipecah supaya tetap terbaca. Mermaid sudah didukung GitHub
dan kebanyakan viewer markdown; kalau tidak render, lihat versi teks di bawah tiap diagram.

## 2. Inti domain (ORM)

```mermaid
classDiagram
    class Base {
        <<SQLAlchemy DeclarativeBase>>
        +metadata
    }
    class User {
        +id: UUID
        +email: str
        +password_hash: str
    }
    class Farm {
        +id: UUID
        +user_id: UUID
        +name: str
        +legacy_placement: str
    }
    class Plant {
        +id: UUID
        +farm_id: UUID
        +user_id: UUID
        +label: str
        +variety: str
        +commodity_code: str
        +nursery_started_at: date
        +planted_at: date
        +placement: str
        +irrigation_schedule: str
        +productive_until: date
        +ended_at: date
    }
    class HarvestRecord {
        +id: UUID
        +plant_id: UUID
        +harvested_at: date
        +quantity_kg: Decimal
        +quality: HarvestQuality
        +success_pct: Decimal
        +note: str
    }
    class DiseaseEpisode {
        +id: UUID
        +plant_id: UUID
        +disease_code: str
        +started_at: date
        +ended_at: date
    }
    class Scan {
        +id: UUID
        +plant_id: UUID
        +status: str
        +model_version: str
    }
    class PlantPhoto {
        +id: UUID
        +plant_id: UUID
        +key: str
        +is_cover: bool
    }
    class CareLog {
        +id: UUID
        +plant_id: UUID
        +action: str
    }
    class IrrigationChange {
        +id: UUID
        +plant_id: UUID
        +schedule: str
        +reason: str
        +changed_at: datetime
    }
    class CropProfile {
        +commodity_code: str
        +first_harvest_min_days: int
        +first_harvest_max_days: int
        +harvest_cycle_days: int
        +productive_years: int
        +source: str
    }
    class Disease {
        +code: str
        +label: str
        +harvest_delay_days: int
    }
    Base <|-- User
    Base <|-- Farm
    Base <|-- Plant
    Base <|-- HarvestRecord
    Base <|-- DiseaseEpisode
    Base <|-- Scan
    Base <|-- PlantPhoto
    Base <|-- CareLog
    Base <|-- IrrigationChange
    Base <|-- CropProfile
    Base <|-- Disease
    User "1" --> "*" Farm : owns
    Farm "1" --> "*" Plant : contains
    Plant "1" --> "*" HarvestRecord : produces
    Plant "1" --> "*" DiseaseEpisode : suffers
    Plant "1" --> "*" Scan : inspected
    Plant "1" --> "*" PlantPhoto : documented
    Plant "1" --> "*" CareLog : treated
    Plant "1" --> "*" IrrigationChange : re-scheduled
    Plant "*" --> "1" CropProfile : estimated by
    DiseaseEpisode "*" --> "1" Disease : typed as
```

Versi teks: `User` punya banyak `Farm`, `Farm` punya banyak `Plant`; satu
`Plant` punya banyak `HarvestRecord`, `DiseaseEpisode`, `Scan`, `PlantPhoto`,
`CareLog`, `IrrigationChange`; `Plant` merujuk `CropProfile`; `DiseaseEpisode`
merujuk `Disease`. Semua turunan `Base`.

## 3. Service dan provider (backend)

```mermaid
classDiagram
    class ApiModel {
        <<Pydantic BaseModel>>
        +model_config
    }
    class AppError {
        <<Exception>>
        +status_code: int
        +code: str
    }
    class ValidationError
    class NotFound
    class Conflict
    class InvalidImage
    class ServiceUnavailable
    AppError <|-- ValidationError
    AppError <|-- NotFound
    AppError <|-- Conflict
    AppError <|-- InvalidImage
    AppError <|-- ServiceUnavailable

    class FarmService {
        +create_farm()
        +update_farm()
    }
    class PlantService {
        +create()
        +update()
        +end_plant()
        +add_harvest()
        +update_irrigation()
        +progress()
        +irrigation_advice()
        +_apply_harvest_result()
    }
    class ScanService {
        +scan()
        +feedback()
    }
    class EpisodeService {
        +open()
        +close()
    }
    class TrackingService {
        +timeline()
    }
    class Estimator {
        +percent_to_first_harvest()
        +phase()
        +delay_from_episodes()
    }
    class ReminderService {
        +sweep()
    }
    class AuthService {
        +login()
        +refresh()
    }
    class VisionProvider {
        <<Protocol>>
        +predict(commodity_code, image)
    }
    class VisionClient {
        +predict() POST /v1/predict
        +ready() GET /readyz
        +timeout: 6s, retries: 2
    }
    class StorageProvider {
        <<Protocol>>
        +put(key, data, content_type)
        +public_url(key)
    }
    class MemoryStorage
    class S3Storage
    class WeatherProvider {
        <<Protocol>>
        +fetch(adm4_code)
    }
    class BmkgWeatherProvider
    class PushProvider {
        <<Protocol>>
        +send(token, data)
    }
    class LogPushProvider
    class FcmV1PushProvider
    StorageProvider <|.. MemoryStorage
    StorageProvider <|.. S3Storage
    WeatherProvider <|.. BmkgWeatherProvider
    PushProvider <|.. LogPushProvider
    PushProvider <|.. FcmV1PushProvider
    VisionProvider <|.. VisionClient
    PlantService --> Estimator : uses
    PlantService --> StorageProvider : stored photo
    ScanService --> VisionProvider : predicts
    ReminderService --> PushProvider : notifies
    PlantService --> WeatherProvider : outdoor advice
```

Versi teks: `AppError` adalah induk semua error (`ValidationError`, `NotFound`,
`Conflict`, `InvalidImage`, `ServiceUnavailable`, dan lain-lain). Service memakai
`Protocol` sebagai kontrak provider: `VisionClient` implementasi `VisionProvider`,
`S3Storage`/`MemoryStorage` implementasi `StorageProvider`, `BmkgWeatherProvider`
implementasi `WeatherProvider`, `FcmV1PushProvider`/`LogPushProvider`
implementasi `PushProvider`. `PlantService` memakai `Estimator`, `ScanService`
memakai `VisionProvider`.

## 4. Service tanami-vision (ML)

```mermaid
classDiagram
    class ModelManifest {
        <<dataclass>>
        +model_version: str
        +scan_type: str
        +commodity_code: str
        +labels: list[str]
        +input_size: int
    }
    class Predictor {
        <<Protocol>>
        +predict(image)
    }
    class StubPredictor
    class OnnxPredictor
    class ModelRegistry {
        +get(scan_type, commodity_code, version)
        +loaded: LoadedModel
    }
    class LoadedModel {
        +manifest: ModelManifest
        +predictor: Predictor
    }
    class PreparedImage {
        <<dataclass>>
        +pixels
        +original_size
    }
    class QualityReport {
        <<dataclass>>
        +blur: float
        +is_acceptable: bool
    }
    class PredictCommand {
        <<dataclass>>
        +image: bytes
        +scan_type: str
        +commodity_code: str
    }
    class PredictService {
        +execute(command) PredictionResponse
    }
    class ApiModel {
        <<Pydantic BaseModel>>
    }
    class PredictionResponse
    class HealthResponse
    class ReadyResponse
    Predictor <|.. StubPredictor
    Predictor <|.. OnnxPredictor
    ModelRegistry "1" --> "*" LoadedModel : caches
    LoadedModel --> ModelManifest : described by
    LoadedModel --> Predictor : runs
    PredictService --> ModelRegistry : resolves
    PredictService --> PreparedImage : preprocesses
    PredictService --> QualityReport : checks
    PredictService --> PredictionResponse : returns
    ApiModel <|-- PredictionResponse
    ApiModel <|-- HealthResponse
    ApiModel <|-- ReadyResponse
```

**Detail layanan vision (dari kode, bukan dugaan):**

- `POST /v1/predict` — multipart `type` (hanya `disease`), `image`,
  `commodity_code` (`mango`/`citrus`/`strawberry`, default `mango`), `client_uuid`;
  header `Idempotency-Key` dan `Authorization: Bearer ...`. Respons envelope
  `{ "data": … }` atau `{ "error": … }`.
- `GET /healthz`, `/readyz`, `/livez`, `/metrics`, `GET /v1/models`,
  `POST /v1/models/reload` (admin). Listen di port **8001**.
- `ModelRegistry` menyimpan model **primary + shadow per komoditas**
  (`LoadedModel.is_shadow`); model shadow dijalankan tapi tidak memengaruhi
  respons. `is_ready` bila ketiga komoditas punya primary.
- `known_labels(scan_type, commodity_code)` mengembalikan label komoditas;
  `load_manifest(...)` memvalidasi label **dan** `commodity_code` manifest.
- `decide_status()` di `app/services/decision.py` menentukan
  `confident | uncertain | unknown | invalid_image` dengan ambang
  `confident = 0,75`, `uncertain = 0,50`, dan kualitas gambar menang atas
  confidence. `build_disease_result()` menyusun `result`. Sesuai `design.md`
  11.2: **layanan vision** yang menentukan status; backend hanya menyimpan
  nilainya di `scans`, frontend tidak menghitung ulang.
- `assess_quality()` (varians Laplacian + luminance) dan `decode_and_prepare()`
  membuang EXIF lalu resize ke `input_size` manifest.

Manifest yang **aktif** adalah `disease-mango-v0.1.0`,
`disease-citrus-v0.1.0`, dan `disease-strawberry-v0.1.0` (shadow opsional
`-v0.2.0-rc1`), dengan label per komoditas sesuai `design.md` 11.5 (mango 8,
citrus 5, strawberry 5). `StubPredictor` deterministik dan ditolak di
production; produksi memakai `OnnxPredictor`. Lima kategori ML v2 adalah
pengelompokan training, dipetakan via `ml_labels`. Lihat
`docs/data-integration.md`.

## 5. Kenapa ini OOP, bukan DFD

- **Encapsulation:** state tanaman (umur, placement, jadwal siram) melekat di
  objek `Plant`, bukan variabel global.
- **Inheritance:** `AppError` → 10 turunan dengan status HTTP masing-masing;
  `Base` → semua tabel.
- **Polymorphism:** service menerima `Protocol`, jadi bisa memakai
  `MemoryStorage` saat test dan `S3Storage` saat produksi tanpa mengubah service.
- **Validasi menempel pada data:** `ApiModel` menolak payload salah sebelum
  masuk service.
- **Testability:** provider bisa di-stub, sehingga test tidak butuh BMKG/S3/real ML.
- DFD adalah **alat dokumentasi aliran data**, bukan gaya kode. Diagram alur
  (mermaid `flowchart`) di `design.md` itu DFD-like, tapi kodenya tetap OOP.

## 6. Cara menjaga diagram tetap sinkron

1. Ambil daftar class dari kode, jangan dari ingatan:

   ```bash
   # backend
   cd tanami-backend
   grep -rhn "^class " app/models/*.py app/services/*.py app/providers/*.py \
     app/core/errors.py app/schemas/*.py | sort -u
   # vision
   cd .. && grep -rhn "^class \|^@dataclass" app/inference/*.py \
     app/services/*.py app/schemas/*.py | sort -u
   ```

2. Edit hanya diagram yang berubah, lalu sebutkan di pesan commit yang sama.
3. Kalau class baru hanya turunan `ApiModel`/`Base`, cukup tambahkan ke daftar
   ringkasan; tidak perlu menggambar kotak baru.
