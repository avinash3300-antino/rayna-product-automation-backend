import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_db, require_role
from app.core.exceptions import NotFoundError
from app.db.models.auth import AuthUser
from app.schemas.destinations import (
    CategoryPipelineStatus,
    DestinationCreate,
    DestinationDetail,
    DestinationListItem,
    DestinationStatsOverview,
    DestinationStatusUpdate,
    DestinationUpdate,
    IngestionJobBrief,
    LastIngestionRunBrief,
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    PaginatedResponse,
    ProductCountSummary,
)
from app.services import destination_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/destinations", tags=["destinations"])

MANAGER_ROLES = ("product_manager", "admin")
ADMIN_ROLES = ("admin",)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _build_destination_list_item(
    dest,
    product_counts_map: dict,
    last_ingestion_map: dict,
) -> DestinationListItem:
    counts = product_counts_map.get(dest.id, {})
    hotels = counts.get("hotels", 0)
    attractions = counts.get("attractions", 0)
    transfers = counts.get("transfers", 0)
    restaurants = counts.get("restaurants", 0)
    total = hotels + attractions + transfers + restaurants

    last_run_data = last_ingestion_map.get(dest.id)
    last_ingestion_run = None
    if last_run_data:
        last_ingestion_run = LastIngestionRunBrief(**last_run_data)

    return DestinationListItem(
        id=dest.id,
        code=dest.code,
        name=dest.name,
        country_code=dest.country_code,
        country_name=dest.country_name,
        country_flag=dest.country_flag,
        region_name=dest.region_name,
        city_name=dest.city_name,
        timezone=dest.timezone,
        latitude=float(dest.latitude) if dest.latitude is not None else None,
        longitude=float(dest.longitude) if dest.longitude is not None else None,
        status=dest.status,
        enabled_categories=dest.enabled_categories or ["hotels", "attractions", "transfers", "restaurants"],
        created_at=dest.created_at,
        updated_at=dest.updated_at,
        location_count=len(dest.locations) if dest.locations else 0,
        product_counts=ProductCountSummary(
            hotels=hotels,
            attractions=attractions,
            transfers=transfers,
            restaurants=restaurants,
            total=total,
        ),
        last_ingestion_run=last_ingestion_run,
    )


def _build_destination_detail(
    dest,
    recent_jobs: list,
    pipeline: list[dict],
) -> DestinationDetail:
    return DestinationDetail(
        id=dest.id,
        code=dest.code,
        name=dest.name,
        country_code=dest.country_code,
        country_name=dest.country_name,
        country_flag=dest.country_flag,
        region_name=dest.region_name,
        city_name=dest.city_name,
        timezone=dest.timezone,
        latitude=float(dest.latitude) if dest.latitude is not None else None,
        longitude=float(dest.longitude) if dest.longitude is not None else None,
        status=dest.status,
        enabled_categories=dest.enabled_categories or ["hotels", "attractions", "transfers", "restaurants"],
        created_at=dest.created_at,
        updated_at=dest.updated_at,
        locations=[LocationResponse.model_validate(loc) for loc in dest.locations],
        recent_ingestion_jobs=[IngestionJobBrief.model_validate(j) for j in recent_jobs],
        pipeline_status=[CategoryPipelineStatus(**p) for p in pipeline],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /stats routes — MUST come before /{destination_id} to avoid path collision
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/stats/overview", response_model=DestinationStatsOverview)
async def get_stats_overview(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stats = await destination_service.get_stats_overview(db)
    return DestinationStatsOverview(
        total_destinations=stats["total_destinations"],
        active_destinations=stats["active_destinations"],
        total_products=ProductCountSummary(**stats["total_products"]),
        products_published=stats["products_published"],
        products_in_pipeline=stats["products_in_pipeline"],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Destination CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("", response_model=PaginatedResponse[DestinationListItem])
async def list_destinations(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None),
    status: str | None = Query(None),
    country_code: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    destinations, total, product_counts_map, last_ingestion_map = (
        await destination_service.list_destinations(
            db, search, status, country_code, page, per_page,
        )
    )
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        items=[
            _build_destination_list_item(d, product_counts_map, last_ingestion_map)
            for d in destinations
        ],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.post("", response_model=DestinationDetail, status_code=201)
async def create_destination(
    body: DestinationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    data = body.model_dump(exclude_unset=True)
    dest = await destination_service.create_destination(db, data, current_user.id)
    recent_jobs = await destination_service.get_recent_ingestion_jobs(db, dest.id)
    pipeline = await destination_service.get_pipeline_status(db, dest.id)
    return _build_destination_detail(dest, recent_jobs, pipeline)


@router.get("/{destination_id}", response_model=DestinationDetail)
async def get_destination(
    destination_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    dest = await destination_service.get_destination_by_id(db, destination_id)
    if not dest:
        raise NotFoundError("Destination not found")
    recent_jobs = await destination_service.get_recent_ingestion_jobs(db, destination_id)
    pipeline = await destination_service.get_pipeline_status(db, destination_id)
    return _build_destination_detail(dest, recent_jobs, pipeline)


@router.patch("/{destination_id}", response_model=DestinationDetail)
async def update_destination(
    destination_id: UUID,
    body: DestinationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    data = body.model_dump(exclude_unset=True)
    dest = await destination_service.update_destination(db, destination_id, data, current_user.id)
    recent_jobs = await destination_service.get_recent_ingestion_jobs(db, dest.id)
    pipeline = await destination_service.get_pipeline_status(db, dest.id)
    return _build_destination_detail(dest, recent_jobs, pipeline)


@router.patch("/{destination_id}/status", response_model=DestinationDetail)
async def update_destination_status(
    destination_id: UUID,
    body: DestinationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
):
    dest = await destination_service.update_destination_status(
        db, destination_id, body.status, current_user.id,
    )
    recent_jobs = await destination_service.get_recent_ingestion_jobs(db, dest.id)
    pipeline = await destination_service.get_pipeline_status(db, dest.id)
    return _build_destination_detail(dest, recent_jobs, pipeline)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Location CRUD (nested under destination)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/{destination_id}/locations", response_model=list[LocationResponse])
async def list_locations(
    destination_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    locations = await destination_service.list_locations(db, destination_id)
    return [LocationResponse.model_validate(loc) for loc in locations]


@router.post(
    "/{destination_id}/locations",
    response_model=LocationResponse,
    status_code=201,
)
async def create_location(
    destination_id: UUID,
    body: LocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    data = body.model_dump(exclude_unset=True)
    loc = await destination_service.create_location(db, destination_id, data, current_user.id)
    return LocationResponse.model_validate(loc)


@router.patch(
    "/{destination_id}/locations/{location_id}",
    response_model=LocationResponse,
)
async def update_location(
    destination_id: UUID,
    location_id: UUID,
    body: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    data = body.model_dump(exclude_unset=True)
    loc = await destination_service.update_location(
        db, destination_id, location_id, data, current_user.id,
    )
    return LocationResponse.model_validate(loc)


@router.delete(
    "/{destination_id}/locations/{location_id}",
    status_code=204,
)
async def delete_location(
    destination_id: UUID,
    location_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
):
    await destination_service.delete_location(
        db, destination_id, location_id, current_user.id,
    )
