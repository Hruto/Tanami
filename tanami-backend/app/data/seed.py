"""Idempotent seeding of reference data.

Run at startup when ``TANAMI_SEED_ON_STARTUP`` is true, and by ``scripts/seed.py``
in environments where the app should not write on boot.

Both seeds upsert by natural key, so running them twice changes nothing and a
content edit is picked up without a migration (the rows are data, not schema).
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.data.diseases_seed import disease_rows
from app.data.regions_seed import region_rows
from app.models.content import Disease, Region

logger = get_logger("seed")


async def seed_diseases(session: AsyncSession) -> int:
    """Insert missing diseases, update the text of existing ones.

    ``is_active`` is deliberately *not* overwritten with ``True``: taking a
    disease out of the catalogue is an editorial action that must survive a
    deploy. For the same reason the text is only replaced when the seed's
    ``reviewed_at`` is newer than the stored one, so an expert's edit from the
    staff dashboard (signed with the day it was made) is not undone by the
    next restart. Bump ``REVIEWED_AT`` in the seed to roll new text out.
    """
    rows = disease_rows()
    statement = insert(Disease).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Disease.commodity_code, Disease.code],
        set_={
            "name_id": statement.excluded.name_id,
            "name_latin": statement.excluded.name_latin,
            "cause_category": statement.excluded.cause_category,
            "symptoms": statement.excluded.symptoms,
            "causes_text": statement.excluded.causes_text,
            "prevention": statement.excluded.prevention,
            "severity_note": statement.excluded.severity_note,
            "treatments": statement.excluded.treatments,
            "reviewed_by": statement.excluded.reviewed_by,
            "reviewed_at": statement.excluded.reviewed_at,
        },
        where=or_(
            Disease.reviewed_at.is_(None),
            Disease.reviewed_at < statement.excluded.reviewed_at,
        ),
    )
    await session.execute(statement)
    await session.commit()
    logger.info("diseases_seeded", count=len(rows))
    return len(rows)


async def seed_regions(session: AsyncSession) -> int:
    """Insert villages that are missing; never overwrite a corrected row."""
    rows = region_rows()
    statement = insert(Region).values(rows)
    statement = statement.on_conflict_do_nothing(index_elements=[Region.adm4_code])
    result = await session.execute(statement)
    await session.commit()
    # ``Result`` has no rowcount; an INSERT always yields a CursorResult.
    inserted = int(cast(CursorResult[Any], result).rowcount or 0)
    logger.info("regions_seeded", attempted=len(rows), inserted=inserted)
    return inserted


async def seed_reference_data(session: AsyncSession) -> dict[str, int]:
    return {
        "diseases": await seed_diseases(session),
        "regions": await seed_regions(session),
    }


async def count_active_diseases(session: AsyncSession) -> int:
    rows = (
        await session.execute(select(Disease.code).where(Disease.is_active.is_(True)))
    ).scalars()
    return len(list(rows))
