from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Response Models ───────────────────────────────────────────────────────


class ActivityCard(BaseModel):
    """Slim model for listing cards."""

    id: UUID
    name: str
    slug: str
    category: str
    city: str
    price_from: float
    currency: str
    rating: float | None = None
    review_count: int = 0
    cover_image_url: str | None = None
    instant_confirmation: bool = False
    free_cancellation: bool = False
    duration_minutes: int
    quality_score: int = 0
    status: str = "draft"
    is_package: bool = False
    has_transport: bool = False
    has_meals: bool = False

    model_config = {"from_attributes": True}


class ActivityTimelineItem(BaseModel):
    """Timeline step for activity flow."""
    id: UUID
    order: int
    time_label: str | None = None
    title: str
    description: str | None = None

    model_config = {"from_attributes": True}


class ActivityResponse(BaseModel):
    """Full activity detail response."""

    id: UUID
    name: str
    slug: str
    city_id: UUID
    category: str
    sub_category: str | None = None
    activity_type: str
    tags: list | None = None
    status: str
    description_short: str
    description_long: str
    highlights: list | None = None
    included: list | None = None
    excluded: list | None = None
    what_to_bring: str | None = None
    important_notes: list | None = None
    redemption_instructions: list | None = None
    price_adult: float
    price_child: float | None = None
    price_infant: float | None = None
    price_group: float | None = None
    price_original: float | None = None
    currency: str
    price_type: str
    discount_pct: float | None = None
    price_from: float
    scraped_prices: list | None = None
    local_currency: str | None = None
    price_local: float | None = None
    duration_minutes: int
    start_times: list | None = None
    operating_days: list | None = None
    instant_confirmation: bool = False
    free_cancellation: bool = False
    cancellation_hours: int | None = None
    cancellation_policy: str | None = None
    min_participants: int | None = None
    max_participants: int | None = None
    advance_booking_days: int | None = None
    country: str
    city: str
    area: str | None = None
    address: str
    lat: float
    lng: float
    maps_link: str | None = None
    meeting_point_name: str | None = None
    meeting_point_desc: str | None = None
    nearby_landmark: str | None = None
    pickup_available: bool = False
    pickup_locations: list | None = None
    hotel_pickup_included: bool = False
    dropoff_available: bool = False
    refund_policy_details: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    fitness_level: str | None = None
    difficulty: str | None = None
    pregnancy_restriction: bool = False
    wheelchair_access: str | None = None
    dress_code_note: str | None = None
    languages: list | None = None
    cover_image_url: str | None = None
    gallery_json: list | None = None
    video_url: str | None = None
    rating: float | None = None
    review_count: int = 0
    rating_5: int = 0
    rating_4: int = 0
    rating_3: int = 0
    rating_2: int = 0
    rating_1: int = 0
    review_snippets: list | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    focus_keyword: str | None = None
    json_ld: dict | None = None
    canonical_url: str | None = None
    source_url: str
    source_urls: list[str] | None = None
    source_type: str
    operator_name: str | None = None
    operator_website: str | None = None
    operator_established_year: int | None = None
    operator_certifications: list | None = None
    verified: bool = False
    dedup_hash: str
    quality_score: int = 0
    is_package: bool = False
    has_transport: bool = False
    has_meals: bool = False
    faqs: list | None = None
    other_attributes: list | None = None
    timeline: list[ActivityTimelineItem] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Input Models ──────────────────────────────────────────────────────────


class ActivityCreate(BaseModel):
    """Required fields for creating an activity."""

    name: str = Field(min_length=1, max_length=300)
    city_id: UUID
    category: str = Field(min_length=1, max_length=100)
    activity_type: str = Field(min_length=1, max_length=100)
    description_short: str = Field(min_length=1)
    description_long: str = Field(min_length=1)
    highlights: list[str]
    included: list[str]
    excluded: list[str]
    price_adult: float
    currency: str = Field(min_length=1, max_length=3)
    price_type: str = Field(min_length=1, max_length=50)
    price_from: float
    duration_minutes: int
    start_times: list[str]
    operating_days: list[str]
    country: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    lat: float
    lng: float
    languages: list[str]
    source_url: str = Field(min_length=1, max_length=500)
    source_type: str = Field(min_length=1, max_length=50)
    dedup_hash: str = Field(min_length=1, max_length=32)

    # Optional fields
    sub_category: str | None = None
    tags: list | None = None
    what_to_bring: str | None = None
    important_notes: list | None = None
    redemption_instructions: list | None = None
    price_child: float | None = None
    price_infant: float | None = None
    price_group: float | None = None
    price_original: float | None = None
    discount_pct: float | None = None
    cancellation_hours: int | None = None
    cancellation_policy: str | None = None
    min_participants: int | None = None
    max_participants: int | None = None
    advance_booking_days: int | None = None
    area: str | None = None
    maps_link: str | None = None
    meeting_point_name: str | None = None
    meeting_point_desc: str | None = None
    nearby_landmark: str | None = None
    pickup_locations: list | None = None
    refund_policy_details: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    fitness_level: str | None = None
    difficulty: str | None = None
    wheelchair_access: str | None = None
    cover_image_url: str | None = None
    gallery_json: list | None = None
    video_url: str | None = None
    rating: float | None = None
    review_count: int = 0
    review_snippets: list | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    focus_keyword: str | None = None
    json_ld: dict | None = None
    canonical_url: str | None = None
    operator_name: str | None = None
    operator_website: str | None = None
    operator_established_year: int | None = None
    operator_certifications: list | None = None
    dress_code_note: str | None = None
    other_attributes: list | None = None


class ActivityUpdate(BaseModel):
    """All fields optional for PATCH."""

    name: str | None = Field(default=None, min_length=1, max_length=300)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    sub_category: str | None = None
    activity_type: str | None = None
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
    duration_minutes: int | None = None
    start_times: list | None = None
    operating_days: list | None = None
    instant_confirmation: bool | None = None
    free_cancellation: bool | None = None
    cancellation_hours: int | None = None
    cancellation_policy: str | None = None
    min_participants: int | None = None
    max_participants: int | None = None
    advance_booking_days: int | None = None
    country: str | None = None
    city: str | None = None
    area: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    maps_link: str | None = None
    meeting_point_name: str | None = None
    meeting_point_desc: str | None = None
    nearby_landmark: str | None = None
    pickup_available: bool | None = None
    pickup_locations: list | None = None
    hotel_pickup_included: bool | None = None
    dropoff_available: bool | None = None
    refund_policy_details: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    fitness_level: str | None = None
    difficulty: str | None = None
    pregnancy_restriction: bool | None = None
    wheelchair_access: str | None = None
    languages: list | None = None
    cover_image_url: str | None = None
    gallery_json: list | None = None
    video_url: str | None = None
    rating: float | None = None
    review_count: int | None = None
    review_snippets: list | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    focus_keyword: str | None = None
    json_ld: dict | None = None
    canonical_url: str | None = None
    operator_name: str | None = None
    operator_website: str | None = None
    operator_established_year: int | None = None
    operator_certifications: list | None = None
    dress_code_note: str | None = None
    faqs: list | None = None
    other_attributes: list | None = None
    verified: bool | None = None
    quality_score: int | None = None
    is_package: bool | None = None
    has_transport: bool | None = None
    has_meals: bool | None = None


class ActivityStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=20)


class ActivityFilters(BaseModel):
    """Query parameters for activity listing."""

    category: str | None = None
    sub_category: str | None = None
    city_id: UUID | None = None
    min_price: float | None = None
    max_price: float | None = None
    free_cancellation: bool | None = None
    instant_confirmation: bool | None = None
    languages: str | None = None
    fitness_level: str | None = None
    search: str | None = None
    status: str | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)
