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
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CruiseProduct(Base):
    __tablename__ = "catalog_cruise_products"

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
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="'Cruise'"
    )
    sub_category: Mapped[str | None] = mapped_column(String(100))  # Dinner/River/Ocean/Luxury/Dhow-Premium
    cruise_class: Mapped[str | None] = mapped_column(String(100))  # Economy/Standard/Premium/Luxury
    cruise_type: Mapped[str | None] = mapped_column(String(100))   # dinner/sightseeing/overnight/multi-day/party/fishing/sunset
    tags = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )

    # ── Descriptions ──────────────────────────────────────────────────────
    description_short: Mapped[str] = mapped_column(Text, nullable=False)
    description_long: Mapped[str] = mapped_column(Text, nullable=False)
    highlights = mapped_column(JSON, nullable=False)              # JSONB array of strings
    included = mapped_column(JSON, nullable=False)                # JSONB array of strings
    excluded = mapped_column(JSON, nullable=False)                # JSONB array of strings
    what_to_bring: Mapped[str | None] = mapped_column(Text)
    important_notes = mapped_column(JSON, nullable=True)          # JSONB array of strings
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

    # ── Duration & Scheduling ─────────────────────────────────────────────
    duration_hours: Mapped[float | None] = mapped_column(Numeric(5, 1))
    duration_days: Mapped[int | None] = mapped_column(Integer)
    number_of_nights: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    departure_times = mapped_column(JSON, nullable=True)          # JSONB array of time strings
    operating_days = mapped_column(JSON, nullable=True)           # JSONB array of day names
    seasonal_availability: Mapped[str | None] = mapped_column(Text)
    boarding_time: Mapped[str | None] = mapped_column(String(50))
    instant_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    free_cancellation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    cancellation_hours: Mapped[int | None] = mapped_column(Integer)
    cancellation_policy: Mapped[str | None] = mapped_column(Text)
    advance_booking_days: Mapped[int | None] = mapped_column(Integer)

    # ── Location & Boarding ───────────────────────────────────────────────
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(200), nullable=False)
    area: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    lat: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    lng: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    maps_link: Mapped[str | None] = mapped_column(String(500))
    boarding_point_name: Mapped[str | None] = mapped_column(String(300))
    boarding_point_description: Mapped[str | None] = mapped_column(Text)
    nearby_landmark: Mapped[str | None] = mapped_column(String(300))
    pickup_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    pickup_points = mapped_column(JSON, nullable=True)  # JSONB array

    # ── Vessel Details ────────────────────────────────────────────────────
    vessel_name: Mapped[str | None] = mapped_column(String(300))
    vessel_type: Mapped[str | None] = mapped_column(String(100))  # Dhow/Yacht/Catamaran/Riverboat/Cruise Ship
    vessel_length_m: Mapped[float | None] = mapped_column(Numeric(6, 1))
    vessel_year_built: Mapped[int | None] = mapped_column(Integer)
    vessel_capacity: Mapped[int | None] = mapped_column(Integer)
    deck_count: Mapped[int | None] = mapped_column(Integer)
    onboard_facilities = mapped_column(JSON, nullable=True)  # JSONB array of strings

    # ── Onboard Experience ────────────────────────────────────────────────
    meal_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    meal_type: Mapped[str | None] = mapped_column(String(100))  # Buffet/Set Menu/A La Carte
    entertainment_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    entertainment_details = mapped_column(JSON, nullable=True)  # JSONB array of strings
    wifi_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # ── Route ─────────────────────────────────────────────────────────────
    route_description: Mapped[str | None] = mapped_column(Text)

    # ── Eligibility & Requirements ────────────────────────────────────────
    min_age: Mapped[int | None] = mapped_column(Integer)
    max_age: Mapped[int | None] = mapped_column(Integer)
    age_pricing_breaks = mapped_column(JSON, nullable=True)  # JSONB e.g. {"child_free_under": 6, "child_50pct_under": 12}
    dress_code: Mapped[str | None] = mapped_column(String(200))
    wheelchair_accessible: Mapped[str | None] = mapped_column(String(50))  # Yes/No/Partially
    languages = mapped_column(JSON, nullable=True)            # JSONB array of ISO codes
    fitness_level: Mapped[str | None] = mapped_column(String(50))
    pregnancy_restriction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # ── Operator ──────────────────────────────────────────────────────────
    operator_name: Mapped[str | None] = mapped_column(String(300))
    operator_website: Mapped[str | None] = mapped_column(String(500))
    operator_license_body: Mapped[str | None] = mapped_column(String(300))
    operator_established_year: Mapped[int | None] = mapped_column(Integer)
    operator_fleet_size: Mapped[int | None] = mapped_column(Integer)
    operator_certifications = mapped_column(JSON, nullable=True)  # JSONB array

    # ── Images & Media ────────────────────────────────────────────────────
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    gallery_json = mapped_column(JSON, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500))

    # ── Reviews & Ratings ─────────────────────────────────────────────────
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
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
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    dedup_hash: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False
    )
    quality_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

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
    itinerary: Mapped[list["CruiseItinerary"]] = relationship(
        back_populates="cruise",
        cascade="all, delete-orphan",
        order_by="CruiseItinerary.order",
    )
    cabins: Mapped[list["CruiseCabin"]] = relationship(
        back_populates="cruise",
        cascade="all, delete-orphan",
    )
    pricing_tiers: Mapped[list["CruisePricingTier"]] = relationship(
        back_populates="cruise",
        cascade="all, delete-orphan",
    )


class CruiseItinerary(Base):
    """Day-by-day or hour-by-hour itinerary for a cruise."""
    __tablename__ = "catalog_cruise_itinerary"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    cruise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_cruise_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    day_number: Mapped[int | None] = mapped_column(Integer)  # For multi-day cruises
    time_label: Mapped[str | None] = mapped_column(String(100))
    port_or_stop: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    shore_excursion_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    cruise: Mapped["CruiseProduct"] = relationship(back_populates="itinerary")


class CruiseCabin(Base):
    """Cabin types for overnight cruises."""
    __tablename__ = "catalog_cruise_cabins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    cruise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_cruise_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cabin_type: Mapped[str] = mapped_column(String(100), nullable=False)  # Interior/Ocean View/Balcony/Suite
    cabin_count: Mapped[int | None] = mapped_column(Integer)
    max_occupancy: Mapped[int | None] = mapped_column(Integer)
    amenities = mapped_column(JSON, nullable=True)  # JSONB array of strings
    description: Mapped[str | None] = mapped_column(Text)

    cruise: Mapped["CruiseProduct"] = relationship(back_populates="cabins")


class CruisePricingTier(Base):
    """Cabin-based pricing for multi-day cruises."""
    __tablename__ = "catalog_cruise_pricing_tiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    cruise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_cruise_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cabin_type: Mapped[str] = mapped_column(String(100), nullable=False)
    price_adult: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_child: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_infant: Mapped[float | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    includes_description: Mapped[str | None] = mapped_column(Text)

    cruise: Mapped["CruiseProduct"] = relationship(back_populates="pricing_tiers")
