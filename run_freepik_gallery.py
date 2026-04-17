"""Fetch Freepik images + upload to Cloudinary for Cairo activities."""
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
    from app.services.image_service import fetch_and_upload_images

    city_id = uuid.UUID("941c503c-82a0-4a76-80ae-f8bb78cd7437")  # Cairo

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(Activity.city_id == city_id)
        )
        activities = list(result.scalars().all())
        print(f"Found {len(activities)} Cairo activities", flush=True)

        count = 0
        for i, act in enumerate(activities, 1):
            print(f"\n[{i}/{len(activities)}] {act.name}", flush=True)

            # Clear old scraped gallery data
            act.gallery_json = None

            try:
                gallery = await fetch_and_upload_images(
                    act.name, act.city, str(act.id), num_images=8
                )
                if gallery:
                    act.gallery_json = gallery
                    act.cover_image_url = gallery[0]["url"]
                    count += 1
                    print(f"  OK: {len(gallery)} images uploaded to Cloudinary", flush=True)
                else:
                    print(f"  No Freepik results", flush=True)
            except Exception as exc:
                print(f"  Error: {exc}", flush=True)

            await db.flush()

        await db.commit()
        print(f"\n=== Done: {count}/{len(activities)} activities got Freepik images ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
