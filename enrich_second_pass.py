"""Second-pass enrichment: re-run Claude on reviews where enriched_text = review_text.

These are the ~1,505 reviews that fell back to the original text during v3's run
because Anthropic returned 529 Overloaded errors. The API is stable now, so
retry them cleanly.

Uses the same retry/skip logic as v3. On skip: delete row.
On error (still failing): leave enriched_text = review_text (no worse than before).
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from app.db.base import async_session_factory
from app.db.models.reviews import ProductReview
from app.integrations.claude_client import claude_client
from app.services.review_service import ENRICH_SYSTEM_PROMPT

LOCK_FILE = "/tmp/enrich_second_pass.pid"
BATCH_SIZE = 10
SLEEP_BETWEEN_BATCHES = 1.0
CUTOFF = datetime(2026, 6, 30, 7, 0, 0, tzinfo=timezone.utc)
MAX_RETRIES_PER_CALL = 2
BACKOFF_BASE = 5.0
CONSECUTIVE_ERROR_BAILOUT = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("enrich_2nd")


async def call_claude_with_retry(original_text: str) -> tuple[str | None, str]:
    last_exc = None
    for attempt in range(MAX_RETRIES_PER_CALL + 1):
        try:
            result = await claude_client.generate(
                prompt=f"Original review:\n\n{original_text}\n\nRewrite this review professionally:",
                system=ENRICH_SYSTEM_PROMPT,
                model="claude-sonnet-4-6",
                max_tokens=1024,
                temperature=0.3,
            )
            cleaned = result.strip()
            if cleaned == "__SKIP__" or "__SKIP__" in cleaned[:20]:
                return (None, "skip")
            return (cleaned, "success")
        except Exception as exc:
            last_exc = exc
            is_overloaded = "529" in str(exc) or "Overloaded" in str(exc)
            if attempt < MAX_RETRIES_PER_CALL and is_overloaded:
                await asyncio.sleep(BACKOFF_BASE * (attempt + 1))
                continue
            log.error("Claude failed (attempt %d): %s", attempt + 1, str(exc)[:200])
            break
    label = "overloaded_giveup" if last_exc and ("529" in str(last_exc) or "Overloaded" in str(last_exc)) else "error"
    return (None, label)


async def main():
    async with async_session_factory() as db:
        ids_result = await db.execute(text(
            "SELECT id FROM activities "
            "WHERE LOWER(city) = 'london' "
            "AND tour_variants IS NOT NULL "
            "AND jsonb_array_length(tour_variants::jsonb) > 0"
        ))
        product_ids = [r[0] for r in ids_result.all()]
    log.info("Scope: %d London activities", len(product_ids))

    async with async_session_factory() as db:
        total = (await db.execute(
            select(func.count(ProductReview.id)).where(
                ProductReview.product_type == "activities",
                ProductReview.product_id.in_(product_ids),
                ProductReview.enriched_text == ProductReview.review_text,
                ProductReview.created_at > CUTOFF,
            )
        )).scalar() or 0
    log.info("Fallback reviews to re-enrich: %d", total)
    if total == 0:
        return

    n_success = 0
    n_skip_deleted = 0
    n_still_failing = 0
    consecutive_errors = 0
    processed = 0

    # We'll iterate by fetching a batch, processing, then re-querying.
    # Since success/skip changes enriched_text, they're excluded from the next batch.
    # Failed rows keep enriched_text = review_text, so we'd loop them. To prevent this,
    # once a row fails, we mark it done (leave as is) by using an "already-tried" set
    # in memory. When batch returns only already-tried rows, break.
    tried_ids: set = set()

    while True:
        async with async_session_factory() as db:
            stmt = select(ProductReview).where(
                ProductReview.product_type == "activities",
                ProductReview.product_id.in_(product_ids),
                ProductReview.enriched_text == ProductReview.review_text,
                ProductReview.created_at > CUTOFF,
            )
            if tried_ids:
                stmt = stmt.where(ProductReview.id.notin_(tried_ids))
            batch = (await db.execute(stmt.limit(BATCH_SIZE))).scalars().all()

            if not batch:
                break

            for r in batch:
                tried_ids.add(r.id)
                enriched, status = await call_claude_with_retry(r.review_text)
                if enriched is not None:
                    r.enriched_text = enriched
                    n_success += 1
                    consecutive_errors = 0
                elif status == "skip":
                    await db.delete(r)
                    n_skip_deleted += 1
                    consecutive_errors = 0
                else:
                    n_still_failing += 1
                    consecutive_errors += 1
                processed += 1

                if consecutive_errors >= CONSECUTIVE_ERROR_BAILOUT:
                    log.error("Bailout: %d consecutive Claude errors. Halting.", consecutive_errors)
                    await db.commit()
                    return

            await db.commit()

        log.info(
            "progress %d/%d  success=%d  skip_deleted=%d  still_failing=%d  (%.1f%%)",
            processed, total, n_success, n_skip_deleted, n_still_failing,
            100.0 * processed / total if total else 0.0,
        )
        await asyncio.sleep(SLEEP_BETWEEN_BATCHES)

    log.info("=" * 60)
    log.info("DONE — processed=%d  success=%d  skip_deleted=%d  still_failing=%d",
             processed, n_success, n_skip_deleted, n_still_failing)


def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            if os.path.exists(f"/proc/{pid}"):
                log.error("Another instance running (PID %d). Refusing.", pid)
                sys.exit(2)
        except (OSError, ValueError):
            pass
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


if __name__ == "__main__":
    acquire_lock()
    try:
        asyncio.run(main())
    finally:
        release_lock()
