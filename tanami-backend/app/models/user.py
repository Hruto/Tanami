"""Users, consent and notification settings."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, updated_at_column
from app.domain import UserRole
from app.models.columns import enum_check, enum_values, uuid_pk

if TYPE_CHECKING:
    from app.models.farm import Farm
    from app.models.forum import ForumComment, ForumPost, ForumReport
    from app.models.reminder import Device, Reminder
    from app.models.scan import Scan, ScanFeedback


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = uuid_pk()

    # Requirement 6: email, username, full name, password. Email and username
    # are stored lower-cased so the unique indexes are case-insensitive.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    full_name: Mapped[str] = mapped_column(String(80), nullable=False)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=UserRole.FARMER.value
    )

    consent_training_data: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    consent_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Per-reminder-type switches and quiet hours (design 10.8).
    notification_settings: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Last number handed out per commodity for plant display codes (``MGA-007``);
    # never reused, so a deleted plant's code does not come back (design 8.2).
    plant_code_seq: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    farms: Mapped[list[Farm]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reminders: Mapped[list[Reminder]] = relationship(back_populates="user")
    devices: Mapped[list[Device]] = relationship(back_populates="user")
    scans: Mapped[list[Scan]] = relationship(back_populates="user")
    scan_feedback: Mapped[list[ScanFeedback]] = relationship(
        back_populates="user", foreign_keys="ScanFeedback.user_id"
    )
    forum_posts: Mapped[list[ForumPost]] = relationship(back_populates="user")
    forum_comments: Mapped[list[ForumComment]] = relationship(back_populates="user")
    forum_reports: Mapped[list[ForumReport]] = relationship(
        back_populates="reporter", foreign_keys="ForumReport.reporter_id"
    )

    __table_args__ = (
        enum_check("role", UserRole, name="role"),
        CheckConstraint("username ~ '^[a-z0-9_.]{3,32}$'", name="username_format"),
        Index("uq_users_email", "email", unique=True),
        Index("uq_users_username", "username", unique=True),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.id} role={self.role}>"


# Re-exported for migrations that need the literal value list.
USER_ROLE_VALUES = enum_values(UserRole)
