"""Enrich raw reviews on tier-0 activities using Gemini Flash.

Uses the existing ENRICH_SYSTEM_PROMPT from review_service:
  - Polishes grammar
  - Preserves sentiment, facts, rating
  - Strips OTA brand mentions
  - Marks with __SKIP__ if unusable after brand-stripping

Idempotent: only processes rows where enriched_text IS NULL.
"""
import argparse
import asyncio
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("enrich_reviews")


async def main(concurrency: int, limit: int):
    from app.db.base import async_session_factory
    from app.db.models.reviews import ProductReview
    from app.services.review_service import enrich_single_review
    from sqlalchemy import text, select, update

    async with async_session_factory() as db:
        # tier-0 activity IDs
        r = await db.execute(text("""
          SELECT id FROM activities
          WHERE deleted_at IS NULL AND merged_into_id IS NULL
            AND tour_variants IS NOT NULL AND tour_variants::text NOT IN ('null','[]')
            AND gallery_json IS NOT NULL AND gallery_json::text NOT IN ('null','[]')
        """))
        tier0_ids = [row.id for row in r.fetchall()]

        # Reviews on tier-0 without enriched_text
        query = text(f"""
          SELECT id, review_text FROM product_reviews
          WHERE product_type='activities'
            AND enriched_text IS NULL
            AND review_text IS NOT NULL AND length(review_text) >= 20
            AND product_id = ANY(:ids)
          {f"LIMIT {int(limit)}" if limit and limit > 0 else ""}
        """)
        r = await db.execute(query, {"ids": tier0_ids})
        rows = r.fetchall()

    logger.info("Enrich sweep: %d reviews to process (concurrency=%d)", len(rows), concurrency)

    stats = {"enriched": 0, "skipped": 0, "failed": 0}
    sem = asyncio.Semaphore(concurrency)
    start = time.time()

    async def _one(idx, review_id, original_text):
        async with sem:
            try:
                enriched = await enrich_single_review(original_text, provider="gemini")
            except Exception as exc:
                stats["failed"] += 1
                logger.warning("[%d] enrich failed: %s", idx, str(exc)[:120])
                return

            async with async_session_factory() as db:
                if enriched is None:
                    # Mark as skipped by storing __SKIP__ so we don't retry it
                    await db.execute(
                        update(ProductReview)
                        .where(ProductReview.id == review_id)
                        .values(enriched_text="__SKIP__")
                    )
                    stats["skipped"] += 1
                else:
                    await db.execute(
                        update(ProductReview)
                        .where(ProductReview.id == review_id)
                        .values(enriched_text=enriched[:5000])
                    )
                    stats["enriched"] += 1
                await db.commit()

            if idx % 200 == 0 or idx == len(rows):
                elapsed = time.time() - start
                rate = idx / elapsed if elapsed > 0 else 0
                eta_min = (len(rows) - idx) / rate / 60 if rate > 0 else 0
                logger.info(
                    "[%d/%d] enriched=%d skipped=%d failed=%d | %.1f/min | ETA %.0fm",
                    idx, len(rows), stats["enriched"], stats["skipped"], stats["failed"],
                    rate * 60, eta_min,
                )

    tasks = [_one(i, r.id, r.review_text) for i, r in enumerate(rows, 1)]

    CHUNK = concurrency * 20
    for i in range(0, len(tasks), CHUNK):
        chunk = tasks[i : i + CHUNK]
        await asyncio.gather(*chunk, return_exceptions=True)

    logger.info("=" * 60)
    logger.info(
        "DONE: enriched=%d skipped=%d failed=%d elapsed=%.1fm",
        stats["enriched"], stats["skipped"], stats["failed"],
        (time.time() - start) / 60,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0, help="0 for all")
    args = parser.parse_args()
    asyncio.run(main(args.concurrency, args.limit))
