"""Execute activity dedup merger.

For each duplicate group (from dedup_activities_dryrun.py logic):
- Pick canonical row: highest quality_score, tie-break oldest created_at
- Merge into canonical:
  - source_urls: append dupe's source_url + any URLs from dupe's source_urls JSON, dedup
  - product_reviews: UPDATE product_id = canonical.id
  - catalog_activity_timeline: re-parent to canonical (unless canonical already has entries)
- Soft-delete dupe: merged_into_id = canonical.id, deleted_at = NOW()

Per-group transaction so a single failure doesn't corrupt other groups.

Usage: python dedup_activities_merge.py
"""
import asyncio
import json
import logging
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("dedup_merge")

FILLER_TOKENS = [
    "tickets", "ticket", "tours", "tour", "experiences", "experience",
    "entry", "entrance", "passes", "pass",
    "skip-the-line", "skip the line", "skip-the-lines",
    "guided", "self-guided", "combo", "combos", "combo ticket",
    "day trip", "day trips", "day tour", "day tours",
    "half day", "half-day", "full day", "full-day",
    "and", "with", "the",
]
PUNCT_RE = re.compile(r"[^\w\s]")
WS_RE = re.compile(r"\s+")


def normalize_name(name: str, city_name: str | None = None) -> str:
    if not name:
        return ""
    s = name.lower()
    s = PUNCT_RE.sub(" ", s)
    if city_name:
        c = city_name.lower()
        s = re.sub(rf"\b{re.escape(c)}\b", " ", s)
    for tok in FILLER_TOKENS:
        s = re.sub(rf"\b{re.escape(tok)}\b", " ", s)
    s = s.replace("&", " ").replace("/", " ").replace("-", " ")
    s = WS_RE.sub(" ", s).strip()
    return s


def _merge_source_urls(canonical_urls, dupe_urls, dupe_source_url, canonical_source_url):
    """Return merged list of source URLs (dedup, preserve order)."""
    merged = []
    seen = set()

    def add(u):
        if not u:
            return
        u = u.strip()
        if u and u not in seen:
            merged.append(u)
            seen.add(u)

    add(canonical_source_url)
    if isinstance(canonical_urls, list):
        for u in canonical_urls:
            add(u)
    add(dupe_source_url)
    if isinstance(dupe_urls, list):
        for u in dupe_urls:
            add(u)
    return merged


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    async with async_session_factory() as db:
        result = await db.execute(text("""
            SELECT id, name, city, city_id, category, quality_score, created_at,
                   source_url, source_urls
            FROM activities
            WHERE deleted_at IS NULL AND merged_into_id IS NULL
        """))
        rows = result.fetchall()

    logger.info("Loaded %d active activities", len(rows))

    groups: dict[tuple, list] = {}
    for r in rows:
        key = (str(r.city_id), normalize_name(r.name, r.city))
        if not key[1]:
            continue
        groups.setdefault(key, []).append(r)

    dupe_groups = {k: v for k, v in groups.items() if len(v) > 1}
    logger.info("Found %d duplicate groups (%d rows to merge)",
                len(dupe_groups), sum(len(v) - 1 for v in dupe_groups.values()))

    merged_total = 0
    failed_groups = 0
    per_city_merged: dict[str, int] = {}

    for i, (key, group) in enumerate(dupe_groups.items(), 1):
        # Pick canonical: highest quality_score, tie-break oldest created_at
        group_sorted = sorted(group, key=lambda r: (-r.quality_score, r.created_at))
        canonical = group_sorted[0]
        dupes = group_sorted[1:]
        city = canonical.city

        try:
            async with async_session_factory() as db:
                # Load current source_urls from canonical
                cur_urls = await db.execute(text(
                    "SELECT source_urls, source_url FROM activities WHERE id = :id"
                ), {"id": canonical.id})
                row = cur_urls.first()
                canonical_urls = row.source_urls if row else None

                # Merge source URLs from all dupes
                merged_urls = _merge_source_urls(
                    canonical_urls, None, None, row.source_url
                )
                for d in dupes:
                    merged_urls = _merge_source_urls(
                        merged_urls, d.source_urls, d.source_url, None
                    )

                # Update canonical's source_urls
                await db.execute(text(
                    "UPDATE activities SET source_urls = CAST(:urls AS JSON), updated_at = NOW() "
                    "WHERE id = :id"
                ), {"urls": json.dumps(merged_urls), "id": canonical.id})

                # For each dupe: re-parent FKs, then soft-delete
                for d in dupes:
                    # Reviews: move to canonical
                    await db.execute(text(
                        "UPDATE product_reviews SET product_id = :canon "
                        "WHERE product_id = :dupe AND product_type = 'activities'"
                    ), {"canon": canonical.id, "dupe": d.id})

                    # Timeline: if canonical has no timeline, re-parent dupe's;
                    # otherwise delete dupe's timeline (CASCADE will do it on soft-delete
                    # but we're not actually deleting the row, just marking it).
                    # So just re-parent if canonical is empty.
                    has_canon = await db.execute(text(
                        "SELECT 1 FROM catalog_activity_timeline WHERE activity_id = :id LIMIT 1"
                    ), {"id": canonical.id})
                    canon_has_timeline = has_canon.first() is not None
                    if not canon_has_timeline:
                        await db.execute(text(
                            "UPDATE catalog_activity_timeline SET activity_id = :canon "
                            "WHERE activity_id = :dupe"
                        ), {"canon": canonical.id, "dupe": d.id})
                    else:
                        # Delete dupe's timeline to avoid orphaned rows when we soft-delete
                        await db.execute(text(
                            "DELETE FROM catalog_activity_timeline WHERE activity_id = :dupe"
                        ), {"dupe": d.id})

                    # Soft-delete the dupe row
                    await db.execute(text("""
                        UPDATE activities
                        SET merged_into_id = :canon,
                            deleted_at = NOW(),
                            updated_at = NOW()
                        WHERE id = :dupe
                    """), {"canon": canonical.id, "dupe": d.id})

                await db.commit()
                merged_total += len(dupes)
                per_city_merged[city] = per_city_merged.get(city, 0) + len(dupes)

                if i % 50 == 0 or i == len(dupe_groups):
                    logger.info("Progress: %d/%d groups (merged %d rows so far)",
                                i, len(dupe_groups), merged_total)

        except Exception as exc:
            logger.error("Group %d/%d FAILED (canonical=%s): %s",
                         i, len(dupe_groups), canonical.id, exc)
            failed_groups += 1

    logger.info("=" * 70)
    logger.info("MERGER SUMMARY")
    logger.info("=" * 70)
    logger.info("Total groups processed: %d", len(dupe_groups))
    logger.info("Failed groups:          %d", failed_groups)
    logger.info("Rows merged:            %d", merged_total)
    for c in sorted(per_city_merged, key=lambda x: -per_city_merged[x]):
        logger.info("  %-25s merged=%d", c, per_city_merged[c])

    # Verify DB state
    async with async_session_factory() as db:
        r = await db.execute(text(
            "SELECT COUNT(*) FROM activities WHERE deleted_at IS NULL AND merged_into_id IS NULL"
        ))
        remaining = r.scalar()
        r2 = await db.execute(text(
            "SELECT COUNT(*) FROM activities WHERE deleted_at IS NOT NULL"
        ))
        deleted = r2.scalar()
        logger.info("Active activities after merge:  %d", remaining)
        logger.info("Soft-deleted activities:        %d", deleted)


if __name__ == "__main__":
    asyncio.run(main())
