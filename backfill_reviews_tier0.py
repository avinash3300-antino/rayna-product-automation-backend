"""Backfill reviews for tier-0 activities (options + gallery).

For each tier-0 activity with fewer than TARGET_MIN reviews stored:
  1. Scrape Google Maps reviews via SearchAPI
  2. Scrape TripAdvisor via SearchAPI + Jina + Gemini extraction
  3. Scrape Trustpilot via SearchAPI + Jina + Gemini extraction
  4. Dedup by review-text hash across platforms
  5. Additively insert into product_reviews (don't wipe existing)
  6. Update activity rating/review_count/review_snippets

Idempotent: activities already at target are skipped.
"""
import argparse
import asyncio
import hashlib
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("reviews")

TARGET_MIN = 100
GOOGLE_MAX = 40      # paginated, reliable
TA_MAX = 20          # often CAPTCHA-blocked, still try
TP_MAX = 20          # Jina works, keep small to fit token budget


def _norm_text(t: str) -> str:
    import re
    return re.sub(r"\W+", " ", (t or "").lower()).strip()


def _hash(text: str) -> str:
    return hashlib.md5(_norm_text(text)[:200].encode()).hexdigest()


async def process_one(activity_id, name, city, country, operator, existing_hashes):
    """Scrape all 3 platforms, dedup vs existing, return new-review dicts."""
    from app.services.review_service import (
        _scrape_google_reviews,
        _scrape_tripadvisor_reviews,
        _scrape_trustpilot_reviews,
    )

    all_new: list[dict] = []
    per_platform_counts = {"google": 0, "tripadvisor": 0, "trustpilot": 0}

    # Google Maps (primary, paginated)
    try:
        goog = await _scrape_google_reviews(name, city, country, max_reviews=GOOGLE_MAX)
        for r in goog:
            r["source_platform"] = "google"
        all_new.extend(goog)
        per_platform_counts["google"] = len(goog)
    except Exception as exc:
        logger.warning("google fail for %s: %s", name[:40], str(exc)[:100])

    # TripAdvisor (often CAPTCHA-blocked by Jina, expected to yield 0 sometimes)
    try:
        ta = await _scrape_tripadvisor_reviews(name, city, max_reviews=TA_MAX, provider="gemini")
        for r in ta:
            r["source_platform"] = "tripadvisor"
        all_new.extend(ta)
        per_platform_counts["tripadvisor"] = len(ta)
    except Exception as exc:
        logger.warning("tripadvisor fail for %s: %s", name[:40], str(exc)[:100])

    # Trustpilot (operator-based, Jina works)
    try:
        tp = await _scrape_trustpilot_reviews(operator or name, city, max_reviews=TP_MAX, provider="gemini")
        for r in tp:
            r["source_platform"] = "trustpilot"
        all_new.extend(tp)
        per_platform_counts["trustpilot"] = len(tp)
    except Exception as exc:
        logger.warning("trustpilot fail for %s: %s", name[:40], str(exc)[:100])

    # Dedup by review-text hash (within batch + against existing)
    filtered = []
    seen = set(existing_hashes)
    for r in all_new:
        t = r.get("review_text") or ""
        if len(t) < 20:
            continue
        h = _hash(t)
        if h in seen:
            continue
        seen.add(h)
        filtered.append(r)

    return filtered, per_platform_counts


async def persist(db, activity, new_reviews):
    """Insert new reviews and refresh activity rating/count/snippets."""
    from app.db.models.reviews import ProductReview
    from sqlalchemy import select, func

    for r in new_reviews:
        review = ProductReview(
            product_type="activities",
            product_id=activity.id,
            reviewer_name=(r.get("reviewer_name") or "Traveller")[:200],
            reviewer_avatar_url=r.get("reviewer_avatar_url"),
            rating=r.get("rating"),
            review_title=(r.get("review_title") or None),
            review_text=(r.get("review_text") or "")[:5000],
            review_date=r.get("review_date"),
            source_platform=r.get("source_platform", "unknown"),
            source_url=r.get("source_url"),
            verified=bool(r.get("verified", False)),
            language=r.get("language") or "en",
        )
        db.add(review)
    await db.flush()

    # Recompute activity aggregates from ALL reviews (new + old)
    stmt = select(ProductReview).where(
        ProductReview.product_type == "activities",
        ProductReview.product_id == activity.id,
    )
    all_res = await db.execute(stmt)
    all_reviews = list(all_res.scalars().all())

    ratings = [float(x.rating) for x in all_reviews if x.rating is not None]
    if ratings:
        activity.rating = round(sum(ratings) / len(ratings), 2)
    activity.review_count = len(all_reviews)
    activity.rating_5 = sum(1 for x in ratings if x >= 4.5)
    activity.rating_4 = sum(1 for x in ratings if 3.5 <= x < 4.5)
    activity.rating_3 = sum(1 for x in ratings if 2.5 <= x < 3.5)
    activity.rating_2 = sum(1 for x in ratings if 1.5 <= x < 2.5)
    activity.rating_1 = sum(1 for x in ratings if x < 1.5)

    # Top-5 snippets sorted by rating desc
    snippets = []
    for r in sorted(all_reviews, key=lambda x: (x.rating or 0), reverse=True):
        if r.review_text and len(r.review_text) > 20:
            snippets.append(r.review_text[:200])
        if len(snippets) >= 5:
            break
    activity.review_snippets = snippets

    await db.flush()


async def main(concurrency: int, limit: int, city_filter: str | None):
    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.db.models.reviews import ProductReview
    from sqlalchemy import text, select, func

    async with async_session_factory() as db:
        base = f"""
          WITH tier0 AS (
            SELECT a.id, a.name, a.city, a.country, a.operator_name
            FROM activities a
            WHERE a.deleted_at IS NULL AND a.merged_into_id IS NULL
              AND a.tour_variants IS NOT NULL AND a.tour_variants::text NOT IN ('null','[]')
              AND a.gallery_json IS NOT NULL AND a.gallery_json::text NOT IN ('null','[]')
              {"AND a.city = :city" if city_filter else ""}
          )
          SELECT t.id, t.name, t.city, t.country, t.operator_name,
                 COALESCE(cnt.n, 0) AS existing_count
          FROM tier0 t
          LEFT JOIN (
            SELECT product_id, COUNT(*) AS n
            FROM product_reviews
            WHERE product_type='activities'
            GROUP BY product_id
          ) cnt ON cnt.product_id = t.id
          WHERE COALESCE(cnt.n, 0) < :target
          ORDER BY existing_count ASC, t.city, t.name
        """
        if limit and limit > 0:
            base += f" LIMIT {int(limit)}"

        params = {"target": TARGET_MIN}
        if city_filter:
            params["city"] = city_filter

        r = await db.execute(text(base), params)
        rows = r.fetchall()

    logger.info("Review backfill: %d activities queued (target=%d/each, concurrency=%d)",
                len(rows), TARGET_MIN, concurrency)

    stats = {"processed": 0, "added": 0, "reached_target": 0, "no_reviews": 0}
    sem = asyncio.Semaphore(concurrency)
    start = time.time()

    async def _one(idx, aid, aname, acity, acountry, aop, existing_count):
        async with sem:
            # Load existing review-text hashes for this activity to dedup
            async with async_session_factory() as db:
                existing_res = await db.execute(
                    select(ProductReview.review_text).where(
                        ProductReview.product_type == "activities",
                        ProductReview.product_id == aid,
                    )
                )
                existing_hashes = {_hash(t) for (t,) in existing_res.fetchall() if t}

            try:
                new_reviews, per_plat = await process_one(
                    aid, aname, acity, acountry, aop, existing_hashes,
                )
            except Exception as exc:
                logger.warning("[%d/%d] FAIL %s: %s", idx, len(rows), aname[:40], str(exc)[:150])
                return

            if not new_reviews:
                stats["no_reviews"] += 1
                stats["processed"] += 1
                return

            async with async_session_factory() as db:
                activity = await db.get(Activity, aid)
                await persist(db, activity, new_reviews)
                await db.commit()

            total_after = existing_count + len(new_reviews)
            stats["added"] += len(new_reviews)
            stats["processed"] += 1
            if total_after >= TARGET_MIN:
                stats["reached_target"] += 1

            if idx % 25 == 0 or idx == len(rows):
                elapsed = time.time() - start
                rate = idx / elapsed if elapsed > 0 else 0
                eta_min = (len(rows) - idx) / rate / 60 if rate > 0 else 0
                logger.info(
                    "[%d/%d] processed=%d added=%d reached100=%d no_reviews=%d | %.1f/min | ETA %.0fm",
                    idx, len(rows), stats["processed"], stats["added"],
                    stats["reached_target"], stats["no_reviews"],
                    rate * 60, eta_min,
                )

    tasks = [
        _one(i, r.id, r.name, r.city, r.country, r.operator_name, r.existing_count)
        for i, r in enumerate(rows, 1)
    ]

    CHUNK = concurrency * 8
    for i in range(0, len(tasks), CHUNK):
        chunk = tasks[i : i + CHUNK]
        await asyncio.gather(*chunk, return_exceptions=True)

    logger.info("=" * 60)
    logger.info(
        "DONE: processed=%d added=%d reached100=%d no_reviews=%d elapsed=%.1fm",
        stats["processed"], stats["added"], stats["reached_target"],
        stats["no_reviews"], (time.time() - start) / 60,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="0 for all")
    parser.add_argument("--city", type=str, default=None, help="Optional city filter")
    args = parser.parse_args()
    asyncio.run(main(args.concurrency, args.limit, args.city))
