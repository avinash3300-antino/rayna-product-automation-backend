"""Master city-queue runner.

Waits for prior pipeline (Riyadh recovery) to finish, then processes 15
cities sequentially. Each city runs its 15-category list with parallel-3
concurrency, reuse-or-fresh discovery dispatch, and domain-diverse approval.

Design goals:
- Survives Claude Code session disconnects (background nohup)
- One log per city under /tmp/rayna-logs/queue-<slug>.log
- Central progress log at /tmp/rayna-logs/queue-master.log

Usage: nohup .venv/bin/python run_city_queue.py > /tmp/rayna-logs/queue-master.log 2>&1 &
"""
import asyncio
import logging
import os
import sys
import time
import traceback
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
master_logger = logging.getLogger("queue_master")

ADMIN_USER_ID = "b153d252-5802-47a4-8be7-0bb71a466127"
MAX_CONCURRENT = 3
MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 30

# Wait for these processes to disappear before starting the queue.
# Original blocker was Riyadh recovery; on the current (post-London-skip)
# relaunch, we may also need to wait for the outgoing queue master to die
# before this replacement starts.
BLOCKING_PATTERNS = ["run_riyadh_categories_parallel.py"]

# ── City queue ──────────────────────────────────────────────────────────
# (city_id_uuid, display_name, city_col_value, [categories])
# NOTE: Jeddah + Muscat + Cairo completed in prior queue run; London skipped
# per user request (already at 321 activities). Queue resumes from Paris.

CITIES = [
    (
        "3da82c61-ea6d-4fe0-913d-1550b1108e23", "Paris", "Paris",
        [
            "Eiffel Tower & Landmark Tickets", "Louvre & Museum Tours",
            "Seine River Cruise", "Versailles Day Trip",
            "Disneyland Paris", "Skip-the-Line Attractions",
            "Food & Wine Tours", "Cabaret & Shows (Moulin Rouge)",
            "Night Tours & Illuminations", "Cultural & Heritage",
            "Sightseeing Tours", "Cooking Classes",
            "Passes & Combos", "Luxury & Private", "Transfers",
        ],
    ),
    (
        "fe6996fa-f75f-4c50-aa3c-41118762299e", "Zurich", "Zurich",
        [
            "Landmark Tickets", "Lake Zurich Cruise",
            "Uetliberg & Mountain Views", "Rhine Falls Day Trip",
            "Alpine Day Trips (Jungfrau, Titlis)",
            "Swiss Chocolate & Cheese Tours",
            "Museum & Gallery", "Sightseeing Tours",
            "Old Town Walking Tours", "Cultural & Heritage",
            "Food & Drink", "Family & Kids", "Skiing & Winter Sports",
            "Luxury & Private", "Transfers",
        ],
    ),
    (
        "d4f32d0c-e7d9-41b1-8da5-1688aa8a4935", "Lucerne", "Lucerne",
        [
            "Landmark Tickets (Chapel Bridge)", "Mount Pilatus",
            "Mount Rigi", "Mount Titlis & Glacier",
            "Lake Lucerne Cruise", "Interlaken Day Trip",
            "Museum & Gallery", "Sightseeing Tours",
            "Cultural & Heritage", "Food & Drink",
            "Family & Kids", "Adventure & Outdoor",
            "Winter Sports", "Luxury & Private", "Transfers",
        ],
    ),
    (
        "4d6d549a-af58-4975-8f82-4e75212a877a", "Amsterdam", "Amsterdam",
        [
            "Landmark Tickets", "Canal Cruises",
            "Van Gogh & Rijksmuseum", "Anne Frank House",
            "Keukenhof Tulip Gardens", "Zaanse Schans Windmills Day Trip",
            "Museum & Gallery", "Bike Tours", "Sightseeing Tours",
            "Food & Drink", "Red Light District Tours",
            "Boat & Cruise Experiences", "Passes & Combos",
            "Family & Kids", "Transfers",
        ],
    ),
    (
        "75485bfd-e418-49d3-8a23-a0c01f344896", "Rome", "Rome",
        [
            "Colosseum & Roman Forum", "Vatican Museum & Sistine Chapel",
            "Landmark Tickets", "Skip-the-Line Attractions",
            "Food & Wine Tours", "Cooking Classes",
            "Ancient Rome Tours", "Museum & Gallery",
            "Sightseeing Tours", "Cultural & Heritage",
            "Day Trips (Pompeii, Amalfi, Tivoli)",
            "Shows & Entertainment", "Passes & Combos",
            "Luxury & Private", "Transfers",
        ],
    ),
    (
        "41898984-ae97-45a1-adb3-850e99c6b8ff", "Barcelona", "Barcelona",
        [
            "Sagrada Familia & Gaudi Landmarks", "Park Güell",
            "Camp Nou & FC Barcelona Experience", "Landmark Tickets",
            "Flamenco & Tapas Tours", "Cooking Classes",
            "Museum & Gallery", "Sightseeing Tours",
            "Cultural & Heritage", "Beach & Coastal Tours",
            "Day Trips (Montserrat, Girona)",
            "Nightlife & Entertainment", "Family & Kids",
            "Luxury & Private", "Transfers",
        ],
    ),
    (
        "5a994dab-9bfa-4970-91d3-07b0aa97f593", "Istanbul", "Istanbul",
        [
            "Hagia Sophia & Blue Mosque", "Topkapi Palace & Grand Bazaar",
            "Bosphorus Cruise", "Landmark Tickets",
            "Turkish Bath (Hamam) Experiences",
            "Food & Culinary Tours", "Museum & Gallery",
            "Sightseeing Tours", "Cultural & Heritage",
            "Day Trips (Princes' Islands, Cappadocia)",
            "Whirling Dervishes & Shows",
            "Family & Kids", "Nightlife", "Luxury & Private", "Transfers",
        ],
    ),
    (
        "b585e070-72a2-4ff2-ac3d-1966001f4413", "New York", "New York",
        [
            "Statue of Liberty & Ellis Island", "Empire State Building",
            "Landmark Tickets", "Broadway Shows",
            "Central Park Tours", "Museum & Gallery",
            "Hop-On Hop-Off Sightseeing", "Food Tours",
            "Helicopter Tours", "Passes & Combos",
            "Sports & Events", "Cultural & Heritage",
            "Family & Kids", "Luxury & Private", "Transfers",
        ],
    ),
    (
        "42196d0d-9716-47ab-b51d-9456f1329f53", "Orlando", "Orlando",
        [
            "Walt Disney World", "Universal Studios Orlando",
            "SeaWorld & Discovery Cove", "Landmark Tickets",
            "Kennedy Space Center", "Everglades Airboat Day Trip",
            "Water Parks", "Dining Experiences",
            "Passes & Combos", "Sightseeing Tours",
            "Cultural & Heritage", "Family & Kids",
            "Luxury & Private", "VIP Theme Park Experiences",
            "Transfers",
        ],
    ),
    (
        "9fc8647e-337d-4b99-9f4f-80e6fb454a5d", "Washington DC", "Washington DC",
        [
            "Landmark Tickets (Capitol, White House)",
            "Smithsonian Museums", "National Mall Tours",
            "Ghost & Night Tours", "Segway Tours",
            "Potomac River Cruise", "Museum & Gallery",
            "Sightseeing Tours", "Historical & Political Tours",
            "Day Trips (Mount Vernon, Baltimore)",
            "Cultural & Heritage", "Family & Kids",
            "Passes & Combos", "Luxury & Private", "Transfers",
        ],
    ),
    (
        "efe726c4-75a0-4de1-9693-d5dd739f6c1b", "Los Angeles", "Los Angeles",
        [
            "Universal Studios Hollywood", "Hollywood & Celebrity Homes Tours",
            "Landmark Tickets", "Beach Tours (Santa Monica, Venice)",
            "Disneyland Anaheim", "Movie Studio Tours",
            "Museum & Gallery", "Sightseeing Tours",
            "Wine Country Day Trips", "Cultural & Heritage",
            "Family & Kids", "Passes & Combos",
            "Luxury & Private", "Night Tours & Entertainment",
            "Transfers",
        ],
    ),
]


# ── Common pipeline helpers ─────────────────────────────────────────────

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


async def _run_category_once(logger, city_id_str, category, idx, total, attempt):
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.discovery_service import run_discovery, approve_sources
    from app.services.pipeline_service import run_pipeline_for_discovery
    from sqlalchemy import select
    from app.db.models.scraping import ScrapeSource

    city_id = UUID(city_id_str)
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
                product_type="activities",
                triggered_by=admin_id,
            )
            run_id = discovery_run.id
            sources_found = discovery_run.sources_found or 0
            logger.info(
                "[%d/%d] Discovery: %s — run_id=%s sources_found=%d",
                idx, total, category, run_id, sources_found,
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
    total_enriched = 0
    async with async_session_factory() as db:
        jobs = await run_pipeline_for_discovery(
            db, discovery_run_id=run_id, category=category,
            product_type="activities", triggered_by=admin_id,
        )
        for job in jobs:
            total_saved += job.records_saved or 0
            total_enriched += job.records_enriched or 0
            logger.info(
                "[%d/%d] Job %s: %s — found=%s saved=%s dup=%s enriched=%s",
                idx, total, job.id, category,
                job.records_found, job.records_saved,
                job.records_skipped_dup, job.records_enriched,
            )

    logger.info("[%d/%d] DONE: %s — saved=%d enriched=%d",
                idx, total, category, total_saved, total_enriched)
    return {"category": category, "status": "completed", "saved": total_saved, "enriched": total_enriched}


async def _run_one_category(sem, logger, city_id_str, category, idx, total):
    async with sem:
        last_exc = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await _run_category_once(logger, city_id_str, category, idx, total, attempt)
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


async def process_city(city_id_str, display_name, city_col_value, categories):
    slug = display_name.lower().replace(" ", "-")
    log_path = f"/tmp/rayna-logs/queue-{slug}.log"

    # Set up per-city file logger (in addition to master stdout)
    city_logger = logging.getLogger(f"queue.{slug}")
    city_logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    city_logger.addHandler(fh)
    # Also propagate to root (so master log sees everything)
    city_logger.propagate = True

    city_logger.info("=" * 70)
    city_logger.info("CITY START: %s — %d categories, max %d concurrent",
                     display_name, len(categories), MAX_CONCURRENT)
    city_logger.info("=" * 70)

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [
        _run_one_category(sem, city_logger, city_id_str, cat, i, len(categories))
        for i, cat in enumerate(categories, 1)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    city_logger.info("=" * 70)
    city_logger.info("%s FINAL SUMMARY", display_name.upper())
    city_logger.info("=" * 70)
    total_saved = 0
    for r in results:
        city_logger.info("  %s: %s (saved=%s)", r["category"], r["status"], r.get("saved", "N/A"))
        total_saved += r.get("saved", 0) or 0

    try:
        from app.db.base import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as db:
            row = await db.execute(text(
                "SELECT count(*) FROM activities WHERE city = :c"
            ), {"c": city_col_value})
            db_count = row.scalar()
            city_logger.info("Total %s activities in DB: %d", display_name, db_count)
            master_logger.info("[QUEUE] %s finished — saved this run=%d, total in DB=%d",
                               display_name, total_saved, db_count)
    except Exception as exc:
        city_logger.warning("Final count query failed: %s", exc)

    city_logger.removeHandler(fh)
    fh.close()


def _wait_for_prior_pipelines():
    """Poll pgrep every 30s until no blocking pipeline is running."""
    import subprocess
    while True:
        alive = False
        for pat in BLOCKING_PATTERNS:
            r = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True)
            if r.stdout.strip():
                alive = True
                break
        if not alive:
            master_logger.info("[QUEUE] No blocking pipelines — starting queue.")
            return
        master_logger.info("[QUEUE] Blocking pipeline still alive, sleeping 30s…")
        time.sleep(30)


async def main():
    master_logger.info("[QUEUE] Master starting — %d cities queued", len(CITIES))
    _wait_for_prior_pipelines()

    for idx, (city_id, display_name, city_col_value, categories) in enumerate(CITIES, 1):
        master_logger.info("[QUEUE] === CITY %d/%d: %s ===", idx, len(CITIES), display_name)
        start_ts = time.time()
        try:
            await process_city(city_id, display_name, city_col_value, categories)
        except Exception as exc:
            master_logger.error("[QUEUE] CITY %s CRASHED: %s", display_name, exc)
            traceback.print_exc()
        elapsed = time.time() - start_ts
        master_logger.info("[QUEUE] CITY %s took %.1f minutes", display_name, elapsed / 60)

    master_logger.info("[QUEUE] === QUEUE COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
