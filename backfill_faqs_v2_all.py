"""Full FAQ v2 backfill for tier-0 (options + gallery) activities WITHOUT existing FAQs.

Scope: activities where tour_variants NOT NULL AND gallery_json NOT NULL
       AND (faqs IS NULL OR faqs empty/short).

Concurrency: 8 parallel Claude Haiku 4.5 calls with validation gate + regen.
"""
import argparse
import asyncio
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("faq_all")


async def main(concurrency: int, limit: int):
    from app.db.base import async_session_factory
    from app.services.faq_service_v2 import generate_faqs_for_activity_v2
    from sqlalchemy import text

    async with async_session_factory() as db:
        query = """
          SELECT id, name, city
          FROM activities
          WHERE deleted_at IS NULL AND merged_into_id IS NULL
            AND tour_variants IS NOT NULL AND tour_variants::text NOT IN ('null','[]')
            AND gallery_json IS NOT NULL AND gallery_json::text NOT IN ('null','[]')
            AND (faqs IS NULL OR faqs::text IN ('null','[]'))
          ORDER BY city, name
        """
        if limit and limit > 0:
            query += f" LIMIT {int(limit)}"
        r = await db.execute(text(query))
        rows = r.fetchall()

    logger.info("FAQ v2 sweep: %d activities to process (concurrency=%d)", len(rows), concurrency)

    stats = {"ok": 0, "part": 0, "fail": 0, "attempts_total": 0}
    sem = asyncio.Semaphore(concurrency)
    start = time.time()

    async def _one(i, a_id, a_name, a_city):
        async with sem:
            try:
                async with async_session_factory() as db:
                    out = await generate_faqs_for_activity_v2(db, a_id)
                    await db.commit()
                stats["attempts_total"] += out["attempts"]
                if out["ok"]:
                    stats["ok"] += 1
                else:
                    stats["part"] += 1
                if i % 25 == 0 or i == len(rows):
                    elapsed = time.time() - start
                    rate = i / elapsed if elapsed > 0 else 0
                    eta_min = (len(rows) - i) / rate / 60 if rate > 0 else 0
                    logger.info(
                        "[%d/%d] ok=%d part=%d fail=%d avg_attempts=%.2f | %.1f/min | ETA %.0fm",
                        i, len(rows), stats["ok"], stats["part"], stats["fail"],
                        stats["attempts_total"] / max(1, i), rate * 60, eta_min,
                    )
            except Exception as exc:
                stats["fail"] += 1
                logger.warning("[%d/%d] FAIL %s (%s): %s",
                               i, len(rows), a_name[:40], a_city, str(exc)[:150])

    tasks = [_one(i, r.id, r.name, r.city) for i, r in enumerate(rows, 1)]

    # Chunk so a hang doesn't lock everything
    CHUNK = concurrency * 6
    for i in range(0, len(tasks), CHUNK):
        chunk = tasks[i : i + CHUNK]
        await asyncio.gather(*chunk, return_exceptions=True)

    logger.info("=" * 60)
    logger.info(
        "DONE: ok=%d, partial=%d, failed=%d, avg attempts=%.2f, elapsed=%.1fm",
        stats["ok"], stats["part"], stats["fail"],
        stats["attempts_total"] / max(1, len(rows)),
        (time.time() - start) / 60,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="0 for all")
    args = parser.parse_args()
    asyncio.run(main(args.concurrency, args.limit))
