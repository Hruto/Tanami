"""Forum posts, flat comments and reports."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, updated_at_column
from app.domain import PostStatus, ReportReason, ReportTargetType
from app.models.columns import enum_check, uuid_pk

if TYPE_CHECKING:
    from app.models.scan import Scan
    from app.models.user import User


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    commodity_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image_keys: Mapped[list[str]] = mapped_column(
        ARRAY(String(255)), nullable=False, server_default=text("'{}'::text[]")
    )
    scan_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=PostStatus.PUBLISHED.value
    )
    # Denormalised counter so the list endpoint does not count comments per row.
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    user: Mapped[User] = relationship(back_populates="forum_posts")
    scan: Mapped[Scan | None] = relationship(back_populates="forum_posts")
    comments: Mapped[list[ForumComment]] = relationship(
        back_populates="post", cascade="all, delete-orphan", order_by="ForumComment.created_at"
    )

    __table_args__ = (
        enum_check("status", PostStatus, name="status"),
        CheckConstraint("char_length(title) BETWEEN 5 AND 120", name="title_length"),
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="body_length"),
        CheckConstraint(
            "array_length(image_keys, 1) IS NULL OR array_length(image_keys, 1) <= 3",
            name="max_three_images",
        ),
        CheckConstraint("comment_count >= 0", name="comment_count_non_negative"),
        Index("ix_forum_posts_status_created", "status", text("created_at DESC")),
        Index(
            "ix_forum_posts_commodity_status", "commodity_code", "status", text("created_at DESC")
        ),
        Index("ix_forum_posts_user_created", "user_id", text("created_at DESC")),
    )


class ForumComment(Base):
    __tablename__ = "forum_comments"

    id: Mapped[UUID] = uuid_pk()
    post_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("forum_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=PostStatus.PUBLISHED.value
    )

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    post: Mapped[ForumPost] = relationship(back_populates="comments")
    user: Mapped[User] = relationship(back_populates="forum_comments")

    __table_args__ = (
        enum_check("status", PostStatus, name="status"),
        CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="body_length"),
        Index("ix_forum_comments_post_created", "post_id", "created_at"),
        Index("ix_forum_comments_user_created", "user_id", text("created_at DESC")),
    )


class ForumReport(Base):
    """A moderation report.

    The target is polymorphic (``target_type`` + ``target_id``), deliberately not
    a foreign key to two tables. Uniqueness per reporter is what makes the ">= 3
    unique reports hide the content" rule (design 13) meaningful.
    """

    __tablename__ = "forum_reports"

    id: Mapped[UUID] = uuid_pk()
    reporter_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    reporter: Mapped[User] = relationship(
        back_populates="forum_reports", foreign_keys=[reporter_id]
    )

    __table_args__ = (
        enum_check("target_type", ReportTargetType, name="target_type"),
        enum_check("reason", ReportReason, name="reason"),
        UniqueConstraint(
            "reporter_id",
            "target_type",
            "target_id",
            name="uq_forum_reports_reporter_target",
        ),
        CheckConstraint("note IS NULL OR char_length(note) <= 1000", name="note_length"),
        Index("ix_forum_reports_target", "target_type", "target_id"),
        Index("ix_forum_reports_unresolved", "resolved_at"),
    )


class ForumReaction(Base):
    """A "like" on a post (requirement 5, "Interaksi Pengguna"). One per user."""

    __tablename__ = "forum_reactions"

    id: Mapped[UUID] = uuid_pk()
    post_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("forum_posts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_forum_reactions_post_user"),
        Index("ix_forum_reactions_user_id", "user_id"),
    )
