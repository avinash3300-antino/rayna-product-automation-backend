from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Nested Response Models ───────────────────────────────────────────────


class CruiseItineraryItem(BaseModel):
    id: UUID
    order: int
    day_number: int | None = None
    time_label: str | None = None
    port_or_stop: str | None = None
    description: str | None = None
    shore_excursion_available: bool = False

    model_config = {"from_attributes": True}


class CruiseCabinItem(BaseModel):
    id: UUID
    cabin_type: str
    cabin_count: int | None = None
    max_occupancy: int | None = None
    amenities: list | None = None
    description: str | None = None

    model_config = {"from_attributes": True}


class CruisePricingTierItem(BaseModel):
    id: UUID
    cabin_type: str
    price_adult: float | None = None
    price_child: float | None = None
    price_infant: float | None = None
    currency: str
    includes_description: str | None = None

    model_config = {"from_attributes": True}


# ── Response Models ───────────────────────────────────────────────────────


class CruiseCard(BaseModel):
    """Slim model for listing cards."""

    id: UUID
    name: str
    slug: str
    sub_category: str | None = None
    cruise_type: str | None = None
    city: str
    price_from: float
    currency: str
    rating: float | None = None
    review_count: int = 0
    cover_image_url: str | None = None
    instant_confirmation: bool = False
    free_cancellation: bool = False
    duration_hours: float | None = None
    number_of_nights: int = 0
    meal_included: bool = False
    vessel_type: str | None = None
    quality_score: int = 0
    status: str = "draft"

    model_config = {"from_attributes": True}


class CruiseResponse(BaseModel):
    """Full cruise detail response."""

    id: UUID
    name: str
    slug: str
    city_id: UUID
    # Classification
    category: str
    sub_category: str | None = None
    cruise_class: str | None = None
    cruise_type: str | None = None
    tags: list | None = None
    status: str
    # Descriptions
    description_short: str
    description_long: str
    highlights: list | None = None
    included: list | None = None
    excluded: list | None = None
    what_to_bring: str | None = None
    important_notes: list | None = None
    redemption_instructions: list | None = None
    # Pricing
    price_adult: float
    price_child: float | None = None
    price_infant: float | None = None
    price_group: float | None = None
    price_original: float | None = None
    currency: str
    price_type: str
    discount_pct: float | None = None
    price_from: float
    # Duration
    duration_hours: float | None = None
    duration_days: int | None = None
    number_of_nights: int = 0
    departure_times: list | None = None
    operating_days: list | None = None
    seasonal_availability: str | None = None
    boarding_time: str | None = None
    instant_confirmation: bool = False
    free_cancellation: bool = False
    cancellation_hours: int | None = None
    cancellation_policy: str | None = None
    advance_booking_days: int | None = None
    # Location
    country: str
    city: str
    area: str | None = None
    address: str
    lat: float
    lng: float
    maps_link: str | None = None
    boarding_point_name: str | None = None
    boarding_point_description: str | None = None
    nearby_landmark: str | None = None
    pickup_available: bool = False
    pickup_points: list | None = None
    # Vessel
    vessel_name: str | None = None
    vessel_type: str | None = None
    vessel_length_m: float | None = None
    vessel_year_built: int | None = None
    vessel_capacity: int | None = None
    deck_count: int | None = None
    onboard_facilities: list | None = None
    # Onboard
    meal_included: bool = False
    meal_type: str | None = None
    entertainment_included: bool = False
    entertainment_details: list | None = None
    wifi_available: bool = False
    # Route
    route_description: str | None = None
    # Eligibility
    min_age: int | None = None
    max_age: int | None = None
    age_pricing_breaks: dict | None = None
    dress_code: str | None = None
    wheelchair_accessible: str | None = None
    languages: list | None = None
    fitness_level: str | None = None
    pregnancy_restriction: bool = False
    # Operator
    operator_name: str | None = None
    operator_website: str | None = None
    operator_license_body: str | None = None
    operator_established_year: int | None = None
    operator_fleet_size: int | None = None
    operator_certifications: list | None = None
    # Media
    cover_image_url: str | None = None
    gallery_json: list | None = None
    video_url: str | None = None
    # Reviews
    rating: float | None = None
    review_count: int = 0
    rating_5: int = 0
    rating_4: int = 0
    rating_3: int = 0
    rating_2: int = 0
    rating_1: int = 0
    review_snippets: list | None = None
    # SEO
    meta_title: str | None = None
    meta_description: str | None = None
    focus_keyword: str | None = None
    json_ld: dict | None = None
    canonical_url: str | None = None
    # Source
    source_url: str
    source_urls: list[str] | None = None
    source_type: str
    verified: bool = False
    dedup_hash: str
    quality_score: int = 0
    other_attributes: list | None = None
    # Nested
    itinerary: list[CruiseItineraryItem] = []
    cabins: list[CruiseCabinItem] = []
    pricing_tiers: list[CruisePricingTierItem] = []
    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Input Models ──────────────────────────────────────────────────────────


class CruiseUpdate(BaseModel):
    """All fields optional for PATCH."""

    name: str | None = Field(default=None, min_length=1, max_length=300)
    sub_category: str | None = None
    cruise_class: str | None = None
    cruise_type: str | None = None
    tags: list | None = None
    status: str | None = None
    description_short: str | None = None
    description_long: str | None = None
    highlights: list | None = None
    included: list | None = None
    excluded: list | None = None
    what_to_bring: str | None = None
    important_notes: list | None = None
    redemption_instructions: list | None = None
    price_adult: float | None = None
    price_child: float | None = None
    price_infant: float | None = None
    price_group: float | None = None
    price_original: float | None = None
    currency: str | None = None
    price_type: str | None = None
    discount_pct: float | None = None
    price_from: float | None = None
    duration_hours: float | None = None
    duration_days: int | None = None
    number_of_nights: int | None = None
    departure_times: list | None = None
    operating_days: list | None = None
    seasonal_availability: str | None = None
    boarding_time: str | None = None
    instant_confirmation: bool | None = None
    free_cancellation: bool | None = None
    cancellation_hours: int | None = None
    cancellation_policy: str | None = None
    advance_booking_days: int | None = None
    country: str | None = None
    city: str | None = None
    area: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    maps_link: str | None = None
    boarding_point_name: str | None = None
    boarding_point_description: str | None = None
    nearby_landmark: str | None = None
    pickup_available: bool | None = None
    pickup_points: list | None = None
    # Vessel
    vessel_name: str | None = None
    vessel_type: str | None = None
    vessel_length_m: float | None = None
    vessel_year_built: int | None = None
    vessel_capacity: int | None = None
    deck_count: int | None = None
    onboard_facilities: list | None = None
    # Onboard
    meal_included: bool | None = None
    meal_type: str | None = None
    entertainment_included: bool | None = None
    entertainment_details: list | None = None
    wifi_available: bool | None = None
    route_description: str | None = None
    # Eligibility
    min_age: int | None = None
    max_age: int | None = None
    age_pricing_breaks: dict | None = None
    dress_code: str | None = None
    wheelchair_accessible: str | None = None
    languages: list | None = None
    fitness_level: str | None = None
    pregnancy_restriction: bool | None = None
    # Operator
    operator_name: str | None = None
    operator_website: str | None = None
    operator_license_body: str | None = None
    operator_established_year: int | None = None
    operator_fleet_size: int | None = None
    operator_certifications: list | None = None
    # Media
    cover_image_url: str | None = None
    gallery_json: list | None = None
    video_url: str | None = None
    # Review
    rating: float | None = None
    review_count: int | None = None
    review_snippets: list | None = None
    # SEO
    meta_title: str | None = None
    meta_description: str | None = None
    focus_keyword: str | None = None
    json_ld: dict | None = None
    canonical_url: str | None = None
    other_attributes: list | None = None
    verified: bool | None = None
    quality_score: int | None = None


class CruiseStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=20)


class CruiseFilters(BaseModel):
    """Query parameters for cruise listing."""

    sub_category: str | None = None
    cruise_type: str | None = None
    vessel_type: str | None = None
    city_id: UUID | None = None
    min_price: float | None = None
    max_price: float | None = None
    free_cancellation: bool | None = None
    instant_confirmation: bool | None = None
    meal_included: bool | None = None
    search: str | None = None
    status: str | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)
