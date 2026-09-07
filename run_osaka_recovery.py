"""Recover the 3 Osaka categories that failed in the main run by REUSING
their existing successful discovery runs.

Why we can't just re-run the standard pipeline: after a partial failure,
new discovery calls create empty runs (existing sources get "already exists"
skips, so sources_created=0 → no_sources).

Approach: hardcode the run_ids of the best existing discovery runs (highest
sources_found), skip discovery, do domain-diverse approval + pipeline directly.

Usage: python run_osaka_recovery.py
"""
import asyncio
import logging
import traceback
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("osaka_recovery")

OSAKA_CITY_ID = "6d390948-2750-42e6-87fc-91f517f19c77"
ADMIN_USER_ID = "b153d252-5802-47a4-8be7-0bb71a466127"

# (category, discovery_run_id) — reusing existing successful runs
RECOVERY_TARGETS = [
    ("Landmark Tickets", "e8690230-5a63-49a2-922d-85bb45a888d2"),
    ("Universal Studios Japan", "e24413c7-2c93-47ea-bc66-a877adf44b84"),
    ("Kyoto & Nara Day Trips", "aee4de3f-a938-4d37-8426-4025b16a9e1d"),
]

MAX_CONCURRENT = 2  # gentle for the recovery


def _root_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


async def _run_category_from_existing_discovery(category: str, run_id_str: str, idx: int, total: int):
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.discovery_service import approve_sources
    from app.services.pipeline_service import run_pipeline_for_discovery
    from sqlalchemy import select
    from app.db.models.scraping import ScrapeSource

    admin_id = UUID(ADMIN_USER_ID)
    run_id = UUID(run_id_str)

    logger.info("[%d/%d] START (recovery, existing run %s): %s",
                idx, total, run_id_str, category)

    async with async_session_factory() as db:
        result = await db.execute(
            select(ScrapeSource).where(
                ScrapeSource.discovery_run_id == run_id,
            ).order_by(ScrapeSource.tier, ScrapeSource.authority_score.desc())
        )
        sources = result.scalars().all()
        logger.info("[%d/%d] existing sources for %s: %d total",
                    idx, total, category, len(sources))

        tier1 = [s for s in sources if s.tier == 1]
        seen: set[str] = set()
        to_approve = []
        for s in tier1:
            d = _root_domain(s.source_url)
            if d in seen:
                continue
            seen.add(d)
            to_approve.append(s)
            if len(to_approve) >= 3:
                break

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


async def _guarded(sem, category, run_id_str, idx, total):
    async with sem:
        try:
            return await _run_category_from_existing_discovery(category, run_id_str, idx, total)
        except Exception as exc:
            logger.error("[%d/%d] FAILED: %s — %s", idx, total, category, exc)
            traceback.print_exc()
            return {"category": category, "status": "failed", "error": str(exc), "saved": 0}


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    total = len(RECOVERY_TARGETS)
    logger.info("=" * 70)
    logger.info("OSAKA RECOVERY — %d categories, max %d concurrent, reusing existing discovery runs",
                total, MAX_CONCURRENT)
    logger.info("=" * 70)

    tasks = [
        _guarded(sem, cat, run_id, i, total)
        for i, (cat, run_id) in enumerate(RECOVERY_TARGETS, 1)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    logger.info("\n" + "=" * 70)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 70)
    for r in results:
        logger.info("  %s: %s (saved=%s)", r["category"], r["status"], r.get("saved", "N/A"))

    try:
        async with async_session_factory() as db:
            row = await db.execute(text("SELECT count(*) FROM activities WHERE city = 'Osaka'"))
            logger.info("\nTotal Osaka activities in DB: %d", row.scalar())
    except Exception as exc:
        logger.warning("Final count query failed: %s", exc)


if __name__ == "__main__":
    asyncio.run(main())
