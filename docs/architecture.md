# Arsitektur layanan inferensi

## Keputusan: satu layanan inferensi terpisah dari backend

**Konteks.** `design.md` 16 menaruh `ml/` di dalam `tanami-backend`, dengan
ONNX Runtime dipanggil langsung dari proses FastAPI. Itu pilihan yang sah untuk
MVP satu server. Masalahnya muncul saat:

- model perlu diganti tanpa deploy backend (TQA 8.4 mewajibkan rollback model
  tanpa rilis aplikasi),
- lonjakan scan musim panen menghabiskan CPU seluruh API,
- satu gambar rusak bisa menjatuhkan proses yang juga melayani login dan forum,
- tim ML perlu merilis artefak tanpa menyentuh kode backend.

**Keputusan.** Memisahkan layanan **stateless tanpa database** yang hanya
melakukan satu hal: gambar masuk, hasil ML keluar. Backend tetap pemilik semua
data.

**Konsekuensi.**

- Satu lompatan jaringan ekstra (~1–3 ms di jaringan internal, dapat diabaikan
  di samping inferensi puluhan hingga ratusan ms).
- Backend harus menangani `503` dan mencoba ulang, bukan lagi sekadar memanggil
  fungsi Python.
- Perlu dua pipeline CI dan dua deployable, tetapi keduanya kecil.
- Versi model bisa berbeda antara backend lama dan layanan baru; karena itu
  `model_version` dikembalikan di setiap hasil.

**Alternatif yang ditolak.**

| Alternatif | Alasan ditolak |
|---|---|
| Tetap di dalam backend | Gagal memenuhi syarat rollback model tanpa deploy dan isolasi beban |
| Satu layanan per model | Dua model, dua deployable, dua titik gagal; tidak sepadan untuk tim 5 orang |
| Server inferensi generik (TorchServe/Triton) | Fitur berlebih, kontrak keluar tidak bisa dikunci ke design.md 11, biaya operasional lebih tinggi |
| Model di perangkat | Ditunda pasca-MVP (design.md 14); butuh TFLite dan pembaruan model lewat store |

## Alur satu scan

```
Aplikasi                 Backend                        tanami-vision
   |                        |                                 |
   |-- POST /scans -------->|                                 |
   |   (multipart)          |-- validasi ukuran/tipe ---------|
   |                        |-- simpan gambar ke storage -----|
   |                        |-- INSERT scans (pending) -------|
   |                        |-- POST /v1/predict ------------>|
   |                        |      Bearer service token       | decode
   |                        |                                 | quality gate
   |                        |                                 | inferensi ONNX
   |                        |                                 | status + result
   |                        |<---- 200 data.{status,result} --|
   |                        |-- gabung advice dari diseases --|
   |                        |-- INSERT result, UPDATE plant --|
   |                        |-- (opsional) push reminder -----|
   |<-- 201 hasil scan -----|                                 |
```

Yang penting dari diagram itu: **tidak ada** tanda panah dari layanan ini ke
database, storage, atau FCM. Itu bukan kekurangan, melainkan batas yang membuat
layanan mudah diuji, di-scale, dan di-rollback.

## Pembagian tanggung jawab

| Hal | Backend | tanami-vision |
|---|---|---|
| Validasi 2 MB / 1280 px | ya (otoritatif) | ya (pagar kedua) |
| Deteksi gambar bukan daun/buah | tidak | ya, lewat ambang kualitas + model |
| Ambang `status` | tidak | ya, sumber tunggal |
| Rekomendasi pengobatan | ya (`diseases`) | tidak pernah |
| Tanggal panen absolut | ya | tidak (hanya rentang hari) |
| Idempotensi scan | ya (`client_uuid` + DB) | tidak (stateless) |
| Rate limit | ya | tidak |
| Menyimpan `model_version` | ya (di `scans`) | mengembalikannya |

## Mode stub

`VISION_MODEL_BACKEND=stub` menghasilkan prediksi deterministik dari hash piksel.
Tujuannya agar frontend, backend, dan CI bisa berjalan end-to-end sebelum model
pertama dilatih. Stub tidak membaca file apa pun dan **ditolak** saat
`VISION_APP_ENV=production`, sehingga tidak mungkin tanpa sengaja menjadi
"model" di produksi.

## Model bayangan (shadow)

Bila `VISION_SHADOW_*_MODEL_VERSION` diisi, setiap request juga dinilai model
bayangan. Hasilnya **tidak** memengaruhi respons utama; yang dikembalikan hanya
`shadow_model_version` dan `shadow_status`. Kegagalan model bayangan ditelan dan
dicatat sebagai `inference_error{reason="shadow_error"}`.

Ini memenuhi TQA 8.4 (model baru dijalankan mode bayangan di staging) tanpa
membutuhkan database terpisah untuk membandingkan. Backend dapat menyimpan kedua
status bila ingin analisis lebih lanjut.

Keterbatasan: inferensi bayangan berjalan *inline*, jadi menambah waktu respons.
Untuk staging itu dapat diterima; untuk produksi, pindahkan ke antrean.

## Jalur peningkatan berikutnya

| Kapan | Perubahan |
|---|---|
| Model pertama siap | Isi `models/`, set `VISION_MODEL_BACKEND=onnx`, verifikasi `sha256` |
| Trafik naik | Scale horizontal; layanan tidak punya state, cukup tambah replika |
| Butuh GPU | Tambah provider `CUDAExecutionProvider`; kontrak HTTP tidak berubah |
| Shadow di produksi | Pindahkan ke job antrean (Redis) dan tulis perbandingan ke DB backend |
| Model di perangkat | Ekspor TFLite dari kode latih yang sama; kontrak `result` tetap |
