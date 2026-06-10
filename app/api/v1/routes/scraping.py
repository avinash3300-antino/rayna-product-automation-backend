import asyncio
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
from app.services.pipeline_service import (
    create_pending_jobs,
    process_pending_jobs,
    run_post_enrichment_for_city,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraping", tags=["scraping"])

MANAGER_ROLES = ("product_manager", "admin")


@router.post("/run", response_model=list[ScrapeJobResponse], status_code=201)
async def trigger_scraping_pipeline(
    body: ScrapeJobTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Create pending scrape jobs and start background processing.

    Returns immediately with pending jobs. The frontend polls each job's
    status via GET /scraping/jobs/{id} to track real-time progress.
    """
    # Step 1: Create pending jobs (fast, committed immediately)
    jobs = await create_pending_jobs(
        db,
        discovery_run_id=body.discovery_run_id,
        category=body.category,
        product_type=body.product_type,
        triggered_by=current_user.id,
    )

    # Step 2: Extract (job_id, source_id) tuples for background task
    job_source_pairs = [(j.id, j.source_id) for j in jobs]

    # Step 3: Fire and forget — process in background
    asyncio.create_task(
        process_pending_jobs(
            job_source_pairs,
            product_type=body.product_type,
            triggered_by=current_user.id,
        )
    )

    # Step 4: Return pending jobs immediately
    return [ScrapeJobResponse.model_validate(j) for j in jobs]


@router.get("/jobs", response_model=PaginatedResponse[ScrapeJobResponse])
async def list_scrape_jobs(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    city_id: UUID | None = Query(None),
    category: str | None = Query(None),
    product_type: str | None = Query(None),
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
    if product_type:
        query = query.where(ScrapeJob.product_type == product_type)
        count_query = count_query.where(ScrapeJob.product_type == product_type)
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


@router.post("/post-enrich/{city_id}")
async def trigger_post_enrichment(
    city_id: UUID,
    product_type: str = Query("activities"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Run gallery images, geocoding, and reviews for all products in a city."""
    result = await run_post_enrichment_for_city(db, city_id, product_type=product_type)
    return result


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


@router.post("/jobs/process-pending")
async def process_pending_jobs_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
    city_id: UUID | None = Query(None, description="Optional: only this city's pending jobs"),
    product_type: str = Query("activities"),
):
    """Pick up any 'pending' scrape jobs and kick off background processing.

    Useful after a backend restart where the original asyncio task died.
    Returns the list of job IDs that were scheduled.
    """
    import asyncio
    from app.services.pipeline_service import process_pending_jobs

    q = select(ScrapeJob).where(ScrapeJob.status == "pending")
    if city_id:
        q = q.where(ScrapeJob.city_id == city_id)
    result = await db.execute(q)
    pending = list(result.scalars().all())

    if not pending:
        return {"scheduled": 0, "job_ids": []}

    job_source_pairs = [(j.id, j.source_id) for j in pending if j.source_id]

    asyncio.create_task(
        process_pending_jobs(
            job_source_pairs,
            product_type=product_type,
            triggered_by=current_user.id,
        )
    )

    return {
        "scheduled": len(job_source_pairs),
        "job_ids": [str(jid) for jid, _ in job_source_pairs],
    }


@router.post("/jobs/{job_id}/cancel", response_model=ScrapeJobResponse)
async def cancel_scrape_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Mark a running scrape job as cancelled. The worker pipeline checks
    this flag between activities and stops cleanly at the next checkpoint."""
    from datetime import datetime, timezone

    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise NotFoundError("Scrape job not found")
    if job.status in ("completed", "failed", "cancelled"):
        # Already in a terminal state — nothing to cancel
        return ScrapeJobResponse.model_validate(job)
    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return ScrapeJobResponse.model_validate(job)


@router.post("/jobs/{job_id}/rerun", response_model=ScrapeJobResponse, status_code=201)
async def rerun_scrape_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*MANAGER_ROLES)),
):
    """Re-run a completed/failed/cancelled job by spawning a new ScrapeJob
    against the same source. Returns the newly-created job."""
    from app.services.pipeline_service import run_product_pipeline

    old_job = await db.get(ScrapeJob, job_id)
    if not old_job:
        raise NotFoundError("Scrape job not found")

    new_job = await run_product_pipeline(
        db,
        source_id=old_job.source_id,
        product_type=old_job.product_type or "activities",
        triggered_by=current_user.id,
    )
    await db.commit()
    return ScrapeJobResponse.model_validate(new_job)
