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
    highlights = mapped_column(JSON, nullable=False)          # JSONB array of strings
    included = mapped_column(JSON, nullable=False)            # JSONB array of strings
    excluded = mapped_column(JSON, nullable=False)            # JSONB array of strings
    what_to_bring: Mapped[str | None] = mapped_column(Text)
    important_notes = mapped_column(JSON, nullable=True)      # JSONB array of strings (was Text)
    redemption_instructions = mapped_column(JSON, nullable=True)  # JSONB array of step strings

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

    # ── Scraped Pricing ──────────────────────────────────────────────────
    scraped_prices = mapped_column(JSON, nullable=True)  # [{source, url, local_currency, local_price, aed_price, scraped_at}]
    local_currency: Mapped[str | None] = mapped_column(String(3))
    price_local: Mapped[float | None] = mapped_column(Numeric(10, 2))

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
    dress_code_note: Mapped[str | None] = mapped_column(Text)

    # ── Images & Media ────────────────────────────────────────────────────
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    gallery_json = mapped_column(JSON, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500))

    # ── Reviews & Ratings ─────────────────────────────────────────────────
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rating_5: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rating_4: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rating_3: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rating_2: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rating_1: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    review_snippets = mapped_column(JSON, nullable=True)

    # ── SEO ───────────────────────────────────────────────────────────────
    meta_title: Mapped[str | None] = mapped_column(String(60))
    meta_description: Mapped[str | None] = mapped_column(String(155))
    focus_keyword: Mapped[str | None] = mapped_column(String(200))
    json_ld = mapped_column(JSON, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(500))

    # ── Source & Data Quality ─────────────────────────────────────────────
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_urls = mapped_column(JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(300))
    operator_website: Mapped[str | None] = mapped_column(String(500))
    operator_established_year: Mapped[int | None] = mapped_column(Integer)
    operator_certifications = mapped_column(JSON, nullable=True)  # JSONB array
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    dedup_hash: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False
    )
    quality_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    # ── Classification flags ──────────────────────────────────────────────
    is_package: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    has_transport: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    has_meals: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # ── FAQs ───────────────────────────────────────────────────────────────
    faqs = mapped_column(JSON, nullable=True)  # [{question: str, answer: str}]

    # ── Tour Variants ──────────────────────────────────────────────────────
    tour_variants = mapped_column(JSON, nullable=True)  # [{name, description, duration_minutes, price: {amount, currency}, includes, excludes, is_default}]

    # ── Daily Availability (Playwright-scraped) ──────────────────────────
    daily_availability = mapped_column(JSON, nullable=True)  # {scraped_at, source_url, week_start, daily: {Monday: {date, available, time_slots, tour_options}, ...}}

    # ── Catchall ──────────────────────────────────────────────────────────
    other_attributes = mapped_column(JSON, nullable=True)  # [{label, value, category_hint}]

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
    destination = relationship("CatalogDestination", foreign_keys=[city_id])
    timeline: Mapped[list["ActivityTimeline"]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        order_by="ActivityTimeline.order",
    )


class ActivityTimeline(Base):
    """What You Do / Activity Flow — ordered timeline steps."""
    __tablename__ = "catalog_activity_timeline"

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
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    time_label: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    activity: Mapped["Activity"] = relationship(back_populates="timeline")
