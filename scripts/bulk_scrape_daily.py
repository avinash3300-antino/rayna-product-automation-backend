"""Bulk scrape day-wise availability for all activities using Playwright.

Usage:
    python scripts/bulk_scrape_daily.py [--city Cairo] [--limit 10] [--offset 0]
"""

import argparse
import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from app.db.base import async_session_factory
from app.db.models.activities import Activity
from sqlalchemy import select, func


async def main(city: str | None, limit: int, offset: int):
    async with async_session_factory() as db:
        # Count total
        count_q = select(func.count(Activity.id)).where(Activity.source_urls.isnot(None))
        if city:
            count_q = count_q.where(Activity.city.ilike(city))
        total = (await db.execute(count_q)).scalar_one()

        # Fetch activities
        query = select(Activity).where(Activity.source_urls.isnot(None))
        if city:
            query = query.where(Activity.city.ilike(city))
        query = query.order_by(Activity.name).offset(offset).limit(limit)
        result = await db.execute(query)
        activities = list(result.scalars().all())

        print(f"Total activities: {total}")
        print(f"Processing: {len(activities)} (offset={offset}, limit={limit})")
        print("=" * 70)

        from app.services.playwright_scraper import scrape_daily_for_activity

        updated = 0
        failed = 0

        for i, activity in enumerate(activities, 1):
            print(f"\n[{i}/{len(activities)}] {activity.name[:60]}...")
            source_urls = activity.source_urls or []
            if not source_urls:
                print("  SKIP: No source URLs")
                continue

            try:
                res = await scrape_daily_for_activity(db, activity.id)
                if res.get("updated"):
                    updated += 1
                    print(f"  UPDATED: {res.get('updated_fields', [])}")
                    summary = res.get("daily_summary", {})
                    for day, info in summary.items():
                        avail = "Y" if info.get("available") else "N"
                        slots = info.get("time_slots", 0)
                        opts = info.get("options", 0)
                        print(f"    {day}: avail={avail} slots={slots} opts={opts}")
                else:
                    print(f"  NO CHANGE: {res.get('error', 'no updates')}")

                await db.commit()

            except Exception as exc:
                failed += 1
                print(f"  ERROR: {exc}")
                await db.rollback()

        print("\n" + "=" * 70)
        print(f"Done! Updated: {updated}, Failed: {failed}, Total: {len(activities)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    asyncio.run(main(args.city, args.limit, args.offset))
