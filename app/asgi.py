from __future__ import annotations

from app.core.config import Settings
from app.main import create_app

app = create_app(Settings())
