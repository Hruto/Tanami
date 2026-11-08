# Audit dan Penyempurnaan Backend Tanami

| | |
|---|---|
| Tanggal | 7 November 2026 |
| Cakupan | `tanami-backend/` dibandingkan dengan `design.md` dan `tqa.md` |
| Hasil akhir | ruff bersih, mypy strict bersih, 163 tes lulus (unit, integrasi PostgreSQL 16, kontrak), coverage 87% |

## 1. Ringkasan

Struktur backend sudah rapi dan mengikuti design (route tipis, logika di `services/`, amplop respons, kode galat, Argon2, refresh token di Redis, validasi gambar + hapus EXIF). Namun backend **belum pernah dijalankan end-to-end**: tidak ada satu pun tes, dan dua bug kritis membuat hampir semua request ke database gagal. Selain itu ada aturan bisnis yang menyimpang dari design, beberapa celah keamanan, dan fitur design yang belum ada (moderasi, ganti sandi, purge akun, job yang dijanjikan di komentar kode).

## 2. Bug kritis (memblokir, sudah diperbaiki)

| # | Masalah | Dampak | Perbaikan |
|---|---|---|---|
| K1 | Semua kolom `Mapped[datetime]` dibuat sebagai `timestamp without time zone`, padahal kode menulis datetime ber-timezone. | asyncpg menolak (`can't subtract offset-naive and offset-aware datetimes`): **setiap scan, arsip lahan, panen, reminder, hapus akun gagal 500.** Terbukti dengan uji terhadap skema `0001`. | `Base.type_annotation_map` -> `timestamptz`; migrasi `0002_timestamptz`. |
| K2 | Relasi ORM `ForumReport.reporter` dan `ScanFeedback.user` ambigu (dua FK ke `users`). | Mapper SQLAlchemy gagal dikonfigurasi saat query pertama: **semua endpoint yang menyentuh DB error.** | `foreign_keys=` eksplisit di kedua sisi relasi. |
| K3 | `tests/__init__.py` berisi docstring tanpa tanda kutip. | `pytest` tidak bisa jalan sama sekali. | Diperbaiki. |
| K4 | Push memakai FCM legacy `/fcm/send` (server key). | API itu sudah dimatikan Google (2024): **notifikasi push tidak akan pernah terkirim.** | Provider baru FCM HTTP v1 (service account, token OAuth di-cache, token perangkat tidak valid dihapus). |

## 3. Penyimpangan dari design (sudah diperbaiki)

| Bagian design | Sebelumnya | Sekarang |
|---|---|---|
| 8.2 status tanaman | Scan sehat pertama setelah sakit langsung `healthy` (scan saat ini terhitung dua kali), `recovering` tidak pernah muncul; "penyakit ringan" diabaikan; foto lama dari antrean offline menimpa status terbaru; hapus scan tidak menghitung ulang; tidak ada aturan 14 hari -> `unknown`. | Mesin status murni `next_health_status`, di-*replay* berurutan waktu foto setiap kali scan tanaman berubah; `severity = mild` -> `at_risk`; job harian `decay_health`. Grafik `/stats` memakai mesin yang sama. |
| 10.6 idempoten | Kirim ulang mengembalikan 201. | 201 untuk scan baru, **200** untuk duplikat. |
| 11.3 `advice` | Teks hardcode di `domain.py`, bukan dari tabel `diseases`; kode penyakit baru dari model melanggar FK -> 500. | Dibangun dari baris `diseases` yang ditinjau (ringkasan, pertolongan pertama, peninjau, tanggal tinjau - TQA 8.3). Kode tak dikenal disimpan tanpa tautan dan tanpa saran. |
| 12.3 hujan lebat | Membandingkan **kecepatan angin** dengan ambang mm hujan; memeriksa seluruh 3 hari; hanya dievaluasi bila panen <= 2 hari (jendela 3 hari tidak pernah tercapai). | Kata BMKG ("Hujan Lebat", "Hujan Petir") atau total curah hujan harian `tp` >= 50 mm, hanya di jendela sebelum panen. Field `tp` ditambahkan ke data cuaca. |
| 12.3 risiko jamur | "Cerah Berawan" dihitung sebagai berawan tebal; syarat basah boleh di luar periode lembap; riwayat jamur 14 hari (design: 30). | Hanya hujan/berawan tebal/mendung **di dalam** periode lembap >= 48 jam; riwayat 30 hari (`TANAMI_FUNGAL_HISTORY_DAYS`). |
| 12.3 siap panen | Estimasi yang sudah lewat memicu reminder setiap hari selamanya. | Berhenti setelah jendela panen lewat atau tanaman `finished`. |
| 12.4 pengiriman | Dedupe dan batas harian memakai tanggal **UTC** (job pagi & sore di hari WIB yang sama membuat duplikat); jam tenang pengguna diabaikan; push normal saat jam tenang **dibuang**, bukan ditunda. | Tanggal lokal (`TANAMI_TIMEZONE`); jam tenang per pengguna; kolom `push_state` + job per jam `dispatch_pushes` mengirim yang tertunda; batas 3 push/hari lokal. |
| 12.1 BMKG | Job terjadwal membaca cache (tidak mengambil data baru); tanpa jeda (bisa melewati 60 req/menit); gagal menulis arsip menggagalkan seluruh respons cuaca. | `WeatherService.refresh` paksa ambil BMKG; jeda `TANAMI_BMKG_MIN_INTERVAL_SECONDS`; arsip gagal hanya dicatat di log. |
| 13 forum | `scan_summary` selalu `null`; posting tersembunyi tetap bisa dibuka publik; komentar tersembunyi tidak mengurangi `comment_count`. | Ringkasan scan (foto + hasil singkat, tanpa data tanaman); visibilitas `hidden` hanya penulis & moderator; penghitung konsisten. |
| TQA 9 hapus akun | Komentar kode menjanjikan "sweep job" yang tidak ada. | Job `purge_accounts` menghapus foto dan baris setelah 30 hari. |
| Panen cabai | Panen pertama menandai tanaman `finished`. | `harvesting`; hanya `is_final: true` yang menandai `finished`. |

## 4. Keamanan dan ketahanan (sudah diperbaiki)

| Masalah | Perbaikan |
|---|---|
| Posting forum menerima `image_keys` apa saja: pengguna bisa mempublikasikan foto milik orang lain, termasuk **foto scan pribadi**. | Kunci wajib berawalan `forum/<user_id>/` dan benar-benar ada di storage. |
| `X-Forwarded-For` selalu dipercaya: batas login 5/menit bisa dilewati dengan mengganti header. | Hanya dipercaya bila `TANAMI_TRUST_FORWARDED_FOR=true` (di balik proxy). |
| `scan_id`, `target_id`, `device_id` bertipe string: nilai bukan UUID menghasilkan 500. | Bertipe `UUID` -> 400 `validation_error`. |
| PATCH dengan `null` pada kolom wajib (nama lahan, label tanaman) atau email/HP yang sudah dipakai -> 500. | Divalidasi -> 400 / 409. |
| Login: akun tidak ada dijawab lebih cepat dari sandi salah (enumerasi akun lewat waktu respons). | Verifikasi hash tiruan agar waktunya setara. |
| "Logout semua perangkat" memindai seluruh keyspace Redis (`SCAN`). | Indeks sesi per pengguna. |
| `request_id` tidak pernah muncul di log (TQA 12). | Processor structlog menambahkan `request_id` dan `user_id`. |
| Urutan middleware: respons 413/429 tanpa `X-Request-ID`; rate limiter global memakai klien Redis yang dibuat saat start. | Request-id paling luar (setelah CORS); limiter dibaca dari state setiap request. |
| Klien HTTP (vision, BMKG, FCM) tidak ditutup saat shutdown. | `AppState.close()` dipanggil di lifespan. |
| Paginasi timeline bisa melewatkan entri yang waktunya sama. | Urutan dan kursor memakai kunci `(waktu, id)` yang sama. |
| Pencarian forum: `%`/`_` dari pengguna menjadi wildcard. | Di-escape. |

## 5. Fitur yang ditambahkan

* `POST /users/me/password` (layanan sudah ada, rutenya belum).
* Moderasi forum (design 13): antrean laporan, resolve `dismiss/hide/remove`, ubah status posting/komentar, hapus komentar.
* Admin: ubah peran (verifikasi ahli, angkat moderator), broadcast reminder `general`. Admin pertama dari `TANAMI_BOOTSTRAP_ADMINS`.
* Review umpan balik model oleh ahli (TQA 8.4) beserta status persetujuan data latih pengguna.
* `GET /scans/{id}` kini memuat `feedback` dan `commodity_code`.
* `/readyz` memeriksa layanan vision (soft check); rute `/media/*` lokal untuk storage memori.
* Job: `dispatch_pushes`, `decay_health`, `purge_accounts`; semua job dibungkus agar galat dicatat dan tidak mematikan scheduler.
* `scripts/export_openapi.py` + `contracts/openapi.json` untuk generator tipe frontend.
* CI `.github/workflows/backend-ci.yml` (PostgreSQL 16 service, ruff, mypy, tes, coverage >= 80%, cek kontrak, pip-audit).

## 6. Pengujian

| Jenis | Isi | Jumlah |
|---|---|---|
| Unit | status tanaman, aturan reminder & pengiriman, gambar/EXIF, token, kursor, parser BMKG, FCM v1, klien vision | 60 |
| Integrasi (PostgreSQL 16 asli + migrasi Alembic) | auth, lahan/tanaman/panen/riwayat, scan, cuaca/beranda/reminder/job, forum/moderasi/admin/review, probe, **nol drift migrasi** | 54 |
| Kontrak | 47 endpoint design bagian 10 ada; semua respons 2xx memakai amplop; `openapi.json` mutakhir | 49 |

Coverage baris+cabang 87% (`services/reminder.py` 92%). Rantai migrasi `upgrade head -> downgrade base -> upgrade head` sudah diuji.

## 7. Belum dikerjakan / rekomendasi berikutnya

1. **Dockerfile + docker-compose backend** (Postgres, Redis, MinIO, vision). Belum ditulis karena Docker tidak tersedia di mesin audit sehingga tidak bisa diverifikasi.
2. **Data wilayah lengkap**: `regions_seed.py` hanya contoh kecil. Muat daftar kode desa Kemendagri penuh sebelum UAT; `/regions/resolve` memakai jarak derajat sederhana.
3. **Open-Meteo** sebagai cadangan cuaca (design 12.1) belum ada; saat ini cadangan = cache terakhir + arsip.
4. **Sentry** (TQA 3, 12) belum dipasang.
5. Komentar forum belum dipaginasi (aman untuk MVP, perlu bila diskusi panjang).
6. Isi basis pengetahuan penyakit masih bertanda peninjau internal; perlu tinjauan ahli mitra (design 17 #3, #8).
7. Kredensial FCM service account dan bucket S3 produksi perlu disiapkan tim (design 17 #5).

## 8. Penyesuaian dengan dokumen requirement (8 November 2026)

Setelah audit, backend disesuaikan dengan *Requirements Aplikasi Deteksi dan Tracking Tanaman* (R0-R7); `design.md` dan `tqa.md` dinaikkan ke v0.2. Ringkasan:

| Requirement | Yang ditambahkan / diubah |
|---|---|
| R0 Kebun | `placement` indoor/outdoor; nama kelurahan di respons; reminder cuaca hanya untuk kebun outdoor |
| R1 Tracking | Katalog jenis tanaman (`GET /plant-types`), `irrigation_schedule`, umur otomatis (`age_days`), foto perkembangan, catatan perawatan (siram = riwayat penyiraman), jadwal siram berikutnya, `POST /plants/{id}/end` dengan alasan dan hasil akhir (4 kategori, atau dari persentase) |
| R2 History Tracking | `GET /plants?status=ended`, detail dengan lokasi dan alasan, timeline berisi foto, perawatan, deteksi terhubung, panen, dan pengakhiran; tanaman yang diakhiri hanya-baca |
| R3-R4 Deteksi | Tabel `detection_plants` terpisah dari tanaman tracking; scan dengan `detection_plant_id`; hasil memuat nama penyakit, `confidence_percent`, gejala, saran penanganan lengkap; akhiri dan aktifkan kembali tanpa kehilangan riwayat; opsional terhubung ke tanaman tracking |
| R5 Forum | Suka (`forum_reactions`, `like_count`, `liked_by_me`); penulis tampil dengan username |
| R6 Profil | Email + username + nama lengkap (login dengan salah satu); nomor HP dihapus; periode pengingat foto dan pemantauan |
| R7 Pengingat | Job `care_reminders`: siram (jadwal irigasi), foto (periode pengguna), pemantauan (tanpa aktivitas); pengingat tanaman yang diakhiri ditutup dan tidak dibuat lagi |

Migrasi `0004_requirements_v1` (rename tanpa kehilangan data, backfill username, reversibel). Tes: 188 lulus, coverage 88%.
