"""Scan routes (``design.md`` 10.6) - the product's core interaction.

The upload is multipart, but the idempotency key is a header. Both are accepted
because a retry after a dropped connection sends the same ``client_uuid`` while a
test client may only set the header; they must agree when both are present.

A scan belongs to a registered plant (``plant_id``). Without one it is a "cek
cepat": the result comes back with ``saved: false`` and nothing is stored.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, EpisodeServiceDep, RateLimiterDep, ScanServiceDep
from app.core.errors import Conflict, ValidationError
from app.core.pagination import encode_cursor, page_request
from app.domain import ScanType
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.scan import (
    ConfirmDiseaseOut,
    FeedbackCreate,
    FeedbackOut,
    ScanCreated,
    ScanDetailOut,
    ScanHistoryItem,
)
from app.services.scan import ScanCommand, feedback_out

router = APIRouter(tags=["scans"])

_SCAN_WINDOW_SECONDS = 60


def _resolve_client_uuid(client_uuid: UUID | None, idempotency_key: str | None) -> UUID:
    """The contract requires ``client_uuid``; the header is what a retry sends."""
    header_value: UUID | None = None
    if idempotency_key:
        try:
            header_value = UUID(idempotency_key)
        except ValueError as exc:
            raise ValidationError(
                "Header Idempotency-Key harus berupa UUID.",
                details={"field": "Idempotency-Key"},
            ) from exc

    if client_uuid is not None and header_value is not None and client_uuid != header_value:
        raise Conflict(
            "client_uuid dan Idempotency-Key tidak sama.",
            details={"field": "Idempotency-Key"},
        )
    resolved = client_uuid if client_uuid is not None else header_value
    if resolved is None:
        raise ValidationError(
            "client_uuid wajib dikirim agar pengiriman ulang aman.",
            details={"field": "client_uuid"},
        )
    return resolved


@router.post(
    "/scans",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Duplikat (client_uuid sudah pernah dikirim) atau cek cepat."}},
)
async def create_scan(
    user: CurrentUser,
    service: ScanServiceDep,
    limiter: RateLimiterDep,
    response: Response,
    image: Annotated[UploadFile, File()],
    scan_type: Annotated[ScanType, Form(alias="type")] = ScanType.DISEASE,
    client_uuid: Annotated[UUID | None, Form()] = None,
    plant_id: Annotated[UUID | None, Form()] = None,
    commodity_code: Annotated[str | None, Form()] = None,
    captured_at: Annotated[datetime | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Envelope[ScanCreated]:
    """Analyse one leaf photo.

    With ``plant_id`` the scan is stored: ``201`` for a new one, ``200`` for a
    resend with the same ``client_uuid`` (design 10.6, 14; ``is_duplicate``
    says the same in the body). Without ``plant_id`` it is a "cek cepat" that
    needs ``commodity_code``, is never stored and always answers ``200``.
    """
    await limiter.check(
        bucket="scan",
        identity=str(user.id),
        # design 10.3: 20 uploads per minute per user (TANAMI_SCAN_RATE_LIMIT_PER_MINUTE).
        limit=service.settings.scan_rate_limit_per_minute,
        window_seconds=_SCAN_WINDOW_SECONDS,
    )
    quick = plant_id is None
    resolved_uuid = None if quick else _resolve_client_uuid(client_uuid, idempotency_key)
    raw = await image.read()

    created = await service.create(
        ScanCommand(
            user_id=user.id,
            # design 10.6 v2: every scan is a disease scan. A v0.3 client that
            # still sends "ripeness" must not break, so the value is ignored.
            scan_type=ScanType.DISEASE if scan_type is ScanType.RIPENESS else scan_type,
            image=raw,
            client_uuid=resolved_uuid,
            captured_at=captured_at,
            plant_id=plant_id,
            commodity_code=commodity_code,
        )
    )
    if quick or created.is_duplicate:
        response.status_code = status.HTTP_200_OK
    return Envelope(data=created)


@router.get("/scans")
async def list_scans(
    user: CurrentUser,
    service: ScanServiceDep,
    plant_id: Annotated[UUID | None, Query()] = None,
    commodity_code: Annotated[str | None, Query()] = None,
    disease_code: Annotated[str | None, Query()] = None,
    result_status: Annotated[
        Literal["confident", "uncertain", "unknown", "invalid_image", "all"] | None,
        Query(alias="status"),
    ] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> ListEnvelope[ScanHistoryItem]:
    """Riwayat Scan (design 5.8): filter by plant, commodity, disease, status and day."""
    page = page_request(limit, cursor)
    rows = await service.history(
        user.id,
        plant_id=plant_id,
        commodity_code=commodity_code,
        disease_code=disease_code,
        status=result_status,
        date_from=date_from,
        date_to=date_to,
        limit=page.limit + 1,
        cursor=page.cursor,
    )
    has_more = len(rows) > page.limit
    page_rows = rows[: page.limit]
    next_cursor = (
        encode_cursor(page_rows[-1][0].created_at, page_rows[-1][0].id)
        if has_more and page_rows
        else None
    )
    return ListEnvelope(
        data=[item for _, item in page_rows],
        meta=PaginationMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/scans/{scan_id}")
async def get_scan(
    scan_id: UUID, user: CurrentUser, service: ScanServiceDep
) -> Envelope[ScanDetailOut]:
    """Detail Scan, including the user's verdict if they gave one."""
    return Envelope(data=await service.get_detail(user.id, scan_id))


@router.delete("/scans/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(scan_id: UUID, user: CurrentUser, service: ScanServiceDep) -> Response:
    await service.delete(user.id, scan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scans/{scan_id}/confirm-disease", status_code=status.HTTP_201_CREATED)
async def confirm_disease(
    scan_id: UUID, user: CurrentUser, episodes: EpisodeServiceDep, response: Response
) -> Envelope[ConfirmDiseaseOut]:
    """ "Ya, tanaman ini sakit" (design 5.4, 8.5).

    ``201`` opens an episode. ``200`` means the scan joined an episode that was
    already open (or was confirmed before), which adds no further delay.
    """
    result = await episodes.confirm(user.id, scan_id)
    if not result.is_new:
        response.status_code = status.HTTP_200_OK
    out = (await episodes.to_out([result.episode]))[0]
    return Envelope(
        data=ConfirmDiseaseOut(
            is_new=result.is_new,
            episode=out,
            next_harvest=await episodes.next_harvest_for(result.plant),
        )
    )


@router.put("/scans/{scan_id}/feedback")
async def upsert_feedback(
    scan_id: UUID, payload: FeedbackCreate, user: CurrentUser, service: ScanServiceDep
) -> Envelope[FeedbackOut]:
    """Create or replace the user's verdict on a scan.

    ``PUT`` rather than ``POST`` because there is at most one feedback per scan;
    sending it twice must not create a second row.
    """
    feedback = await service.upsert_feedback(
        user.id,
        scan_id,
        value=payload.value.value,
        comment=payload.comment,
    )
    out = feedback_out(feedback)
    assert out is not None  # noqa: S101 - upsert always returns a row
    return Envelope(data=out)
