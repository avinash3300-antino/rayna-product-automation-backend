"""Scrape variants for activities sourced from sites OTHER than Viator/GYG.

Targets Ticketmaster, VisitLondon, WB Studio Tour, LondonTheatre, Other.
Uses the existing tour_variants_service pipeline (Jina → Apify → Playwright).
"""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("other-bulk")


def _has_variants(activity) -> bool:
    v = activity.tour_variants
    return isinstance(v, list) and len(v) > 0


async def main(limit: int | None) -> None:
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.services.tour_variants_service import scrape_variants_for_activity

    async with async_session_factory() as db:
        q = select(Activity).where(
            ~Activity.source_url.ilike("%viator.com%"),
            ~Activity.source_url.ilike("%getyourguide.com%"),
        ).order_by(Activity.name)
        result = await db.execute(q)
        all_acts = list(result.scalars().all())

    targets = [a for a in all_acts if not _has_variants(a)]

    logger.info("=" * 60)
    logger.info("Other sources: %d activities (Ticketmaster/VisitLondon/WB/etc)",
                len(targets))
    logger.info("=" * 60)

    if limit:
        targets = targets[:limit]
        logger.info("Limited to first %d", limit)

    wins = 0
    no_options = 0
    errors = 0

    for i, act in enumerate(targets, 1):
        logger.info("[%d/%d] %s — %s", i, len(targets), act.city, act.name[:60])
        logger.info("       url: %s", act.source_url[:90])
        try:
            async with async_session_factory() as db:
                result = await scrape_variants_for_activity(db, act.id)
                await db.commit()

            if result.get("updated"):
                wins += 1
                count = result.get("new_count", "?")
                logger.info("  OK: %s options scraped", count)
            else:
                no_options += 1
                logger.info("  No options found")
        except Exception as exc:
            errors += 1
            logger.warning("  FAILED: %s", str(exc)[:140])

        if i % 3 == 0:
            await asyncio.sleep(2)

    logger.info("=" * 60)
    logger.info("DONE OTHER-BULK — Wins: %d  No options: %d  Errors: %d",
                wins, no_options, errors)
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Cap activities processed")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.limit))
    except KeyboardInterrupt:
        print("\nInterrupted — committed work survives.")
        sys.exit(130)
