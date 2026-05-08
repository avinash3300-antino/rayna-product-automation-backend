import csv
import io
import json
import logging
import uuid
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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


@router.get("/categories", response_model=list[str])
async def list_activity_categories(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Return distinct category names from activities, sorted alphabetically."""
    result = await db.execute(
        select(Activity.category)
        .where(Activity.category.isnot(None))
        .distinct()
        .order_by(Activity.category)
    )
    return [row[0] for row in result.all()]


@router.get("/export")
async def export_activities_csv(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    city: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
):
    """Export all activities as CSV. Optionally filter by city/category/status."""
    query = select(Activity)
    if city:
        query = query.where(Activity.city.ilike(city))
    if category:
        query = query.where(Activity.category == category)
    if status:
        query = query.where(Activity.status == status)
    query = query.order_by(Activity.city, Activity.category, Activity.name)

    result = await db.execute(query)
    activities = result.scalars().all()

    CSV_COLUMNS = [
        ("id", lambda a: str(a.id)),
        ("name", lambda a: a.name),
        ("slug", lambda a: a.slug),
        ("status", lambda a: a.status),
        ("category", lambda a: a.category),
        ("sub_category", lambda a: a.sub_category or ""),
        ("activity_type", lambda a: a.activity_type or ""),
        ("city", lambda a: a.city or ""),
        ("country", lambda a: a.country or ""),
        ("area", lambda a: a.area or ""),
        ("address", lambda a: a.address or ""),
        ("lat", lambda a: a.lat),
        ("lng", lambda a: a.lng),
        ("price_adult", lambda a: a.price_adult),
        ("price_child", lambda a: a.price_child or ""),
        ("price_infant", lambda a: a.price_infant or ""),
        ("price_group", lambda a: a.price_group or ""),
        ("price_original", lambda a: a.price_original or ""),
        ("price_from", lambda a: a.price_from),
        ("currency", lambda a: a.currency or ""),
        ("local_currency", lambda a: a.local_currency or ""),
        ("price_local", lambda a: a.price_local or ""),
        ("price_type", lambda a: a.price_type or ""),
        ("discount_pct", lambda a: a.discount_pct or ""),
        ("duration_minutes", lambda a: a.duration_minutes),
        ("rating", lambda a: a.rating or ""),
        ("review_count", lambda a: a.review_count or 0),
        ("quality_score", lambda a: a.quality_score or 0),
        ("free_cancellation", lambda a: a.free_cancellation),
        ("instant_confirmation", lambda a: a.instant_confirmation),
        ("cancellation_hours", lambda a: a.cancellation_hours or ""),
        ("description_short", lambda a: a.description_short or ""),
        ("description_long", lambda a: a.description_long or ""),
        ("highlights", lambda a: json.dumps(a.highlights) if a.highlights else ""),
        ("included", lambda a: json.dumps(a.included) if a.included else ""),
        ("excluded", lambda a: json.dumps(a.excluded) if a.excluded else ""),
        ("tags", lambda a: json.dumps(a.tags) if a.tags else ""),
        ("operating_days", lambda a: json.dumps(a.operating_days) if a.operating_days else ""),
        ("start_times", lambda a: json.dumps(a.start_times) if a.start_times else ""),
        ("languages", lambda a: json.dumps(a.languages) if a.languages else ""),
        ("source_url", lambda a: a.source_url or ""),
        ("source_urls", lambda a: json.dumps(a.source_urls) if a.source_urls else ""),
        ("source_type", lambda a: a.source_type or ""),
        ("operator_name", lambda a: a.operator_name or ""),
        ("cover_image_url", lambda a: a.cover_image_url or ""),
        ("gallery_count", lambda a: len(a.gallery_json) if a.gallery_json else 0),
        ("pickup_available", lambda a: a.pickup_available),
        ("hotel_pickup_included", lambda a: a.hotel_pickup_included),
        ("min_age", lambda a: a.min_age or ""),
        ("max_age", lambda a: a.max_age or ""),
        ("fitness_level", lambda a: a.fitness_level or ""),
        ("wheelchair_access", lambda a: a.wheelchair_access or ""),
        ("meta_title", lambda a: a.meta_title or ""),
        ("meta_description", lambda a: a.meta_description or ""),
        ("verified", lambda a: a.verified),
        ("created_at", lambda a: a.created_at.isoformat() if a.created_at else ""),
        ("updated_at", lambda a: a.updated_at.isoformat() if a.updated_at else ""),
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([col[0] for col in CSV_COLUMNS])
    for act in activities:
        writer.writerow([col[1](act) for col in CSV_COLUMNS])

    output.seek(0)
    filename = f"activities{'_' + city if city else ''}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    is_package: bool | None = Query(None),
    has_transport: bool | None = Query(None),
    has_meals: bool | None = Query(None),
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
    if is_package is not None:
        query = query.where(Activity.is_package == is_package)
        count_query = count_query.where(Activity.is_package == is_package)
    if has_transport is not None:
        query = query.where(Activity.has_transport == has_transport)
        count_query = count_query.where(Activity.has_transport == has_transport)
    if has_meals is not None:
        query = query.where(Activity.has_meals == has_meals)
        count_query = count_query.where(Activity.has_meals == has_meals)
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


# ── Generate FAQs ─────────────────────────────────────────────────────


@router.post("/{activity_id}/generate-faqs")
async def generate_activity_faqs(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Generate FAQs for an activity using AI based on its content."""
    from app.services.faq_service import generate_faqs_for_activity

    faqs = await generate_faqs_for_activity(db, activity_id)
    await db.commit()
    return {"faqs": faqs, "count": len(faqs)}


# ── Download Images ───────────────────────────────────────────────────


class DownloadImagesRequest(BaseModel):
    formats: list[str] = ["L", "S", "P", "2_1", "3_2"]
    scale: str = "1x"
    image_index: int | None = None  # None = all images


@router.post("/{activity_id}/download-images")
async def download_activity_images(
    activity_id: UUID,
    body: DownloadImagesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """Download gallery images as a zip with Cloudinary-transformed variants."""
    import asyncio
    import zipfile
    from io import BytesIO

    import httpx

    from app.utils.image_formats import (
        IMAGE_FORMATS,
        SCALE_MULTIPLIERS,
        get_format_dimensions,
        transform_cloudinary_url,
    )

    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    gallery = activity.gallery_json or []
    if not gallery:
        raise NotFoundError("Activity has no gallery images")

    # Validate inputs
    valid_formats = [f for f in body.formats if f in IMAGE_FORMATS]
    if not valid_formats:
        raise NotFoundError("No valid formats specified")
    if body.scale not in SCALE_MULTIPLIERS:
        raise NotFoundError("Invalid scale — use 1x, 2x, or 4x")

    # Select images
    if body.image_index is not None:
        if body.image_index < 0 or body.image_index >= len(gallery):
            raise NotFoundError("Image index out of range")
        images = [(body.image_index, gallery[body.image_index])]
    else:
        images = list(enumerate(gallery))

    # Build (filename, url) pairs
    download_tasks: list[tuple[str, str]] = []
    for idx, item in images:
        original_url = item["url"] if isinstance(item, dict) else item
        for fmt in valid_formats:
            w, h = get_format_dimensions(fmt, body.scale)
            transformed_url = transform_cloudinary_url(original_url, w, h)
            filename = f"{fmt}/{idx + 1}.webp"
            download_tasks.append((filename, transformed_url))

    # Download all images concurrently
    async def _fetch(client: httpx.AsyncClient, url: str) -> bytes:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch(client, url) for _, url in download_tasks],
            return_exceptions=True,
        )

    # Build zip
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for (filename, _), data in zip(download_tasks, results):
            if isinstance(data, bytes):
                zf.writestr(filename, data)
            else:
                logger.warning("Failed to download %s: %s", filename, data)

    buf.seek(0)
    slug = activity.slug or str(activity_id)[:8]
    zip_name = f"{slug}_gallery_{body.scale}.zip"

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )
