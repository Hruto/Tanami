"""Disease episodes: one stretch of a plant being sick with one disease (design 8.5)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, updated_at_column
from app.domain import EpisodeCloseReason, EpisodeStatus
from app.models.columns import enum_check, uuid_pk

if TYPE_CHECKING:
    from app.models.farm import Plant
    from app.models.scan import Scan


class DiseaseEpisode(Base):
    """Opened when the user confirms a ``confident`` scan; never opened by the model alone.

    ``delay_days`` is copied from ``diseases.harvest_delay_days`` when the episode
    opens, so editing the knowledge base later does not rewrite old estimates.
    """

    __tablename__ = "disease_episodes"

    id: Mapped[UUID] = uuid_pk()
    plant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("plants.id", ondelete="CASCADE"),
        nullable=False,
    )
    disease_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("diseases.code", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=EpisodeStatus.OPEN.value
    )

    opened_at: Mapped[datetime] = mapped_column(nullable=False)
    # Null once the scan that opened it is deleted; the episode itself stays.
    opened_by_scan_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "scans.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_disease_episodes_opened_by_scan_id_scans",
        ),
        nullable=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    plant: Mapped[Plant] = relationship(back_populates="episodes")
    scans: Mapped[list[Scan]] = relationship(
        back_populates="episode", foreign_keys="Scan.disease_episode_id"
    )

    __table_args__ = (
        enum_check("status", EpisodeStatus, name="status"),
        CheckConstraint(
            f"close_reason IS NULL OR close_reason IN ("
            f"{', '.join(repr(member.value) for member in EpisodeCloseReason)})",
            name="close_reason",
        ),
        CheckConstraint("delay_days >= 0", name="delay_non_negative"),
        # An open episode has no resolution; a resolved one has both.
        CheckConstraint(
            "(status = 'open') = (resolved_at IS NULL) "
            "AND (status = 'open') = (close_reason IS NULL)",
            name="resolution_matches_status",
        ),
        # One open episode per plant and disease: confirming again attaches to it.
        Index(
            "uq_disease_episodes_open",
            "plant_id",
            "disease_code",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_disease_episodes_plant_opened", "plant_id", text("opened_at DESC")),
    )
