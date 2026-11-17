# Perubahan API pasca-rapat (2026-11-17)

Semua perubahan ini sudah diterapkan di `feat/backend-design-v2`, diverifikasi
dengan 295 test, `ruff`, dan `mypy`. Kontrak terbit di `contracts/openapi.json`.

## Ringkasan

| Sebelum | Sesudah |
|---|---|
| `commodity_code` dikirim klien | `variety` (teks bebas, mis. `Mangga Arumanis`); komoditas diturunkan backend |
| `planted_at` jadi dasar umur | `nursery_started_at` (estimasi mulai pembibitan) jadi dasar umur; `planted_at` opsional |
| `placement` di kebun | `placement` di tiap tanaman (`indoor`/`outdoor`) |
| `DELETE /plants/{id}`, `DELETE /farms/{id}` (archive) | dihapus; pakai `POST /plants/{id}/end` |
| `quality_note` string | `quality` = `gagal` / `kurang_optimal` / `normal` / `panen_raya` |
| tidak ada persen panen | `success_pct` dihitung backend |
| jadwal irigasi statis | `PATCH /plants/{id}/irrigation` + riwayat + saran cuaca |
| tidak ada ringkasan perjalanan | `GET /plants/{id}/progress` |

## Endpoint baru

| Method | Path | Fungsi |
|---|---|---|
| `PATCH` | `/api/v1/plants/{id}/irrigation` | `{ "schedule": "daily", "reason": "cuaca panas" }` |
| `GET` | `/api/v1/plants/{id}/irrigation/history` | riwayat perubahan jadwal (terbaru dulu) |
| `GET` | `/api/v1/plants/{id}/irrigation-advice` | saran sistem; `weather_used: false` untuk indoor |
| `GET` | `/api/v1/plants/{id}/progress` | umur, fase, `%` menuju panen pertama, estimasi tanggal, delay penyakit |

## Create tanaman (form Tambah Tanaman)

```http
POST /api/v1/farms/{farm_id}/plants
Content-Type: application/json

{
  "label": "Pohon Mangga",
  "variety": "Mangga Arumanis",
  "nursery_started_at": "2026-11-01",
  "placement": "indoor",
  "irrigation_schedule": "every_3_5_days"
}
```

Respons memuat `age_days` (dihitung dari `nursery_started_at`), `commodity_label`,
`placement`, dan `cover_photo_url`.

Foto sampul diunggah segera setelah create (dua panggilan, satu layar):

```http
POST /api/v1/plants/{id}/photos
Content-Type: multipart/form-data

image=@daun.jpg
caption=Foto awal
```

Foto pertama otomatis menjadi sampul (`cover_photo_url`). Endpoint foto
pertumbuhan tetap tersedia untuk foto berikutnya. Pilihan "ambil foto / galeri"
ada di sisi aplikasi; backend menerima file JPG/PNG sampai 2 MB.

## Aturan yang perlu diketahui frontend

- `variety` bebas, tetapi harus menyebut `mangga`, `jeruk`, atau `stroberi`;
  selain itu ditolak 400.
- `placement: indoor` → backend **tidak** memanggil BMKG; saran irigasi statis.
- `success_pct = quantity_kg / target_panen_komiditas × 100`; kategori
  `quality` diturunkan dari persen itu. Jika keduanya dikirim dan tidak cocok,
  respons 400.
- Kisaran kategori: `<20` gagal, `20–<70` kurang optimal, `70–100` normal,
  `>100` panen raya.
- `POST /plants/{id}/end` tetap dipakai untuk mengakhiri tracking; alasan
  yang diterima: `productive_period_over`, `disease`, `cut_down`, `died_other`,
  `other`.
- `growth_stage` dan `ripeness_pct` tidak ada lagi di kontrak.

## Migrasi

`migrations/versions/0006_post_meeting.py` — menambah
`plants.nursery_started_at`, `plants.placement`, tabel `irrigation_changes`,
serta `harvest_records.quality` dan `harvest_records.success_pct`. Kolom lama
`farms.placement` dan `farms.archived_at` sengaja dibiarkan agar downgrade aman.
