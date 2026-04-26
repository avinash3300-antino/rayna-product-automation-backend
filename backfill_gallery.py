"""Backfill gallery images for activities missing them (Freepik -> Pexels -> Unsplash).

Usage: python backfill_gallery.py [--city Cairo] [--num-images 8]
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

logger = logging.getLogger("backfill_gallery")


async def main(city_name: str, num_images: int):
    from app.db.base import async_session_factory
    from app.services.image_service import fetch_and_upload_images
    from sqlalchemy import select
    from app.db.models.activities import Activity

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(
                Activity.city == city_name,
                Activity.gallery_json == None,
            ).order_by(Activity.category)
        )
        activities = list(result.scalars().all())

    logger.info("Found %d %s activities needing gallery images", len(activities), city_name)

    success = 0
    failed = 0

    for i, act in enumerate(activities, 1):
        short_name = act.name[:55].encode("ascii", "replace").decode()
        logger.info("[%d/%d] %s - %s", i, len(activities), act.category, short_name)
        try:
            gallery = await fetch_and_upload_images(
                act.name, act.city or city_name, str(act.id),
                product_type="activities", num_images=num_images,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="Cairo", help="City name to backfill")
    parser.add_argument("--num-images", type=int, default=8, help="Images per activity")
    args = parser.parse_args()

    asyncio.run(main(args.city, args.num_images))
