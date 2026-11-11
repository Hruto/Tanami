"""ASGI entry point.

``uvicorn app.asgi:app`` is the documented way to run the service; ``app`` here is
built once from the environment so the module-level object is what a process
manager imports.
"""

from __future__ import annotations

from app.main import create_app

app = create_app()

__all__ = ["app"]
