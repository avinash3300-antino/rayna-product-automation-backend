"""Backfill source URLs, reviews, and gallery images for all activities.

Usage: python backfill_quality.py [--source-urls] [--reviews] [--gallery] [--all]

Default (no flags) = --all (runs everything).
"""
import argparse
import asyncio
import logging
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("backfill")


async def backfill_source_urls(db, activities):
    """Add additional source URLs for activities with <2."""
    from app.services.discovery_service import discover_additional_source_urls

    updated = 0
    for i, act in enumerate(activities, 1):
        current_urls = act.source_urls or ([act.source_url] if act.source_url else [])
        if len(current_urls) >= 2:
            logger.info("[%d/%d] '%s' already has %d URLs, skipping.", i, len(activities), act.name, len(current_urls))
            continue

        logger.info("[%d/%d] Searching source URLs for '%s'...", i, len(activities), act.name)
        try:
            new_urls = await discover_additional_source_urls(
                act.name, act.city, existing_urls=current_urls, max_new=2,
            )
            if new_urls:
                act.source_urls = current_urls + new_urls
                updated += 1
                logger.info("  Added %d URLs → total %d for '%s'", len(new_urls), len(act.source_urls), act.name)
            else:
                logger.info("  No new URLs found for '%s'", act.name)
        except Exception as exc:
            logger.warning("  Source URL discovery failed for '%s': %s", act.name, exc)

        await db.flush()
        await asyncio.sleep(1)  # Rate limit

    await db.commit()
    logger.info("Source URLs: updated %d / %d activities", updated, len(activities))
    return updated


async def backfill_reviews(db, activities):
    """Scrape reviews for activities that have none."""
    from app.services.review_service import scrape_reviews_for_product

    updated = 0
    for i, act in enumerate(activities, 1):
        if act.review_snippets:
            logger.info("[%d/%d] '%s' already has reviews, skipping.", i, len(activities), act.name)
            continue

        logger.info("[%d/%d] Scraping reviews for '%s'...", i, len(activities), act.name)
        try:
            result = await scrape_reviews_for_product(
                db, act.id,
                product_type="activities",
                product_name=act.name,
                product_city=act.city,
                product_country=act.country,
                operator_name=act.operator_name,
                platforms=["google", "tripadvisor"],
            )
            total = result.get("total_scraped", 0)
            if total > 0:
                updated += 1
                logger.info("  Scraped %d reviews for '%s'", total, act.name)
            else:
                logger.info("  No reviews found for '%s'", act.name)
        except Exception as exc:
            logger.warning("  Review scrape failed for '%s': %s", act.name, exc)

        await db.commit()
        await asyncio.sleep(2)  # Rate limit — reviews hit multiple APIs

    logger.info("Reviews: updated %d / %d activities", updated, len(activities))
    return updated


async def backfill_gallery(db, activities):
    """Fetch gallery images for activities that have none."""
    from app.services.image_service import fetch_and_upload_images

    updated = 0
    for i, act in enumerate(activities, 1):
        if act.gallery_json:
            logger.info("[%d/%d] '%s' already has gallery, skipping.", i, len(activities), act.name)
            continue

        logger.info("[%d/%d] Fetching gallery for '%s'...", i, len(activities), act.name)
        try:
            gallery = await fetch_and_upload_images(
                act.name, act.city, str(act.id),
                product_type="activities", num_images=8,
            )
            if gallery:
                act.gallery_json = gallery
                if not act.cover_image_url:
                    act.cover_image_url = gallery[0]["url"]
                updated += 1
                logger.info("  Uploaded %d images for '%s'", len(gallery), act.name)
            else:
                logger.info("  No images found for '%s'", act.name)
        except Exception as exc:
            logger.warning("  Gallery fetch failed for '%s': %s", act.name, exc)

        await db.flush()
        await asyncio.sleep(1)

    await db.commit()
    logger.info("Gallery: updated %d / %d activities", updated, len(activities))
    return updated


async def main(do_source_urls: bool, do_reviews: bool, do_gallery: bool):
    from sqlalchemy import select, text
    from app.db.base import async_session_factory
    from app.db.models.activities import Activity

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).order_by(Activity.category, Activity.name)
        )
        activities = list(result.scalars().all())
        logger.info("Found %d activities to process", len(activities))

    summary = {}

    if do_source_urls:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 1: SOURCE URL BACKFILL")
        logger.info("=" * 60)
        async with async_session_factory() as db:
            result = await db.execute(
                select(Activity).order_by(Activity.category, Activity.name)
            )
            activities = list(result.scalars().all())
            summary["source_urls"] = await backfill_source_urls(db, activities)

    if do_reviews:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 2: REVIEWS BACKFILL")
        logger.info("=" * 60)
        async with async_session_factory() as db:
            result = await db.execute(
                select(Activity).order_by(Activity.category, Activity.name)
            )
            activities = list(result.scalars().all())
            summary["reviews"] = await backfill_reviews(db, activities)

    if do_gallery:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 3: GALLERY BACKFILL")
        logger.info("=" * 60)
        async with async_session_factory() as db:
            result = await db.execute(
                select(Activity).order_by(Activity.category, Activity.name)
            )
            activities = list(result.scalars().all())
            summary["gallery"] = await backfill_gallery(db, activities)

    # Final stats
    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("=" * 60)
    for step, count in summary.items():
        logger.info("  %s: %d updated", step, count)

    async with async_session_factory() as db:
        row = await db.execute(text(
            "SELECT count(*) FROM activities WHERE json_array_length(source_urls::text::json) >= 2"
        ))
        logger.info("  Activities with 2+ source URLs: %d", row.scalar())

        row = await db.execute(text(
            "SELECT count(*) FROM product_reviews WHERE product_type = 'activities'"
        ))
        logger.info("  Total reviews: %d", row.scalar())

        row = await db.execute(text(
            "SELECT count(*) FROM activities WHERE gallery_json IS NOT NULL"
        ))
        logger.info("  Activities with gallery: %d", row.scalar())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill quality data for activities")
    parser.add_argument("--source-urls", action="store_true", help="Backfill source URLs")
    parser.add_argument("--reviews", action="store_true", help="Backfill reviews")
    parser.add_argument("--gallery", action="store_true", help="Backfill gallery images")
    parser.add_argument("--all", action="store_true", help="Run all backfills (default)")
    args = parser.parse_args()

    # Default to --all if no flags given
    if not (args.source_urls or args.reviews or args.gallery):
        args.all = True

    do_source = args.source_urls or args.all
    do_reviews = args.reviews or args.all
    do_gallery = args.gallery or args.all

    asyncio.run(main(do_source, do_reviews, do_gallery))
