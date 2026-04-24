"""Backfill cover images to Cloudinary.

Finds activities whose cover_image_url is NOT on Cloudinary,
re-uploads them, and updates the DB.
"""

import asyncio
import logging
import sys

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import async_session_factory
from app.db.models.activities import Activity
from app.services.s3_service import upload_from_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CLOUDINARY_DOMAINS = ("res.cloudinary.com",)
BATCH_SIZE = 10


async def main():
    async with async_session_factory() as db:
        # Find activities with non-Cloudinary cover images
        stmt = select(Activity).where(
            Activity.cover_image_url.isnot(None),
            Activity.cover_image_url != "",
            ~Activity.cover_image_url.contains("res.cloudinary.com"),
        )
        result = await db.execute(stmt)
        activities = result.scalars().all()

        total = len(activities)
        logger.info("Found %d activities with non-Cloudinary cover images", total)

        if total == 0:
            logger.info("Nothing to do.")
            return

        success = 0
        failed = 0

        for i, activity in enumerate(activities, 1):
            try:
                key = f"activities/{activity.id}/cover.webp"
                new_url = await upload_from_url(
                    source_url=activity.cover_image_url,
                    key=key,
                    resize=(1200, 800),
                )
                activity.cover_image_url = new_url
                success += 1
                logger.info(
                    "[%d/%d] Uploaded: %s -> %s",
                    i, total, activity.name[:50], new_url[:80],
                )
            except Exception as exc:
                failed += 1
                logger.error(
                    "[%d/%d] FAILED: %s — %s",
                    i, total, activity.name[:50], exc,
                )

            # Commit in batches
            if i % BATCH_SIZE == 0:
                await db.commit()
                logger.info("Committed batch %d", i // BATCH_SIZE)
                await asyncio.sleep(0.5)

        # Final commit
        await db.commit()
        logger.info(
            "Done. Success: %d, Failed: %d, Total: %d",
            success, failed, total,
        )


if __name__ == "__main__":
    asyncio.run(main())
