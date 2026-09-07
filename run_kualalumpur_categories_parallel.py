"""Run the REAL pipeline for Kuala Lumpur — PARALLEL-3 variant.

Same shape as run_singapore_categories_parallel.py:
- 15 KL-tailored categories, semaphore(3) concurrent
- Per-category retry-on-connection-error (paired with tunnel watchdog)
- Existing DB rows deduped by activity_pipeline's name+city match

Usage: python run_kualalumpur_categories_parallel.py
"""
import asyncio
import logging
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kl_parallel")

KL_CITY_ID = "f016b91b-9364-4293-89aa-e26921cbd947"
ADMIN_USER_ID = "b153d252-5802-47a4-8be7-0bb71a466127"

ALL_CATEGORIES = [
    "Landmark Tickets",
    "Petronas Twin Towers & KL Tower",
    "Batu Caves & Nature",
    "Theme Parks & Attractions",
    "Zoo & Wildlife",
    "Museum & Gallery",
    "Sightseeing Tours",
    "Food & Drink",
    "Cultural & Heritage",
    "Shows & Entertainment",
    "Day Trips",
    "Passes & Combos",
    "Family & Kids",
    "Luxury & Private",
    "Transfers",
]

MAX_CONCURRENT = 3
MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 30


def _is_connection_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "connect call failed" in msg
        or "connection refused" in msg
        or "greenlet_spawn" in msg
        or "server closed the connection" in msg
        or "ssl syscall" in msg
        or "operationalerror" in type(exc).__name__.lower()
    )


async def _run_category_once(category: str, idx: int, total: int, attempt: int):
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.discovery_service import run_discovery, approve_sources
    from app.services.pipeline_service import run_pipeline_for_discovery
    from sqlalchemy import select
    from app.db.models.scraping import ScrapeSource

    city_id = UUID(KL_CITY_ID)
    admin_id = UUID(ADMIN_USER_ID)

    logger.info("[%d/%d] START: %s (attempt %d)", idx, total, category, attempt)

    async with async_session_factory() as db:
        discovery_run = await run_discovery(
            db, city_id, category,
            product_type="activities",
            triggered_by=admin_id,
        )
        run_id = discovery_run.id
        sources_found = discovery_run.sources_found or 0
        logger.info(
            "[%d/%d] Discovery: %s — run_id=%s sources_found=%d status=%s",
            idx, total, category, run_id, sources_found, discovery_run.status,
        )

        if not sources_found:
            logger.warning("[%d/%d] no_sources: %s — skipping", idx, total, category)
            return {"category": category, "status": "no_sources", "saved": 0}

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
            logger.info("[%d/%d] Approving: %s (%s) tier=%d",
                        idx, total, s.source_name, s.source_url, s.tier)

        await approve_sources(db, source_ids, approved=True, actor_id=admin_id)

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
                "[%d/%d] Job %s: %s — found=%s saved=%s dup=%s enriched=%s status=%s",
                idx, total, job.id, category,
                job.records_found, job.records_saved,
                job.records_skipped_dup, job.records_enriched, job.status,
            )

    logger.info("[%d/%d] DONE: %s — saved=%d enriched=%d",
                idx, total, category, total_saved, total_enriched)
    return {"category": category, "status": "completed", "saved": total_saved, "enriched": total_enriched}


async def run_one_category(sem: asyncio.Semaphore, category: str, idx: int, total: int):
    async with sem:
        last_exc = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await _run_category_once(category, idx, total, attempt)
            except Exception as exc:
                last_exc = exc
                if _is_connection_error(exc) and attempt < MAX_ATTEMPTS:
                    logger.warning(
                        "[%d/%d] connection error on %s (attempt %d): %s — waiting %ds",
                        idx, total, category, attempt, exc, RETRY_WAIT_SECONDS,
                    )
                    await asyncio.sleep(RETRY_WAIT_SECONDS)
                    continue
                logger.error("[%d/%d] FAILED: %s — %s", idx, total, category, exc)
                traceback.print_exc()
                return {"category": category, "status": "failed", "error": str(exc), "saved": 0}

        return {"category": category, "status": "failed", "error": str(last_exc), "saved": 0}


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    total = len(ALL_CATEGORIES)
    logger.info("=" * 70)
    logger.info("KUALA LUMPUR PARALLEL RUN — %d categories, max %d concurrent",
                total, MAX_CONCURRENT)
    logger.info("=" * 70)

    tasks = [
        run_one_category(sem, cat, i, total)
        for i, cat in enumerate(ALL_CATEGORIES, 1)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    logger.info("\n" + "=" * 70)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 70)
    for r in results:
        logger.info("  %s: %s (saved=%s)", r["category"], r["status"], r.get("saved", "N/A"))

    async with async_session_factory() as db:
        row = await db.execute(text("SELECT count(*) FROM activities WHERE city = 'Kuala Lumpur'"))
        logger.info("\nTotal Kuala Lumpur activities in DB: %d", row.scalar())

    logger.info("Check http://localhost:3003/activities to see results!")


if __name__ == "__main__":
    asyncio.run(main())
