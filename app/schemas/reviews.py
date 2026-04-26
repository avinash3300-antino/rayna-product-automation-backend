from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReviewResponse(BaseModel):
    id: UUID
    product_type: str
    product_id: UUID
    reviewer_name: str
    reviewer_avatar_url: str | None = None
    rating: float | None = None
    review_title: str | None = None
    review_text: str
    enriched_text: str | None = None
    enriched_reviewer_name: str | None = None
    review_date: str | None = None
    source_platform: str
    source_url: str | None = None
    verified: bool = False
    language: str = "en"
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    product_id: UUID
    product_type: str = "activities"
    total: int
    avg_rating: float | None = None
    platform_counts: dict[str, int] = {}
    reviews: list[ReviewResponse] = []


class ScrapeReviewsRequest(BaseModel):
    platforms: list[str] | None = None  # ["google", "tripadvisor", "trustpilot"]
