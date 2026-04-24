"""Backfill enriched review text for all reviews.

Uses Claude AI to create polished versions of original review text.
"""

import asyncio
import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import async_session_factory
from app.db.models.reviews import ProductReview
from app.services.review_service import enrich_single_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 10
DELAY_BETWEEN_BATCHES = 1  # seconds


async def main():
    async with async_session_factory() as db:
        # Count total un-enriched reviews
        count_stmt = select(func.count(ProductReview.id)).where(
            ProductReview.enriched_text.is_(None),
        )
        total = (await db.execute(count_stmt)).scalar() or 0
        logger.info("Found %d reviews needing enrichment", total)

        if total == 0:
            logger.info("Nothing to do.")
            return

        # Process in batches
        offset = 0
        success = 0
        failed = 0

        while offset < total:
            stmt = (
                select(ProductReview)
                .where(ProductReview.enriched_text.is_(None))
                .limit(BATCH_SIZE)
                .offset(0)  # Always 0 since we commit and rows change
            )
            result = await db.execute(stmt)
            reviews = result.scalars().all()

            if not reviews:
                break

            for review in reviews:
                enriched = await enrich_single_review(review.review_text)
                if enriched:
                    review.enriched_text = enriched
                    success += 1
                else:
                    # Mark as failed so we don't retry forever
                    review.enriched_text = review.review_text  # fallback to original
                    failed += 1

            await db.commit()
            offset += len(reviews)
            logger.info(
                "Progress: %d/%d (success: %d, failed: %d)",
                min(offset, total), total, success, failed,
            )
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

        logger.info(
            "Done. Success: %d, Failed: %d, Total: %d",
            success, failed, total,
        )


if __name__ == "__main__":
    asyncio.run(main())
