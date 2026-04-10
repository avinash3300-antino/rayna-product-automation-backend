import asyncio
import logging

from celery_app import celery
from app.db.base import async_session_factory

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=2, default_retry_delay=120)
def run_pipeline_task(self, source_id: str, triggered_by: str | None = None):
    """Celery task to run the full scraping pipeline for a source."""
    import uuid
    from app.services.pipeline_service import run_activity_pipeline

    async def _run():
        async with async_session_factory() as db:
            return await run_activity_pipeline(
                db,
                source_id=uuid.UUID(source_id),
                triggered_by=uuid.UUID(triggered_by) if triggered_by else None,
            )

    try:
        result = asyncio.run(_run())
        return {
            "job_id": str(result.id),
            "status": result.status,
            "records_found": result.records_found,
            "records_saved": result.records_saved,
            "records_enriched": result.records_enriched,
        }
    except Exception as exc:
        logger.error("Pipeline task failed for source %s: %s", source_id, exc)
        raise self.retry(exc=exc)


@celery.task(bind=True, max_retries=2, default_retry_delay=60)
def enrich_activity_task(self, activity_id: str):
    """Celery task to enrich a single activity."""
    import uuid
    from app.services.enrichment_service import enrich_activity

    async def _run():
        async with async_session_factory() as db:
            from app.db.models.activities import Activity

            activity = await db.get(Activity, uuid.UUID(activity_id))
            if not activity:
                return {"error": "Activity not found"}

            enriched = await enrich_activity(db, activity)
            await db.commit()
            return {
                "activity_id": str(enriched.id),
                "quality_score": enriched.quality_score,
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Enrich task failed for activity %s: %s", activity_id, exc)
        raise self.retry(exc=exc)


@celery.task
def weekly_discovery_sweep():
    """Weekly task: run discovery for all active destinations."""
    from sqlalchemy import select
    from app.db.models.destinations import CatalogDestination

    async def _run():
        async with async_session_factory() as db:
            result = await db.execute(
                select(CatalogDestination).where(
                    CatalogDestination.status == "active"
                )
            )
            destinations = list(result.scalars().all())

            dispatched = 0
            for dest in destinations:
                categories = dest.enabled_categories or []
                for category in categories:
                    run_discovery_task.delay(
                        str(dest.id), category, None
                    )
                    dispatched += 1

            return {"destinations": len(destinations), "tasks_dispatched": dispatched}

    return asyncio.run(_run())
