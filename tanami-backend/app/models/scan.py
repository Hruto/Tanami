"""Scans and user feedback on a scan result."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, updated_at_column
from app.domain import FeedbackValue, ResultStatus
from app.models.columns import enum_check, uuid_pk, values_check

if TYPE_CHECKING:
    from app.models.content import Disease
    from app.models.episode import DiseaseEpisode
    from app.models.farm import Plant
    from app.models.forum import ForumPost
    from app.models.user import User


class Scan(Base):
    """One analysed leaf photo of a registered plant (design v2).

    Every stored scan belongs to a plant; a "cek cepat" scan is never stored.
    ``user_id`` is kept as well so history and feedback do not need a join.
    """

    __tablename__ = "scans"

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("plants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Set when the user confirmed this result and it opened or joined an episode.
    disease_episode_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("disease_episodes.id", ondelete="SET NULL"),
        nullable=True,
    )

    scan_type: Mapped[str] = mapped_column(String(16), nullable=False)
    image_key: Mapped[str] = mapped_column(String(255), nullable=False)
    image_content_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Idempotency: the client generates it, and a resend with the same value
    # returns the stored result instead of calling the model again (design 10.6).
    client_uuid: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    captured_at: Mapped[datetime] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    disease_code: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("diseases.code", ondelete="RESTRICT"),
        nullable=True,
    )
    quality: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    # Copied from the vision response for reporting and drift analysis.
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    commodity_code: Mapped[str] = mapped_column(String(32), nullable=False, server_default="chili")
    inference_ms: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[User] = relationship(back_populates="scans")
    plant: Mapped[Plant] = relationship(back_populates="scans")
    episode: Mapped[DiseaseEpisode | None] = relationship(
        back_populates="scans", foreign_keys=[disease_episode_id]
    )
    disease: Mapped[Disease | None] = relationship(back_populates="scans")
    feedback: Mapped[ScanFeedback | None] = relationship(
        back_populates="scan", cascade="all, delete-orphan", uselist=False
    )
    forum_posts: Mapped[list[ForumPost]] = relationship(back_populates="scan")

    __table_args__ = (
        values_check("scan_type", ("disease",), name="scan_type"),
        enum_check("status", ResultStatus, name="status"),
        UniqueConstraint("user_id", "client_uuid", name="uq_scans_user_client_uuid"),
        CheckConstraint(
            "status IN ('confident', 'uncertain') OR disease_code IS NULL",
            name="disease_code_only_when_named",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        # History per plant: "the last ripeness scan for this plant".
        Index("ix_scans_plant_captured", "plant_id", text("captured_at DESC")),
        # Global history and keyset pagination per user.
        Index("ix_scans_user_created", "user_id", text("created_at DESC")),
        Index("ix_scans_user_plant_created", "user_id", "plant_id", text("created_at DESC")),
        Index("ix_scans_disease_code", "disease_code"),
        Index("ix_scans_status", "status"),
        Index("ix_scans_disease_episode_id", "disease_episode_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Scan {self.id} type={self.scan_type} status={self.status}>"


class ScanFeedback(Base):
    __tablename__ = "scan_feedback"

    id: Mapped[UUID] = uuid_pk()
    scan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # ``user_id`` is denormalised from the scan so consent is one join away when
    # building a training export; the FK is RESTRICT-free because the scan owns
    # the row.
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    value: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    scan: Mapped[Scan] = relationship(back_populates="feedback")
    user: Mapped[User] = relationship(back_populates="scan_feedback", foreign_keys=[user_id])

    __table_args__ = (enum_check("value", FeedbackValue, name="value"),)
