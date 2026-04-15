import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class ActivityReview(Base):
    __tablename__ = "activity_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Review Content ───────────────────────────────────────────────────
    reviewer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewer_avatar_url: Mapped[str | None] = mapped_column(String(500))
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    review_title: Mapped[str | None] = mapped_column(String(500))
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    review_date: Mapped[str | None] = mapped_column(String(100))

    # ── Source ───────────────────────────────────────────────────────────
    source_platform: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # google, tripadvisor, trustpilot
    source_url: Mapped[str | None] = mapped_column(String(500))
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="'en'"
    )

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ── Relationships ────────────────────────────────────────────────────
    activity = relationship("Activity", foreign_keys=[activity_id])
