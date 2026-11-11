"""Staff operations: users and roles, team broadcasts, the disease knowledge
base and the model-feedback review queue."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, ValidationError
from app.core.logging import get_logger
from app.core.pagination import Cursor
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
from app.models.content import Disease
from app.models.reminder import Reminder
from app.models.scan import Scan, ScanFeedback
from app.models.user import User
from app.providers.storage import StorageProvider
from app.schemas.admin import (
    BroadcastHistoryItem,
    DiseaseAdminOut,
    DiseaseUpdate,
    FeedbackReviewItem,
    StaffUserOut,
)

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
        consent_training_data=user.consent_training_data,
        deleted_at=user.deleted_at,
        created_at=user.created_at,
    )


def disease_admin_out(disease: Disease) -> DiseaseAdminOut:
    return DiseaseAdminOut(
        code=disease.code,
        commodity_code=disease.commodity_code,
        name_id=disease.name_id,
        name_latin=disease.name_latin,
        cause_category=disease.cause_category,
        symptoms=disease.symptoms,
        causes_text=disease.causes_text,
        treatments=dict(disease.treatments),
        prevention=disease.prevention,
        severity_note=disease.severity_note,
        reviewed_by=disease.reviewed_by,
        reviewed_at=disease.reviewed_at,
        is_active=disease.is_active,
        updated_at=disease.updated_at,
    )


def _like(term: str) -> str:
    """``%term%`` with the LIKE wildcards in ``term`` taken literally."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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

    async def list_users(
        self,
        *,
        query: str | None,
        role: UserRole | None,
        include_deleted: bool,
        limit: int,
        cursor: Cursor | None,
    ) -> list[User]:
        """Newest first, keyset-paginated. ``query`` matches name, username, email."""
        statement = select(User).order_by(User.created_at.desc(), User.id.desc()).limit(limit)
        if not include_deleted:
            statement = statement.where(User.deleted_at.is_(None))
        if role is not None:
            statement = statement.where(User.role == role.value)
        if query and query.strip():
            pattern = _like(query.strip())
            statement = statement.where(
                or_(
                    User.username.ilike(pattern, escape="\\"),
                    User.full_name.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                )
            )
        if cursor is not None:
            statement = statement.where(
                or_(
                    User.created_at < cursor.created_at,
                    and_(User.created_at == cursor.created_at, User.id < cursor.last_id),
                )
            )
        return list((await self.session.execute(statement)).scalars())

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
                    payload={"broadcast": batch, "audience": "user" if user_id else "all"},
                    dedupe_key=f"general:{batch}",
                    valid_until=moment + _BROADCAST_VALIDITY,
                    push_state=PushState.PENDING.value,
                )
            )
        await self.session.commit()
        logger.info("general_reminder_broadcast", recipients=len(recipients))
        return len(recipients)

    async def broadcast_history(self, *, limit: int) -> list[BroadcastHistoryItem]:
        """One row per broadcast, newest first, with how many recipients read it."""
        batch = Reminder.payload["broadcast"].astext
        audience = func.coalesce(Reminder.payload["audience"].astext, "all")
        sent_at = func.min(Reminder.created_at).label("sent_at")
        rows = await self.session.execute(
            select(
                batch,
                Reminder.title,
                Reminder.body,
                audience,
                func.count(),
                func.count(Reminder.read_at),
                sent_at,
            )
            .where(Reminder.type == ReminderType.GENERAL.value, batch.is_not(None))
            .group_by(batch, Reminder.title, Reminder.body, audience)
            .order_by(sent_at.desc())
            .limit(limit)
        )
        items: list[BroadcastHistoryItem] = []
        for batch_id, title, body, target, recipients, read, sent in rows.tuples():
            kind: Literal["all", "user"] = "user" if target == "user" else "all"
            items.append(
                BroadcastHistoryItem(
                    batch=str(batch_id),
                    title=title,
                    body=body,
                    audience=kind,
                    recipients=recipients,
                    read=read,
                    sent_at=sent,
                )
            )
        return items

    async def list_diseases(self) -> list[DiseaseAdminOut]:
        """The whole catalogue, including diseases taken out of it."""
        rows = await self.session.execute(
            select(Disease).order_by(Disease.commodity_code, Disease.name_id)
        )
        return [disease_admin_out(row) for row in rows.scalars()]

    async def update_disease(
        self, reviewer: User, code: str, payload: DiseaseUpdate, *, today: date
    ) -> DiseaseAdminOut:
        """Apply an expert's edit and sign it with their name and today's date.

        The signature is what keeps the edit across deploys: the startup seed
        only overwrites rows whose ``reviewed_at`` is older than its own.
        """
        disease = (
            await self.session.execute(select(Disease).where(Disease.code == code))
        ).scalar_one_or_none()
        if disease is None:
            raise NotFound("Penyakit tidak ditemukan.")
        data = payload.model_dump(exclude_unset=True, exclude={"treatments"})
        for field in ("name_id", "symptoms", "causes_text", "prevention", "is_active"):
            if field in data and data[field] is None:
                raise ValidationError(f"{field} tidak boleh kosong.", details={"field": field})
        for field, value in data.items():
            setattr(disease, field, value.strip() if isinstance(value, str) else value)
        if payload.treatments is not None:
            disease.treatments = payload.treatments.model_dump()
        disease.reviewed_by = reviewer.full_name
        disease.reviewed_at = today
        await self.session.commit()
        await self.session.refresh(disease)
        logger.info("disease_updated", code=code, reviewer_id=str(reviewer.id))
        return disease_admin_out(disease)

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

        allowed = set(_allowed_labels(scan.scan_type))
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
            allowed_labels=_allowed_labels(scan.scan_type),
            reviewed_at=feedback.reviewed_at,
            created_at=feedback.created_at,
        )


def _allowed_labels(scan_type: str) -> list[str]:
    if scan_type == ScanType.DISEASE.value:
        return list(DISEASE_LABELS)
    return [stage.value for stage in RipenessStage]
