"""Disease knowledge base routes (``design.md`` 10.9).

Content comes from the reviewed ``diseases`` table, never from the model
(TQA 8.3). Both endpoints are public knowledge, but still require a session so
the reference data is not scraped anonymously.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.scan import DiseaseOut, DiseaseSummaryOut
from app.services.content import DiseaseService

router = APIRouter(tags=["diseases"])


@router.get("/diseases")
async def list_diseases(
    user: CurrentUser,
    session: SessionDep,
    commodity_code: Annotated[str | None, Query(max_length=32)] = None,
) -> ListEnvelope[DiseaseSummaryOut]:
    _ = user
    items = await DiseaseService(session).list(commodity_code=commodity_code)
    return ListEnvelope(data=items, meta=PaginationMeta(next_cursor=None, has_more=False))


@router.get("/diseases/{code}")
async def get_disease(code: str, user: CurrentUser, session: SessionDep) -> Envelope[DiseaseOut]:
    _ = user
    return Envelope(data=await DiseaseService(session).get(code))
