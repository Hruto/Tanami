"""Housekeeping that keeps derived state honest over time.

``decay_stale_health``
    ``design.md`` 8.2: a plant with no leaf scan in the last 14 days is
    ``unknown``. The status is otherwise only recomputed when a scan arrives, so
    without this job a plant scanned "sick" once would stay sick forever.
``purge_deleted_accounts``
    ``tqa.md`` 9: account deletion completes "within a reasonable time".
    ``DELETE /users/me`` marks the account; after ``account_purge_days`` this job
    removes the photos from object storage and the rows from PostgreSQL (the
    foreign keys cascade to farms, plants, scans, reminders, devices and posts).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain import HealthStatus, ScanType
from app.models.farm import Plant
from app.models.forum import ForumPost
from app.models.scan import Scan
from app.models.user import User
from app.providers.storage import StorageProvider

logger = get_logger("maintenance")


async def decay_stale_health(session: AsyncSession, *, now: datetime, stale_days: int) -> int:
    cutoff = now - timedelta(days=stale_days)
    recent_leaf_scan = exists().where(
        Scan.plant_id == Plant.id,
        Scan.scan_type == ScanType.DISEASE.value,
        Scan.captured_at >= cutoff,
    )
    result = await session.execute(
        update(Plant)
        .where(
            Plant.health_status != HealthStatus.UNKNOWN.value,
            Plant.ended_at.is_(None),
            ~recent_leaf_scan,
        )
        .values(health_status=HealthStatus.UNKNOWN.value, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    changed = int(cast(CursorResult[Any], result).rowcount or 0)
    if changed:
        logger.info("plant_health_decayed", plants=changed, stale_days=stale_days)
    return changed


async def purge_deleted_accounts(
    session: AsyncSession,
    storage: StorageProvider,
    *,
    now: datetime,
    after_days: int,
) -> int:
    cutoff = now - timedelta(days=after_days)
    users = list(
        (
            await session.execute(
                select(User).where(User.deleted_at.is_not(None), User.deleted_at <= cutoff)
            )
        ).scalars()
    )
    for user in users:
        keys = list(
            (await session.execute(select(Scan.image_key).where(Scan.user_id == user.id))).scalars()
        )
        for post_keys in (
            await session.execute(select(ForumPost.image_keys).where(ForumPost.user_id == user.id))
        ).scalars():
            keys.extend(post_keys or [])
        for key in keys:
            # Best effort: an orphaned object is recoverable, a half-deleted
            # account is not, so storage errors never block the row deletion.
            await storage.delete(key)
        # A Core DELETE lets the database cascades do the work; the ORM would
        # instead try to null out every loaded child row first.
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()
        logger.info("account_purged", images=len(keys))
    return len(users)
