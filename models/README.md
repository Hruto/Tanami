# Model directory

Each version lives in its own folder and is discovered only through its
`manifest.json`:

```
models/
  disease-chili-v0.1.0/
    manifest.json
    model.onnx
  ripeness-chili-v0.1.0/
    manifest.json
    model.onnx
```

`manifest.json` is written by the `tanami-ml` export step and is the only
description of a model the service trusts:

| field               | type     | notes                                                        |
| ------------------- | -------- | ------------------------------------------------------------ |
| `model_version`     | str      | must equal the folder name (TQA 8.4 naming: `<jenis>-<komoditas>-v<semver>`) |
| `scan_type`         | str      | `disease` or `ripeness`                                      |
| `commodity_code`    | str      | `chili` for the MVP                                          |
| `artifact`          | str      | relative filename of the `.onnx` file                        |
| `labels`            | string[] | output order; must match the contract label set exactly      |
| `input_size`        | int      | square side length the model expects                         |
| `input_name`        | str      | ONNX input tensor name                                       |
| `output_name`       | str      | ONNX output tensor name (one score vector)                   |
| `normalization`     | str      | `zero_one` (default) or `imagenet`                           |
| `output_activation` | str      | `softmax` (default) or `none`                                |
| `sha256`            | str      | artifact checksum, recorded for the audit trail              |
| `metrics`           | object   | whatever the evaluation wrote; surfaced by `/healthz`        |

Example (a trained model):

```json
{
  "model_version": "disease-chili-v0.1.0",
  "scan_type": "disease",
  "commodity_code": "chili",
  "artifact": "model.onnx",
  "labels": [
    "healthy",
    "anthracnose",
    "cercospora_leaf_spot",
    "bacterial_wilt",
    "leaf_curl_virus",
    "pest_damage",
    "nutrient_deficiency"
  ],
  "input_size": 224,
  "input_name": "input",
  "output_name": "logits",
  "normalization": "zero_one",
  "output_activation": "softmax",
  "sha256": "<sha256 of model.onnx>",
  "metrics": { "macro_f1": 0.83, "eval_set": "field-2026-10" }
}
```

The `stub` backend reads the same manifests, so the whole pipeline can be
exercised before the first model exists (see `scripts/make_stub_models.py`).
Stub mode is refused when `VISION_APP_ENV=production`.
