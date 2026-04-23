"""Backfill gallery images for activities missing them (Freepik -> Pexels -> Unsplash)."""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("backfill_gallery")

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"


async def main():
    from uuid import UUID
    from app.db.base import async_session_factory
    from app.services.image_service import fetch_and_upload_images
    from sqlalchemy import select
    from app.db.models.activities import Activity

    city_id = UUID(LONDON_CITY_ID)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(
                Activity.city_id == city_id,
                Activity.gallery_json == None,
            ).order_by(Activity.category)
        )
        activities = list(result.scalars().all())

    logger.info("Found %d activities needing gallery images", len(activities))

    success = 0
    failed = 0

    for i, act in enumerate(activities, 1):
        logger.info("[%d/%d] %s - %s", i, len(activities), act.category, act.name)
        try:
            gallery = await fetch_and_upload_images(
                act.name, act.city or "London", str(act.id),
                product_type="activities", num_images=8,
            )
            if gallery:
                async with async_session_factory() as db:
                    a = await db.get(Activity, act.id)
                    a.gallery_json = gallery
                    if not a.cover_image_url:
                        a.cover_image_url = gallery[0]["url"]
                    await db.commit()
                success += 1
                logger.info("  OK: %d images uploaded to Cloudinary", len(gallery))
            else:
                failed += 1
                logger.warning("  No images found from any source")
        except Exception as exc:
            failed += 1
            logger.warning("  FAILED: %s", str(exc)[:120])

        # Rate limiting - 1s between activities
        await asyncio.sleep(1)

    logger.info("=" * 60)
    logger.info("GALLERY BACKFILL COMPLETE: %d success, %d failed (out of %d)",
                success, failed, len(activities))
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
