"""Targeted variant scraper: only activities with at least one non-Viator/GYG source URL.

Skips Viator and GetYourGuide URLs entirely (they block our scrapers). Targets each
activity's FIRST good URL — TourScanner, TripAdvisor, Klook, Expedia, etc. — which
have proven to work end-to-end with Jina+Claude.

Output format matches the existing 48 / Harry Potter records (AED prices,
price_local preserved, per-1-adult).
"""

import argparse
import asyncio
import logging
import sys
from uuid import UUID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("good-urls")

CITY_IDS = {
    "london": UUID("c5cda0a7-0b95-4a26-a8b4-1001b81014a5"),
    "cairo": UUID("941c503c-82a0-4a76-80ae-f8bb78cd7437"),
}

# Booking aggregators that show multiple tour options per attraction
# (proven: TourScanner. Likely: Klook, Musement, Headout, Tiqets, Civitatis, etc.)
# Review-only sites (TripAdvisor, VisitLondon) and single-product ticket pages
# (Ticketmaster, Londontheatre) are intentionally excluded — they don't have
# variant panels.
GOOD_DOMAINS = (
    "tourscanner.com",
    "klook.com",
    "musement.com",
    "headout.com",
    "tiqets.com",
    "civitatis.com",
    "attractiontickets.com",
    "goldentours.com",
    "londonpass.com",
    "expedia.com",
)


def _is_good_url(url: str) -> bool:
    u = url.lower()
    return any(d in u for d in GOOD_DOMAINS)


def _has_variants(activity) -> bool:
    v = activity.tour_variants
    return isinstance(v, list) and len(v) > 0


def _first_good_url(activity) -> str | None:
    urls = activity.source_urls or []
    if activity.source_url and activity.source_url not in urls:
        urls = [activity.source_url] + list(urls)
    for u in urls:
        if isinstance(u, str) and _is_good_url(u):
            return u
    return None


async def main(city: str, limit: int | None) -> None:
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.services.tour_variants_service import (
        _convert_variants_to_aed,
        _extract_variants_from_url,
        _has_variants as service_has_variants,
    )

    city_id = CITY_IDS[city.lower()]

    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(Activity.city_id == city_id).order_by(Activity.name)
        )
        all_activities = list(result.scalars().all())

    # Filter: missing variants AND has at least one good URL
    candidates = []
    for a in all_activities:
        if _has_variants(a):
            continue
        good_url = _first_good_url(a)
        if good_url:
            candidates.append((a, good_url))

    logger.info("=" * 60)
    logger.info(
        "%s: %d total, %d candidates with good source URL",
        city.upper(), len(all_activities), len(candidates),
    )
    logger.info("=" * 60)

    if limit:
        candidates = candidates[:limit]
        logger.info("Limited to first %d", limit)

    updated = 0
    no_variants = 0
    errors = 0

    for i, (act, url) in enumerate(candidates, 1):
        logger.info("[%d/%d] %s — %s", i, len(candidates), act.category, act.name)
        logger.info("       trying: %s", url[:90])
        try:
            data = await _extract_variants_from_url(url)
            if not service_has_variants(data):
                no_variants += 1
                logger.info("  No options found")
                continue

            new_variants = _convert_variants_to_aed(data.get("tour_variants", []))
            if not new_variants:
                no_variants += 1
                logger.info("  No options after conversion")
                continue

            async with async_session_factory() as db:
                a = await db.get(Activity, act.id)
                a.tour_variants = new_variants
                await db.commit()

            updated += 1
            logger.info("  OK: %d options scraped", len(new_variants))
        except Exception as exc:
            errors += 1
            logger.warning("  FAILED: %s", str(exc)[:140])

        # Rate limit every 3 activities
        if i % 3 == 0:
            await asyncio.sleep(2)

    logger.info("=" * 60)
    logger.info(
        "DONE %s — Updated: %d  No options: %d  Errors: %d",
        city.upper(), updated, no_variants, errors,
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True, choices=["london", "cairo"])
    parser.add_argument("--limit", type=int, help="Cap activities processed (test mode)")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.city, args.limit))
    except KeyboardInterrupt:
        print("\nInterrupted — completed activities were committed independently.")
        sys.exit(130)
