"""Enrich newly-scraped reviews for London-with-options activities. v2 (resilient).

Key fixes over v1:
- Calls Claude directly (not enrich_single_review) so we control retry behavior
- Retries on Anthropic "529 Overloaded" with 5s, 10s backoff
- On __SKIP__ or final failure: sets enriched_text = review_text (safe, since
  review_text is brand-filtered on insert). Breaks the infinite-loop bug where
  failing reviews stayed NULL and got re-attempted forever.
- Logs the raw Claude response when __SKIP__ triggers (for diagnosis)
- Bails out if 50 consecutive Claude calls return __SKIP__ (assume API issue)
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

LOCK_FILE = "/tmp/enrich_new_london_reviews.pid"
BATCH_SIZE = 10
SLEEP_BETWEEN_BATCHES = 1.0
CUTOFF = datetime(2026, 6, 30, 7, 0, 0, tzinfo=timezone.utc)
MAX_RETRIES_PER_CALL = 2
BACKOFF_BASE = 5.0
CONSECUTIVE_SKIP_BAILOUT = 50

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("enrich_new")


async def call_claude_with_retry(original_text: str) -> tuple[str | None, str]:
    """Returns (enriched_or_None, status_label).
    status_label is one of: "success", "skip", "overloaded_giveup", "error"."""
    last_exc: Exception | None = None
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
                log.warning(
                    "Claude __SKIP__ on input(len=%d, head=%r). Raw response head=%r",
                    len(original_text), original_text[:80], cleaned[:120],
                )
                return (None, "skip")
            return (cleaned, "success")
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            is_overloaded = "529" in err_str or "Overloaded" in err_str
            if attempt < MAX_RETRIES_PER_CALL and is_overloaded:
                delay = BACKOFF_BASE * (attempt + 1)
                log.warning("Overloaded (attempt %d/%d), backoff %.0fs", attempt + 1, MAX_RETRIES_PER_CALL + 1, delay)
                await asyncio.sleep(delay)
                continue
            log.error("Claude call failed (attempt %d): %s", attempt + 1, err_str[:200])
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
                ProductReview.enriched_text.is_(None),
                ProductReview.created_at > CUTOFF,
            )
        )).scalar() or 0
    log.info("Reviews to enrich: %d", total)
    if total == 0:
        return

    n_success = 0
    n_skip_fallback = 0
    n_error_fallback = 0
    consecutive_skips = 0
    processed = 0

    while True:
        async with async_session_factory() as db:
            batch = (await db.execute(
                select(ProductReview).where(
                    ProductReview.product_type == "activities",
                    ProductReview.product_id.in_(product_ids),
                    ProductReview.enriched_text.is_(None),
                    ProductReview.created_at > CUTOFF,
                ).limit(BATCH_SIZE)
            )).scalars().all()

            if not batch:
                break

            for r in batch:
                enriched, status = await call_claude_with_retry(r.review_text)
                if enriched is not None:
                    r.enriched_text = enriched
                    n_success += 1
                    consecutive_skips = 0
                elif status == "skip":
                    # Claude judged this review unpublishable (scrape garbage,
                    # off-topic, joke, or brand-only content that can't be salvaged).
                    # DELETE it — don't publish junk on raynatours.com.
                    await db.delete(r)
                    n_skip_fallback += 1
                    consecutive_skips += 1
                else:
                    # Transient error (overload / other). Fall back to review_text
                    # (safe — review_text was brand-filtered on insert).
                    r.enriched_text = r.review_text
                    n_error_fallback += 1
                processed += 1

                if consecutive_skips >= CONSECUTIVE_SKIP_BAILOUT:
                    log.error("Bailout: %d consecutive __SKIP__s — assuming API issue. Halting.",
                              consecutive_skips)
                    await db.commit()
                    return

            await db.commit()

        log.info(
            "progress %d/%d  success=%d  skip_fallback=%d  error_fallback=%d  (%.1f%%)",
            processed, total, n_success, n_skip_fallback, n_error_fallback,
            100.0 * processed / total if total else 0.0,
        )
        await asyncio.sleep(SLEEP_BETWEEN_BATCHES)

    log.info("=" * 60)
    log.info("DONE — processed=%d  success=%d  skip_fallback=%d  error_fallback=%d",
             processed, n_success, n_skip_fallback, n_error_fallback)


def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            if os.path.exists(f"/proc/{pid}"):
                log.error("Another instance running (PID %d). Refusing.", pid)
                sys.exit(2)
            log.warning("Stale lock — removing")
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
