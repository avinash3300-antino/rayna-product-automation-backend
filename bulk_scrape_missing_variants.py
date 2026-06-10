"""Scrape tour_variants for activities that don't have any yet.

Follows the patterns from backfill_remaining.py and run_post_enrich.py:
- Suppress noisy SQLAlchemy/httpx logs
- Hardcode city_ids (London / Cairo) as the proven filter
- Load all activities, filter in Python for missing variants
- One DB session per write so partial progress is safe
- Periodic rate limiting

Uses the updated tour_variants_service which now converts prices to AED
and prompts Claude for per-1-adult pricing.

Usage:
    python bulk_scrape_missing_variants.py --city london
    python bulk_scrape_missing_variants.py --city cairo
    python bulk_scrape_missing_variants.py --city london --limit 10   # smoke test
"""

import argparse
import asyncio
import logging
import sys
from uuid import UUID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("variants")

CITY_IDS = {
    "london": UUID("c5cda0a7-0b95-4a26-a8b4-1001b81014a5"),
    "cairo": UUID("941c503c-82a0-4a76-80ae-f8bb78cd7437"),
}


def _has_variants(activity) -> bool:
    v = activity.tour_variants
    return isinstance(v, list) and len(v) > 0


async def main(city: str, limit: int | None) -> None:
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.services.tour_variants_service import scrape_variants_for_activity

    city_id = CITY_IDS[city.lower()]

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(Activity.city_id == city_id).order_by(Activity.name)
        )
        all_activities = list(result.scalars().all())

    # Filter in Python — same pattern as backfill_remaining.py
    need_variants = [
        a for a in all_activities
        if not _has_variants(a) and (a.source_urls or a.source_url)
    ]

    logger.info("=" * 60)
    logger.info("%s: %d total activities, %d need variants (%d already have)",
                city.upper(), len(all_activities), len(need_variants),
                len(all_activities) - len(need_variants))
    logger.info("=" * 60)

    if limit:
        need_variants = need_variants[:limit]
        logger.info("Limited to first %d", limit)

    updated = 0
    no_variants = 0
    errors = 0

    for i, act in enumerate(need_variants, 1):
        logger.info("[%d/%d] %s — %s", i, len(need_variants), act.category, act.name)
        try:
            async with async_session_factory() as db:
                result = await scrape_variants_for_activity(db, act.id)
                await db.commit()

            if result.get("updated"):
                updated += 1
                count = result.get("new_count", result.get("count", "?"))
                logger.info("  OK: %s options scraped", count)
            else:
                no_variants += 1
                logger.info("  No options found")
        except Exception as exc:
            errors += 1
            logger.warning("  FAILED: %s", str(exc)[:120])

        # Rate limit every 3 (Claude + Jina/Apify quotas)
        if i % 3 == 0:
            await asyncio.sleep(2)

    logger.info("=" * 60)
    logger.info("DONE %s — Updated: %d  No options: %d  Errors: %d",
                city.upper(), updated, no_variants, errors)
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True, choices=["london", "cairo"])
    parser.add_argument("--limit", type=int, help="Smoke-test mode: cap activities processed")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.city, args.limit))
    except KeyboardInterrupt:
        print("\nInterrupted — completed iterations were committed independently.")
        sys.exit(130)
