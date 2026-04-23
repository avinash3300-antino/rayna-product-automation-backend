"""Backfill reviews for activities that are missing review_snippets."""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger("backfill_reviews")

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"


async def main():
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.review_service import scrape_reviews_for_product
    from sqlalchemy import select
    from app.db.models.activities import Activity

    city_id = UUID(LONDON_CITY_ID)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(
                Activity.city_id == city_id,
                Activity.review_snippets == None,
            ).order_by(Activity.category)
        )
        activities = list(result.scalars().all())

    logger.info("Found %d activities needing reviews", len(activities))

    success = 0
    failed = 0

    for i, act in enumerate(activities, 1):
        logger.info("[%d/%d] %s — %s", i, len(activities), act.category, act.name)
        try:
            async with async_session_factory() as db:
                result = await scrape_reviews_for_product(
                    db,
                    product_id=act.id,
                    product_type="activities",
                    product_name=act.name,
                    product_city=act.city,
                    product_country=act.country,
                )
                logger.info("  OK: %s", result)
                success += 1
        except Exception as exc:
            logger.warning("  FAILED: %s", str(exc)[:150])
            failed += 1

        # Rate limiting (2s between calls)
        await asyncio.sleep(2)

    logger.info("=" * 60)
    logger.info("REVIEWS BACKFILL COMPLETE: %d success, %d failed", success, failed)


if __name__ == "__main__":
    asyncio.run(main())
