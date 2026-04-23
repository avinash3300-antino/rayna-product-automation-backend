import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_db, require_role
from app.core.exceptions import NotFoundError
from app.db.models.auth import AuthUser
from app.db.models.scraping import ScrapeSource, SourceDiscoveryRun
from app.schemas.scraping import (
    AddSourceRequest,
    ScrapeSourceResponse,
    SourceApprovalRequest,
    SourceDiscoveryRequest,
    SourceDiscoveryRunResponse,
)
from app.services import discovery_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["discovery"])

MANAGER_ROLES = ("product_manager", "admin")


@router.post("/run", response_model=SourceDiscoveryRunResponse, status_code=201)
async def trigger_discovery(
    body: SourceDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Trigger source discovery for a city + category."""
    run = await discovery_service.run_discovery(
        db,
        city_id=body.city_id,
        category=body.category,
        product_type=body.product_type,
        triggered_by=current_user.id,
    )
    return SourceDiscoveryRunResponse.model_validate(run)


@router.get("/runs/{run_id}", response_model=SourceDiscoveryRunResponse)
async def get_discovery_run(
    run_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get discovery run details."""
    run = await db.get(SourceDiscoveryRun, run_id)
    if not run:
        raise NotFoundError("Discovery run not found")
    return SourceDiscoveryRunResponse.model_validate(run)


@router.get("/runs/{run_id}/sources", response_model=list[ScrapeSourceResponse])
async def list_discovery_sources(
    run_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List sources discovered in a run."""
    run = await db.get(SourceDiscoveryRun, run_id)
    if not run:
        raise NotFoundError("Discovery run not found")

    result = await db.execute(
        select(ScrapeSource)
        .where(ScrapeSource.discovery_run_id == run_id)
        .order_by(ScrapeSource.tier, ScrapeSource.created_at)
    )
    sources = list(result.scalars().all())
    return [ScrapeSourceResponse.model_validate(s) for s in sources]


@router.post("/runs/{run_id}/approve-sources", response_model=list[ScrapeSourceResponse])
async def approve_sources(
    run_id: UUID,
    body: SourceApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Approve or reject discovered sources."""
    run = await db.get(SourceDiscoveryRun, run_id)
    if not run:
        raise NotFoundError("Discovery run not found")

    sources = await discovery_service.approve_sources(
        db, body.source_ids, body.approved, current_user.id
    )
    return [ScrapeSourceResponse.model_validate(s) for s in sources]


@router.post("/runs/{run_id}/add-source", response_model=ScrapeSourceResponse, status_code=201)
async def add_manual_source(
    run_id: UUID,
    body: AddSourceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Manually add a source to a discovery run."""
    run = await db.get(SourceDiscoveryRun, run_id)
    if not run:
        raise NotFoundError("Discovery run not found")

    source = await discovery_service.add_manual_source(
        db,
        city_id=run.city_id,
        category=run.category,
        source_url=body.source_url,
        source_name=body.source_name,
        tier=body.tier,
        actor_id=current_user.id,
        product_type=run.product_type or "activities",
        discovery_run_id=run_id,
    )
    return ScrapeSourceResponse.model_validate(source)
