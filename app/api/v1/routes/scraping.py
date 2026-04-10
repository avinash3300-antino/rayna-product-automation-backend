import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_db, require_role
from app.core.exceptions import NotFoundError
from app.db.models.auth import AuthUser
from app.db.models.scraping import ScrapeJob
from app.schemas.destinations import PaginatedResponse
from app.schemas.scraping import ScrapeJobResponse, ScrapeJobTriggerRequest
from app.services.pipeline_service import run_pipeline_for_discovery

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraping", tags=["scraping"])

MANAGER_ROLES = ("product_manager", "admin")


@router.post("/run", response_model=list[ScrapeJobResponse], status_code=201)
async def trigger_scraping_pipeline(
    body: ScrapeJobTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Trigger the scraping pipeline for approved sources in a discovery run."""
    jobs = await run_pipeline_for_discovery(
        db,
        discovery_run_id=body.discovery_run_id,
        category=body.category,
        triggered_by=current_user.id,
    )
    return [ScrapeJobResponse.model_validate(j) for j in jobs]


@router.get("/jobs", response_model=PaginatedResponse[ScrapeJobResponse])
async def list_scrape_jobs(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    city_id: UUID | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """List scrape jobs with filters."""
    query = select(ScrapeJob)
    count_query = select(func.count(ScrapeJob.id))

    if city_id:
        query = query.where(ScrapeJob.city_id == city_id)
        count_query = count_query.where(ScrapeJob.city_id == city_id)
    if category:
        query = query.where(ScrapeJob.category == category)
        count_query = count_query.where(ScrapeJob.category == category)
    if status:
        query = query.where(ScrapeJob.status == status)
        count_query = count_query.where(ScrapeJob.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    query = query.order_by(ScrapeJob.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    jobs = list(result.scalars().all())

    return PaginatedResponse(
        items=[ScrapeJobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/jobs/{job_id}", response_model=ScrapeJobResponse)
async def get_scrape_job(
    job_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get scrape job details."""
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise NotFoundError("Scrape job not found")
    return ScrapeJobResponse.model_validate(job)
