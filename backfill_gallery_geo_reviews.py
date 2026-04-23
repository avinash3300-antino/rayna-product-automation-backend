"""Backfill gallery images, geocoding, and reviews for all activities."""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open("backfill_output.log", "w", encoding="utf-8"))],
)
# Also print to console (UTF-8 safe)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
logging.getLogger("backfill").addHandler(console)

logger = logging.getLogger("backfill")

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"


async def main():
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.image_service import fetch_and_upload_images
    from app.services.geocoding_service import geocode_activity
    from app.services.review_service import scrape_reviews_for_product
    from sqlalchemy import select
    from app.db.models.activities import Activity

    city_id = UUID(LONDON_CITY_ID)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(Activity.city_id == city_id).order_by(Activity.category)
        )
        activities = list(result.scalars().all())

    logger.info("Found %d activities to backfill", len(activities))

    gallery_count = 0
    geo_count = 0
    review_count = 0

    for i, act in enumerate(activities, 1):
        logger.info("[%d/%d] %s — %s", i, len(activities), act.category, act.name)

        # Gallery
        if not act.gallery_json:
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
                    logger.info("  Gallery: %d images", len(gallery))
            except Exception as exc:
                logger.warning("  Gallery failed: %s", str(exc)[:100])

        # Geocoding
        if act.lat == 0 or act.lng == 0:
            try:
                coords = await geocode_activity(
                    act.name, act.city, act.country,
                    getattr(act, "address", None),
                )
                if coords["lat"] != 0:
                    async with async_session_factory() as db:
                        a = await db.get(Activity, act.id)
                        a.lat = coords["lat"]
                        a.lng = coords["lng"]
                        await db.commit()
                    geo_count += 1
                    logger.info("  Geocoded: %s, %s", coords["lat"], coords["lng"])
            except Exception as exc:
                logger.warning("  Geocode failed: %s", str(exc)[:100])

        # Reviews (only for first 3 per category to save API calls)
        if not act.review_snippets and (i % 5 == 1):  # ~1 in 5 activities
            try:
                await scrape_reviews_for_product(
                    product_id=act.id,
                    product_type="activities",
                    product_name=act.name,
                    city=act.city,
                    country=act.country,
                )
                review_count += 1
                logger.info("  Reviews scraped")
            except Exception as exc:
                logger.warning("  Reviews failed: %s", str(exc)[:100])

        # Rate limiting
        if i % 3 == 0:
            await asyncio.sleep(1)

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETE: %d gallery, %d geocoded, %d reviews", gallery_count, geo_count, review_count)


if __name__ == "__main__":
    asyncio.run(main())
