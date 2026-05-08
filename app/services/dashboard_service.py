import logging

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models.activities import Activity
from app.db.models.cruises import CruiseProduct
from app.db.models.destinations import CatalogDestination
from app.db.models.scraping import ScrapeJob
from app.schemas.dashboard import (
    DashboardStatsResponse,
    KpiStats,
    PipelineStage,
    ProductsByCategoryItem,
    ProductsByDestinationItem,
    RecentJobItem,
    StatusBreakdown,
)

logger = logging.getLogger(__name__)

PIPELINE_STAGES = [
    ("draft", "Draft"),
    ("enriched", "Enriched"),
    ("review_ready", "Review"),
    ("approved", "Approved"),
    ("published", "Published"),
]


async def get_dashboard_stats(db: AsyncSession) -> DashboardStatsResponse:
    # ── KPI: product counts by status ────────────────────────────────
    act_status_q = await db.execute(
        select(Activity.status, func.count(Activity.id)).group_by(Activity.status)
    )
    act_status_map = dict(act_status_q.all())

    cruise_status_q = await db.execute(
        select(CruiseProduct.status, func.count(CruiseProduct.id)).group_by(
            CruiseProduct.status
        )
    )
    cruise_status_map = dict(cruise_status_q.all())

    # Merge both maps
    all_statuses = set(act_status_map.keys()) | set(cruise_status_map.keys())
    merged = {s: act_status_map.get(s, 0) + cruise_status_map.get(s, 0) for s in all_statuses}

    total_activities = sum(act_status_map.values())
    total_cruises = sum(cruise_status_map.values())
    total_products = total_activities + total_cruises

    by_status = StatusBreakdown(
        draft=merged.get("draft", 0),
        enriched=merged.get("enriched", 0),
        review_ready=merged.get("review_ready", 0),
        approved=merged.get("approved", 0),
        published=merged.get("published", 0),
    )

    # ── KPI: active scrape jobs ──────────────────────────────────────
    active_jobs_q = await db.execute(
        select(func.count(ScrapeJob.id)).where(
            ScrapeJob.status.in_(["pending", "running"])
        )
    )
    active_scrape_jobs = active_jobs_q.scalar_one()

    kpi = KpiStats(
        total_products=total_products,
        total_activities=total_activities,
        total_cruises=total_cruises,
        by_status=by_status,
        active_scrape_jobs=active_scrape_jobs,
        is_scraping_running=active_scrape_jobs > 0,
    )

    # ── Pipeline stages ──────────────────────────────────────────────
    pipeline_stages = [
        PipelineStage(id=stage_id, label=label, count=merged.get(stage_id, 0))
        for stage_id, label in PIPELINE_STAGES
    ]

    # ── Recent jobs (last 10) ────────────────────────────────────────
    dest_alias = aliased(CatalogDestination)
    recent_q = await db.execute(
        select(ScrapeJob, dest_alias.name)
        .outerjoin(dest_alias, ScrapeJob.city_id == dest_alias.id)
        .order_by(ScrapeJob.created_at.desc())
        .limit(10)
    )
    recent_rows = recent_q.all()

    recent_jobs = []
    for job, dest_name in recent_rows:
        duration_ms = 0
        if job.started_at and job.completed_at:
            duration_ms = int(
                (job.completed_at - job.started_at).total_seconds() * 1000
            )
        recent_jobs.append(
            RecentJobItem(
                id=job.id,
                destination=dest_name or "Unknown",
                category=job.category,
                product_type=job.product_type,
                status=job.status,
                records_found=job.records_found,
                records_saved=job.records_saved,
                started_at=job.started_at,
                completed_at=job.completed_at,
                created_at=job.created_at,
                duration_ms=duration_ms,
            )
        )

    # ── Products by destination ──────────────────────────────────────
    # Count activities per destination name
    act_by_dest = await db.execute(
        select(CatalogDestination.name, func.count(Activity.id))
        .join(Activity, Activity.city_id == CatalogDestination.id)
        .group_by(CatalogDestination.name)
    )
    dest_counts: dict[str, int] = {}
    for name, count in act_by_dest.all():
        dest_counts[name] = dest_counts.get(name, 0) + count

    cruise_by_dest = await db.execute(
        select(CatalogDestination.name, func.count(CruiseProduct.id))
        .join(CruiseProduct, CruiseProduct.city_id == CatalogDestination.id)
        .group_by(CatalogDestination.name)
    )
    for name, count in cruise_by_dest.all():
        dest_counts[name] = dest_counts.get(name, 0) + count

    products_by_destination = sorted(
        [
            ProductsByDestinationItem(destination=name, count=count)
            for name, count in dest_counts.items()
        ],
        key=lambda x: x.count,
        reverse=True,
    )

    # ── Products by category (grouped by destination) ────────────────
    cat_q = await db.execute(
        select(
            CatalogDestination.name,
            Activity.category,
            func.count(Activity.id),
        )
        .join(CatalogDestination, Activity.city_id == CatalogDestination.id)
        .where(Activity.category.isnot(None))
        .group_by(CatalogDestination.name, Activity.category)
    )
    cat_by_dest: dict[str, dict[str, int]] = {}
    for dest_name, cat, count in cat_q.all():
        cat_by_dest.setdefault(dest_name, {})
        cat_by_dest[dest_name][cat or "Uncategorized"] = (
            cat_by_dest[dest_name].get(cat or "Uncategorized", 0) + count
        )

    products_by_category: dict[str, list[ProductsByCategoryItem]] = {}
    for dest_name, cats in cat_by_dest.items():
        products_by_category[dest_name] = sorted(
            [
                ProductsByCategoryItem(category=c, count=n)
                for c, n in cats.items()
            ],
            key=lambda x: x.count,
            reverse=True,
        )

    return DashboardStatsResponse(
        kpi=kpi,
        pipeline_stages=pipeline_stages,
        recent_jobs=recent_jobs,
        products_by_destination=products_by_destination,
        products_by_category=products_by_category,
    )
