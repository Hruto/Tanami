# API update — perubahan setelah rapat 17 Nov 2026

Catatan resmi untuk tim frontend dan ML. Dua commit yang mendasari dokumen ini:

- `2a53bea` — varietas bebas, umur pembibitan, placement per tanaman, progress panen, irigasi, kualitas panen
- `22831aa` — create tanaman sekali kirim dengan thumbnail

Kontrak tergenerate: `contracts/openapi.json` (**66 path**). Jangan menyalin contoh dari `docs/design.md` yang lama tanpa mengecek file ini.

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
| Update profil | dua endpoint (`PATCH /users/me` + `POST /users/me/password`) | satu `PATCH /users/me`, password opsional | klien kirim field profil + password sekaligus |

---

## 2. Endpoint

### Dihapus

| Method | Path | Pengganti |
|---|---|---|
| `DELETE` | `/api/v1/farms/{farm_id}` | tidak ada (data tidak dihapus) |
| `DELETE` | `/api/v1/plants/{plant_id}` | `POST /api/v1/plants/{plant_id}/end` |
| `POST` | `/api/v1/users/me/password` | `PATCH /api/v1/users/me` dengan `current_password` + `new_password` |

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
| `PATCH` | `/api/v1/users/me` | menerima `current_password` + `new_password`; respons `data.tokens` saat sandi diganti |

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

Backend mengirim ke model: `commodity_code` (hasil turunan: `mango`/`citrus`/
`strawberry`) + gambar. Layanan vision menentukan `status` (`decide_status()`);
backend hanya menyimpannya di `scans`. Desain ML Memet **draft 2** memakai
output nama penyakit langsung + status `sehat/sakit/tak_terdeteksi/foto_ditolak`;
ini **belum** dipakai runtime. Runtime memakai kode penyakit `design.md` 11.5;
pemetaan dan konfliknya ada di `docs/data-integration.md` §3.3/§3.5.

## 7. Cara memperbarui dokumentasi ini

```bash
cd tanami-backend
./.venv/Scripts/python.exe scripts/export_openapi.py   # regenerate kontrak
./.venv/Scripts/python.exe -m pytest -q               # verifikasi
```

Lalu ubah tabel di atas, bukan menyalin manual isi `openapi.json`.

---

## 8. Kontrak layanan vision (`POST /v1/predict`) — perubahan v2

Catatan perubahan kontrak teks (`contracts/API.md`, `models/README.md`) mengikuti
keputusan tiga komoditas. `contracts/openapi.json` tetap dihasilkan dari kode.

| Area | Sebelum | Sesudah |
|---|---|---|
| Komoditas | default `chili`, daftar tidak divalidasi ketat | tepat `mango`, `citrus`, `strawberry`; default `mango`; selain itu 400 |
| `type` | `disease` \| `ripeness` | hanya `disease`; `ripeness` dihapus total |
| Model | `disease-chili-v0.1.0`, `ripeness-chili-v0.1.0` | `disease-mango-v0.1.0`, `disease-citrus-v0.1.0`, `disease-strawberry-v0.1.0`; shadow opsional `-v0.2.0-rc1` |
| Manifest | 7 label cabai + 4 stage ripeness | 8/5/5 label per komoditas (`design.md` 11.5); `commodity_code` manifest wajib sama dengan yang diminta |
| Contoh payload | `chili`, `anthracnose`, field `stage` | `mango`, `mango_anthracnose`, tanpa `stage`/`estimated_days_*` |
| `status` | sumber kebenaran didokumentasikan sebagai backend (`design.md` 11.2 lama) | **layanan vision** (`decide_status()`); backend hanya menyimpan di `scans`, frontend tidak menghitung ulang |
| Kategori ML | 5 kategori disangka label runtime | 5 kategori = pengelompokan training, dipetakan via `ml_labels`; runtime memakai kode penyakit 11.5 |

Dampak klien: kirim `commodity_code` eksplisit, `type=disease`, dan jangan
menghitung `status` sendiri. Karena enum dan arti `status` berubah, versi kontrak
naik ke `2.0.0` (lihat `contracts/API.md` bagian 8).

---

## 9. Draft 2 ML — belum ada perubahan kontrak klien

`design (4).md` (draft 2, Memet) **menggantikan** desain 5 kategori di
`design.md` 19. Poin penting:

| Draft 1 | Draft 2 |
|---|---|
| 5 kategori `sehat/jamur/bakteri/virus/lainnya` | kategori dibuang; output nama penyakit kanonis |
| ≥150 gambar per kategori, mode ketat/loose | ≥100 gambar per penyakit, ≥4 penyakit per tanaman |
| tanaman mengikuti komoditas app | tanaman dipilih dari jumlah penyakit di dataset (gelombang 1: tomat, padi, jagung, apel) |
| satu ambang keyakinan | tiga lapis tolak: ambang, skor anomali, hard-negative |
| `config.json` opsional | `config.json` wajib per tanaman (kelas, ambang, versi fitur) |

Kontrak output draft 2 (`crop`, `status`, `disease`, `confidence`, `top_k`,
`rejected_reason`) **tidak sama** dengan `POST /v1/predict` sekarang. Belum ada
perubahan pada `contracts/openapi.json` atau klien. Sebelum diimplementasikan,
harus diputuskan apakah backend menerjemahkan draft 2 ke kontrak 11.3 atau
kontrak 11.3 diubah. Lihat `design.md` keputusan terbuka 21 dan
`docs/data-integration.md` §3.5.

---

## 10. Profil disatukan di `PATCH /api/v1/users/me`

`POST /api/v1/users/me/password` **dihapus**. Frontend cukup memanggil
`PATCH /api/v1/users/me` untuk mengubah profil dan/atau kata sandi.

```http
PATCH /api/v1/users/me
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "username": "nama.baru",
  "full_name": "Nama Baru",
  "current_password": "***",
  "new_password": "***"
}
```

Aturan:

- `current_password` dan `new_password` wajib berpasangan; kirim salah satu saja → `400`.
- Tanpa kedua field, tetap `PATCH` biasa (`email`, `username`, `full_name`, `consent_training_data`) dan `data.tokens` bernilai `null`.
- Password baru minimal 8 karakter dan harus berbeda dari lama.
- Username/email bentrok → `409` dan tidak ada perubahan sama sekali, termasuk password.
- Password lama salah → `400`, profil tidak berubah.
- Saat password diganti, semua sesi dicabut dan `data.tokens` berisi token pair baru. **Frontend wajib menyimpan token ini**; header lama tidak lagi valid.


