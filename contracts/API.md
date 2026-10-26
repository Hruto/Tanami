# Kontrak API — `tanami-vision`

| | |
|---|---|
| Versi kontrak | 0.1.0 |
| Tanggal | 26 Oktober 2026 |
| Pemilik | Backend/ML 2 (lihat `tqa.md` bagian 2) |
| Pendamping | `design.md` bagian 11 (kontrak output ML) dan bagian 10.1 (format galat) |
| Sumber kebenaran mesin | [`openapi.json`](openapi.json) |

Dokumen ini ringkasan untuk disepakati tim. Bila berbeda dengan `openapi.json`,
yang menang adalah berkas OpenAPI; perbedaan itu harus diperbaiki lewat PR.

---

## 1. Batas tanggung jawab

| Urusan | Pemilik |
|---|---|
| Autentikasi pengguna, kepemilikan data | **Backend** |
| Menyimpan gambar ke object storage | **Backend** |
| Memvalidasi 2 MB / 1280 px sesuai design.md 11.1 | **Backend** (aplikasi) + layanan ini (pagar kedua) |
| Menjalankan model dan memutuskan `status` | **Layanan ini** |
| Mengisi `advice` dan rekomendasi dari tabel `diseases` | **Backend** |
| Menghitung tanggal panen absolut dari rentang hari | **Backend** |
| Menyimpan hasil scan, feedback, notifikasi | **Backend** |

Layanan ini **tidak** menyimpan apa pun. Satu request masuk, satu hasil keluar,
tidak ada efek samping selain metrik dan log.

## 2. Konvensi

Semua konvensi mengikuti `design.md` 10.1:

- basis path `/v1`, JSON `snake_case`, waktu ISO 8601 UTC, ID UUID;
- envelope sukses `{ "data": ... }`;
- envelope galat `{ "error": { "code", "message", "details", "request_id" } }`;
- `message` berbahasa Indonesia dan layak tampil ke pengguna; klien bercabang
  berdasarkan `code`;
- header `X-Request-Id` selalu dikembalikan; nilai dari klien dipakai bila
  formatnya sah (`[A-Za-z0-9._-]{1,128}`).

## 3. Autentikasi

```
Authorization: Bearer <VISION_SERVICE_TOKEN>
```

Hanya backend yang memegang token ini. Bila `VISION_SERVICE_TOKEN` kosong
(hanya boleh di `local`), pemeriksaan dilewati; di `production` layanan
**menolak start** tanpa token.

| Endpoint | Butuh token layanan | Butuh token admin |
|---|---|---|
| `POST /v1/predict` | ya | tidak |
| `GET /v1/models` | tidak | tidak |
| `POST /v1/models/reload` | tidak | ya |
| `/healthz`, `/readyz`, `/livez`, `/metrics` | tidak | tidak |

Endpoint ops sengaja terbuka agar probe Kubernetes/uptime monitor tidak perlu
membawa rahasia. Jangan ekspos layanan ini ke internet publik; taruh di jaringan
internal.

## 4. `POST /v1/predict`

`multipart/form-data`

| Bidang | Wajib | Tipe | Keterangan |
|---|---|---|---|
| `type` | ya | `disease` \| `ripeness` | Jenis scan (design.md 8.2) |
| `image` | ya | file | JPEG/PNG. Batas keras layanan: `VISION_MAX_UPLOAD_BYTES` (default 8 MB) dan sisi ≤ `VISION_MAX_IMAGE_SIDE` |
| `commodity_code` | tidak | string | Default `VISION_COMMODITY_CODE` (`chili`). Nilai di luar `VISION_SUPPORTED_COMMODITIES` → 400 |
| `client_uuid` | tidak | UUID | UUID dari aplikasi; dicatat di log untuk korelasi |
| `Idempotency-Key` (header) | tidak | string | Dipakai sebagai `client_uuid` bila bidang form kosong |

Layanan ini **tidak** melakukan cache idempotensi. Idempotensi scan adalah
tanggung jawab backend (kolom `scans.client_uuid`), karena hanya backend yang
punya database. Nilai ini di sini murni untuk penelusuran log.

### 4.1 Respons `200`

```json
{
  "data": {
    "type": "disease",
    "status": "confident",
    "model_version": "disease-chili-v0.1.0",
    "commodity_code": "chili",
    "confidence": 0.87,
    "quality": { "blur": "ok", "brightness": "ok" },
    "result": {
      "top": {
        "disease_code": "anthracnose",
        "label": "Antraknosa",
        "cause_category": "fungus",
        "confidence": 0.87
      },
      "alternatives": [
        {
          "disease_code": "cercospora_leaf_spot",
          "label": "Bercak Daun Cercospora",
          "cause_category": "fungus",
          "confidence": 0.08
        }
      ],
      "is_healthy": false,
      "severity": null
    },
    "shadow_model_version": null,
    "shadow_status": null,
    "inference_ms": 143.7
  }
}
```

Scan buah (`type=ripeness`):

```json
{
  "data": {
    "type": "ripeness",
    "status": "confident",
    "model_version": "ripeness-chili-v0.1.0",
    "commodity_code": "chili",
    "confidence": 0.81,
    "quality": { "blur": "ok", "brightness": "ok" },
    "result": {
      "stage": "turning",
      "stage_label": "Mengkal",
      "confidence": 0.81,
      "estimated_days_min": 4,
      "estimated_days_max": 7,
      "estimate_confidence": "medium",
      "note": "Perkiraan kasar; dipengaruhi cuaca dan varietas."
    },
    "shadow_model_version": null,
    "shadow_status": null,
    "inference_ms": 96.2
  }
}
```

Aturan yang mengikat hasil (dari design.md 11.2–11.4):

1. `status` diputuskan **layanan ini**, bukan frontend:
   `>= 0.75` confident, `0.50–<0.75` uncertain, `< 0.50` unknown.
2. Kualitas gambar menang atas keyakinan: foto buram/gelap/terlalu terang →
   `status = invalid_image` walaupun model 0,99.
3. `result.top = null` untuk `unknown` dan `invalid_image`. Untuk `unknown`,
   `alternatives` tetap berisi kandidat agar alur "tanya ahli" punya konteks;
   untuk `invalid_image`, `alternatives` kosong karena skornya tidak bermakna.
4. Scan buah **selalu** mengembalikan rentang hari. Tidak ada field berisi satu
   angka tunggal. `overripe` → `0..0`.
5. `advice` **tidak ada** di respons ini. Itu wilayah backend, dari tabel
   `diseases` yang ditinjau ahli (TQA 8.3).
6. `estimated_harvest_date_*` **tidak ada** di sini. Backend menambahkannya
   dari `captured_at`/`created_at` + rentang hari.

### 4.2 Kode galat

| HTTP | `code` | Kapan |
|---|---|---|
| 400 | `validation_error` | `type` tidak dikenal, `commodity_code` tidak didukung, multipart rusak |
| 401 | `unauthorized` | Bearer salah/absen saat token diaktifkan |
| 413 | `payload_too_large` | Body > `VISION_MAX_UPLOAD_BYTES`, atau piksel > `VISION_MAX_IMAGE_PIXELS` |
| 415 | `unsupported_media_type` | Bukan JPEG/PNG (dideteksi dari isi, bukan ekstensi) |
| 422 | `invalid_image` | Bytes tidak bisa didekode, atau sisi < `VISION_MIN_IMAGE_SIDE` |
| 429 | `rate_limited` | Dikeluarkan **backend**; layanan ini tidak melakukan rate limit |
| 500 | `internal_error` | Bug layanan. Traceback hanya ke log |
| 503 | `service_unavailable` | Model belum termuat, atau inferensi lewat `VISION_INFERENCE_TIMEOUT_SECONDS` |

**Penting:** `status = invalid_image` di dalam respons `200` berbeda artinya dari
HTTP `422 invalid_image`. Yang pertama adalah *kesimpulan* atas gambar yang sah
namun tidak layak dianalisis (buram). Yang kedua adalah *kegagalan* membaca
berkas. Frontend menampilkan keduanya sebagai "minta foto ulang", tetapi hanya
yang kedua masuk jalur galat.

## 5. Endpoint operasional

### `GET /healthz`

`200` bila semua model primer termuat, `503` bila ada yang gagal. Bentuknya sama
dengan `GET /v1/models`. Isinya sengaja kaya agar bisa dipakai saat insiden:
versi model, backend, daftar label, dan metrik yang dilaporkan manifest.

### `GET /readyz`

```json
{ "data": { "ready": false, "missing": ["manifest model tidak ditemukan: ..."] } }
```

Dipakai sebagai probe. Bila `missing` tidak kosong, deploy berhenti di sini,
bukan di request pertama pengguna.

### `GET /livez`

Selalu `200` selama proses hidup. Tidak menyentuh model.

### `GET /metrics`

Format Prometheus. Metrik: `vision_predictions_total{scan_type,status}`,
`vision_prediction_latency_seconds{scan_type}`,
`vision_inference_errors_total{reason}`, `vision_model_loads_total{scan_type,result}`.

### `POST /v1/models/reload`

Membaca ulang semua manifest dari `VISION_MODEL_DIR`. Dipakai untuk rilis model
saja atau rollback (TQA 8.4) tanpa mematikan pod.

| Skenario | Hasil |
|---|---|
| `VISION_ADMIN_TOKEN` kosong | `404 not_found` — API dinonaktifkan |
| Bearer salah | `401 unauthorized` |
| Bearer benar | Model dimuat ulang; `200` dengan status terbaru |

Reload bersifat *in-place*: bila model baru gagal dimuat, model lama tetap
melayani. `/healthz` akan melaporkan `degraded` dan `readyz` menyebut penyebabnya.

## 6. Kontrak dengan `tanami-ml` (manifest model)

Layanan ini tidak menebak label dari isi artefak. Setiap model wajib punya
`manifest.json` di `VISION_MODEL_DIR/<model_version>/`:

```json
{
  "model_version": "disease-chili-v0.1.0",
  "scan_type": "disease",
  "commodity_code": "chili",
  "artifact": "model.onnx",
  "labels": ["healthy", "anthracnose", "..."],
  "input_size": 224,
  "input_name": "input",
  "output_name": "logits",
  "normalization": "zero_one",
  "output_activation": "softmax",
  "sha256": "...",
  "metrics": { "macro_f1": 0.83 }
}
```

Divalidasi saat start (gagal = model tidak dipakai):

- `scan_type` cocok dengan slot;
- himpunan `labels` **sama persis** dengan kontrak design.md 11.5;
- `artifact` relatif dan tidak keluar dari folder versi;
- `input_size` > 0, `normalization` ∈ {`zero_one`, `imagenet`},
  `output_activation` ∈ {`softmax`, `none`}.

`sha256` dicatat tetapi belum diverifikasi ulang saat load. Verifikasi checksum
masuk daftar pekerjaan sebelum rilis produksi pertama.

## 7. Ambang dan konfigurasi yang memengaruhi kontrak

Perubahan nilai ini mengubah perilaku yang dilihat pengguna, jadi harus lewat PR
kontrak (TQA bagian 6):

| Variabel | Default | Efek |
|---|---|---|
| `VISION_CONFIDENT_THRESHOLD` | 0.75 | Batas `confident` |
| `VISION_UNCERTAIN_THRESHOLD` | 0.50 | Batas `uncertain`; wajib < confident |
| `VISION_BLUR_MIN_VARIANCE` | 45.0 | Ambang blur (varians Laplacian pada maks 512 px) |
| `VISION_BRIGHTNESS_MIN/MAX` | 0.15 / 0.92 | Ambang pencahayaan (rata-rata luminance 0–1) |
| `VISION_TOP_K` | 3 | Jumlah `alternatives` |
| `VISION_INFERENCE_TIMEOUT_SECONDS` | 2.0 | Batas keras, sesuai TQA 8.4 (p95 ≤ 2 dtk) |
| `VISION_MAX_CONCURRENT_INFERENCE` | 4 | Batas inferensi paralel per proses |

`VISION_INFERENCE_TIMEOUT_SECONDS` membungkus antrean limiter + dekode +
inferensi, sehingga kehabisan slot juga berakhir sebagai 503 `service_unavailable`
alih-alih menggantung. `VISION_MAX_CONCURRENT_INFERENCE` berlaku per proses,
bukan per request: `PredictService` dibuat sekali saat startup agar limiter-nya
benar-benar dipakai bersama.

`inference_ms` mengukur **hanya waktu model** (satu pemanggilan `predict`).
Dekode, resize, dan pemeriksaan kualitas tidak termasuk; itu yang diukur oleh
`vision_prediction_latency_seconds`.

Nilai ambang blur/pencahayaan adalah **[USULAN]** dan harus dikalibrasi pada
dataset lapangan. Saat ini tidak ada model yang memprediksi `severity`, jadi
field itu selalu `null`; backend boleh mengisinya dari basis pengetahuan.

## 8. Kompatibilitas

- Menambah field opsional: kompatibel, boleh kapan saja.
- Mengubah nama/menghapus field, mengubah enum, atau mengubah arti `status`:
  perubahan merusak → versi baru `/v2` atau masa transisi 2 sprint.
- Kontrak ini dijaga otomatis: CI gagal bila `openapi.json` tidak sinkron
  dengan kode, dan setiap respons diuji terhadap dokumen tersebut.
