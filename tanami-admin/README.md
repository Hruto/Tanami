# tanami-admin

> **Status:** dokumen ini menjelaskan kode yang berjalan sekarang, yang masih mengikuti `docs/design.md` **v0.3** (cabai, daftar deteksi terpisah, scan kematangan). Targetnya `docs/design.md` **v2** (mangga, jeruk, stroberi); daftar perubahan yang tertunda ada di lampiran "Dampak ke Implementasi".

Ruang kerja tim Tanami: web untuk **ahli**, **moderator**, dan **admin**. Akun petani ditolak saat masuk.

| Layar | Peran | Untuk apa |
|---|---|---|
| Ringkasan | ahli, moderator, admin | Antrean hari ini, grafik scan 14 hari, pengguna, hasil panen, deteksi 30 hari |
| Laporan forum | moderator, admin | Abaikan laporan, sembunyikan, atau hapus konten |
| Tinjauan deteksi | ahli, admin | Beri label benar untuk hasil yang ditandai salah oleh petani |
| Basis penyakit | ahli, admin | Sunting gejala, penyebab, pencegahan, dan penanganan |
| Pengguna | admin | Cari akun, ubah peran, kirim pesan ke satu pengguna |
| Pengumuman | admin | Kirim notifikasi ke semua akun atau satu pengguna, lihat berapa yang membaca |

Kontrak API: `docs/design.md` bagian 10.10 dan 10.11, `tanami-backend/contracts/openapi.json`.

## Menjalankan secara lokal

Butuh Node 20+ dan Python 3.12 (untuk backend).

```bash
# 1. Backend dengan data demo (Postgres tertanam, tanpa Docker)
cd tanami-backend
.venv/Scripts/python scripts/dev_server.py      # Windows
# .venv/bin/python scripts/dev_server.py        # macOS/Linux

# 2. Dashboard, di terminal lain
cd tanami-admin
npm install
npm run dev                                       # http://localhost:5173
```

Akun demo (sandi `tanami-demo-123`): `admin`, `ahli`, `moderator`. Akun petani seperti `slamet_1` dipakai untuk mencoba penolakan.

Vite meneruskan `/api` dan `/media` ke `http://127.0.0.1:8000`. Ganti tujuan dengan `TANAMI_API_PROXY` di `.env.local`.

## Build produksi

```bash
npm run build        # typecheck + bundle ke dist/
```

- Sajikan `dist/` dari domain yang sama dengan API, atau isi `VITE_API_BASE_URL` (misalnya `https://api.tanami.id`) dan tambahkan origin dashboard ke `TANAMI_CORS_ORIGINS` di backend.
- Server statis harus mengarahkan semua path yang tidak dikenal ke `index.html` (aplikasi memakai routing di browser).
- Refresh token disimpan di `sessionStorage`, jadi sesi berakhir saat tab ditutup. Itu disengaja untuk komputer kantor yang dipakai bersama.

## Struktur

```
src/
  api/          klien fetch (amplop {data}, refresh token otomatis) dan tipe dari OpenAPI
  auth/         konteks login; menolak akun petani
  components/   kerangka navigasi, grafik batang, dialog, drawer, toast, ikon
  lib/          label Bahasa Indonesia, format tanggal (Asia/Jakarta), hak akses per peran
  pages/        satu file per layar
  styles/       token warna dan tipografi, lalu gaya per bagian
```

## Desain

Krem dan hijau seperti buku catatan lapangan: kertas `#f1ecdd`, tinta hijau pinus `#1f3d2e`, aksi `#3d6b47`. Judul memakai Literata, antarmuka memakai Figtree. Daftar ditampilkan sebagai tabel bergaris, bukan kartu. Satu-satunya elemen yang menonjol adalah grafik scan harian yang digambar sebagai batang tanaman. Warna kuning tua hanya untuk "menunggu", merah bata hanya untuk tindakan yang menghapus.

Hak akses di layar hanya menentukan menu yang tampil. Pemeriksaan sebenarnya tetap dilakukan backend pada setiap permintaan.
