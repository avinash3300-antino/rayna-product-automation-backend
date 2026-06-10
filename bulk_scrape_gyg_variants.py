"""Bulk scrape tour variants for GYG-source activities missing variants.

Uses the new date-click flow in tour_variants_service._scrape_gyg_with_date_click
which: opens the GYG page → clicks Check Availability → picks date 7 days out
→ extracts the rendered options panel via Claude → saves as AED + per-1-adult.

Only targets activities where the primary source_url is GetYourGuide.
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

logger = logging.getLogger("gyg-bulk")


def _has_variants(activity) -> bool:
    v = activity.tour_variants
    return isinstance(v, list) and len(v) > 0


async def main(city: str | None, limit: int | None) -> None:
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.services.tour_variants_service import scrape_variants_for_activity

    async with async_session_factory() as db:
        q = select(Activity).where(
            Activity.source_url.ilike("%getyourguide.com%"),
        ).order_by(Activity.name)
        if city:
            q = q.where(Activity.city.ilike(city))
        result = await db.execute(q)
        all_acts = list(result.scalars().all())

    # Filter in Python: need variants AND has source_url
    need = [a for a in all_acts if not _has_variants(a)]

    logger.info("=" * 60)
    logger.info("GYG bulk: %d total GYG activities, %d need variants",
                len(all_acts), len(need))
    logger.info("=" * 60)

    if limit:
        need = need[:limit]
        logger.info("Limited to first %d", limit)

    updated = 0
    no_options = 0
    errors = 0

    for i, act in enumerate(need, 1):
        logger.info("[%d/%d] %s — %s", i, len(need), act.city, act.name[:70])
        try:
            async with async_session_factory() as db:
                result = await scrape_variants_for_activity(db, act.id)
                await db.commit()

            if result.get("updated"):
                updated += 1
                count = result.get("new_count", "?")
                logger.info("  OK: %s options scraped", count)
            else:
                no_options += 1
                logger.info("  No options found")
        except Exception as exc:
            errors += 1
            logger.warning("  FAILED: %s", str(exc)[:140])

        # Light rate-limit every 3 activities
        if i % 3 == 0:
            await asyncio.sleep(2)

    logger.info("=" * 60)
    logger.info("DONE GYG-BULK — Updated: %d  No options: %d  Errors: %d",
                updated, no_options, errors)
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", help="Filter by city (e.g. 'London' or 'Cairo')")
    parser.add_argument("--limit", type=int, help="Cap activities processed")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.city, args.limit))
    except KeyboardInterrupt:
        print("\nInterrupted — committed work survives (commit-per-activity).")
        sys.exit(130)
