import logging
import uuid
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import CurrentUser, get_db, require_role
from app.core.exceptions import NotFoundError
from app.db.models.activities import Activity
from app.db.models.auth import AuthUser
from app.db.models.audit import AuditAuditLog
from app.schemas.activities import (
    ActivityCard,
    ActivityCreate,
    ActivityFilters,
    ActivityResponse,
    ActivityStatusUpdate,
    ActivityUpdate,
)
from app.schemas.destinations import PaginatedResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activities", tags=["activities"])

MANAGER_ROLES = ("product_manager", "admin")
ADMIN_ROLES = ("admin",)


async def _get_activity_with_timeline(db: AsyncSession, activity_id: UUID) -> Activity | None:
    """Fetch an activity with its timeline relationship eagerly loaded."""
    result = await db.execute(
        select(Activity)
        .options(selectinload(Activity.timeline))
        .where(Activity.id == activity_id)
    )
    return result.scalars().first()


def _json_safe(data: dict | None) -> dict | None:
    """Convert Decimal/UUID values so they're JSON-serializable for audit logs."""
    if data is None:
        return None
    out = {}
    for k, v in data.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    old_data: dict | None = None,
    new_data: dict | None = None,
) -> None:
    log = AuditAuditLog(
        actor_user_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_data=_json_safe(old_data),
        new_data=_json_safe(new_data),
    )
    db.add(log)
    await db.flush()


# ── List Activities ──────────────────────────────────────────────────────


@router.get("/cities", response_model=list[str])
async def list_activity_cities(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Return distinct city names from activities, sorted alphabetically."""
    result = await db.execute(
        select(Activity.city).where(Activity.city.isnot(None)).distinct().order_by(Activity.city)
    )
    return [row[0] for row in result.all()]


@router.get("", response_model=PaginatedResponse[ActivityCard])
async def list_activities(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    category: str | None = Query(None),
    sub_category: str | None = Query(None),
    city_id: UUID | None = Query(None),
    city: str | None = Query(None),
    min_price: float | None = Query(None),
    max_price: float | None = Query(None),
    free_cancellation: bool | None = Query(None),
    instant_confirmation: bool | None = Query(None),
    languages: str | None = Query(None),
    fitness_level: str | None = Query(None),
    search: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """List activities with filters and pagination."""
    query = select(Activity)
    count_query = select(func.count(Activity.id))

    if category:
        query = query.where(Activity.category == category)
        count_query = count_query.where(Activity.category == category)
    if sub_category:
        query = query.where(Activity.sub_category == sub_category)
        count_query = count_query.where(Activity.sub_category == sub_category)
    if city_id:
        query = query.where(Activity.city_id == city_id)
        count_query = count_query.where(Activity.city_id == city_id)
    if city:
        query = query.where(Activity.city.ilike(city))
        count_query = count_query.where(Activity.city.ilike(city))
    if min_price is not None:
        query = query.where(Activity.price_from >= min_price)
        count_query = count_query.where(Activity.price_from >= min_price)
    if max_price is not None:
        query = query.where(Activity.price_from <= max_price)
        count_query = count_query.where(Activity.price_from <= max_price)
    if free_cancellation is not None:
        query = query.where(Activity.free_cancellation == free_cancellation)
        count_query = count_query.where(Activity.free_cancellation == free_cancellation)
    if instant_confirmation is not None:
        query = query.where(Activity.instant_confirmation == instant_confirmation)
        count_query = count_query.where(Activity.instant_confirmation == instant_confirmation)
    if fitness_level:
        query = query.where(Activity.fitness_level == fitness_level)
        count_query = count_query.where(Activity.fitness_level == fitness_level)
    if status:
        query = query.where(Activity.status == status)
        count_query = count_query.where(Activity.status == status)
    if search:
        pattern = f"%{search}%"
        search_filter = Activity.name.ilike(pattern) | Activity.city.ilike(pattern)
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    query = query.order_by(Activity.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    activities = list(result.scalars().all())

    return PaginatedResponse(
        items=[ActivityCard.model_validate(a) for a in activities],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


# ── Get by Slug (BEFORE /{id} to avoid path collision) ──────────────────


@router.get("/slug/{slug}", response_model=ActivityResponse)
async def get_activity_by_slug(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get activity by slug."""
    result = await db.execute(
        select(Activity)
        .options(selectinload(Activity.timeline))
        .where(Activity.slug == slug)
    )
    activity = result.scalars().first()
    if not activity:
        raise NotFoundError("Activity not found")
    return ActivityResponse.model_validate(activity)


# ── Get by ID ────────────────────────────────────────────────────────────


@router.get("/{activity_id}", response_model=ActivityResponse)
async def get_activity(
    activity_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get activity details."""
    activity = await _get_activity_with_timeline(db, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")
    return ActivityResponse.model_validate(activity)


# ── Update Activity ──────────────────────────────────────────────────────


@router.patch("/{activity_id}", response_model=ActivityResponse)
async def update_activity(
    activity_id: UUID,
    body: ActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Update an activity (partial update)."""
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    data = body.model_dump(exclude_unset=True)
    old_data = {k: getattr(activity, k, None) for k in data}

    for field, value in data.items():
        if hasattr(activity, field):
            setattr(activity, field, value)

    await _write_audit(
        db, current_user.id, "activities", activity_id, "updated", old_data, data
    )
    await db.commit()

    # Re-fetch with timeline
    activity = await _get_activity_with_timeline(db, activity_id)
    return ActivityResponse.model_validate(activity)


# ── Status Change ────────────────────────────────────────────────────────


@router.patch("/{activity_id}/status", response_model=ActivityResponse)
async def update_activity_status(
    activity_id: UUID,
    body: ActivityStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Change activity status (draft → enriched → review_ready → approved → published)."""
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    old_status = activity.status
    activity.status = body.status

    await _write_audit(
        db,
        current_user.id,
        "activities",
        activity_id,
        "status_changed",
        {"status": old_status},
        {"status": body.status},
    )
    await db.commit()

    activity = await _get_activity_with_timeline(db, activity_id)
    return ActivityResponse.model_validate(activity)


# ── Delete Activity ──────────────────────────────────────────────────────


@router.delete("/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
):
    """Delete an activity (admin only)."""
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    old_data = {"name": activity.name, "slug": activity.slug, "city": activity.city}
    await db.delete(activity)

    await _write_audit(
        db, current_user.id, "activities", activity_id, "deleted", old_data, None
    )
    await db.commit()


# ── Re-enrich ────────────────────────────────────────────────────────────


@router.post("/{activity_id}/re-enrich", response_model=ActivityResponse)
async def re_enrich_activity(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Re-enrich an activity with AI (Claude + geocoding + images)."""
    from app.services.enrichment_service import enrich_activity

    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    activity = await enrich_activity(db, activity)
    await db.commit()

    activity = await _get_activity_with_timeline(db, activity_id)
    return ActivityResponse.model_validate(activity)


@router.post("/{activity_id}/scrape-pricing")
async def scrape_activity_pricing(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Scrape current pricing from source URLs."""
    from app.services.pricing_service import scrape_pricing_for_activity

    result = await scrape_pricing_for_activity(db, activity_id)
    await db.commit()
    return result
