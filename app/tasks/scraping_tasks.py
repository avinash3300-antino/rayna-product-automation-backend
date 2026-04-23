import asyncio
import logging

from celery_app import celery
from app.db.base import async_session_factory

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=2, default_retry_delay=120)
def run_pipeline_task(
    self,
    source_id: str,
    product_type: str = "activities",
    triggered_by: str | None = None,
):
    """Celery task to run the full scraping pipeline for a source."""
    import uuid
    from app.services.pipeline_service import run_product_pipeline

    async def _run():
        async with async_session_factory() as db:
            return await run_product_pipeline(
                db,
                source_id=uuid.UUID(source_id),
                product_type=product_type,
                triggered_by=uuid.UUID(triggered_by) if triggered_by else None,
            )

    try:
        result = asyncio.run(_run())
        return {
            "job_id": str(result.id),
            "status": result.status,
            "product_type": product_type,
            "records_found": result.records_found,
            "records_saved": result.records_saved,
            "records_enriched": result.records_enriched,
        }
    except Exception as exc:
        logger.error("Pipeline task failed for source %s: %s", source_id, exc)
        raise self.retry(exc=exc)


@celery.task(bind=True, max_retries=2, default_retry_delay=60)
def enrich_product_task(
    self,
    product_id: str,
    product_type: str = "activities",
):
    """Celery task to enrich a single product."""
    import uuid
    from app.services.pipelines import get_pipeline

    async def _run():
        pipeline = get_pipeline(product_type)

        if product_type == "cruises":
            from app.db.models.cruises import CruiseProduct as Model
        else:
            from app.db.models.activities import Activity as Model

        async with async_session_factory() as db:
            product = await db.get(Model, uuid.UUID(product_id))
            if not product:
                return {"error": f"{product_type} product not found"}

            await pipeline.enrich_product(db, product)
            await db.commit()
            return {
                "product_id": str(product.id),
                "product_type": product_type,
                "quality_score": product.quality_score,
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Enrich task failed for %s %s: %s", product_type, product_id, exc)
        raise self.retry(exc=exc)


# Legacy alias
enrich_activity_task = enrich_product_task


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
