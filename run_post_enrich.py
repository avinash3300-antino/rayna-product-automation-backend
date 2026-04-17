"""Run post-enrichment (gallery, geocoding) for Cairo activities."""
import asyncio
import logging
import os
import sys
import uuid

os.environ.setdefault("ENVIRONMENT", "production")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def main():
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.services.gallery_service import scrape_gallery_images
    from app.services.geocoding_service import geocode_activity

    city_id = uuid.UUID("941c503c-82a0-4a76-80ae-f8bb78cd7437")  # Cairo

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(Activity.city_id == city_id)
        )
        activities = list(result.scalars().all())
        print(f"Found {len(activities)} Cairo activities", flush=True)

        gallery_count = 0
        geocoded_count = 0

        for i, act in enumerate(activities, 1):
            print(f"\n[{i}/{len(activities)}] {act.name}", flush=True)

            # Gallery
            if not act.gallery_json and act.source_url:
                try:
                    imgs = await scrape_gallery_images(
                        act.source_url, act.name, max_images=10
                    )
                    if imgs:
                        act.gallery_json = imgs
                        gallery_count += 1
                        print(f"  Gallery: {len(imgs)} images", flush=True)
                    elif act.cover_image_url:
                        act.gallery_json = [act.cover_image_url]
                        gallery_count += 1
                        print(f"  Gallery: cover image fallback", flush=True)
                except Exception as exc:
                    if act.cover_image_url:
                        act.gallery_json = [act.cover_image_url]
                        gallery_count += 1
                    print(f"  Gallery error: {exc}", flush=True)
            else:
                print(f"  Gallery: already has {len(act.gallery_json or [])} images", flush=True)

            # Geocoding
            if act.lat == 0 and act.lng == 0:
                try:
                    coords = await geocode_activity(
                        act.name, act.city, act.country, act.address
                    )
                    if coords["lat"] != 0:
                        act.lat = coords["lat"]
                        act.lng = coords["lng"]
                        geocoded_count += 1
                        print(f"  Geocoded: {coords['lat']}, {coords['lng']}", flush=True)
                    else:
                        print(f"  Geocoding: no results", flush=True)
                except Exception as exc:
                    print(f"  Geocoding error: {exc}", flush=True)
                # Rate limit for Nominatim (1 req/sec policy)
                await asyncio.sleep(1.1)
            else:
                print(f"  Already geocoded: {act.lat}, {act.lng}", flush=True)

            await db.flush()

        await db.commit()

        print(f"\n=== Results ===", flush=True)
        print(f"Gallery added: {gallery_count}/{len(activities)}", flush=True)
        print(f"Geocoded: {geocoded_count}/{len(activities)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
