"""Run the REAL pipeline for ALL 15 Cairo categories sequentially.

Usage: python run_cairo_categories.py
"""
import asyncio
import logging
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cairo_categories")

CAIRO_CITY_ID = "941c503c-82a0-4a76-80ae-f8bb78cd7437"
ADMIN_USER_ID = "b153d252-5802-47a4-8be7-0bb71a466127"

ALL_CATEGORIES = [
    "Pyramids & Ancient Sites",
    "Nile River",
    "Museum & Gallery",
    "Sightseeing Tours",
    "Day Trips",
    "Desert Safari & Adventure",
    "Food & Drink",
    "Bazaar & Shopping",
    "Night Tours",
    "Shows & Entertainment",
    "Cultural & Heritage",
    "Luxury & Private",
    "Family & Kids",
    "Passes & Combos",
    "Transfers",
]


async def run_one_category(category: str, idx: int, total: int):
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.discovery_service import run_discovery, approve_sources
    from app.services.pipeline_service import run_pipeline_for_discovery
    from sqlalchemy import select
    from app.db.models.scraping import ScrapeSource

    city_id = UUID(CAIRO_CITY_ID)
    admin_id = UUID(ADMIN_USER_ID)

    logger.info("=" * 70)
    logger.info("[%d/%d] CATEGORY: %s", idx, total, category)
    logger.info("=" * 70)

    # Step 1: Discovery
    logger.info("  STEP 1: Running discovery...")
    async with async_session_factory() as db:
        discovery_run = await run_discovery(
            db, city_id, category,
            product_type="activities",
            triggered_by=admin_id,
        )
        run_id = discovery_run.id
        sources_found = discovery_run.sources_found or 0
        logger.info(
            "  Discovery: run_id=%s, sources_found=%d, status=%s",
            run_id, sources_found, discovery_run.status,
        )

        if not sources_found:
            logger.warning("  No sources found for '%s', skipping.", category)
            return {"category": category, "status": "no_sources", "saved": 0}

    # Step 2: Approve top sources (tier 1, max 3)
    logger.info("  STEP 2: Approving sources...")
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
            logger.info("    Approving: %s (%s) tier=%d", s.source_name, s.source_url, s.tier)

        await approve_sources(db, source_ids, approved=True, actor_id=admin_id)
        logger.info("  Approved %d sources", len(source_ids))

    # Step 3: Full pipeline (scrape + extract + dedup + enrich + gallery + reviews)
    logger.info("  STEP 3: Running full pipeline...")
    total_saved = 0
    total_enriched = 0
    async with async_session_factory() as db:
        jobs = await run_pipeline_for_discovery(
            db,
            discovery_run_id=run_id,
            category=category,
            product_type="activities",
            triggered_by=admin_id,
        )
        for job in jobs:
            total_saved += job.records_saved or 0
            total_enriched += job.records_enriched or 0
            logger.info(
                "    Job %s: found=%s saved=%s dup=%s enriched=%s status=%s",
                job.id, job.records_found, job.records_saved,
                job.records_skipped_dup, job.records_enriched, job.status,
            )

    logger.info("  DONE: %s — saved=%d, enriched=%d", category, total_saved, total_enriched)
    return {"category": category, "status": "completed", "saved": total_saved, "enriched": total_enriched}


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    results = []
    for i, category in enumerate(ALL_CATEGORIES, 1):
        try:
            result = await run_one_category(category, i, len(ALL_CATEGORIES))
            results.append(result)
        except Exception as exc:
            logger.error("FAILED: %s — %s", category, exc)
            traceback.print_exc()
            results.append({"category": category, "status": "failed", "error": str(exc)})

        # Small pause between categories
        if i < len(ALL_CATEGORIES):
            await asyncio.sleep(3)

    # Final summary
    logger.info("\n" + "=" * 70)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 70)
    for r in results:
        logger.info("  %s: %s (saved=%s)", r["category"], r["status"], r.get("saved", "N/A"))

    # Count total Cairo activities
    async with async_session_factory() as db:
        row = await db.execute(text("SELECT count(*) FROM activities WHERE city = 'Cairo'"))
        logger.info("\nTotal Cairo activities in DB: %d", row.scalar())

    logger.info("Check http://localhost:3000/activities to see results!")


if __name__ == "__main__":
    asyncio.run(main())
