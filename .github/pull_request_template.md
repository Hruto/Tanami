## Apa yang berubah

<!-- Satu paragraf. Sebutkan fitur/berkas yang berubah dan alasannya. -->

## Kenapa

<!-- Masalah yang diselesaikan. Tautkan tiket. -->

## Cara menguji

```bash
ruff check . && ruff format --check . && mypy && pytest
```

<!-- Tambahkan langkah manual bila ada, mis. curl ke /v1/predict. -->

## Dampak kontrak

- [ ] Tidak mengubah kontrak (`contracts/openapi.json` tidak berubah)
- [ ] Mengubah kontrak — `python scripts/export_openapi.py --write` sudah dijalankan
- [ ] Mengubah `result` / `status` — perlu persetujuan satu frontend dan satu backend (TQA bagian 6)
- [ ] Mengubah ambang keyakinan / kualitas gambar — jelaskan dampaknya ke pengguna

## Daftar periksa

- [ ] Tes baru ditambahkan (regresi untuk perbaikan bug)
- [ ] `models/README.md` diperbarui bila format manifest berubah
- [ ] Tidak ada rahasia, token, atau gambar pengguna di kode/log/tes
- [ ] Dokumentasi diperbarui (`README.md`, `contracts/API.md`, `docs/architecture.md`)
