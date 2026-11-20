# Model directory

> **Status:** dokumen ini mengikuti `docs/design.md` **v2** — tepat tiga komoditas
> (`mango`, `citrus`, `tomato`), hanya `type=disease`.

> Folder aktif: `disease-mango-v0.1.0/`, `disease-citrus-v0.1.0/`, dan
> `disease-tomato-v0.1.0/`. Shadow opsional memakai versi `-v0.2.0-rc1`
> per komoditas.

Tiap versi hidup di folder sendiri dan ditemukan hanya lewat `manifest.json`:

```
models/
  disease-mango-v0.1.0/
    manifest.json
    model.onnx
  disease-citrus-v0.1.0/
    manifest.json
    model.onnx
  disease-tomato-v0.1.0/
    manifest.json
    model.onnx
```

`manifest.json` ditulis oleh langkah ekspor `tanami-ml` dan merupakan satu-satunya
deskripsi model yang dipercaya layanan:

| field               | type     | notes                                                        |
| ------------------- | -------- | ------------------------------------------------------------ |
| `model_version`     | str      | harus sama dengan nama folder (TQA 8.4: `<jenis>-<komoditas>-v<semver>`) |
| `scan_type`         | str      | hanya `disease`                                              |
| `commodity_code`    | str      | `mango` / `citrus` / `tomato`; wajib sama dengan yang diminta |
| `artifact`          | str      | nama berkas `.onnx` relatif terhadap folder versi             |
| `labels`            | string[] | urutan output; harus sama persis dengan 11.5 untuk komoditas itu |
| `input_size`        | int      | sisi kotak yang diharapkan model                             |
| `input_name`        | str      | nama tensor input ONNX                                       |
| `output_name`       | str      | nama tensor output ONNX (satu vektor skor)                   |
| `normalization`     | str      | `zero_one` (default) atau `imagenet`                          |
| `output_activation` | str      | `softmax` (default) atau `none`                              |
| `sha256`            | str      | checksum artefak untuk jejak audit                           |
| `metrics`           | object   | hasil evaluasi; ditampilkan `/healthz`                        |

Contoh (model mango, 8 label sesuai `design.md` 11.5):

```json
{
  "model_version": "disease-mango-v0.1.0",
  "scan_type": "disease",
  "commodity_code": "mango",
  "artifact": "model.onnx",
  "labels": [
    "healthy",
    "mango_anthracnose",
    "mango_bacterial_canker",
    "mango_die_back",
    "mango_powdery_mildew",
    "mango_sooty_mould",
    "mango_gall_midge",
    "mango_cutting_weevil"
  ],
  "input_size": 224,
  "input_name": "input",
  "output_name": "logits",
  "normalization": "zero_one",
  "output_activation": "softmax",
  "sha256": "<sha256 of model.onnx>",
  "metrics": { "macro_f1": 0.83, "eval_set": "field-2026-11" }
}
```

Lima kategori ML v2 (`sehat`, `jamur`, `bakteri`, `virus`, `lainnya`) adalah
pengelompokan **training**, bukan label runtime; pemetaannya ada di `ml_labels`
(`docs/data-integration.md`). Label runtime memakai kode penyakit berprefiks
komoditas di `design.md` 11.5.

Backend `stub` membaca manifest yang sama, sehingga seluruh alur bisa dijalankan
sebelum model sungguhan tersedia (`scripts/make_stub_models.py`). Mode stub
ditolak saat `VISION_APP_ENV=production`.
