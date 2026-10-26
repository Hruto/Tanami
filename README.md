# Tanami

Fitur yang diberikan adalah menerima satu foto daun atau buah, mengembalikan
hasil diagnosis atau tahap kematangan **sesuai kontrak `design.md` bagian 11**.

## Kenapa layanan terpisah

Backend Tanami (`tanami-backend`) tetap menjadi satu-satunya pemilik data: user,
kebun, tanaman, scan, reminder, forum. Layanan ini **stateless** dan tidak punya
database. Pemisahan ini masuk akal karena:

| Alasan | Penjelasan |
| --- | --- |
| Siklus rilis berbeda | Model berubah lebih sering daripada API. `POST /v1/models/reload` mengganti model tanpa deploy ulang backend dan tanpa rilis aplikasi (TQA 8.4). |
| Isolasi beban | ONNX Runtime memakai CPU dan RAM besar. Scan meledak saat musim panen; API lain tidak boleh ikut lambat. |
| Isolasi kegagalan | Model gagal dimuat hanya mematikan fitur scan. `/healthz` layanan ini jadi sinyal tunggal untuk 503 `service_unavailable`. |
| Batas keamanan | Hanya layanan ini yang membuka dan mendekode gambar pengguna, sehingga parser file terisolasi. |
| Milik tim ML | Artefak, manifest, dan evaluasi ada di repo yang sama dengan kode yang merilisnya. |

Yang **tidak** dipindah ke sini: penyimpanan gambar (object storage), rekomendasi
pengobatan (tabel `diseases`), estimasi tanggal panen absolut, notifikasi, dan
semua penulisan database. Lihat `docs/architecture.md` untuk diagram alir.

## Menjalankan

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows; source .venv/bin/activate di Linux
pip install -e ".[dev]"
python scripts/make_stub_models.py
copy .env.example .env          # cp di Linux
uvicorn app.asgi:app --reload --port 8001
```

Buka <http://localhost:8001/docs>. Backend `stub` membuat layanan bisa dipakai
end-to-end sebelum model pertama ada. Stub **ditolak** saat
`VISION_APP_ENV=production`.

Dengan backend ONNX:

```bash
export VISION_MODEL_BACKEND=onnx
python scripts/make_fixture_onnx.py --version disease-chili-v0.1.0 --scan-type disease
python scripts/make_fixture_onnx.py --version ripeness-chili-v0.1.0 --scan-type ripeness
```

Dengan Docker:

```bash
python scripts/make_stub_models.py     # model tidak dibundel ke image
docker compose up --build
```

Model **tidak** ikut ke dalam image. Image hanya membuat folder kosong
`/app/models`; isi lewat volume atau `VISION_MODEL_DIR`, supaya rilis model
tidak menuntut build image baru.

Contoh panggilan:

```bash
curl -X POST http://localhost:8001/v1/predict \
  -F "type=disease" \
  -F "image=@daun.jpg;type=image/jpeg" \
  -F "commodity_code=chili"
```

## Perintah

| Perintah | Kegunaan |
| --- | --- |
| `ruff check . && ruff format --check .` | lint + format |
| `mypy` | type check ketat |
| `pytest` | semua tes |
| `pytest -m contract` | validasi kontrak OpenAPI |
| `pytest --cov=app --cov-report=term-missing` | cakupan |
| `python scripts/export_openapi.py --write` | regenerasi `contracts/openapi.json` |
| `python scripts/export_openapi.py --check` | dipakai CI: gagal bila kontrak basi |

## Konfigurasi

Semua lewat variabel lingkungan berprefix `VISION_`; daftar lengkap ada di
[`.env.example`](.env.example). Yang penting:

- `VISION_MODEL_BACKEND` — `stub` atau `onnx`.
- `VISION_SERVICE_TOKEN` — bearer token yang wajib dikirim backend di `/v1/*`.
  Wajib di production.
- `VISION_CONFIDENT_THRESHOLD` / `VISION_UNCERTAIN_THRESHOLD` — ambang status
  design.md 11.2. Urutannya divalidasi saat start.
- `VISION_SHADOW_*_MODEL_VERSION` — model bayangan untuk staging (TQA 8.4).

## Kontrak

- [`contracts/API.md`](contracts/API.md) — ringkasan yang bisa dibaca manusia.
- [`contracts/openapi.json`](contracts/openapi.json) — sumber kebenaran mesin.
  Dibuat dari kode, dijaga sinkron oleh CI.
- [`docs/architecture.md`](docs/architecture.md) — alasan pemisahan layanan dan
  batas tanggung jawab dengan backend.

## Yang belum ada

- Penyimpanan hasil atau gambar (memang di luar tanggung jawab).
- Kalibrasi ambang kualitas gambar; nilai awal hanya titik mulai.
- Model ONNX sungguhan. `models/README.md` menjelaskan format manifest yang
  harus dihasilkan pipeline training.
