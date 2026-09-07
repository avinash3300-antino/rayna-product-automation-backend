"""Backfill gallery images for ALL active activities missing gallery_json.

Order: Pexels -> Unsplash -> Freepik (attribution-free preferred).
Scope: every deleted_at IS NULL AND merged_into_id IS NULL activity with
       NULL/empty gallery_json (regardless of tour_variants).

Idempotent: skips activities that already have a gallery.

Usage: python backfill_gallery_full.py --num-images 8 --concurrency 5
"""
import argparse
import asyncio
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("gallery_full")


async def main(num_images: int, concurrency: int):
    from app.db.base import async_session_factory
    from app.services.image_service import fetch_and_upload_images
    from app.db.models.activities import Activity
    from sqlalchemy import text

    async with async_session_factory() as db:
        result = await db.execute(text("""
            SELECT id, name, city, cover_image_url
            FROM activities
            WHERE deleted_at IS NULL AND merged_into_id IS NULL
              AND (gallery_json IS NULL OR gallery_json::text IN ('null','[]'))
            ORDER BY city, category
        """))
        rows = result.fetchall()

    logger.info("Full gallery backfill: %d activities missing gallery (concurrency=%d)",
                len(rows), concurrency)

    sem = asyncio.Semaphore(concurrency)
    stats = {"success": 0, "failed": 0, "no_images": 0}
    start = time.time()

    async def _one(idx, a_id, a_name, a_city, cover_url):
        async with sem:
            try:
                gallery = await fetch_and_upload_images(
                    a_name, a_city or "", str(a_id),
                    product_type="activities", num_images=num_images,
                )
                if not gallery:
                    stats["no_images"] += 1
                    return
                async with async_session_factory() as db:
                    a = await db.get(Activity, a_id)
                    a.gallery_json = gallery
                    if not a.cover_image_url:
                        a.cover_image_url = gallery[0]["url"]
                    await db.commit()
                stats["success"] += 1
                if idx % 50 == 0 or idx == len(rows):
                    elapsed = time.time() - start
                    rate = idx / elapsed if elapsed > 0 else 0
                    eta_min = (len(rows) - idx) / rate / 60 if rate > 0 else 0
                    logger.info(
                        "[%d/%d] success=%d, no_images=%d, failed=%d | %.1f/min | ETA %.0fm",
                        idx, len(rows), stats["success"], stats["no_images"], stats["failed"],
                        rate * 60, eta_min,
                    )
            except Exception as exc:
                stats["failed"] += 1
                logger.warning("[%d/%d] FAILED %s (%s): %s",
                               idx, len(rows), a_name[:40], a_city, str(exc)[:120])

    tasks = [_one(i, r.id, r.name, r.city, r.cover_image_url)
             for i, r in enumerate(rows, 1)]

    CHUNK = concurrency * 8
    for i in range(0, len(tasks), CHUNK):
        chunk = tasks[i : i + CHUNK]
        await asyncio.gather(*chunk, return_exceptions=True)

    logger.info("=" * 60)
    logger.info(
        "DONE: success=%d, no_images=%d, failed=%d (total %d), elapsed=%.1fm",
        stats["success"], stats["no_images"], stats["failed"], len(rows),
        (time.time() - start) / 60,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-images", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(main(args.num_images, args.concurrency))
