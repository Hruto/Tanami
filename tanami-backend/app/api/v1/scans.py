"""Scan routes (``design.md`` 10.6) - the product's core interaction.

The upload is multipart, but the idempotency key is a header. Both are accepted
because a retry after a dropped connection sends the same ``client_uuid`` while a
test client may only set the header; they must agree when both are present.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, RateLimiterDep, ScanServiceDep
from app.core.errors import Conflict, ValidationError
from app.core.pagination import encode_cursor, page_request
from app.domain import ScanType
from app.models.scan import Scan
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.scan import (
    FeedbackCreate,
    FeedbackOut,
    ScanAttach,
    ScanCreated,
    ScanDetailOut,
    ScanOut,
)
from app.services.scan import ScanCommand, ScanService, feedback_out

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


def _scans_out(scan: Scan, service: ScanService) -> ScanOut:
    """The stored row, without the ``is_duplicate`` hint of the create body."""
    return ScanOut(**service.scan_fields(scan))


@router.post(
    "/scans",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Duplikat: client_uuid sudah pernah dikirim."}},
)
async def create_scan(
    user: CurrentUser,
    service: ScanServiceDep,
    limiter: RateLimiterDep,
    response: Response,
    image: Annotated[UploadFile, File()],
    scan_type: Annotated[ScanType, Form(alias="type")],
    client_uuid: Annotated[UUID | None, Form()] = None,
    plant_id: Annotated[UUID | None, Form()] = None,
    detection_plant_id: Annotated[UUID | None, Form()] = None,
    captured_at: Annotated[datetime | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Envelope[ScanCreated]:
    """Analyse one photo.

    ``201`` for a new scan. A resend with the same ``client_uuid`` returns the
    stored result with ``200`` and never calls the vision service again
    (design 10.6, 14); ``is_duplicate`` carries the same information in the body.
    """
    await limiter.check(
        bucket="scan",
        identity=str(user.id),
        # design 10.3: 20 uploads per minute per user (TANAMI_SCAN_RATE_LIMIT_PER_MINUTE).
        limit=service.settings.scan_rate_limit_per_minute,
        window_seconds=_SCAN_WINDOW_SECONDS,
    )
    resolved_uuid = _resolve_client_uuid(client_uuid, idempotency_key)
    raw = await image.read()

    created = await service.create(
        ScanCommand(
            user_id=user.id,
            scan_type=scan_type,
            image=raw,
            client_uuid=resolved_uuid,
            captured_at=captured_at,
            plant_id=plant_id,
            detection_plant_id=detection_plant_id,
        )
    )
    if created.is_duplicate:
        response.status_code = status.HTTP_200_OK
    return Envelope(data=created)


@router.get("/scans")
async def list_scans(
    user: CurrentUser,
    service: ScanServiceDep,
    plant_id: Annotated[UUID | None, Query()] = None,
    detection_plant_id: Annotated[UUID | None, Query()] = None,
    scan_type: Annotated[ScanType | None, Query(alias="type")] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> ListEnvelope[ScanOut]:
    page = page_request(limit, cursor)
    scans = await service.list(
        user.id,
        plant_id=plant_id,
        detection_plant_id=detection_plant_id,
        scan_type=scan_type,
        limit=page.limit + 1,
        cursor=page.cursor,
    )
    has_more = len(scans) > page.limit
    page_scans = scans[: page.limit]
    next_cursor = (
        encode_cursor(page_scans[-1].created_at, page_scans[-1].id)
        if has_more and page_scans
        else None
    )
    return ListEnvelope(
        data=[_scans_out(scan, service) for scan in page_scans],
        meta=PaginationMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/scans/{scan_id}")
async def get_scan(
    scan_id: UUID, user: CurrentUser, service: ScanServiceDep
) -> Envelope[ScanDetailOut]:
    """Detail Scan (S12), including the user's verdict if they gave one."""
    return Envelope(data=await service.get_detail(user.id, scan_id))


@router.delete("/scans/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(scan_id: UUID, user: CurrentUser, service: ScanServiceDep) -> Response:
    await service.delete(user.id, scan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/scans/{scan_id}")
async def attach_scan(
    scan_id: UUID, payload: ScanAttach, user: CurrentUser, service: ScanServiceDep
) -> Envelope[ScanOut]:
    scan = await service.attach_plant(user.id, scan_id, payload.plant_id)
    return Envelope(data=_scans_out(scan, service))


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
