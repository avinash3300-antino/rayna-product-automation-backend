import uuid
from datetime import datetime

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None
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
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class Activity(Base):
    __tablename__ = "activities"

    # ── Identity ──────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    city_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_destinations.id"),
        nullable=False,
    )

    # ── Classification ────────────────────────────────────────────────────
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(100))
    activity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tags = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )

    # ── Descriptions ──────────────────────────────────────────────────────
    description_short: Mapped[str] = mapped_column(Text, nullable=False)
    description_long: Mapped[str] = mapped_column(Text, nullable=False)
    highlights = mapped_column(JSON, nullable=False)
    included = mapped_column(JSON, nullable=False)
    excluded = mapped_column(JSON, nullable=False)
    what_to_bring: Mapped[str | None] = mapped_column(Text)
    important_notes: Mapped[str | None] = mapped_column(Text)

    # ── Pricing ───────────────────────────────────────────────────────────
    price_adult: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    price_child: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_infant: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_group: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_original: Mapped[float | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_type: Mapped[str] = mapped_column(String(50), nullable=False)
    discount_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    price_from: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # ── Duration & Scheduling ─────────────────────────────────────────────
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    start_times = mapped_column(JSON, nullable=False)
    operating_days = mapped_column(JSON, nullable=False)
    instant_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    free_cancellation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    cancellation_hours: Mapped[int | None] = mapped_column(Integer)
    cancellation_policy: Mapped[str | None] = mapped_column(Text)
    min_participants: Mapped[int | None] = mapped_column(Integer)
    max_participants: Mapped[int | None] = mapped_column(Integer)
    advance_booking_days: Mapped[int | None] = mapped_column(Integer)

    # ── Location ──────────────────────────────────────────────────────────
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(200), nullable=False)
    area: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    lat: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    lng: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    maps_link: Mapped[str | None] = mapped_column(String(500))
    meeting_point_name: Mapped[str | None] = mapped_column(String(300))
    meeting_point_desc: Mapped[str | None] = mapped_column(Text)
    nearby_landmark: Mapped[str | None] = mapped_column(String(300))

    # ── Pickup & Dropoff ──────────────────────────────────────────────────
    pickup_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    pickup_locations = mapped_column(JSON, nullable=True)
    hotel_pickup_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    dropoff_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # ── Policies & Restrictions ───────────────────────────────────────────
    refund_policy_details: Mapped[str | None] = mapped_column(Text)
    min_age: Mapped[int | None] = mapped_column(Integer)
    max_age: Mapped[int | None] = mapped_column(Integer)
    fitness_level: Mapped[str | None] = mapped_column(String(50))
    difficulty: Mapped[str | None] = mapped_column(String(50))
    pregnancy_restriction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    wheelchair_access: Mapped[str | None] = mapped_column(String(50))
    languages = mapped_column(JSON, nullable=False)

    # ── Images & Media ────────────────────────────────────────────────────
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    gallery_json = mapped_column(JSON, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500))

    # ── Reviews & Ratings ─────────────────────────────────────────────────
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rating_5: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rating_4: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rating_3: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    review_snippets = mapped_column(JSON, nullable=True)

    # ── SEO ───────────────────────────────────────────────────────────────
    meta_title: Mapped[str | None] = mapped_column(String(60))
    meta_description: Mapped[str | None] = mapped_column(String(155))
    focus_keyword: Mapped[str | None] = mapped_column(String(200))
    json_ld = mapped_column(JSON, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(500))

    # ── Source & Data Quality ─────────────────────────────────────────────
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(300))
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    dedup_hash: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False
    )
    quality_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────
    destination = relationship(
        "CatalogDestination", foreign_keys=[city_id]
    )


# NOTE: ActivityEmbedding is defined below but only usable when pgvector
# extension is installed and the activity_embeddings table exists.
# A future migration will create the table.

class ActivityEmbedding(Base):
    __tablename__ = "activity_embeddings"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activities.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    embedding = mapped_column(Vector(1536) if Vector else Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
