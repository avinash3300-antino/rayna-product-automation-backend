"""One-off: recompute dedup_hash for all active activities using the new
normalized-name formula (category-agnostic). Only affects live rows so
future pipeline scrapes see accurate dupe matches.
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("backfill_hash")


async def main():
    from app.db.base import async_session_factory
    from app.services.dedup_service import compute_dedupe_hash
    from sqlalchemy import text

    async with async_session_factory() as db:
        result = await db.execute(text("""
            SELECT id, name, city, category
            FROM activities
            WHERE deleted_at IS NULL AND merged_into_id IS NULL
        """))
        rows = result.fetchall()

    logger.info("Backfilling %d active activities", len(rows))
    updated = 0
    async with async_session_factory() as db:
        for i, r in enumerate(rows, 1):
            new_hash = compute_dedupe_hash(r.name, r.city, r.category)
            await db.execute(text(
                "UPDATE activities SET dedup_hash = :h WHERE id = :id"
            ), {"h": new_hash, "id": r.id})
            updated += 1
            if i % 500 == 0:
                await db.commit()
                logger.info("progress %d/%d", i, len(rows))
        await db.commit()
    logger.info("Done. Updated %d rows.", updated)


if __name__ == "__main__":
    asyncio.run(main())
