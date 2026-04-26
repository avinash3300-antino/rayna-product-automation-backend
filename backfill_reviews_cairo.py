"""
Backfill reviews for Cairo activities that have none in product_reviews.
Scrapes Google Maps reviews via SearchAPI, then enriches with Claude.

Usage: python backfill_reviews_cairo.py [--city Cairo] [--max-per-activity 10]
"""
import argparse
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("backfill_reviews")

CAIRO_CITY_ID = "941c503c-82a0-4a76-80ae-f8bb78cd7437"


async def main(city_name: str, max_per_activity: int):
    from sqlalchemy import select, func
    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.db.models.reviews import ProductReview
    from app.services.review_service import scrape_reviews_for_product

    # Find activities with no reviews in product_reviews
    async with async_session_factory() as db:
        # Subquery: activity IDs that already have reviews
        reviewed_ids = select(ProductReview.product_id).where(
            ProductReview.product_type == "activities"
        ).scalar_subquery()

        result = await db.execute(
            select(Activity)
            .where(
                Activity.city == city_name,
                Activity.id.not_in(reviewed_ids),
            )
            .order_by(Activity.category, Activity.name)
        )
        activities = list(result.scalars().all())

    logger.info("Found %d %s activities needing reviews", len(activities), city_name)

    success = 0
    failed = 0
    skipped = 0

    for i, act in enumerate(activities, 1):
        short_name = act.name[:60].encode("ascii", "replace").decode()
        logger.info("[%d/%d] %s — %s", i, len(activities), act.category, short_name)

        try:
            async with async_session_factory() as db:
                result = await scrape_reviews_for_product(
                    db=db,
                    product_id=act.id,
                    product_type="activities",
                    product_name=act.name,
                    product_city=act.city or city_name,
                    product_country=act.country or "Egypt",
                    platforms=["google"],  # Google only — most coverage for Cairo
                )
                total_scraped = result.get("total_scraped", 0)
                await db.commit()

            if total_scraped > 0:
                success += 1
                logger.info("  OK: %d reviews saved", total_scraped)
            else:
                skipped += 1
                logger.info("  No reviews found on Google Maps")

        except Exception as exc:
            failed += 1
            logger.warning("  FAILED: %s", str(exc)[:120])

        # Rate limit: 1s pause every 5 activities
        if i % 5 == 0:
            await asyncio.sleep(1)

    logger.info("=" * 60)
    logger.info(
        "REVIEW BACKFILL COMPLETE: %d with reviews, %d not found, %d failed (out of %d)",
        success, skipped, failed, len(activities),
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="Cairo", help="City name to backfill")
    parser.add_argument("--max-per-activity", type=int, default=10, help="Max reviews per activity")
    args = parser.parse_args()

    asyncio.run(main(args.city, args.max_per_activity))
