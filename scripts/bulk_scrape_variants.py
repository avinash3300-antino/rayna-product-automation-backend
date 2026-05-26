"""Fast bulk scrape tour variants using Jina only (no Apify fallback)."""

import asyncio
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db.base import async_session_factory
from app.db.models.activities import Activity
from app.integrations.jina_client import jina_client
from app.services.tour_variants_service import _extract_from_markdown, _has_variants


async def _extract_jina_only(url: str) -> dict | None:
    """Extract tour variants using Jina only (no Apify fallback)."""
    try:
        markdown = await jina_client.clean_page(url)
        if markdown and len(markdown) >= 100:
            data = await _extract_from_markdown(markdown[:15000])
            if _has_variants(data):
                return data
    except Exception:
        pass
    return None


async def bulk_scrape(city: str | None = None, limit: int = 509, offset: int = 0):
    async with async_session_factory() as db:
        query = select(Activity).where(Activity.source_urls.isnot(None))
        if city:
            query = query.where(Activity.city.ilike(city))
        query = query.order_by(Activity.name).offset(offset).limit(limit)

        result = await db.execute(query)
        activities = list(result.scalars().all())

        print(f"\n{'='*60}")
        print(f"Fast Bulk Tour Variants Scrape (Jina only)")
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
                print(f"[{i}/{len(activities)}] SKIP {activity.name[:50]} -- no source URLs")
                continue

            name_short = activity.name[:50]
            print(f"[{i}/{len(activities)}] {name_short}...", end=" ", flush=True)

            try:
                variants_data = None
                for url in source_urls[:3]:
                    variants_data = await _extract_jina_only(url)
                    if _has_variants(variants_data):
                        break

                if not variants_data or not _has_variants(variants_data):
                    failed += 1
                    print("NO VARIANTS")
                    continue

                new_variants = variants_data.get("tour_variants", [])
                old_variants = activity.tour_variants or []

                old_names = sorted([v.get("name", "") for v in old_variants]) if old_variants else []
                new_names = sorted([v.get("name", "") for v in new_variants])

                if new_names != old_names:
                    activity.tour_variants = new_variants
                    updated += 1
                    variant_names = ", ".join([v.get("name", "?") for v in new_variants[:3]])
                    print(f"UPDATED ({len(new_variants)} variants: {variant_names})")
                else:
                    no_change += 1
                    print(f"OK ({len(new_variants)} variants)")

            except Exception as exc:
                failed += 1
                print(f"ERR: {str(exc)[:60]}")

            await asyncio.sleep(0.3)

            if i % 20 == 0:
                await db.commit()
                print(f"  --- Batch committed: {updated} updated, {failed} failed, {no_change} ok ---")

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
