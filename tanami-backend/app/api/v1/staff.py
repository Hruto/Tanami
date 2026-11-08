"""Staff routes: forum moderation, roles, team broadcasts, feedback review.

* ``/moderation/*``  moderator or admin (design 13)
* ``/admin/*``       admin only
* ``/review/*``      expert or admin: validating model feedback before it may
  be used for retraining (TQA 8.1, 8.4)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    AdminUser,
    ForumServiceDep,
    ModeratorUser,
    SessionDep,
    StorageDep,
    require_roles,
)
from app.domain import FeedbackValue, ReportTargetType, UserRole
from app.models.user import User
from app.schemas.admin import (
    BroadcastOut,
    FeedbackReview,
    FeedbackReviewItem,
    GeneralReminderCreate,
    RoleUpdate,
    StaffUserOut,
)
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.forum import ModerationStatusUpdate, ReportedTargetOut, ReportResolve
from app.services.admin import AdminService, staff_user_out

router = APIRouter()

ExpertUser = Annotated[User, Depends(require_roles(UserRole.EXPERT, UserRole.ADMIN))]


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
