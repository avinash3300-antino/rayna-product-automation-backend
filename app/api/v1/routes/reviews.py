import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_db, require_role
from app.db.models.auth import AuthUser
from app.schemas.reviews import ReviewListResponse, ReviewResponse, ScrapeReviewsRequest
from app.services.review_service import (
    get_reviews_for_product,
    scrape_reviews_for_product,
    enrich_reviews_for_product,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reviews", tags=["reviews"])

MANAGER_ROLES = ("product_manager", "admin")


@router.get("/{product_type}/{product_id}", response_model=ReviewListResponse)
async def list_reviews(
    product_type: str,
    product_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get all reviews for a product (any type)."""
    data = await get_reviews_for_product(db, product_id, product_type=product_type)
    return ReviewListResponse(
        product_id=data["product_id"],
        product_type=data["product_type"],
        total=data["total"],
        avg_rating=data["avg_rating"],
        platform_counts=data["platform_counts"],
        reviews=[ReviewResponse.model_validate(r) for r in data["reviews"]],
    )


@router.post("/{product_type}/{product_id}/scrape")
async def scrape_reviews(
    product_type: str,
    product_id: UUID,
    body: ScrapeReviewsRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Trigger review scraping for a product from external platforms."""
    platforms = body.platforms if body else None
    result = await scrape_reviews_for_product(
        db, product_id,
        product_type=product_type,
        platforms=platforms,
    )
    await db.commit()
    return result


# ── Backward-compatible activity-specific endpoints ──────────────────────


activity_review_router = APIRouter(
    prefix="/activities/{activity_id}/reviews", tags=["reviews"]
)


@activity_review_router.get("", response_model=ReviewListResponse)
async def list_activity_reviews(
    activity_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get all reviews for an activity (backward compatible)."""
    data = await get_reviews_for_product(db, activity_id, product_type="activities")
    return ReviewListResponse(
        product_id=data["product_id"],
        product_type="activities",
        total=data["total"],
        avg_rating=data["avg_rating"],
        platform_counts=data["platform_counts"],
        reviews=[ReviewResponse.model_validate(r) for r in data["reviews"]],
    )


@activity_review_router.post("/scrape")
async def scrape_activity_reviews(
    activity_id: UUID,
    body: ScrapeReviewsRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Trigger review scraping for an activity (backward compatible)."""
    platforms = body.platforms if body else None
    result = await scrape_reviews_for_product(
        db, activity_id,
        product_type="activities",
        platforms=platforms,
    )
    await db.commit()
    return result


@activity_review_router.post("/enrich")
async def enrich_activity_reviews(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Enrich all reviews for an activity using Claude AI."""
    result = await enrich_reviews_for_product(
        db, activity_id, product_type="activities"
    )
    await db.commit()
    return result
