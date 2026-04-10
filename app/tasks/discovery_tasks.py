import asyncio
import logging

from celery_app import celery
from app.db.base import async_session_factory

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def run_discovery_task(self, city_id: str, category: str, triggered_by: str | None = None):
    """Celery task to run source discovery asynchronously."""
    import uuid
    from app.services.discovery_service import run_discovery

    async def _run():
        async with async_session_factory() as db:
            return await run_discovery(
                db,
                city_id=uuid.UUID(city_id),
                category=category,
                triggered_by=uuid.UUID(triggered_by) if triggered_by else None,
            )

    try:
        result = asyncio.run(_run())
        return {
            "run_id": str(result.id),
            "status": result.status,
            "sources_found": result.sources_found,
        }
    except Exception as exc:
        logger.error("Discovery task failed: %s", exc)
        raise self.retry(exc=exc)
