"""Bulk generate FAQs for all activities that don't have them yet."""

import asyncio
import logging
import sys
import time

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import engine
from app.db.models.activities import Activity
from app.services.faq_service import generate_faqs_for_activity

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

BATCH_SIZE = 5  # concurrent requests to Claude


async def main():
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        result = await db.execute(
            select(Activity.id, Activity.name)
            .where(Activity.faqs.is_(None))
            .order_by(Activity.created_at)
        )
        activities = result.all()

    total = len(activities)
    print(f"Generating FAQs for {total} activities...")

    done = 0
    failed = 0
    start = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch = activities[i : i + BATCH_SIZE]

        async def process_one(act_id, act_name):
            nonlocal done, failed
            async with async_session() as db:
                try:
                    faqs = await generate_faqs_for_activity(db, act_id)
                    await db.commit()
                    done += 1
                    return True
                except Exception as e:
                    failed += 1
                    print(f"  FAIL: {act_name} — {e}")
                    return False

        tasks = [process_one(aid, aname) for aid, aname in batch]
        await asyncio.gather(*tasks)

        elapsed = time.time() - start
        rate = (done + failed) / elapsed if elapsed > 0 else 0
        eta = (total - done - failed) / rate if rate > 0 else 0
        print(
            f"  [{done + failed}/{total}] "
            f"done={done} failed={failed} "
            f"rate={rate:.1f}/s ETA={eta:.0f}s"
        )

    elapsed = time.time() - start
    print(f"\nFinished! {done} generated, {failed} failed in {elapsed:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
