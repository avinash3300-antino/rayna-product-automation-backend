"""LA recovery — retry the 4 categories that failed during the 31.6-hour
LA run in the city queue. Uses reuse-or-fresh discovery dispatch:
- If a completed discovery run with sources > 0 exists for the category, reuse it
- Otherwise, run fresh discovery
Domain-diverse approval + per-category retry-on-connection-error.

Usage: python run_la_recovery.py
"""
import asyncio
import logging
import traceback
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("la_recovery")

LA_CITY_ID = "efe726c4-75a0-4de1-9693-d5dd739f6c1b"
ADMIN_USER_ID = "b153d252-5802-47a4-8be7-0bb71a466127"

FAILED_CATEGORIES = [
    "Museum & Gallery",
    "Luxury & Private",
    "Night Tours & Entertainment",
    "Transfers",
]

MAX_CONCURRENT = 2
MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 30


def _is_connection_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "connect call failed" in msg
        or "connection refused" in msg
        or "connection was closed" in msg  # new: matches "connection was closed in the middle of operation"
        or "greenlet_spawn" in msg
        or "server closed the connection" in msg
        or "connectiondoesnotexist" in msg
        or "ssl syscall" in msg
        or "operationalerror" in type(exc).__name__.lower()
        or "interfaceerror" in type(exc).__name__.lower()
    )


def _root_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


async def _find_reusable_discovery_run(db, city_id, category):
    from sqlalchemy import select
    from app.db.models.scraping import SourceDiscoveryRun
    result = await db.execute(
        select(SourceDiscoveryRun.id).where(
            SourceDiscoveryRun.city_id == city_id,
            SourceDiscoveryRun.category == category,
            SourceDiscoveryRun.status == "completed",
            SourceDiscoveryRun.sources_found > 0,
        ).order_by(SourceDiscoveryRun.started_at.desc()).limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def _run_category_once(category, idx, total, attempt):
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.discovery_service import run_discovery, approve_sources
    from app.services.pipeline_service import run_pipeline_for_discovery
    from sqlalchemy import select
    from app.db.models.scraping import ScrapeSource

    city_id = UUID(LA_CITY_ID)
    admin_id = UUID(ADMIN_USER_ID)

    logger.info("[%d/%d] START: %s (attempt %d)", idx, total, category, attempt)

    async with async_session_factory() as db:
        reusable_id = await _find_reusable_discovery_run(db, city_id, category)

    if reusable_id:
        logger.info("[%d/%d] REUSE existing discovery run %s for %s",
                    idx, total, reusable_id, category)
        run_id = reusable_id
    else:
        async with async_session_factory() as db:
            discovery_run = await run_discovery(
                db, city_id, category,
                product_type="activities", triggered_by=admin_id,
            )
            run_id = discovery_run.id
            sources_found = discovery_run.sources_found or 0
            logger.info("[%d/%d] Discovery: %s — run_id=%s sources_found=%d",
                        idx, total, category, run_id, sources_found)
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

        tier1 = [s for s in sources if s.tier == 1]
        seen = set()
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
            logger.info("[%d/%d] Approving: %s (%s)", idx, total, s.source_name, s.source_url)
        await approve_sources(db, source_ids, approved=True, actor_id=admin_id)

    total_saved = 0
    async with async_session_factory() as db:
        jobs = await run_pipeline_for_discovery(
            db, discovery_run_id=run_id, category=category,
            product_type="activities", triggered_by=admin_id,
        )
        for job in jobs:
            total_saved += job.records_saved or 0
            logger.info(
                "[%d/%d] Job %s: %s — found=%s saved=%s dup=%s enriched=%s",
                idx, total, job.id, category,
                job.records_found, job.records_saved,
                job.records_skipped_dup, job.records_enriched,
            )

    logger.info("[%d/%d] DONE: %s — saved=%d", idx, total, category, total_saved)
    return {"category": category, "status": "completed", "saved": total_saved}


async def run_one_category(sem, category, idx, total):
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
    total = len(FAILED_CATEGORIES)
    logger.info("=" * 70)
    logger.info("LOS ANGELES RECOVERY — %d failed categories, max %d concurrent",
                total, MAX_CONCURRENT)
    logger.info("=" * 70)

    tasks = [
        run_one_category(sem, cat, i, total)
        for i, cat in enumerate(FAILED_CATEGORIES, 1)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    logger.info("\n" + "=" * 70)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 70)
    for r in results:
        logger.info("  %s: %s (saved=%s)", r["category"], r["status"], r.get("saved", "N/A"))

    try:
        async with async_session_factory() as db:
            row = await db.execute(text("SELECT count(*) FROM activities WHERE city = 'Los Angeles'"))
            logger.info("\nTotal LA activities in DB: %d", row.scalar())
    except Exception as exc:
        logger.warning("Final count query failed: %s", exc)


if __name__ == "__main__":
    asyncio.run(main())
