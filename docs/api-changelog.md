# API update — perubahan setelah rapat 17 Nov 2026

Catatan resmi untuk tim frontend dan ML. Dua commit yang mendasari dokumen ini:

- `2a53bea` — varietas bebas, umur pembibitan, placement per tanaman, progress panen, irigasi, kualitas panen
- `22831aa` — create tanaman sekali kirim dengan thumbnail

Kontrak tergenerate: `contracts/openapi.json` (**67 path**). Jangan menyalin contoh dari `docs/design.md` yang lama tanpa mengecek file ini.

---

## 1. Ringkasan perubahan

| Area | Sebelum | Sesudah | Authoritative |
|---|---|---|---|
| Jenis tanaman | `commodity_code: "mango"` | `variety: "Mangga Arumanis"` (teks bebas) | klien kirim varietas, komoditas diturunkan backend |
| Dasar umur | `planted_at` | `nursery_started_at` (estimasi mulai pembibitan) | klien kirim tanggal, umur & persen dihitung backend |
| Lokasi tanaman | `placement` di Farm | `placement` di Plant | klien kirim per tanaman |
| Archive | `DELETE /plants/{id}`, `DELETE /farms/{id}` | dihapus; `POST /plants/{id}/end` | klien pakai end-tracking |
| Thumbnail | dua panggilan | satu panggilan multipart | `photo` dikirim bareng create |
| Hasil panen | `quality_note` string | `quality` (4 kategori) + `success_pct` | backend hitung persen & kategori |
| Irigasi | jadwal statis | bisa diubah + riwayat + saran cuaca | klien kirim `schedule` |
| Perkembangan | tidak ada ringkasan | `GET /plants/{id}/progress` | backend hitung dari profil + episode |

---

## 2. Endpoint

### Dihapus

| Method | Path | Pengganti |
|---|---|---|
| `DELETE` | `/api/v1/farms/{farm_id}` | tidak ada (data tidak dihapus) |
| `DELETE` | `/api/v1/plants/{plant_id}` | `POST /api/v1/plants/{plant_id}/end` |

### Ditambah

| Method | Path | Fungsi |
|---|---|---|
| `POST` | `/api/v1/farms/{farm_id}/plants/with-photo` | create + upload thumbnail dalam satu kiriman |
| `PATCH` | `/api/v1/plants/{plant_id}/irrigation` | ubah jadwal siraman |
| `GET` | `/api/v1/plants/{plant_id}/irrigation/history` | riwayat perubahan jadwal, terbaru dulu |
| `GET` | `/api/v1/plants/{plant_id}/irrigation-advice` | saran sistem (`weather_used: false` untuk indoor) |
| `GET` | `/api/v1/plants/{plant_id}/progress` | umur, fase, persen menuju panen, delay penyakit |

### Diubah

| Method | Path | Perubahan |
|---|---|---|
| `POST` | `/api/v1/farms` | `placement` tidak diterima lagi |
| `PATCH` | `/api/v1/farms/{id}` | `placement` tidak diterima lagi |
| `POST` | `/api/v1/farms/{id}/plants` | field baru; `commodity_code` ditolak |
| `PATCH` | `/api/v1/plants/{id}` | menerima `variety`, `nursery_started_at`, `placement` |
| `POST` | `/api/v1/plants/{id}/harvests` | `quality` + `quantity_kg` + `note`; `quality_note` ditolak |
| `PATCH` | `/api/v1/plants/{id}/harvests/{harvest_id}` | sama seperti di atas |

---

## 3. Payload create (JSON, tanpa foto)

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

## 4. Payload create + thumbnail (form Tambah Tanaman)

```http
POST /api/v1/farms/{farm_id}/plants/with-photo
Content-Type: multipart/form-data

label=Pohon Mangga
variety=Mangga Arumanis
nursery_started_at=2026-11-01
placement=indoor
irrigation_schedule=every_3_5_days
photo=@daun.jpg
```

Semua field selain `photo` wajib diisi kecuali `planted_at`, `quantity`,
`planting_material` (punya default). `photo` boleh kosong. Foto yang dikirim
langsung menjadi `cover_photo_url`. Gambar divalidasi **sebelum** create:
foto rusak ditolak `422 invalid_image` dan tidak membuat tanaman.

Contoh Flutter:

```dart
final uri = Uri.parse('$baseUrl/farms/$farmId/plants/with-photo');
final req = http.MultipartRequest('POST', uri)
  ..headers.addAll(authHeaders)
  ..fields['label'] = label
  ..fields['variety'] = variety
  ..fields['nursery_started_at'] = nurseryDate.toIso8601String().substring(0, 10)
  ..fields['placement'] = placement
  ..files.add(await http.MultipartFile.fromPath('photo', photoPath));
final res = await req.send();
```

## 5. Aturan yang wajib dipatuhi klien

1. `variety` bebas, tapi harus menyebut `mangga`, `jeruk`, atau `stroberi`. Selain itu `400`.
   Backend menyimpan komoditas hasil turunan; klien tidak perlu mengirim `commodity_code`.
2. `nursery_started_at` tidak boleh di masa depan. `planted_at` tidak boleh lebih awal dari
   tanggal pembibitan; kalau kosong, disamakan backend.
3. `age_days` dihitung dari `nursery_started_at`, bukan `planted_at`.
4. `placement: indoor` → backend tidak memanggil BMKG; `weather_used: false` pada saran irigasi.
5. `success_pct = quantity_kg ÷ target_komoditas × 100`. Kategori `quality` diturunkan dari persen:
   `<20` → `gagal`, `20–<70` → `kurang_optimal`, `70–100` → `normal`, `>100` → `panen_raya`.
   Kalau klien mengirim `quality` yang bertentangan dengan `quantity_kg` → `400`.
   Kalau `quantity_kg` kosong, persen tidak dihitung dan kategori mengikuti input klien.
6. `growth_stage` dan persentase kematangan tidak ada di kontrak. Fase keluar sebagai
   `lifecycle_phase` (dihitung) dan `percent_to_first_harvest` (endpoint progress).
7. `POST /plants/{id}/end` menerima `reason`: `productive_period_over`, `disease`, `cut_down`,
   `died_other`, `other`.

## 6. Dampak ke tim ML

Backend mengirim ke model: `commodity_code` (hasil turunan) + Gambar. Model mengembalikan
`status`/`cause_category` + `confidence`. Desain ML v2 Memet memakai 5 kategori
(`sehat`, `jamur`, `bakteri`, `virus`, `lainnya`) yang **belum** sama dengan kode penyakit
backend. Pemetaan dan rencana penyatuan ada di `docs/data-integration.md`.

## 7. Cara memperbarui dokumentasi ini

```bash
cd tanami-backend
./.venv/Scripts/python.exe scripts/export_openapi.py   # regenerate kontrak
./.venv/Scripts/python.exe -m pytest -q               # verifikasi
```

Lalu ubah tabel di atas, bukan menyalin manual isi `openapi.json`.
