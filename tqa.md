# Tanami - Technical Quality Agreement (TQA)

| | |
|---|---|
| Versi | 0.1 (draft untuk disepakati tim) |
| Tanggal | 23 Oktober 2026 |
| Berlaku untuk | Seluruh anggota tim Tanami (1 PM, 2 Frontend, 2 Backend/ML) |
| Dokumen pendamping | `design.md` (kontrak desain, data, dan API) |

Dokumen ini adalah kesepakatan tim tentang standar kualitas teknis. Semua keputusan teknis yang tidak tertulis di sini mengikuti prinsip: **sederhana, bisa diuji, dan bisa dipahami anggota lain**. Nilai yang bertanda **[USULAN]** adalah titik awal dan boleh diubah lewat prosedur perubahan (bagian 16), selama semua pihak sepakat.

---

## 1. Tujuan dan Ruang Lingkup

**Tujuan:** memastikan frontend, backend, dan ML dibangun dengan standar yang sama sehingga hasilnya konsisten, aman, dan dapat dipercaya petani.

**Ruang lingkup produk (5 fitur):**
1. Deteksi kapan buah siap panen (ML #1)
2. Deteksi kesehatan tanaman dari daun beserta penyebab dan solusi (ML #2)
3. Reminder cuaca dan jadwal siap panen
4. Forum
5. Cek historis pertumbuhan dan status tanaman

**Prioritas rilis MVP:** fitur 2, 1, 5, lalu 3, lalu 4 (forum versi sederhana). Rincian ada di `design.md` bagian 3.

**Di luar ruang lingkup MVP:** banyak komoditas sekaligus, sensor IoT, marketplace saprotan, prediksi harga pasar, peta sebaran penyakit.

---

## 2. Peran dan Tanggung Jawab

| Area | Penanggung jawab utama | Pendukung | Menyetujui |
|---|---|---|---|
| Prioritas fitur, backlog, kriteria penerimaan | Product Manager (PM) | Semua | PM |
| Kemitraan penyuluh/ahli, validasi label | PM | ML Engineer | PM + ML |
| UI/UX, implementasi aplikasi, offline | Frontend 1 dan 2 | PM | PM + Frontend |
| API, database, keamanan, deployment | Backend 1 | Backend 2 | Backend |
| Model ML, dataset, evaluasi, model serving | Backend/ML 2 | Backend 1 | ML |
| Integrasi cuaca (BMKG) dan job reminder | Backend 1 | Backend 2 | Backend |
| Kontrak API (OpenAPI) | Backend 1 | Frontend (reviewer) | Backend + Frontend |
| Kontrak output ML | Backend/ML 2 | Frontend (reviewer) | ML + Frontend |

Aturan: satu area punya **satu pemilik**. Pemilik tidak harus mengerjakan semuanya, tetapi bertanggung jawab atas kualitas dan keputusan akhir di area itu. Pembagian nama Backend 1 dan Backend 2 ditetapkan tim di awal sprint pertama.

---

## 3. Tech Stack yang Disepakati [USULAN]

Stack dipilih untuk tim kecil: sedikit teknologi, bahasa yang sama antara backend dan ML.

| Lapisan | Pilihan | Catatan |
|---|---|---|
| Aplikasi | React Native + Expo, TypeScript (strict) | Satu basis kode untuk Android (prioritas) dan iOS. Alternatif: PWA, jika tim memilih fokus web. |
| State dan data fetching | TanStack Query + Zustand | Cache dan antrean offline. |
| Backend | Python 3.12 + FastAPI | OpenAPI otomatis, satu bahasa dengan ML. |
| Database | PostgreSQL 16 | Kolom JSONB untuk hasil ML dan data fleksibel. |
| Cache dan antrean | Redis | Cache cuaca, rate limit, antrean job. |
| Job terjadwal | APScheduler atau Celery beat | Pengambilan cuaca dan pembuatan reminder. |
| Penyimpanan gambar | Object storage kompatibel S3 (mis. Cloudflare R2/MinIO) | Gambar tidak disimpan di database. |
| Training ML | PyTorch (atau TensorFlow/Keras) | Eksperimen dilacak (MLflow atau Weights & Biases). |
| Serving ML | ONNX Runtime di dalam backend | Model diekspor ke ONNX. TFLite/ONNX Mobile dipertimbangkan setelah MVP untuk mode offline. |
| Arsitektur model | MobileNetV3 atau EfficientNet-Lite | Ringan, cocok untuk perangkat dan server murah. |
| Versi data | DVC (atau skema folder berversi di storage) | Dataset dan model punya versi. |
| Notifikasi | Firebase Cloud Messaging | Push notification. |
| Kontainerisasi | Docker + Docker Compose | Lingkungan lokal sama dengan staging. |
| CI/CD | GitHub Actions | Lihat bagian 11. |
| Monitoring | Sentry + log terstruktur | Lihat bagian 12. |

Perubahan stack setelah sprint 2 memerlukan persetujuan seluruh tim karena biayanya tinggi.

---

## 4. Manajemen Repositori dan Git

**Struktur repo [USULAN]:** tiga repo (atau dua, jika `tanami-ml` digabung ke backend).
- `tanami-app` (frontend)
- `tanami-backend` (API, job, kode serving ML)
- `tanami-ml` (eksperimen, training, evaluasi, data card). Boleh digabung ke `tanami-backend` pada tahap awal jika tim lebih nyaman.

**Alur branch:** GitHub Flow.
- `main` selalu dalam keadaan bisa dirilis dan diproteksi (tidak boleh push langsung).
- Cabang kerja: `feat/<ringkas>`, `fix/<ringkas>`, `chore/<ringkas>`, `docs/<ringkas>`, `ml/<ringkas>`.
- Cabang hidup maksimal **3 hari kerja**. Pekerjaan lebih besar dipecah.

**Commit:** format Conventional Commits.
```
feat(scan): tambah endpoint unggah foto daun
fix(history): perbaiki urutan timeline
docs(design): perbarui skema reminder
```

**Pull Request:**
- Wajib mengisi template PR (apa, kenapa, cara uji, tangkapan layar bila UI).
- Minimal **1 persetujuan**. Perubahan pada kontrak API atau output ML memerlukan persetujuan dari **satu orang di sisi frontend dan satu di sisi backend**.
- Semua pemeriksaan CI harus lulus sebelum merge.
- Ukuran PR ideal di bawah 400 baris perubahan. PR lebih besar dijelaskan alasannya.
- Review dilakukan maksimal **1 hari kerja** setelah PR dibuka.
- Merge dengan **squash**.

---

## 5. Standar Kode

### 5.1 Umum
- Nama variabel, fungsi, file, dan komentar kode memakai **bahasa Inggris**. Teks yang tampil ke pengguna memakai **bahasa Indonesia** dan disimpan di berkas i18n, bukan ditulis langsung di komponen.
- Tidak ada rahasia (API key, password, token) di dalam repo. Gunakan variabel lingkungan. Sediakan `.env.example`.
- Fungsi pendek dan satu tujuan. Hindari duplikasi lebih dari tiga kali.
- Komentar menjelaskan **kenapa**, bukan **apa**.
- TODO ditulis dengan format `TODO(nama): ...` dan harus punya tiket.

### 5.2 Backend (Python)
- Formatter dan linter: `ruff` (lint + format). Type check: `mypy` (mode ketat untuk modul inti).
- Wajib type hints di seluruh fungsi publik.
- Validasi data masuk dan keluar dengan Pydantic. **Tidak ada** dictionary mentah sebagai kontrak API.
- Penamaan: `snake_case` untuk fungsi dan variabel, `PascalCase` untuk kelas.
- Akses database lewat SQLAlchemy dan migrasi dengan Alembic. **Dilarang** mengubah skema langsung di database tanpa migrasi.
- Logika bisnis berada di lapisan `services`, bukan di route handler.

### 5.3 Frontend (TypeScript)
- ESLint + Prettier. TypeScript `strict: true`. **Dilarang** memakai `any` tanpa komentar alasan.
- Penamaan: `camelCase` untuk variabel dan fungsi, `PascalCase` untuk komponen, `kebab-case` untuk nama berkas non-komponen.
- Tipe data API **dibuat otomatis dari OpenAPI** (mis. `openapi-typescript`), tidak ditulis manual.
- Semua warna, ukuran huruf, dan jarak diambil dari **design tokens** (lihat `design.md` bagian 7). Tidak ada nilai warna hex di dalam komponen.
- Setiap layar menangani lima keadaan: memuat (loading), kosong, berhasil, galat, dan offline.
- Teks pengguna lewat fungsi i18n (`t('key')`).

### 5.4 ML (Python)
- Notebook hanya untuk eksplorasi. Kode training dan evaluasi yang dipakai produksi berada di modul Python yang bisa dijalankan ulang.
- Setiap eksperimen mencatat: versi dataset, versi kode (commit), hyperparameter, seed acak, metrik.
- Seed acak ditetapkan agar hasil dapat direproduksi.

---

## 6. Kontrak API dan Integrasi Frontend-Backend

1. **OpenAPI adalah sumber kebenaran tunggal.** Perubahan API dimulai dengan mengubah spesifikasi, bukan kode.
2. Semua endpoint berada di bawah `/api/v1`. Perubahan yang merusak (breaking) memerlukan versi baru (`/api/v2`) atau masa transisi minimal 2 sprint.
3. Format JSON memakai `snake_case`. Waktu memakai **ISO 8601 UTC** (`2026-10-23T06:04:00Z`); frontend mengonversi ke WIB/WITA/WIT untuk tampilan. ID memakai **UUID**.
4. Format respons sukses dan galat, daftar kode galat, dan aturan paginasi ditetapkan di `design.md` bagian 10. Keduanya wajib diikuti.
5. Bidang baru yang bersifat opsional boleh ditambahkan kapan saja (kompatibel ke belakang). Menghapus atau mengganti nama bidang termasuk perubahan merusak.
6. Frontend tidak boleh bergantung pada urutan bidang atau bidang yang tidak terdokumentasi.
7. Backend menyediakan **mock/seed data** dan lingkungan staging yang stabil sejak sprint 1 supaya frontend dapat bekerja paralel.
8. Unggah gambar bersifat idempoten dengan header `Idempotency-Key` (lihat `design.md` bagian 14).

---

## 7. Strategi Pengujian

| Jenis uji | Cakupan | Target [USULAN] | Siapa |
|---|---|---|---|
| Unit test backend | Services, aturan reminder, validasi | Cakupan baris **>= 70%** keseluruhan, **>= 85%** untuk modul aturan reminder dan skor ML | Backend |
| Integration test backend | Endpoint dengan database uji | Semua endpoint punya minimal 1 skenario sukses dan 1 skenario galat | Backend |
| Contract test | Respons API sesuai OpenAPI | Berjalan di CI pada setiap PR | Backend |
| Unit test frontend | Logika, hook, util | Cakupan **>= 60%** untuk logika non-UI | Frontend |
| Component test | Komponen kunci (kartu hasil scan, grafik) | Semua komponen design system | Frontend |
| E2E | Alur utama: daftar, buat kebun, scan, lihat riwayat, terima reminder | 5 alur utama lulus sebelum rilis | Frontend + Backend |
| Uji ML | Lihat bagian 8 | Lihat bagian 8 | ML |
| Uji beban ringan | Endpoint scan | 20 pengguna bersamaan, p95 <= 3 detik | Backend |
| Uji pengguna (UAT) | Dengan petani/penyuluh sungguhan | Minimal 5 petani sebelum rilis beta | PM |

Aturan:
- Bug yang ditemukan di staging atau produksi **harus disertai tes regresi** saat diperbaiki.
- Tes yang rapuh (kadang lulus kadang gagal) diperbaiki atau dinonaktifkan dengan tiket dalam 1 sprint.

---

## 8. Standar Kualitas Machine Learning

Bagian ini paling penting, karena kesalahan model langsung memengaruhi keputusan petani.

### 8.1 Data
- **Sumber data:** foto lapangan dari kebun nyata adalah data utama. Dataset publik hanya untuk pra-latih atau tambahan, dan **lisensinya dicek** sebelum dipakai.
- **Protokol pengambilan foto:** ditulis dan dibagikan ke pengumpul data (sudut, jarak, pencahayaan, variasi latar, minimal beberapa kondisi cuaca).
- **Pelabelan:**
  - Label penyakit dan penyebab **divalidasi oleh ahli** (penyuluh/dosen/dinas pertanian). Sampel tanpa validasi ahli ditandai dan tidak masuk set uji.
  - Sebagian sampel dilabeli dua orang untuk mengukur kesepakatan (Cohen's kappa **>= 0,7** [USULAN]). Sampel yang tidak disepakati ditinjau ulang.
- **Pembagian data (split):**
  - Dibagi **per kebun/per tanaman**, bukan per foto, untuk mencegah kebocoran data (foto dari tanaman yang sama tidak boleh ada di train dan test sekaligus).
  - **Set uji berisi foto lapangan saja** dan tidak pernah dipakai untuk memilih model atau menyetel hyperparameter.
- **Versi data:** setiap dataset dan label punya versi (`dataset-cabai-v0.1`). Perubahan label dicatat.
- **Data card:** tiap dataset punya ringkasan (sumber, jumlah per kelas, tanggal, lokasi, keterbatasan).

### 8.2 Target metrik [USULAN, untuk MVP, diukur pada set uji lapangan]

| Model | Metrik | Target MVP |
|---|---|---|
| Penyakit daun | Macro-F1 | **>= 0,80** |
| Penyakit daun | Recall tiap kelas penyakit | **>= 0,70** (tidak ada kelas yang diabaikan) |
| Penyakit daun | Akurasi sehat vs sakit | **>= 0,90** |
| Kematangan buah | Akurasi (3-4 tahap) | **>= 0,85** |
| Estimasi hari panen | MAE terhadap hari panen aktual | MVP: tampil sebagai **rentang** dan dievaluasi apakah panen aktual jatuh dalam rentang pada **>= 65%** kasus. Target jangka menengah MAE <= 2 hari. |
| Deteksi gambar tidak valid | Recall gambar bukan daun/buah | **>= 0,90** |

Jika target tidak tercapai, fitur tetap boleh dirilis sebagai **beta** dengan label jelas ("hasil perkiraan") hanya dengan persetujuan PM dan ML. Target tidak boleh diturunkan diam-diam. Perubahannya dicatat dan diumumkan ke tim.

### 8.3 Perilaku yang aman
Ambang keyakinan **berlaku sama di backend, frontend, dan dokumen ini** (sumber tunggal ada di `design.md` bagian 11):

| Keyakinan model | Status | Perilaku aplikasi |
|---|---|---|
| >= 0,75 | `confident` | Tampilkan hasil dan rekomendasi. |
| 0,50 sampai < 0,75 | `uncertain` | Tampilkan hasil dengan peringatan "belum yakin", tawarkan foto ulang dan tanya di forum/ahli. |
| < 0,50 | `unknown` | Jangan menyebut satu penyakit; minta foto ulang dan tawarkan bantuan ahli. |
| Gambar tidak valid atau buram | `invalid_image` | Minta foto ulang dengan panduan. |

- Model **tidak boleh** memaksa memilih satu kelas ketika tidak yakin.
- Rekomendasi pengobatan berasal dari **basis pengetahuan yang ditulis dan ditinjau ahli** (tabel `diseases`), bukan dihasilkan bebas oleh model. Setiap rekomendasi memuat sumber/peninjau dan tanggal tinjau.
- Rekomendasi bahan kimia memuat peringatan keselamatan standar (baca label kemasan, alat pelindung diri, jangan melebihi dosis anjuran) dan **tidak memberi angka dosis** sebelum ditinjau ahli. Untuk keluhan berat atau menyebar, aplikasi mengarahkan ke penyuluh.

### 8.4 Pengelolaan model
- **Penamaan versi:** `<jenis>-<komoditas>-v<semver>`, mis. `disease-cabai-v0.1.0`. Versi ini disertakan dalam setiap hasil scan.
- **Model card** untuk tiap model: data latih, metrik per kelas, keterbatasan, kondisi yang tidak didukung.
- **Registri model:** model yang akan dirilis disimpan dengan hash berkas, metrik, dan tanggal.
- **Rilis model:** model baru harus lebih baik atau setara pada set uji tetap, **dan** lolos uji regresi (kumpulan gambar acuan yang hasilnya tidak boleh berubah drastis). Model baru dijalankan dulu di mode bayangan (shadow) pada staging.
- **Rollback:** versi model sebelumnya selalu tersedia dan dapat diaktifkan kembali tanpa rilis aplikasi.
- **Umpan balik:** pengguna dapat menandai hasil "benar" atau "salah" (`design.md` bagian 10). Data ini ditinjau berkala dan, setelah validasi ahli, dipakai untuk melatih ulang.
- **Pemantauan:** pantau distribusi keyakinan, proporsi `uncertain`/`unknown`, dan umpan balik "salah". Jika proporsi `uncertain`+`unknown` naik di atas 40% selama seminggu, ML menyelidiki kemungkinan pergeseran data (data drift).
- **Latensi dan ukuran:** inferensi sisi server p95 <= **2 detik** (di luar unggah). Ukuran model <= **20 MB** per model jika kelak dipasang di perangkat.

### 8.5 Etika dan batasan
- Aplikasi **tidak menggantikan ahli**. Teks bantuan ini muncul di layar hasil.
- Klaim di materi promosi tidak boleh melebihi metrik terukur.

---

## 9. Keamanan dan Privasi

**Autentikasi dan akses**
- Login dengan JWT (access token pendek, refresh token) atau mekanisme setara. Kata sandi di-hash dengan Argon2 atau bcrypt.
- Setiap endpoint memeriksa **kepemilikan data** (pengguna hanya bisa mengakses kebun, tanaman, dan scan miliknya).
- Rate limiting pada login dan unggah (nilai awal di `design.md` bagian 10).
- Validasi unggahan: tipe berkas diperiksa dari isi (bukan hanya ekstensi), ukuran maksimal, dan nama berkas dibuat ulang server.
- HTTPS wajib. CORS dibatasi ke asal yang diizinkan.

**Rahasia dan dependensi**
- Rahasia disimpan di variabel lingkungan atau secret manager, tidak pernah di repo. Jika rahasia bocor ke repo, segera diganti.
- Dependensi dipindai (mis. Dependabot, `pip-audit`, `npm audit`) di CI. Kerentanan tingkat tinggi diperbaiki dalam 1 sprint.

**Privasi data pribadi** (mengacu pada UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi; konfirmasikan kewajiban rinci dengan pihak yang paham hukum)
- Kumpulkan data seminimal mungkin. Lokasi kebun disimpan pada tingkat **desa/kelurahan (kode adm4)** dan, jika perlu, koordinat; koordinat tidak ditampilkan ke pengguna lain.
- Metadata lokasi (EXIF GPS) pada foto **dibuang** sebelum disimpan.
- Pengguna memberi **persetujuan** eksplisit untuk penggunaan foto dalam pelatihan model. Persetujuan bisa ditarik.
- Pengguna dapat menghapus akun dan datanya. Penghapusan dijalankan dalam waktu wajar (mis. 30 hari) kecuali data yang wajib disimpan.
- Konten forum yang dibagikan bersifat publik. Aplikasi memberi tahu hal ini sebelum posting.

**Forum**
- Pelaporan konten, moderasi oleh PM atau moderator ditunjuk, dan penghapusan konten melanggar (spam, penipuan, ujaran kebencian). Aturan dan alur ada di `design.md` bagian 13.

---

## 10. Standar Kinerja, Ketersediaan, dan Aksesibilitas

| Aspek | Target [USULAN] |
|---|---|
| Waktu respons API biasa (tidak termasuk scan) | p95 <= 500 ms |
| Waktu scan (unggah + inferensi + respons), jaringan 4G | p95 <= 5 detik |
| Waktu mulai aplikasi (dingin) pada HP kelas menengah | <= 4 detik |
| Ketersediaan layanan MVP | >= 99% per bulan (di luar jadwal perawatan yang diumumkan) |
| Ukuran unduhan aplikasi | Dijaga serendah mungkin; sasaran awal < 60 MB |
| Dukungan perangkat | Android 8+ (prioritas); layar kecil (360 px) |
| Jaringan buruk | Aplikasi tetap bisa dibuka, menampilkan data tersimpan, dan mengantre unggahan scan (lihat `design.md` bagian 14) |

**Aksesibilitas dan kegunaan untuk petani**
- Area sentuh minimal **48 x 48 dp**. Teks isi minimal **16 sp**.
- Kontras warna minimal WCAG AA. Informasi penting **tidak hanya** dibedakan lewat warna (selalu ada ikon dan teks).
- Bahasa Indonesia sederhana, minim istilah teknis. Istilah teknis diberi penjelasan awam.
- Panduan foto di layar kamera (bingkai, saran jarak dan pencahayaan).

---

## 11. Lingkungan, CI/CD, dan Rilis

**Lingkungan**
| Lingkungan | Tujuan | Data |
|---|---|---|
| `local` | Pengembangan | Data seed/mock |
| `staging` | Uji tim dan UAT | Data uji, bukan data pengguna asli |
| `production` | Pengguna nyata | Data nyata, akses terbatas |

**Pemeriksaan wajib di CI (setiap PR)**
- Backend: `ruff`, `mypy`, tes unit dan integrasi, contract test OpenAPI, pemindaian dependensi.
- Frontend: `eslint`, `tsc --noEmit`, tes unit/komponen, pembangunan (build) berhasil.
- ML: tes unit untuk pra-pemrosesan dan modul serving; evaluasi pada set uji tetap (saat model berubah).
- Pemeriksaan rahasia di repo (secret scanning).

**Deployment**
- Merge ke `main` menerapkan ke **staging** otomatis. Rilis ke **production** dilakukan manual setelah daftar periksa rilis.
- Migrasi database harus **kompatibel ke belakang** untuk satu rilis (agar rollback aman).
- Penomoran versi **SemVer**. Catatan rilis (changelog) dibuat setiap rilis.
- Rollback harus dapat dilakukan dalam <= 30 menit.
- Cadangan (backup) database harian, disimpan minimal 7 hari, dan **pemulihan diuji** minimal sekali sebelum rilis publik.

**Daftar periksa rilis**
- [ ] Semua CI hijau, E2E alur utama lulus
- [ ] Tidak ada bug tingkat Kritis/Tinggi yang terbuka
- [ ] Metrik model memenuhi bagian 8.2 atau ada persetujuan beta tertulis
- [ ] Migrasi diuji pada salinan data staging
- [ ] Catatan rilis dan rencana rollback siap
- [ ] Atribusi sumber data (BMKG, Open-Meteo bila dipakai) tampil di aplikasi

---

## 12. Observabilitas dan Penanganan Insiden

- **Log terstruktur (JSON)** dengan `request_id` yang juga dikembalikan di respons galat. Data pribadi, token, dan isi foto **tidak** dicatat di log.
- **Sentry** (atau setara) untuk galat backend dan aplikasi.
- **Metrik:** jumlah scan per hari, latensi, tingkat galat, distribusi status hasil ML, keberhasilan job cuaca/reminder, jumlah notifikasi terkirim.
- **Pemeriksaan kesehatan:** endpoint `/health` untuk API, database, Redis, dan model.
- **Peringatan:** galat 5xx > 2% selama 10 menit, job cuaca gagal 2 kali berturut-turut, kegagalan pemuatan model.

**Tingkat keparahan bug**

| Tingkat | Definisi | Target respons | Target perbaikan |
|---|---|---|---|
| Kritis | Layanan mati, kebocoran data, hasil berbahaya (mis. rekomendasi menyesatkan) | Segera | <= 1 hari (hotfix) |
| Tinggi | Fitur utama rusak, tanpa jalan pintas | <= 1 hari kerja | <= 3 hari kerja |
| Sedang | Fitur sekunder rusak atau ada jalan pintas | Sprint berjalan | Sprint berjalan/berikutnya |
| Rendah | Kosmetik | Backlog | Dijadwalkan |

Setelah insiden Kritis, tim membuat catatan **post-mortem** tanpa menyalahkan individu (apa yang terjadi, penyebab, perbaikan, pencegahan).

---

## 13. Integrasi Pihak Ketiga dan Lisensi

- **BMKG (Prakiraan Cuaca Terbuka):** wajib mencantumkan BMKG sebagai sumber data di aplikasi. Batas akses 60 permintaan per menit per IP; semua panggilan lewat backend dengan cache (lihat `design.md` bagian 12).
- **Open-Meteo (opsional):** versi gratis hanya untuk penggunaan non-komersial; atribusi wajib. Jika Tanami menjadi layanan berbayar, beralih ke langganan atau self-host.
- **Dataset dan model pra-latih:** catat lisensi di data card. Dilarang memakai data yang lisensinya tidak mengizinkan.
- **Pustaka pihak ketiga:** hanya yang berlisensi kompatibel (MIT/Apache/BSD diutamakan). Tambahan dependensi besar dibahas di PR.
- **Abstraksi cuaca:** semua sumber cuaca diakses lewat satu `WeatherProvider` di backend agar sumber dapat diganti tanpa mengubah fitur lain.

---

## 14. Definition of Ready dan Definition of Done

**Definition of Ready (tiket boleh dikerjakan jika):**
- Ada tujuan dan kriteria penerimaan yang jelas dan dapat diuji.
- Ketergantungan (API, desain, data) sudah diketahui atau tiketnya ada.
- Perubahan kontrak API/ML yang dibutuhkan sudah disepakati di `design.md`/OpenAPI.
- Perkiraan ukuran muat dalam satu sprint.

**Definition of Done (tiket selesai jika):**
- [ ] Kriteria penerimaan terpenuhi dan didemonstrasikan ke PM
- [ ] Kode lolos lint, tipe, dan semua tes CI
- [ ] Tes baru ditambahkan (unit/integrasi, dan regresi untuk bug)
- [ ] PR direview dan disetujui sesuai bagian 4
- [ ] Dokumentasi diperbarui (OpenAPI, `design.md`, README, atau model card)
- [ ] Kelima keadaan UI ditangani (frontend)
- [ ] Teks pengguna dalam bahasa Indonesia dan lewat i18n
- [ ] Tidak ada rahasia atau data pribadi di kode/log
- [ ] Sudah diterapkan ke staging dan diuji di sana

---

## 15. Ritme Kerja Tim

- **Sprint:** 1 atau 2 minggu [USULAN: 2 minggu].
- **Stand-up singkat** (maks. 15 menit) 2-3 kali seminggu atau harian.
- **Sprint review dan retrospektif** di akhir sprint.
- **Sinkronisasi kontrak:** setiap perubahan pada `design.md` bagian 8, 10, dan 11 diumumkan di kanal tim dan ditandai di PR.
- **Pengambilan keputusan:** pemilik area memutuskan, setelah mendengar masukan. Jika tidak ada kesepakatan dalam 2 hari kerja, PM memutuskan, dan keputusan dicatat.
- **Catatan keputusan teknis (ADR):** keputusan arsitektur penting ditulis singkat (konteks, pilihan, keputusan, konsekuensi) di folder `docs/adr`.

---

## 16. Perubahan terhadap Dokumen Ini

- Siapa pun dapat mengusulkan perubahan lewat PR ke berkas ini.
- Perubahan disetujui oleh pemilik area terkait dan PM.
- Setiap perubahan menaikkan nomor versi dan dicatat di riwayat Git.
- Tinjau dokumen ini di akhir setiap bulan atau setelah setiap rilis besar.

---

## 17. Persetujuan

Dengan menandatangani, anggota tim menyatakan telah membaca dan menyepakati dokumen ini.

| Nama | Peran | Tanda tangan / persetujuan | Tanggal |
|---|---|---|---|
| | Product Manager | | |
| | Frontend 1 | | |
| | Frontend 2 | | |
| | Backend / ML Engineer 1 | | |
| | Backend / ML Engineer 2 | | |
