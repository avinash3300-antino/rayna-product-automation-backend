"""Backfill gallery images for ALL active activities missing gallery_json.

Uses Pexels -> Unsplash -> Freepik (in that order — Pexels/Unsplash are
attribution-free; Freepik is last-resort).

Idempotent: only processes activities with NULL/empty gallery_json.

Usage: python backfill_gallery_all_cities.py --num-images 8
"""
import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("gallery_all")


async def main(num_images: int, concurrency: int):
    from app.db.base import async_session_factory
    from app.services.image_service import fetch_and_upload_images
    from app.db.models.activities import Activity
    from sqlalchemy import select

    # Load target activities: ONLY those with tour_variants (options) AND missing gallery.
    # Per user direction: focus image backfill on the ~1.5k option-rich rows first.
    from sqlalchemy import text
    async with async_session_factory() as db:
        result = await db.execute(text("""
            SELECT id, name, city, cover_image_url
            FROM activities
            WHERE tour_variants IS NOT NULL
              AND tour_variants::text NOT IN ('null','[]')
              AND (gallery_json IS NULL OR gallery_json::text IN ('null','[]'))
              AND deleted_at IS NULL AND merged_into_id IS NULL
            ORDER BY city, category
        """))
        rows = result.fetchall()

    logger.info("Gallery backfill (options-only scope): %d activities missing gallery", len(rows))

    sem = asyncio.Semaphore(concurrency)
    stats = {"success": 0, "failed": 0, "no_images": 0}
    per_city_last: dict[str, int] = {}

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
                if idx % 50 == 0:
                    logger.info("[%d/%d] progress — success=%d, no_images=%d, failed=%d",
                                idx, len(rows), stats["success"], stats["no_images"], stats["failed"])
            except Exception as exc:
                stats["failed"] += 1
                logger.warning("[%d/%d] FAILED %s (%s): %s",
                               idx, len(rows), a_name[:40], a_city, str(exc)[:120])

    tasks = [
        _one(i, r.id, r.name, r.city, r.cover_image_url)
        for i, r in enumerate(rows, 1)
    ]

    # Process in chunks so we can log progress every ~50 activities
    CHUNK = concurrency * 8
    for i in range(0, len(tasks), CHUNK):
        chunk = tasks[i : i + CHUNK]
        await asyncio.gather(*chunk, return_exceptions=True)

    logger.info("=" * 60)
    logger.info("DONE: success=%d, no_images=%d, failed=%d (total %d)",
                stats["success"], stats["no_images"], stats["failed"], len(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-images", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(main(args.num_images, args.concurrency))
