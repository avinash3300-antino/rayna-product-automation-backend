"""Backfill additional source URLs for activities that only have 1 source.

Uses discover_additional_source_urls() to search Google for matching
listings on other booking platforms (Viator, GetYourGuide, Klook, etc.)

Usage: python backfill_source_urls.py [--city Cairo] [--max-new 2]
"""

import argparse
import asyncio
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("backfill_sources")

BATCH_SIZE = 10
PAUSE_EVERY = 10
PAUSE_SECONDS = 2


async def main(city_name: str, max_new: int):
    from sqlalchemy import select, func, text
    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.services.discovery_service import discover_additional_source_urls

    async with async_session_factory() as db:
        # Find activities with only 1 source URL
        stmt = (
            select(Activity)
            .where(Activity.city == city_name)
            .where(func.json_array_length(Activity.source_urls) <= 1)
            .order_by(Activity.name)
        )
        result = await db.execute(stmt)
        activities = result.scalars().all()

        total = len(activities)
        logger.info("Found %d %s activities with <= 1 source URL", total, city_name)

        updated = 0
        skipped = 0

        for i, activity in enumerate(activities, 1):
            existing_urls = activity.source_urls or [activity.source_url]
            short_name = activity.name[:55].encode("ascii", "replace").decode()

            try:
                new_urls = await discover_additional_source_urls(
                    activity_name=activity.name,
                    activity_city=activity.city,
                    existing_urls=existing_urls,
                    max_new=max_new,
                )

                if new_urls:
                    activity.source_urls = existing_urls + new_urls
                    updated += 1
                    logger.info(
                        "[%d/%d] %s -> +%d URLs (total: %d)",
                        i, total, short_name, len(new_urls),
                        len(activity.source_urls),
                    )
                else:
                    skipped += 1
                    logger.info("[%d/%d] %s -> no new URLs found", i, total, short_name)

            except Exception as e:
                skipped += 1
                logger.error("[%d/%d] %s -> ERROR: %s", i, total, short_name, e)

            # Batch commit
            if i % BATCH_SIZE == 0:
                await db.commit()

            # Rate limit
            if i % PAUSE_EVERY == 0 and i < total:
                await asyncio.sleep(PAUSE_SECONDS)

        # Final commit
        await db.commit()

    logger.info("\nDone! Updated: %d, Skipped: %d, Total: %d", updated, skipped, total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="Cairo", help="City name to backfill")
    parser.add_argument("--max-new", type=int, default=2, help="Max new URLs per activity")
    args = parser.parse_args()

    asyncio.run(main(args.city, args.max_new))
