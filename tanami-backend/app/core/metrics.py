"""Prometheus metrics.

Only aggregate counters and histograms. User id, request id, image content and
anything else personal never become a label (TQA 12).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

SCANS_TOTAL = Counter(
    "backend_scans_total",
    "Scan requests by type and resulting status.",
    labelnames=("scan_type", "status"),
)

SCAN_LATENCY = Histogram(
    "backend_scan_duration_seconds",
    "End-to-end scan handling time, including the vision call.",
    labelnames=("scan_type",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0),
)

VISION_ERRORS = Counter(
    "backend_vision_errors_total",
    "Vision calls that failed, by reason.",
    labelnames=("reason",),
)

JOB_RUNS = Counter(
    "backend_job_runs_total",
    "Scheduled job outcomes.",
    labelnames=("job", "result"),
)

REMINDERS_CREATED = Counter(
    "backend_reminders_created_total",
    "Reminders created, by type.",
    labelnames=("type",),
)

PUSHES_SENT = Counter(
    "backend_pushes_sent_total",
    "Push notifications dispatched, by channel result.",
    labelnames=("result",),
)
