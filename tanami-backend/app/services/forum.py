"""Forum: posts, comments, reports, automatic hiding and moderation.

The moderation rule from ``design.md`` 13 is implemented here: N *unique*
reporters (``TANAMI_FORUM_REPORTS_TO_HIDE``, 3 by default) hide the content
until a moderator reviews it. Uniqueness is enforced by
``uq_forum_reports_reporter_target``, so a single user cannot hide a post by
reporting it three times.

Visibility:

* ``published``: everyone, including anonymous readers.
* ``hidden``: the author (so they see why it vanished) and moderators.
* ``removed``: moderators only.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Conflict, Forbidden, NotFound, ValidationError
from app.core.logging import get_logger
from app.core.pagination import Cursor
from app.domain import (
    COMMODITY_LABELS,
    FORUM_GENERAL_CATEGORY,
    PostStatus,
    ReportReason,
    ReportTargetType,
    ScanType,
    UserRole,
)
from app.models.forum import ForumComment, ForumPost, ForumReaction, ForumReport
from app.models.scan import Scan
from app.models.user import User
from app.providers.storage import StorageProvider
from app.schemas.forum import (
    AuthorOut,
    ForumCommentOut,
    ForumPostDetailOut,
    ForumPostOut,
    ReportedTargetOut,
)

logger = get_logger("forum")

_STAFF_ROLES = frozenset({UserRole.MODERATOR.value, UserRole.ADMIN.value})


def is_staff(user: User | None) -> bool:
    return user is not None and user.role in _STAFF_ROLES


def _can_see(status: str, *, author_id: UUID, viewer: User | None) -> bool:
    if status == PostStatus.PUBLISHED.value or is_staff(viewer):
        return True
    return status == PostStatus.HIDDEN.value and viewer is not None and viewer.id == author_id


def author_out(user: User) -> AuthorOut:
    return AuthorOut(
        id=str(user.id),
        username=user.username,
        display_name=user.full_name,
        role=UserRole(user.role),
        is_expert=user.role == UserRole.EXPERT.value,
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ForumService:
    def __init__(self, session: AsyncSession, settings: Settings, storage: StorageProvider) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage

    # ------------------------------------------------------------------ #
    # Posts
    # ------------------------------------------------------------------ #
    async def list_posts(
        self,
        *,
        commodity_code: str | None,
        query: str | None,
        limit: int,
        cursor: Cursor | None = None,
        viewer: User | None = None,
    ) -> list[ForumPostOut]:
        """Published posts, newest first, keyset-paginated."""
        statement = (
            select(ForumPost, User)
            .join(User, User.id == ForumPost.user_id)
            .where(ForumPost.status == PostStatus.PUBLISHED.value)
            .order_by(ForumPost.created_at.desc(), ForumPost.id.desc())
            .limit(limit)
        )
        if commodity_code:
            statement = statement.where(ForumPost.commodity_code == commodity_code)
        if query and query.strip():
            pattern = f"%{_escape_like(query.strip())}%"
            statement = statement.where(
                or_(
                    ForumPost.title.ilike(pattern, escape="\\"),
                    ForumPost.body.ilike(pattern, escape="\\"),
                )
            )
        if cursor is not None:
            statement = statement.where(
                or_(
                    ForumPost.created_at < cursor.created_at,
                    and_(
                        ForumPost.created_at == cursor.created_at,
                        ForumPost.id < cursor.last_id,
                    ),
                )
            )

        rows = (await self.session.execute(statement)).all()
        scans = await self._scans_by_id([post.scan_id for post, _ in rows if post.scan_id])
        liked = await self._liked_ids(viewer, [post.id for post, _ in rows])
        return [
            self._post_out(post, author, scans.get(post.scan_id), liked=post.id in liked)
            for post, author in rows
        ]

    async def _liked_ids(self, viewer: User | None, post_ids: list[UUID]) -> set[UUID]:
        if viewer is None or not post_ids:
            return set()
        rows = await self.session.execute(
            select(ForumReaction.post_id).where(
                ForumReaction.user_id == viewer.id, ForumReaction.post_id.in_(post_ids)
            )
        )
        return set(rows.scalars())

    async def set_like(self, user: User, post_id: UUID, *, liked: bool) -> ForumPostOut:
        """Idempotent like/unlike; ``like_count`` stays in step with the rows."""
        post, _ = await self.get_post(post_id, user)
        if post.status != PostStatus.PUBLISHED.value:
            raise ValidationError("Posting ini sedang ditinjau.", details={"field": "post_id"})
        existing = (
            await self.session.execute(
                select(ForumReaction).where(
                    ForumReaction.post_id == post.id, ForumReaction.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if liked and existing is None:
            self.session.add(ForumReaction(id=uuid4(), post_id=post.id, user_id=user.id))
            post.like_count = post.like_count + 1
        elif not liked and existing is not None:
            await self.session.delete(existing)
            post.like_count = max(0, post.like_count - 1)
        try:
            await self.session.commit()
        except IntegrityError:
            # A double tap raced another request; the row already exists.
            await self.session.rollback()
        return await self.get_post_out(post_id, user)

    async def get_post(self, post_id: UUID, viewer: User | None) -> tuple[ForumPost, User]:
        row = (
            await self.session.execute(
                select(ForumPost, User)
                .join(User, User.id == ForumPost.user_id)
                .where(ForumPost.id == post_id)
            )
        ).first()
        if row is None:
            raise NotFound("Posting tidak ditemukan.")
        post, author = row
        if not _can_see(post.status, author_id=post.user_id, viewer=viewer):
            raise NotFound("Posting tidak ditemukan.")
        return post, author

    async def get_post_detail(self, post_id: UUID, viewer: User | None) -> ForumPostDetailOut:
        post, author = await self.get_post(post_id, viewer)
        comments = await self.list_comments(post.id, viewer)
        scans = await self._scans_by_id([post.scan_id] if post.scan_id else [])
        liked = await self._liked_ids(viewer, [post.id])
        base = self._post_out(post, author, scans.get(post.scan_id), liked=post.id in liked)
        return ForumPostDetailOut(**base.model_dump(), comments=comments)

    async def get_post_out(self, post_id: UUID, viewer: User | None) -> ForumPostOut:
        post, author = await self.get_post(post_id, viewer)
        scans = await self._scans_by_id([post.scan_id] if post.scan_id else [])
        liked = await self._liked_ids(viewer, [post.id])
        return self._post_out(post, author, scans.get(post.scan_id), liked=post.id in liked)

    async def create_post(
        self,
        user: User,
        *,
        commodity_code: str,
        title: str,
        body: str,
        scan_id: UUID | None,
        image_keys: Sequence[str],
    ) -> ForumPost:
        if scan_id is not None:
            scan = await self.session.get(Scan, scan_id)
            if scan is None or scan.user_id != user.id:
                raise NotFound("Scan tidak ditemukan.", details={"field": "scan_id"})
        await self._validate_image_keys(user, image_keys)

        post = ForumPost(
            id=uuid4(),
            user_id=user.id,
            commodity_code=commodity_code,
            title=title,
            body=body,
            scan_id=scan_id,
            image_keys=list(image_keys),
            status=PostStatus.PUBLISHED.value,
        )
        self.session.add(post)
        await self.session.commit()
        return post

    async def delete_post(self, user: User, post_id: UUID) -> None:
        post, _ = await self.get_post(post_id, user)
        if post.user_id != user.id and not is_staff(user):
            raise Forbidden("Anda hanya dapat menghapus posting milik sendiri.")
        # Soft delete keeps the moderation trail and any linked reports valid.
        post.status = PostStatus.REMOVED.value
        await self.session.commit()

    async def categories(self) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                select(ForumPost.commodity_code, func.count(ForumPost.id))
                .where(ForumPost.status == PostStatus.PUBLISHED.value)
                .group_by(ForumPost.commodity_code)
            )
        ).all()
        counts = {code: int(count) for code, count in rows}
        categories: list[dict[str, Any]] = [
            {"commodity_code": code, "label": label, "post_count": counts.get(code, 0)}
            for code, label in COMMODITY_LABELS.items()
        ]
        categories.append(
            {
                "commodity_code": FORUM_GENERAL_CATEGORY,
                "label": "Umum",
                "post_count": counts.get(FORUM_GENERAL_CATEGORY, 0),
            }
        )
        return categories

    async def _validate_image_keys(self, user: User, image_keys: Sequence[str]) -> None:
        """Only photos this user uploaded through ``/uploads/forum-image``.

        Without the prefix check a post could reference any object key, for
        example another farmer's private scan photo, and publish it.
        """
        prefix = f"forum/{user.id}/"
        for key in image_keys:
            if not key.startswith(prefix) or ".." in key:
                raise ValidationError(
                    "Foto tidak valid. Unggah ulang foto lalu coba lagi.",
                    details={"field": "image_keys"},
                )
            if not await self.storage.exists(key):
                raise ValidationError(
                    "Foto tidak ditemukan. Unggah ulang foto lalu coba lagi.",
                    details={"field": "image_keys"},
                )

    async def _scans_by_id(self, scan_ids: Sequence[UUID | None]) -> dict[UUID | None, Scan]:
        ids = [scan_id for scan_id in scan_ids if scan_id is not None]
        if not ids:
            return {}
        rows = (await self.session.execute(select(Scan).where(Scan.id.in_(ids)))).scalars()
        return {scan.id: scan for scan in rows}

    # ------------------------------------------------------------------ #
    # Comments
    # ------------------------------------------------------------------ #
    async def list_comments(self, post_id: UUID, viewer: User | None) -> list[ForumCommentOut]:
        statuses = [PostStatus.PUBLISHED.value]
        if is_staff(viewer):
            statuses.append(PostStatus.HIDDEN.value)
        rows = (
            await self.session.execute(
                select(ForumComment, User)
                .join(User, User.id == ForumComment.user_id)
                .where(ForumComment.post_id == post_id, ForumComment.status.in_(statuses))
                .order_by(ForumComment.created_at, ForumComment.id)
            )
        ).all()
        return [self._comment_out(comment, author) for comment, author in rows]

    async def create_comment(self, user: User, post_id: UUID, body: str) -> ForumCommentOut:
        post, _ = await self.get_post(post_id, user)
        if post.status != PostStatus.PUBLISHED.value:
            raise ValidationError(
                "Posting ini sedang ditinjau dan belum bisa dikomentari.",
                details={"field": "post_id"},
            )
        comment = ForumComment(
            id=uuid4(),
            post_id=post.id,
            user_id=user.id,
            body=body,
            status=PostStatus.PUBLISHED.value,
        )
        self.session.add(comment)
        post.comment_count = post.comment_count + 1
        await self.session.commit()
        return self._comment_out(comment, user)

    async def delete_comment(self, user: User, comment_id: UUID) -> None:
        comment = await self.session.get(ForumComment, comment_id)
        if comment is None or comment.status == PostStatus.REMOVED.value:
            raise NotFound("Komentar tidak ditemukan.")
        if comment.user_id != user.id and not is_staff(user):
            raise Forbidden("Anda hanya dapat menghapus komentar milik sendiri.")
        await self._set_comment_status(comment, PostStatus.REMOVED)
        await self.session.commit()

    # ------------------------------------------------------------------ #
    # Reports
    # ------------------------------------------------------------------ #
    async def report(
        self,
        user: User,
        *,
        target_type: ReportTargetType,
        target_id: UUID,
        reason: ReportReason,
        note: str | None,
    ) -> ForumReport:
        await self._target(target_type, target_id)

        report = ForumReport(
            id=uuid4(),
            reporter_id=user.id,
            target_type=target_type.value,
            target_id=target_id,
            reason=reason.value,
            note=note,
        )
        self.session.add(report)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise Conflict(
                "Anda sudah melaporkan konten ini.",
                details={"field": "target_id"},
            ) from exc

        await self._maybe_hide(target_type, target_id)
        await self.session.commit()
        return report

    async def _target(
        self, target_type: ReportTargetType, target_id: UUID
    ) -> ForumPost | ForumComment:
        target: ForumPost | ForumComment | None
        if target_type is ReportTargetType.POST:
            target = await self.session.get(ForumPost, target_id)
        else:
            target = await self.session.get(ForumComment, target_id)
        if target is None or target.status == PostStatus.REMOVED.value:
            raise NotFound("Konten yang dilaporkan tidak ditemukan.")
        return target

    async def _open_reporters(self, target_type: ReportTargetType, target_id: UUID) -> int:
        count = (
            await self.session.execute(
                select(func.count(func.distinct(ForumReport.reporter_id))).where(
                    ForumReport.target_type == target_type.value,
                    ForumReport.target_id == target_id,
                    ForumReport.resolved_at.is_(None),
                )
            )
        ).scalar_one()
        return int(count)

    async def _maybe_hide(self, target_type: ReportTargetType, target_id: UUID) -> None:
        reporters = await self._open_reporters(target_type, target_id)
        if target_type is ReportTargetType.POST:
            post = await self.session.get(ForumPost, target_id)
            if post is not None:
                post.report_count = reporters
                if (
                    reporters >= self.settings.forum_reports_to_hide
                    and post.status == PostStatus.PUBLISHED.value
                ):
                    post.status = PostStatus.HIDDEN.value
                    logger.info("forum_post_hidden", post_id=str(target_id))
            return
        comment = await self.session.get(ForumComment, target_id)
        if (
            comment is not None
            and reporters >= self.settings.forum_reports_to_hide
            and comment.status == PostStatus.PUBLISHED.value
        ):
            await self._set_comment_status(comment, PostStatus.HIDDEN)
            logger.info("forum_comment_hidden", comment_id=str(target_id))

    async def _set_comment_status(self, comment: ForumComment, status: PostStatus) -> None:
        """Change a comment status and keep the denormalised counter in step."""
        was_visible = comment.status == PostStatus.PUBLISHED.value
        comment.status = status.value
        is_visible = status is PostStatus.PUBLISHED
        if was_visible == is_visible:
            return
        post = await self.session.get(ForumPost, comment.post_id)
        if post is not None:
            post.comment_count = max(0, post.comment_count + (1 if is_visible else -1))

    # ------------------------------------------------------------------ #
    # Moderation
    # ------------------------------------------------------------------ #
    async def set_status(
        self, target_type: ReportTargetType, target_id: UUID, status: PostStatus
    ) -> None:
        """Moderator action: hide, restore or remove one post or comment."""
        if target_type is ReportTargetType.POST:
            post = await self.session.get(ForumPost, target_id)
            if post is None:
                raise NotFound("Posting tidak ditemukan.")
            post.status = status.value
        else:
            comment = await self.session.get(ForumComment, target_id)
            if comment is None:
                raise NotFound("Komentar tidak ditemukan.")
            await self._set_comment_status(comment, status)
        await self.session.commit()

    async def open_reports(self, *, limit: int = 50) -> list[ReportedTargetOut]:
        """Reported content awaiting review, oldest first (design 13: 2 work days)."""
        grouped = (
            await self.session.execute(
                select(
                    ForumReport.target_type,
                    ForumReport.target_id,
                    func.count(func.distinct(ForumReport.reporter_id)),
                    func.min(ForumReport.created_at),
                    func.max(ForumReport.created_at),
                )
                .where(ForumReport.resolved_at.is_(None))
                .group_by(ForumReport.target_type, ForumReport.target_id)
                .order_by(func.min(ForumReport.created_at))
                .limit(limit)
            )
        ).all()

        out: list[ReportedTargetOut] = []
        for target_type, target_id, count, first_at, last_at in grouped:
            kind = ReportTargetType(target_type)
            reasons_rows = (
                await self.session.execute(
                    select(ForumReport.reason, func.count(ForumReport.id))
                    .where(
                        ForumReport.target_type == target_type,
                        ForumReport.target_id == target_id,
                        ForumReport.resolved_at.is_(None),
                    )
                    .group_by(ForumReport.reason)
                )
            ).all()
            target: ForumPost | ForumComment | None = (
                await self.session.get(ForumPost, target_id)
                if kind is ReportTargetType.POST
                else await self.session.get(ForumComment, target_id)
            )
            if target is None:
                continue
            author = await self.session.get(User, target.user_id)
            if author is None:
                continue
            text = target.title if isinstance(target, ForumPost) else target.body
            out.append(
                ReportedTargetOut(
                    target_type=kind,
                    target_id=str(target_id),
                    status=PostStatus(target.status),
                    excerpt=text[:200],
                    author=author_out(author),
                    post_id=str(target.id if isinstance(target, ForumPost) else target.post_id),
                    report_count=int(count),
                    reasons={reason: int(n) for reason, n in reasons_rows},
                    first_reported_at=first_at,
                    last_reported_at=last_at,
                )
            )
        return out

    async def resolve_reports(
        self,
        moderator: User,
        *,
        target_type: ReportTargetType,
        target_id: UUID,
        action: str,
    ) -> int:
        """Close every open report on a target and apply the decision."""
        reports = list(
            (
                await self.session.execute(
                    select(ForumReport).where(
                        ForumReport.target_type == target_type.value,
                        ForumReport.target_id == target_id,
                        ForumReport.resolved_at.is_(None),
                    )
                )
            ).scalars()
        )
        if not reports:
            raise NotFound("Tidak ada laporan terbuka untuk konten ini.")

        status = {
            "dismiss": PostStatus.PUBLISHED,
            "hide": PostStatus.HIDDEN,
            "remove": PostStatus.REMOVED,
        }[action]
        now = datetime.now(UTC)
        for report in reports:
            report.resolved_at = now
            report.resolved_by = moderator.id
        await self.session.flush()
        await self.set_status(target_type, target_id, status)
        logger.info(
            "forum_reports_resolved",
            target_type=target_type.value,
            action=action,
            reports=len(reports),
        )
        return len(reports)

    # ------------------------------------------------------------------ #
    # Mappers
    # ------------------------------------------------------------------ #
    def _scan_summary(self, scan: Scan | None) -> dict[str, Any] | None:
        """Photo plus the headline of the result; nothing about the plant."""
        if scan is None:
            return None
        result = scan.result if isinstance(scan.result, dict) else {}
        summary: dict[str, Any] = {
            "type": scan.scan_type,
            "status": scan.status,
            "image_url": self.storage.public_url(scan.image_key),
            "model_version": scan.model_version,
        }
        if scan.scan_type == ScanType.DISEASE.value:
            raw_top = result.get("top")
            top = raw_top if isinstance(raw_top, dict) else None
            summary["label"] = top.get("label") if top else None
            summary["cause_category"] = top.get("cause_category") if top else None
            summary["confidence"] = top.get("confidence") if top else None
        else:
            summary["label"] = result.get("stage_label")
            summary["stage"] = result.get("stage")
            summary["confidence"] = result.get("confidence")
        return summary

    def _post_out(
        self, post: ForumPost, author: User, scan: Scan | None = None, *, liked: bool = False
    ) -> ForumPostOut:
        return ForumPostOut(
            id=str(post.id),
            commodity_code=post.commodity_code,
            title=post.title,
            body=post.body,
            status=PostStatus(post.status),
            author=author_out(author),
            image_urls=[self.storage.public_url(key) for key in (post.image_keys or [])],
            scan_id=str(post.scan_id) if post.scan_id else None,
            scan_summary=self._scan_summary(scan),
            comment_count=post.comment_count,
            like_count=post.like_count,
            liked_by_me=liked,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )

    def _comment_out(self, comment: ForumComment, author: User) -> ForumCommentOut:
        return ForumCommentOut(
            id=str(comment.id),
            post_id=str(comment.post_id),
            body=comment.body,
            status=PostStatus(comment.status),
            author=author_out(author),
            created_at=comment.created_at,
        )
