"""SQLAlchemy models for ``design.md`` section 9.

Two deliberate departures from the document, both recorded in
``docs/data-model.md``:

* Enums are stored as ``VARCHAR`` with a ``CHECK`` constraint instead of native
  PostgreSQL enum types. Adding a value then is a constraint swap rather than an
  ``ALTER TYPE`` that cannot run inside every transaction, which keeps migrations
  backward compatible for one release (TQA 11).
* ``weather_snapshots`` is an append-only archive and has no ``updated_at``;
  every mutable table does.
"""

from __future__ import annotations

from app.models.content import CropProfile, Disease, Region, WeatherSnapshot
from app.models.episode import DiseaseEpisode
from app.models.farm import Farm, HarvestRecord, Plant
from app.models.forum import ForumComment, ForumPost, ForumReaction, ForumReport
from app.models.reminder import Device, Reminder
from app.models.scan import Scan, ScanFeedback
from app.models.tracking import CareLog, PlantPhoto
from app.models.user import User

__all__ = [
    "CareLog",
    "CropProfile",
    "Device",
    "Disease",
    "DiseaseEpisode",
    "Farm",
    "ForumComment",
    "ForumPost",
    "ForumReaction",
    "ForumReport",
    "HarvestRecord",
    "Plant",
    "PlantPhoto",
    "Region",
    "Reminder",
    "Scan",
    "ScanFeedback",
    "User",
    "WeatherSnapshot",
]
