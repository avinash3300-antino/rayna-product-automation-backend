"""Fast bulk scrape availability using Jina only (no Apify fallback).
~5-10 sec per activity instead of ~2 min.
"""

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

from sqlalchemy import select
from app.db.base import async_session_factory
from app.db.models.activities import Activity
from app.integrations.jina_client import jina_client
from app.services.availability_service import _extract_from_markdown, _has_availability


async def _extract_jina_only(url: str) -> dict | None:
    """Extract availability using Jina only (no Apify fallback)."""
    try:
        markdown = await jina_client.clean_page(url)
        if markdown and len(markdown) >= 100:
            data = await _extract_from_markdown(markdown[:12000])
            if _has_availability(data):
                return data
    except Exception as exc:
        pass
    return None


async def bulk_scrape(city: str | None = None, limit: int = 509, offset: int = 0):
    """Fast scrape availability for all activities using Jina only."""
    async with async_session_factory() as db:
        query = select(Activity).where(Activity.source_urls.isnot(None))
        if city:
            query = query.where(Activity.city.ilike(city))
        query = query.order_by(Activity.name).offset(offset).limit(limit)

        result = await db.execute(query)
        activities = list(result.scalars().all())

        print(f"\n{'='*60}")
        print(f"Fast Bulk Availability Scrape (Jina only)")
        print(f"Total activities to process: {len(activities)}")
        if city:
            print(f"City filter: {city}")
        print(f"{'='*60}\n")

        updated = 0
        failed = 0
        no_change = 0

        for i, activity in enumerate(activities, 1):
            source_urls = activity.source_urls or []
            if not source_urls:
                print(f"[{i}/{len(activities)}] SKIP {activity.name} -- no source URLs")
                continue

            name_short = activity.name[:50]
            print(f"[{i}/{len(activities)}] {name_short}...", end=" ", flush=True)

            try:
                # Try each source URL with Jina only
                availability_data = None
                for url in source_urls[:3]:
                    availability_data = await _extract_jina_only(url)
                    if _has_availability(availability_data):
                        break

                if not availability_data or not _has_availability(availability_data):
                    failed += 1
                    print("NO DATA")
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
                    changes.append(f"times:{len(old_start_times)}->{len(new_start_times)}")

                if new_operating_days and sorted(new_operating_days) != sorted(old_operating_days):
                    activity.operating_days = new_operating_days
                    changed = True
                    changes.append(f"days:{len(old_operating_days)}->{len(new_operating_days)}")

                if changed:
                    updated += 1
                    print(f"UPDATED {', '.join(changes)}")
                else:
                    no_change += 1
                    print("OK")

            except Exception as exc:
                failed += 1
                print(f"ERR: {str(exc)[:60]}")

            # Small delay
            await asyncio.sleep(0.3)

            # Commit every 20 activities
            if i % 20 == 0:
                await db.commit()
                print(f"  --- Batch committed: {updated} updated, {failed} failed, {no_change} ok ---")

        # Final commit
        await db.commit()

        print(f"\n{'='*60}")
        print(f"DONE!")
        print(f"  Updated:   {updated}")
        print(f"  No change: {no_change}")
        print(f"  Failed:    {failed}")
        print(f"  Total:     {len(activities)}")
        print(f"{'='*60}")


if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 509
    offset = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    asyncio.run(bulk_scrape(city=city, limit=limit, offset=offset))
