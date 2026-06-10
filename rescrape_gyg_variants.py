"""Re-scrape GYG activities that already have variants, to get full data.

Many activities were initially populated via Jina (fast static fetch) which
only returns Option 1's full data — Options 2+ get null prices and missing
descriptions. The new date-click + expand-all-options flow in
tour_variants_service produces the full quality bar (price + description +
includes + excludes per option).

Targets: any activity with source_url ILIKE '%getyourguide.com%' that already
has tour_variants populated.
"""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("gyg-rescrape")


def _has_variants(activity) -> bool:
    v = activity.tour_variants
    return isinstance(v, list) and len(v) > 0


async def main(limit: int | None) -> None:
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.services.tour_variants_service import (
        _convert_variants_to_aed,
        _extract_variants_from_url,
        _has_variants as service_has_variants,
    )

    async with async_session_factory() as db:
        q = select(Activity).where(
            Activity.source_url.ilike("%getyourguide.com%"),
        ).order_by(Activity.name)
        result = await db.execute(q)
        all_acts = list(result.scalars().all())

    # Target only activities that already have variants (were scraped before)
    targets = [a for a in all_acts if _has_variants(a)]

    logger.info("=" * 60)
    logger.info("GYG re-scrape: %d total GYG, %d have variants (targets)",
                len(all_acts), len(targets))
    logger.info("=" * 60)

    if limit:
        targets = targets[:limit]
        logger.info("Limited to first %d", limit)

    improved = 0
    unchanged = 0
    errors = 0

    rejected_regression = 0

    for i, act in enumerate(targets, 1):
        old_variants = act.tour_variants or []
        old_count = len(old_variants)
        old_null_prices = sum(
            1 for v in old_variants
            if isinstance(v, dict) and (v.get("price") is None or
                                        (isinstance(v.get("price"), dict)
                                         and v["price"].get("amount") is None))
        )
        # Skip activities that already have COMPLETE data (no null prices)
        # AND only 1-2 options. These are mostly already optimal — re-scraping
        # risks regression for no gain.
        if old_null_prices == 0 and old_count <= 2:
            unchanged += 1
            logger.info("[%d/%d] %s — %s (was %d opts, COMPLETE — skip)",
                        i, len(targets), act.city, act.name[:60], old_count)
            continue

        logger.info("[%d/%d] %s — %s (was %d opts, %d null prices)",
                    i, len(targets), act.city, act.name[:60], old_count, old_null_prices)
        try:
            url = act.source_url
            data = await _extract_variants_from_url(url)
            if not data or not service_has_variants(data):
                unchanged += 1
                logger.info("  No new data (kept old)")
                continue

            new_variants = _convert_variants_to_aed(data.get("tour_variants", []))
            new_count = len(new_variants)
            new_null_prices = sum(
                1 for v in new_variants
                if isinstance(v, dict) and (v.get("price") is None or
                                            (isinstance(v.get("price"), dict)
                                             and v["price"].get("amount") is None))
            )

            # REGRESSION GUARD: only accept if (more options OR fewer nulls)
            # AND the new null count doesn't exceed the old.
            is_improvement = (
                (new_count > old_count and new_null_prices <= old_null_prices)
                or (new_count == old_count and new_null_prices < old_null_prices)
                or (old_null_prices > 0 and new_null_prices == 0 and new_count >= old_count)
            )

            if not is_improvement:
                rejected_regression += 1
                logger.info("  REJECT: %d→%d opts, %d→%d nulls (no improvement)",
                            old_count, new_count, old_null_prices, new_null_prices)
                continue

            async with async_session_factory() as db:
                a = await db.get(Activity, act.id)
                a.tour_variants = new_variants
                await db.commit()

            improved += 1
            logger.info("  IMPROVED: %d → %d opts, %d → %d null prices",
                        old_count, new_count, old_null_prices, new_null_prices)
        except Exception as exc:
            errors += 1
            logger.warning("  FAILED: %s", str(exc)[:140])

        if i % 3 == 0:
            await asyncio.sleep(2)

    logger.info("=" * 60)
    logger.info("DONE GYG-RESCRAPE — Improved: %d  Rejected (regression): %d  Unchanged: %d  Errors: %d",
                improved, rejected_regression, unchanged, errors)
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Cap activities processed")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.limit))
    except KeyboardInterrupt:
        print("\nInterrupted — completed activities are saved (commit-per-activity).")
        sys.exit(130)
