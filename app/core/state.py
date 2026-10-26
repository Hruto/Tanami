"""Application state shared across requests.

FastAPI's ``app.state`` holds this; routes reach it through dependencies so
tests can swap a registry without monkeypatching module globals.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.config import Settings
from app.services.predict import PredictService
from app.services.registry import ModelRegistry


@dataclass
class AppState:
    settings: Settings
    registry: ModelRegistry
    predict_service: PredictService
    started_at: float = field(default_factory=time.monotonic)

    @property
    def uptime_seconds(self) -> float:
        return round(time.monotonic() - self.started_at, 3)
