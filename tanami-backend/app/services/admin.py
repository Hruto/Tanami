"""Staff operations: roles, team broadcasts and the model-feedback review queue."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, ValidationError
from app.core.logging import get_logger
from app.domain import (
    DISEASE_LABELS,
    FeedbackValue,
    PushState,
    ReminderPriority,
    ReminderStatus,
    ReminderType,
    RipenessStage,
    ScanType,
    UserRole,
)
from app.models.reminder import Reminder
from app.models.scan import Scan, ScanFeedback
from app.models.user import User
from app.providers.storage import StorageProvider
from app.schemas.admin import FeedbackReviewItem, StaffUserOut

logger = get_logger("admin")

# A team message is relevant for a week; after that it expires like any other.
_BROADCAST_VALIDITY = timedelta(days=7)


def staff_user_out(user: User) -> StaffUserOut:
    return StaffUserOut(
        id=str(user.id),
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        role=UserRole(user.role),
        created_at=user.created_at,
    )


class AdminService:
    def __init__(self, session: AsyncSession, storage: StorageProvider) -> None:
        self.session = session
        self.storage = storage

    async def set_role(self, actor: User, user_id: UUID, role: UserRole) -> User:
        user = await self.session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise NotFound("Pengguna tidak ditemukan.")
        if user.id == actor.id and role is not UserRole.ADMIN:
            # Otherwise the last admin can lock everyone out of this endpoint.
            raise ValidationError(
                "Admin tidak dapat menurunkan perannya sendiri.", details={"field": "role"}
            )
        user.role = role.value
        await self.session.commit()
        logger.info("user_role_changed", target_user_id=str(user.id), role=role.value)
        return user

    async def broadcast(
        self, *, title: str, body: str, user_id: UUID | None, now: datetime | None = None
    ) -> int:
        moment = now or datetime.now(UTC)
        query = select(User.id).where(User.deleted_at.is_(None))
        if user_id is not None:
            query = query.where(User.id == user_id)
        recipients = list((await self.session.execute(query)).scalars())
        if user_id is not None and not recipients:
            raise NotFound("Pengguna tidak ditemukan.")

        batch = uuid4().hex[:12]
        for recipient in recipients:
            self.session.add(
                Reminder(
                    id=uuid4(),
                    user_id=recipient,
                    type=ReminderType.GENERAL.value,
                    priority=ReminderPriority.LOW.value,
                    status=ReminderStatus.UNREAD.value,
                    title=title,
                    body=body,
                    payload={"broadcast": batch},
                    dedupe_key=f"general:{batch}",
                    valid_until=moment + _BROADCAST_VALIDITY,
                    push_state=PushState.PENDING.value,
                )
            )
        await self.session.commit()
        logger.info("general_reminder_broadcast", recipients=len(recipients))
        return len(recipients)

    async def feedback_queue(
        self, *, value: FeedbackValue | None, reviewed: bool | None, limit: int
    ) -> list[FeedbackReviewItem]:
        query = (
            select(ScanFeedback, Scan, User)
            .join(Scan, Scan.id == ScanFeedback.scan_id)
            .join(User, User.id == ScanFeedback.user_id)
            .order_by(ScanFeedback.created_at)
            .limit(limit)
        )
        if value is not None:
            query = query.where(ScanFeedback.value == value.value)
        if reviewed is True:
            query = query.where(ScanFeedback.reviewed_at.is_not(None))
        elif reviewed is False:
            query = query.where(ScanFeedback.reviewed_at.is_(None))
        rows = (await self.session.execute(query)).all()
        return [self._item(feedback, scan, owner) for feedback, scan, owner in rows]

    async def review_feedback(
        self, reviewer: User, feedback_id: UUID, correct_label: str
    ) -> FeedbackReviewItem:
        feedback = await self.session.get(ScanFeedback, feedback_id)
        if feedback is None:
            raise NotFound("Umpan balik tidak ditemukan.")
        scan = await self.session.get(Scan, feedback.scan_id)
        owner = await self.session.get(User, feedback.user_id)
        if scan is None or owner is None:
            raise NotFound("Umpan balik tidak ditemukan.")

        allowed = (
            set(DISEASE_LABELS)
            if scan.scan_type == ScanType.DISEASE.value
            else {stage.value for stage in RipenessStage}
        )
        if correct_label not in allowed:
            raise ValidationError(
                "Label tidak dikenal untuk jenis scan ini.",
                details={"field": "correct_label", "allowed": sorted(allowed)},
            )
        feedback.correct_label = correct_label
        feedback.reviewed_at = datetime.now(UTC)
        feedback.reviewed_by = reviewer.id
        await self.session.commit()
        return self._item(feedback, scan, owner)

    def _item(self, feedback: ScanFeedback, scan: Scan, owner: User) -> FeedbackReviewItem:
        result = scan.result if isinstance(scan.result, dict) else {}
        predicted = (
            result.get("top")
            if scan.scan_type == ScanType.DISEASE.value
            else {
                "stage": result.get("stage"),
                "confidence": result.get("confidence"),
            }
        )
        return FeedbackReviewItem(
            id=str(feedback.id),
            scan_id=str(scan.id),
            scan_type=scan.scan_type,
            image_url=self.storage.public_url(scan.image_key),
            model_version=scan.model_version,
            predicted=predicted if isinstance(predicted, dict) else None,
            value=FeedbackValue(feedback.value),
            comment=feedback.comment,
            correct_label=feedback.correct_label,
            consent_training_data=owner.consent_training_data,
            reviewed_at=feedback.reviewed_at,
            created_at=feedback.created_at,
        )
