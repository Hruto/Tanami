# Panduan menyusun & memperbarui dokumentasi Tanami

Ini "cara kerja"nya, supaya dokumentasi tidak berantakan saat ada rapat baru.
Pakai urutan ini setiap kali ada perubahan desain/API.

## 1. Kumpulkan fakta dulu, baru menulis

Dokumentasi Tanami boleh membuat **keputusan**, tapi tidak boleh mengarang
**fakta kode**. Sumber fakta, urut prioritas:

1. Kode yang jalan (`app/`, `tanami-backend/app/`) + test
2. `contracts/openapi.json` (dihasilkan dari kode, bukan ditulis manual)
3. Hasil perintah (`pytest`, `grep`, `git log`)
4. Catatan rapat / desain ML yang dikirim tim
5. Ingatan — **tidak boleh** jadi sumber satu-satunya

Contoh kebiasaan buruk yang harus dihindari: menulis "endpoint archive ada"
padahal sudah dihapus di commit `2a53bea`; atau mengira lima kategori ML v2
adalah label runtime. Runtime memakai 8/5/5 kode penyakit per komoditas
(`design.md` 11.5); kategori itu hanya pengelompokan training yang dipetakan
lewat `ml_labels` (`docs/data-integration.md`).

Perintah yang biasa dipakai:

```bash
# Daftar endpoint yang benar-benar terdaftar
cd tanami-backend
./.venv/Scripts/python.exe scripts/export_openapi.py
./.venv/Scripts/python.exe -c "import json;d=json.load(open('contracts/openapi.json'));print(len(d['paths']))"

# Cek struktur class
grep -rhn "^class " app/models/*.py app/services/*.py app/providers/*.py | sort -u

# Lihat apa yang berubah
git log --oneline -6
git diff --stat HEAD~1
```

## 2. Struktur dokumen yang dipakai

| File | Isi | Kapan diubah |
|---|---|---|
| `docs/design.md` | Desain keseluruhan: software + ML + keputusan arsitektur | Ada keputusan desain baru |
| `docs/api-changelog.md` | Daftar perubahan API, payload, dampak ke klien | Setiap endpoint/field berubah |
| `docs/class-diagram.md` | Struktur OOP: class, relasi, provider | Ada class/relasi baru |
| `docs/data-integration.md` | Pemetaan DB aplikasi ↔ artefak & label ML | Ada perubahan skema/model |
| `docs/ml-router-architecture.md` | Arsitektur **percobaan** Jalur 2: router species → classifier per komoditas → tolak (bukan final) | Ada keputusan arsitektur ML/Cek cepat |
| `docs/post_meeting_changes.md` | Catatan rapat 17 Nov (lampiran, bukan kontrak) | Jarang; diarsipkan saja |
| `docs/architecture.md` | Diagram alur & infra | Infra berubah |
| `contracts/openapi.json` | Kontrak mesin | **Generate**, jangan edit manual |

## 3. Cara menulis satu dokumen

### 3.1 Awali dengan status + sumber

```markdown
# Judul

Status: draft / final
Pemilik: <nama>
Berdasarkan: <commit / rapat / file>

## 1. Ringkasan
## 2. Keputusan
## 3. Detail
...
## N. Cara memperbarui
```

Tulis angka yang bisa diverifikasi (jumlah path, jumlah test, nama commit).
Kalau sesuatu belum diputuskan, tulis **"belum diputuskan"** — jangan
disamarkan sebagai fakta.

### 3.2 Tabel untuk perbandingan, diagram untuk relasi

- Tabel → cocok untuk "sebelum vs sesudah", mapping label, daftar endpoint.
- Mermaid `classDiagram` → struktur OOP.
- Mermaid `flowchart` → alur data / integrasi.
- Hindari paragraf panjang untuk daftar field; pakai tabel atau blok kode.

### 3.3 Pisahkan fakta dan proposal

Tandai dengan jelas:

- ✅ = sudah ada di kode
- 🆕 = usulan, belum diimplementasikan
- ⚠️ = konflik / butuh keputusan tim

Ini penting supaya tim frontend tidak mengira tabel usulan sudah bisa dipanggil.

## 4. Cara menggabungkan desain ML ke `design.md`

File yang dikirim Memet (`design (3).md`) adalah desain **bagian ML**.
Jangan menghapus desain software lama; tambahkan sebagai bagian baru:

1. Baca dulu daftar heading `design.md` (`grep -n "^#" docs/design.md`).
2. Letakkan desain ML **setelah** bagian domain/API, sebelum lampiran.
3. Beri nomor bagian baru yang jelas, misalnya `## 14. Deteksi penyakit — desain ML v2`.
4. Sesuaikan istilah supaya tidak bentrok:
   - "tanaman" di ML → `commodity_code` di backend
   - "kategori" di ML → `disease_code` / `backend_category`
   - "kurang yakin" → status di response, bukan kelas kelima yang dilatih
5. Tambahkan satu paragraf **Hubungan dengan backend** yang menunjuk ke
   `docs/data-integration.md`.
6. Simpan isi asli sebagai lampiran kalau ada kalimat yang belum disepakati
   (misalnya mode ketat vs longgar).

## 5. Cara membuat class diagram (tanpa mengarang)

1. `grep` semua `class` dari modul yang relevan.
2. Kelompokkan per lapisan: ORM model, service, provider/protocol, error, schema.
3. Gambar hanya relasi yang bisa dibuktikan: `ForeignKey`/`relationship` di model,
   `Protocol` + implementasi di provider, pemakaian service ke provider.
4. Tambahkan catatan versi teks di bawah diagram untuk viewer markdown yang tidak
   merender Mermaid.
5. Jalankan `pytest` — kalau class di diagram tapi test gagal, berarti diagram
   atau kode yang salah.

## 6. Checklist sebelum commit

- [ ] Angka di dokumen sesuai hasil perintah terakhir (path/test/commit)
- [ ] Tidak ada nama endpoint/field yang sudah dihapus
- [ ] Tidak ada referensi cabai/ripeness di dokumentasi aktif (kecuali catatan sejarah/migrasi)
- [ ] Kontrak `openapi.json` diregenerasi kalau API berubah
- [ ] `pytest`, `ruff`, `mypy` hijau kalau kode ikut berubah
- [ ] File yang diubah disebut di pesan commit

Contoh pesan commit yang baik:

```text
docs: satukan desain ML v2, class diagram, dan integrasi DB

- design.md: tambah bagian deteksi penyakit v2
- api-changelog.md: catat perubahan pasca-rapat + with-photo
- class-diagram.md: diagram ORM/service/vision
- data-integration.md: usulan tabel ml_* dan pemetaan label
```

## 7. Ritme pembaruan

- **Setiap rapat:** tambah keputusan ke `design.md`, dampak API ke `api-changelog.md`.
- **Setiap perubahan kode:** regenerate OpenAPI + update diagram kalau class berubah.
- **Setiap model ML baru:** daftarkan di `ml_models`, jangan langsung `active`.
- **Sebulan sekali:** baca ulang `docs/` dan hapus catatan yang sudah kedaluwarsa.
