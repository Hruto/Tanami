"""Prometheus metrics for the inference service.

Only aggregate, non-personal numbers are exported. Image content, user ids and
model inputs never become labels (TQA section 12).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

PREDICTIONS_TOTAL = Counter(
    "vision_predictions_total",
    "Number of prediction requests handled.",
    labelnames=("scan_type", "status"),
)

PREDICTION_LATENCY = Histogram(
    "vision_prediction_latency_seconds",
    "End-to-end prediction latency.",
    labelnames=("scan_type",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0),
)

INFERENCE_ERRORS = Counter(
    "vision_inference_errors_total",
    "Inference failures by reason.",
    labelnames=("reason",),
)

MODELS_LOADED = Counter(
    "vision_model_loads_total",
    "Model load attempts.",
    labelnames=("scan_type", "result"),
)
