import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_db, require_role
from app.db.models.auth import AuthUser
from app.schemas.reviews import ReviewListResponse, ReviewResponse, ScrapeReviewsRequest
from app.services.review_service import get_reviews_for_activity, scrape_reviews_for_activity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activities/{activity_id}/reviews", tags=["reviews"])

MANAGER_ROLES = ("product_manager", "admin")


@router.get("", response_model=ReviewListResponse)
async def list_reviews(
    activity_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get all reviews for an activity."""
    data = await get_reviews_for_activity(db, activity_id)
    return ReviewListResponse(
        activity_id=data["activity_id"],
        total=data["total"],
        avg_rating=data["avg_rating"],
        platform_counts=data["platform_counts"],
        reviews=[ReviewResponse.model_validate(r) for r in data["reviews"]],
    )


@router.post("/scrape")
async def scrape_reviews(
    activity_id: UUID,
    body: ScrapeReviewsRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Trigger review scraping for an activity from external platforms."""
    platforms = body.platforms if body else None
    result = await scrape_reviews_for_activity(db, activity_id, platforms)
    await db.commit()
    return result
