"""Backfill remaining gallery images and reviews for all activities."""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Suppress noisy SQLAlchemy logs
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger("backfill")

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"


async def main():
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.image_service import fetch_and_upload_images
    from app.services.review_service import scrape_reviews_for_product
    from sqlalchemy import select
    from app.db.models.activities import Activity

    city_id = UUID(LONDON_CITY_ID)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(Activity.city_id == city_id).order_by(Activity.category)
        )
        activities = list(result.scalars().all())

    logger.info("Found %d activities total", len(activities))

    # Filter to those needing work
    need_gallery = [a for a in activities if not a.gallery_json]
    need_reviews = [a for a in activities if not a.review_snippets]

    logger.info("Need gallery: %d, Need reviews: %d", len(need_gallery), len(need_reviews))

    gallery_count = 0
    review_count = 0
    gallery_fail = 0
    review_fail = 0

    # ── Step 1: Gallery images for activities missing them ──
    logger.info("=" * 60)
    logger.info("STEP 1: Gallery images (%d activities)", len(need_gallery))
    logger.info("=" * 60)

    for i, act in enumerate(need_gallery, 1):
        logger.info("[Gallery %d/%d] %s — %s", i, len(need_gallery), act.category, act.name)
        try:
            gallery = await fetch_and_upload_images(
                act.name, act.city, str(act.id),
                product_type="activities", num_images=8,
            )
            if gallery:
                async with async_session_factory() as db:
                    a = await db.get(Activity, act.id)
                    a.gallery_json = gallery
                    if not a.cover_image_url:
                        a.cover_image_url = gallery[0]["url"]
                    await db.commit()
                gallery_count += 1
                logger.info("  OK: %d images", len(gallery))
            else:
                logger.warning("  No images returned")
                gallery_fail += 1
        except Exception as exc:
            logger.warning("  FAILED: %s", str(exc)[:120])
            gallery_fail += 1

        # Rate limiting
        if i % 3 == 0:
            await asyncio.sleep(2)

    # ── Step 2: Reviews for activities missing them ──
    logger.info("=" * 60)
    logger.info("STEP 2: Reviews (%d activities)", len(need_reviews))
    logger.info("=" * 60)

    for i, act in enumerate(need_reviews, 1):
        logger.info("[Reviews %d/%d] %s — %s", i, len(need_reviews), act.category, act.name)
        try:
            async with async_session_factory() as db:
                await scrape_reviews_for_product(
                    db,
                    product_id=act.id,
                    product_type="activities",
                    product_name=act.name,
                    product_city=act.city,
                    product_country=act.country,
                )
            review_count += 1
            logger.info("  OK: Reviews scraped")
        except Exception as exc:
            logger.warning("  FAILED: %s", str(exc)[:120])
            review_fail += 1

        # Rate limiting (reviews use SearchAPI + Claude)
        if i % 2 == 0:
            await asyncio.sleep(2)

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("  Gallery: %d success, %d failed", gallery_count, gallery_fail)
    logger.info("  Reviews: %d success, %d failed", review_count, review_fail)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
