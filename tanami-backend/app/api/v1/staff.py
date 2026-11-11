"""Staff routes: forum moderation, roles, team broadcasts, feedback review.

* ``/moderation/*``  moderator or admin (design 13)
* ``/admin/overview`` any staff role (aggregate numbers only)
* ``/admin/diseases`` expert or admin: the reviewed knowledge base (TQA 8.3)
* ``/admin/*``       admin only otherwise
* ``/review/*``      expert or admin: validating model feedback before it may
  be used for retraining (TQA 8.1, 8.4)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    AdminUser,
    ForumServiceDep,
    ModeratorUser,
    SessionDep,
    SettingsDep,
    StorageDep,
    require_roles,
)
from app.core.pagination import encode_cursor, page_request
from app.domain import FeedbackValue, ReportTargetType, UserRole
from app.models.user import User
from app.schemas.admin import (
    AdminOverviewOut,
    BroadcastHistoryItem,
    BroadcastOut,
    DiseaseAdminOut,
    DiseaseUpdate,
    FeedbackReview,
    FeedbackReviewItem,
    GeneralReminderCreate,
    RoleUpdate,
    StaffUserOut,
)
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.forum import ModerationStatusUpdate, ReportedTargetOut, ReportResolve
from app.services.admin import AdminService, staff_user_out
from app.services.overview import OverviewService

router = APIRouter()

ExpertUser = Annotated[User, Depends(require_roles(UserRole.EXPERT, UserRole.ADMIN))]
StaffUser = Annotated[
    User,
    Depends(require_roles(UserRole.EXPERT, UserRole.MODERATOR, UserRole.ADMIN)),
]


# --------------------------------------------------------------------------- #
# Dashboard home
# --------------------------------------------------------------------------- #
@router.get("/admin/overview", tags=["admin"])
async def overview(
    _: StaffUser, session: SessionDep, settings: SettingsDep
) -> Envelope[AdminOverviewOut]:
    """Counts for the staff dashboard. Aggregates only, no personal data."""
    return Envelope(data=await OverviewService(session, settings.timezone).build())


# --------------------------------------------------------------------------- #
# Moderation
# --------------------------------------------------------------------------- #
@router.get("/moderation/reports", tags=["moderation"])
async def open_reports(
    _: ModeratorUser,
    service: ForumServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ListEnvelope[ReportedTargetOut]:
    """Reported content awaiting review, oldest first."""
    items = await service.open_reports(limit=limit)
    return ListEnvelope(data=items, meta=PaginationMeta())


@router.post("/moderation/reports/{target_type}/{target_id}/resolve", tags=["moderation"])
async def resolve_reports(
    target_type: ReportTargetType,
    target_id: UUID,
    payload: ReportResolve,
    moderator: ModeratorUser,
    service: ForumServiceDep,
) -> Envelope[dict[str, int]]:
    """``dismiss`` republishes, ``hide`` keeps it hidden, ``remove`` deletes it."""
    resolved = await service.resolve_reports(
        moderator, target_type=target_type, target_id=target_id, action=payload.action
    )
    return Envelope(data={"resolved_reports": resolved})


@router.patch("/moderation/posts/{post_id}", tags=["moderation"])
async def moderate_post(
    post_id: UUID, payload: ModerationStatusUpdate, _: ModeratorUser, service: ForumServiceDep
) -> Envelope[dict[str, str]]:
    await service.set_status(ReportTargetType.POST, post_id, payload.status)
    return Envelope(data={"id": str(post_id), "status": payload.status.value})


@router.patch("/moderation/comments/{comment_id}", tags=["moderation"])
async def moderate_comment(
    comment_id: UUID,
    payload: ModerationStatusUpdate,
    _: ModeratorUser,
    service: ForumServiceDep,
) -> Envelope[dict[str, str]]:
    await service.set_status(ReportTargetType.COMMENT, comment_id, payload.status)
    return Envelope(data={"id": str(comment_id), "status": payload.status.value})


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
@router.patch("/admin/users/{user_id}/role", tags=["admin"])
async def set_role(
    user_id: UUID,
    payload: RoleUpdate,
    admin: AdminUser,
    session: SessionDep,
    storage: StorageDep,
) -> Envelope[StaffUserOut]:
    user = await AdminService(session, storage).set_role(admin, user_id, payload.role)
    return Envelope(data=staff_user_out(user))


@router.get("/admin/users", tags=["admin"])
async def list_users(
    _: AdminUser,
    session: SessionDep,
    storage: StorageDep,
    q: Annotated[str | None, Query(max_length=80)] = None,
    role: Annotated[UserRole | None, Query()] = None,
    include_deleted: Annotated[bool, Query()] = False,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> ListEnvelope[StaffUserOut]:
    """Search accounts by name, username or email, newest first."""
    page = page_request(limit, cursor)
    users = await AdminService(session, storage).list_users(
        query=q,
        role=role,
        include_deleted=include_deleted,
        limit=page.limit + 1,
        cursor=page.cursor,
    )
    has_more = len(users) > page.limit
    shown = users[: page.limit]
    next_cursor = encode_cursor(shown[-1].created_at, shown[-1].id) if has_more and shown else None
    return ListEnvelope(
        data=[staff_user_out(user) for user in shown],
        meta=PaginationMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/admin/reminders/general", tags=["admin"])
async def broadcast_history(
    _: AdminUser,
    session: SessionDep,
    storage: StorageDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ListEnvelope[BroadcastHistoryItem]:
    """Team announcements already sent, newest first, with read counts."""
    items = await AdminService(session, storage).broadcast_history(limit=limit)
    return ListEnvelope(data=items, meta=PaginationMeta())


@router.post("/admin/reminders/general", tags=["admin"], status_code=201)
async def broadcast_general(
    payload: GeneralReminderCreate,
    _: AdminUser,
    session: SessionDep,
    storage: StorageDep,
) -> Envelope[BroadcastOut]:
    created = await AdminService(session, storage).broadcast(
        title=payload.title, body=payload.body, user_id=payload.user_id
    )
    return Envelope(data=BroadcastOut(created=created))


# --------------------------------------------------------------------------- #
# Disease knowledge base
# --------------------------------------------------------------------------- #
@router.get("/admin/diseases", tags=["review"])
async def list_diseases(
    _: ExpertUser, session: SessionDep, storage: StorageDep
) -> ListEnvelope[DiseaseAdminOut]:
    """Every disease, including ones taken out of the catalogue."""
    items = await AdminService(session, storage).list_diseases()
    return ListEnvelope(data=items, meta=PaginationMeta())


@router.patch("/admin/diseases/{code}", tags=["review"])
async def update_disease(
    code: str,
    payload: DiseaseUpdate,
    reviewer: ExpertUser,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> Envelope[DiseaseAdminOut]:
    """Edit reviewed content; the editor and today's date become the review stamp."""
    today = datetime.now(UTC).astimezone(ZoneInfo(settings.timezone)).date()
    item = await AdminService(session, storage).update_disease(reviewer, code, payload, today=today)
    return Envelope(data=item)


# --------------------------------------------------------------------------- #
# Expert review of model feedback
# --------------------------------------------------------------------------- #
@router.get("/review/feedback", tags=["review"])
async def feedback_queue(
    _: ExpertUser,
    session: SessionDep,
    storage: StorageDep,
    value: Annotated[FeedbackValue | None, Query()] = FeedbackValue.INCORRECT,
    reviewed: Annotated[bool | None, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ListEnvelope[FeedbackReviewItem]:
    items = await AdminService(session, storage).feedback_queue(
        value=value, reviewed=reviewed, limit=limit
    )
    return ListEnvelope(data=items, meta=PaginationMeta())


@router.patch("/review/feedback/{feedback_id}", tags=["review"])
async def review_feedback(
    feedback_id: UUID,
    payload: FeedbackReview,
    reviewer: ExpertUser,
    session: SessionDep,
    storage: StorageDep,
) -> Envelope[FeedbackReviewItem]:
    item = await AdminService(session, storage).review_feedback(
        reviewer, feedback_id, payload.correct_label
    )
    return Envelope(data=item)
