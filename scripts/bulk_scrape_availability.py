"""Bulk scrape availability for all activities from their source URLs."""

import asyncio
import json
import sys
import os

# Fix encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from app.db.base import async_session_factory
from app.db.models.activities import Activity
from app.services.availability_service import _extract_availability_from_url, _has_availability


async def bulk_scrape(city: str | None = None, limit: int = 500, offset: int = 0):
    """Scrape availability for all activities."""
    async with async_session_factory() as db:
        query = select(Activity).where(Activity.source_urls.isnot(None))
        if city:
            query = query.where(Activity.city.ilike(city))
        query = query.order_by(Activity.name).offset(offset).limit(limit)

        result = await db.execute(query)
        activities = list(result.scalars().all())

        print(f"\n{'='*60}")
        print(f"Bulk Availability Scrape")
        print(f"Total activities to process: {len(activities)}")
        if city:
            print(f"City filter: {city}")
        print(f"{'='*60}\n")

        updated = 0
        failed = 0
        no_change = 0
        skipped = 0

        for i, activity in enumerate(activities, 1):
            source_urls = activity.source_urls or []
            if not source_urls:
                skipped += 1
                print(f"[{i}/{len(activities)}] SKIP {activity.name} — no source URLs")
                continue

            print(f"[{i}/{len(activities)}] Scraping: {activity.name}...", end=" ", flush=True)

            try:
                # Try each source URL
                availability_data = None
                for url in source_urls[:3]:
                    availability_data = await _extract_availability_from_url(url)
                    if _has_availability(availability_data):
                        break

                if not availability_data or not _has_availability(availability_data):
                    failed += 1
                    print("FAILED (no data from any source)")
                    continue

                new_start_times = availability_data.get("start_times", [])
                new_operating_days = availability_data.get("operating_days", [])

                old_start_times = activity.start_times or []
                old_operating_days = activity.operating_days or []

                changed = False
                changes = []

                if new_start_times and sorted(new_start_times) != sorted(old_start_times):
                    activity.start_times = new_start_times
                    changed = True
                    changes.append(f"times: {old_start_times} → {new_start_times}")

                if new_operating_days and sorted(new_operating_days) != sorted(old_operating_days):
                    activity.operating_days = new_operating_days
                    changed = True
                    changes.append(f"days: {len(old_operating_days)} → {len(new_operating_days)}")

                if changed:
                    updated += 1
                    print(f"UPDATED — {'; '.join(changes)}")
                else:
                    no_change += 1
                    print(f"OK (no change needed)")

            except Exception as exc:
                failed += 1
                print(f"ERROR: {exc}")

            # Small delay between requests
            await asyncio.sleep(0.5)

            # Commit every 10 activities
            if i % 10 == 0:
                await db.commit()
                print(f"  [Committed batch — {updated} updated, {failed} failed, {no_change} unchanged so far]")

        # Final commit
        await db.commit()

        print(f"\n{'='*60}")
        print(f"DONE!")
        print(f"  Updated: {updated}")
        print(f"  No change: {no_change}")
        print(f"  Failed: {failed}")
        print(f"  Skipped: {skipped}")
        print(f"  Total: {len(activities)}")
        print(f"{'='*60}")


if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 else None
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    offset = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    asyncio.run(bulk_scrape(city=city, limit=limit, offset=offset))
