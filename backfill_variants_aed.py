"""One-off: convert existing tour_variants prices from source currency to AED.

For every activity with tour_variants populated, normalise each variant's
`price` to AED using the same exchange rates as pricing_service. The original
local-currency value is preserved under `price_local`. Idempotent: rows already
in AED are skipped.
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models.activities import Activity
from app.services.tour_variants_service import _convert_variants_to_aed

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _needs_conversion(variants: list) -> bool:
    return any(
        isinstance(v, dict)
        and isinstance(v.get("price"), dict)
        and str(v["price"].get("currency", "")).upper() not in ("", "AED")
        for v in variants
    )


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(Activity.tour_variants.isnot(None))
        )
        activities = list(result.scalars().all())

        updated = 0
        skipped = 0
        empty = 0

        for activity in activities:
            variants = activity.tour_variants or []
            if not variants:
                empty += 1
                continue
            if not _needs_conversion(variants):
                skipped += 1
                continue
            activity.tour_variants = _convert_variants_to_aed(variants)
            updated += 1
            logger.info("  converted %s  (%s)", activity.name, activity.id)

        await db.commit()
        print(f"\nDone. Updated: {updated}  Already AED: {skipped}  Empty: {empty}")


if __name__ == "__main__":
    asyncio.run(main())
