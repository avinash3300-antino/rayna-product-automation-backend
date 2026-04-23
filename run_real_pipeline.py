"""Run the REAL pipeline for one category in London.

Usage: python run_real_pipeline.py "Sightseeing Tours"
"""
import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pipeline_runner")

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"
ADMIN_USER_ID = "b153d252-5802-47a4-8be7-0bb71a466127"


async def run(category: str):
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.discovery_service import run_discovery, approve_sources
    from app.services.pipeline_service import run_pipeline_for_discovery
    from sqlalchemy import select
    from app.db.models.scraping import ScrapeSource

    city_id = UUID(LONDON_CITY_ID)
    admin_id = UUID(ADMIN_USER_ID)

    # Step 1: Discovery
    logger.info("=== STEP 1: Running discovery for '%s' in London ===", category)
    async with async_session_factory() as db:
        discovery_run = await run_discovery(
            db, city_id, category,
            product_type="activities",
            triggered_by=admin_id,
        )
        run_id = discovery_run.id
        sources_found = discovery_run.sources_found or 0
        logger.info(
            "Discovery complete: run_id=%s, sources_found=%d, status=%s",
            run_id, sources_found, discovery_run.status,
        )

        if not sources_found:
            logger.error("No sources found! Check SearchAPI key.")
            return

    # Step 2: Approve top sources
    logger.info("=== STEP 2: Approving sources ===")
    async with async_session_factory() as db:
        result = await db.execute(
            select(ScrapeSource).where(
                ScrapeSource.discovery_run_id == run_id,
            ).order_by(ScrapeSource.tier, ScrapeSource.authority_score.desc())
        )
        sources = result.scalars().all()
        to_approve = [s for s in sources if s.tier == 1][:3]
        if not to_approve:
            to_approve = list(sources)[:2]

        source_ids = [s.id for s in to_approve]
        for s in to_approve:
            logger.info("  Approving: %s (%s) tier=%d", s.source_name, s.source_url, s.tier)

        await approve_sources(db, source_ids, approved=True, actor_id=admin_id)
        logger.info("Approved %d sources", len(source_ids))

    # Step 3: Run full pipeline (scrape + extract + dedup + enrich + gallery + reviews)
    logger.info("=== STEP 3: Running full pipeline ===")
    async with async_session_factory() as db:
        jobs = await run_pipeline_for_discovery(
            db,
            discovery_run_id=run_id,
            category=category,
            product_type="activities",
            triggered_by=admin_id,
        )
        for job in jobs:
            logger.info(
                "Job %s: found=%s saved=%s dup=%s enriched=%s status=%s",
                job.id, job.records_found, job.records_saved,
                job.records_skipped_dup, job.records_enriched, job.status,
            )

    logger.info("=== PIPELINE COMPLETE for '%s' ===", category)
    logger.info("Check http://localhost:3000/activities to see real results!")


if __name__ == "__main__":
    category = sys.argv[1] if len(sys.argv) > 1 else "Sightseeing Tours"
    asyncio.run(run(category))
