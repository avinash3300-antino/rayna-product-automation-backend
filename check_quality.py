"""Quick data quality report."""
import asyncio

async def check():
    from app.db.base import async_session_factory
    from sqlalchemy import text
    async with async_session_factory() as db:
        print("=== FINAL DATA QUALITY REPORT ===\n")

        r = await db.execute(text("SELECT count(*) FROM activities"))
        print(f"Total activities: {r.scalar()}")

        r = await db.execute(text(
            "SELECT category, count(*) as cnt FROM activities GROUP BY category ORDER BY cnt DESC"
        ))
        print("\nBY CATEGORY:")
        for row in r.fetchall():
            print(f"  {row[0]}: {row[1]}")

        r = await db.execute(text(
            "SELECT count(*) FROM activities WHERE gallery_json IS NOT NULL"
            " AND gallery_json::text <> 'null' AND gallery_json::text <> '[]'"
        ))
        total = 322
        print(f"\nWith gallery: {r.scalar()}/{total}")

        r = await db.execute(text(
            "SELECT count(*) FROM activities WHERE cover_image_url IS NOT NULL"
            " AND cover_image_url <> ''"
        ))
        print(f"With cover image: {r.scalar()}/{total}")

        r = await db.execute(text(
            "SELECT count(*) FROM activities WHERE lat <> 0 AND lng <> 0"
        ))
        print(f"Geocoded: {r.scalar()}/{total}")

        r = await db.execute(text("SELECT count(*) FROM product_reviews"))
        print(f"Total review records: {r.scalar()}")

        r = await db.execute(text(
            "SELECT count(*) FROM activities WHERE review_snippets IS NOT NULL"
        ))
        print(f"With review_snippets: {r.scalar()}/{total}")

        r = await db.execute(text(
            "SELECT count(*) FROM activities WHERE source_urls IS NOT NULL"
            " AND json_array_length(source_urls) >= 2"
        ))
        print(f"With 2+ source URLs: {r.scalar()}/{total}")

        r = await db.execute(text(
            "SELECT count(*) FROM activities WHERE price_adult > 0"
        ))
        print(f"With pricing: {r.scalar()}/{total}")

        r = await db.execute(text(
            "SELECT count(*) FROM activities WHERE currency = 'AED'"
        ))
        print(f"Currency=AED: {r.scalar()}/{total}")

        r = await db.execute(text(
            "SELECT avg(quality_score)::int, min(quality_score), max(quality_score) FROM activities"
        ))
        row = r.fetchone()
        print(f"Quality score: avg={row[0]}, min={row[1]}, max={row[2]}")

        r = await db.execute(text(
            "SELECT status, count(*) FROM activities GROUP BY status"
        ))
        print("\nStatus breakdown:")
        for row in r.fetchall():
            print(f"  {row[0]}: {row[1]}")

if __name__ == "__main__":
    import logging
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    asyncio.run(check())
