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
from app.db.models.auth import AuthUser
from app.db.models.audit import AuditAuditLog
from app.db.models.cruises import CruiseProduct
from app.schemas.cruises import (
    CruiseCard,
    CruiseResponse,
    CruiseStatusUpdate,
    CruiseUpdate,
)
from app.schemas.destinations import PaginatedResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cruises", tags=["cruises"])

MANAGER_ROLES = ("product_manager", "admin")
ADMIN_ROLES = ("admin",)


def _json_safe(data: dict | None) -> dict | None:
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


# ── List Cruises ──────────────────────────────────────────────────────


@router.get("/cities", response_model=list[str])
async def list_cruise_cities(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Return distinct city names from cruises."""
    result = await db.execute(
        select(CruiseProduct.city)
        .where(CruiseProduct.city.isnot(None))
        .distinct()
        .order_by(CruiseProduct.city)
    )
    return [row[0] for row in result.all()]


@router.get("", response_model=PaginatedResponse[CruiseCard])
async def list_cruises(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    sub_category: str | None = Query(None),
    cruise_type: str | None = Query(None),
    vessel_type: str | None = Query(None),
    city_id: UUID | None = Query(None),
    city: str | None = Query(None),
    min_price: float | None = Query(None),
    max_price: float | None = Query(None),
    free_cancellation: bool | None = Query(None),
    instant_confirmation: bool | None = Query(None),
    meal_included: bool | None = Query(None),
    search: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """List cruises with filters and pagination."""
    query = select(CruiseProduct)
    count_query = select(func.count(CruiseProduct.id))

    if sub_category:
        query = query.where(CruiseProduct.sub_category == sub_category)
        count_query = count_query.where(CruiseProduct.sub_category == sub_category)
    if cruise_type:
        query = query.where(CruiseProduct.cruise_type == cruise_type)
        count_query = count_query.where(CruiseProduct.cruise_type == cruise_type)
    if vessel_type:
        query = query.where(CruiseProduct.vessel_type == vessel_type)
        count_query = count_query.where(CruiseProduct.vessel_type == vessel_type)
    if city_id:
        query = query.where(CruiseProduct.city_id == city_id)
        count_query = count_query.where(CruiseProduct.city_id == city_id)
    if city:
        query = query.where(CruiseProduct.city.ilike(city))
        count_query = count_query.where(CruiseProduct.city.ilike(city))
    if min_price is not None:
        query = query.where(CruiseProduct.price_from >= min_price)
        count_query = count_query.where(CruiseProduct.price_from >= min_price)
    if max_price is not None:
        query = query.where(CruiseProduct.price_from <= max_price)
        count_query = count_query.where(CruiseProduct.price_from <= max_price)
    if free_cancellation is not None:
        query = query.where(CruiseProduct.free_cancellation == free_cancellation)
        count_query = count_query.where(CruiseProduct.free_cancellation == free_cancellation)
    if instant_confirmation is not None:
        query = query.where(CruiseProduct.instant_confirmation == instant_confirmation)
        count_query = count_query.where(CruiseProduct.instant_confirmation == instant_confirmation)
    if meal_included is not None:
        query = query.where(CruiseProduct.meal_included == meal_included)
        count_query = count_query.where(CruiseProduct.meal_included == meal_included)
    if status:
        query = query.where(CruiseProduct.status == status)
        count_query = count_query.where(CruiseProduct.status == status)
    if search:
        pattern = f"%{search}%"
        search_filter = CruiseProduct.name.ilike(pattern) | CruiseProduct.city.ilike(pattern)
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    query = query.order_by(CruiseProduct.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    cruises = list(result.scalars().all())

    return PaginatedResponse(
        items=[CruiseCard.model_validate(c) for c in cruises],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


# ── Get by Slug ────────────────────────────────────────────────────────


@router.get("/slug/{slug}", response_model=CruiseResponse)
async def get_cruise_by_slug(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get cruise by slug."""
    result = await db.execute(
        select(CruiseProduct)
        .where(CruiseProduct.slug == slug)
        .options(
            selectinload(CruiseProduct.itinerary),
            selectinload(CruiseProduct.cabins),
            selectinload(CruiseProduct.pricing_tiers),
        )
    )
    cruise = result.scalar_one_or_none()
    if not cruise:
        raise NotFoundError("Cruise not found")
    return CruiseResponse.model_validate(cruise)


# ── Get by ID ──────────────────────────────────────────────────────────


@router.get("/{cruise_id}", response_model=CruiseResponse)
async def get_cruise(
    cruise_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get cruise details."""
    result = await db.execute(
        select(CruiseProduct)
        .where(CruiseProduct.id == cruise_id)
        .options(
            selectinload(CruiseProduct.itinerary),
            selectinload(CruiseProduct.cabins),
            selectinload(CruiseProduct.pricing_tiers),
        )
    )
    cruise = result.scalar_one_or_none()
    if not cruise:
        raise NotFoundError("Cruise not found")
    return CruiseResponse.model_validate(cruise)


# ── Update Cruise ──────────────────────────────────────────────────────


@router.patch("/{cruise_id}", response_model=CruiseResponse)
async def update_cruise(
    cruise_id: UUID,
    body: CruiseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Update a cruise (partial update)."""
    cruise = await db.get(CruiseProduct, cruise_id)
    if not cruise:
        raise NotFoundError("Cruise not found")

    data = body.model_dump(exclude_unset=True)
    old_data = {k: getattr(cruise, k, None) for k in data}

    for field, value in data.items():
        if hasattr(cruise, field):
            setattr(cruise, field, value)

    await _write_audit(
        db, current_user.id, "cruises", cruise_id, "updated", old_data, data
    )
    await db.commit()

    cruise = await db.get(CruiseProduct, cruise_id)
    return CruiseResponse.model_validate(cruise)


# ── Status Change ──────────────────────────────────────────────────────


@router.patch("/{cruise_id}/status", response_model=CruiseResponse)
async def update_cruise_status(
    cruise_id: UUID,
    body: CruiseStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Change cruise status."""
    cruise = await db.get(CruiseProduct, cruise_id)
    if not cruise:
        raise NotFoundError("Cruise not found")

    old_status = cruise.status
    cruise.status = body.status

    await _write_audit(
        db, current_user.id, "cruises", cruise_id, "status_changed",
        {"status": old_status}, {"status": body.status},
    )
    await db.commit()

    cruise = await db.get(CruiseProduct, cruise_id)
    return CruiseResponse.model_validate(cruise)


# ── Delete Cruise ──────────────────────────────────────────────────────


@router.delete("/{cruise_id}", status_code=204)
async def delete_cruise(
    cruise_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
):
    """Delete a cruise (admin only)."""
    cruise = await db.get(CruiseProduct, cruise_id)
    if not cruise:
        raise NotFoundError("Cruise not found")

    old_data = {"name": cruise.name, "slug": cruise.slug, "city": cruise.city}
    await db.delete(cruise)

    await _write_audit(
        db, current_user.id, "cruises", cruise_id, "deleted", old_data, None
    )
    await db.commit()


# ── Re-enrich ──────────────────────────────────────────────────────────


@router.post("/{cruise_id}/re-enrich", response_model=CruiseResponse)
async def re_enrich_cruise(
    cruise_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Re-enrich a cruise with AI."""
    from app.services.pipelines.cruise_pipeline import CruisePipeline

    cruise = await db.get(CruiseProduct, cruise_id)
    if not cruise:
        raise NotFoundError("Cruise not found")

    pipeline = CruisePipeline()
    await pipeline.enrich_product(db, cruise)
    await db.commit()

    cruise = await db.get(CruiseProduct, cruise_id)
    return CruiseResponse.model_validate(cruise)
