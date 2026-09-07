"""Dry-run report for activity dedup.

Groups activities by (city_id, normalized_name) and reports duplicate groups.
Does NOT modify data. Meant for review before running the actual merger.

Rules (matches the plan):
- Match key: (city_id, normalized_name) — cross-category by design
- Ignores already-deleted rows (deleted_at IS NOT NULL)
- Ignores already-merged rows (merged_into_id IS NOT NULL)

Usage: python dedup_activities_dryrun.py
"""
import asyncio
import logging
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("dedup_dryrun")

# Filler tokens to strip during normalization
FILLER_TOKENS = [
    "tickets", "ticket",
    "tours", "tour",
    "experiences", "experience",
    "entry", "entrance",
    "passes", "pass",
    "skip-the-line", "skip the line", "skip-the-lines",
    "guided", "self-guided",
    "combo", "combos", "combo ticket",
    "day trip", "day trips", "day tour", "day tours",
    "half day", "half-day", "full day", "full-day",
    "and", "with", "the",
]

# Punctuation to remove
PUNCT_RE = re.compile(r"[^\w\s]")
WS_RE = re.compile(r"\s+")


def normalize_name(name: str, city_name: str | None = None) -> str:
    """Normalize an activity name for dedup matching."""
    if not name:
        return ""
    s = name.lower()
    s = PUNCT_RE.sub(" ", s)
    # Strip city name if it appears
    if city_name:
        c = city_name.lower()
        s = re.sub(rf"\b{re.escape(c)}\b", " ", s)
    # Strip filler tokens (word-boundary)
    for tok in FILLER_TOKENS:
        s = re.sub(rf"\b{re.escape(tok)}\b", " ", s)
    # &, /, -, etc
    s = s.replace("&", " ").replace("/", " ").replace("-", " ")
    s = WS_RE.sub(" ", s).strip()
    return s


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    async with async_session_factory() as db:
        # Load active (non-deleted, non-merged) activities
        result = await db.execute(text("""
            SELECT id, name, city, city_id, category, quality_score, created_at,
                   source_url, source_urls
            FROM activities
            WHERE deleted_at IS NULL AND merged_into_id IS NULL
        """))
        rows = result.fetchall()

    logger.info("Loaded %d active activities.", len(rows))

    # Group by (city_id, normalized_name)
    groups: dict[tuple, list] = {}
    for r in rows:
        key = (str(r.city_id), normalize_name(r.name, r.city))
        # Skip rows with empty normalized name (would cause bad matches)
        if not key[1]:
            continue
        groups.setdefault(key, []).append(r)

    dupe_groups = {k: v for k, v in groups.items() if len(v) > 1}
    total_dupe_rows = sum(len(v) for v in dupe_groups.values())
    total_would_merge = total_dupe_rows - len(dupe_groups)  # each group keeps 1 canonical

    logger.info("=" * 70)
    logger.info("DRY-RUN SUMMARY")
    logger.info("=" * 70)
    logger.info("Total active activities:     %d", len(rows))
    logger.info("Unique product groups:       %d", len(groups))
    logger.info("Groups with duplicates:      %d", len(dupe_groups))
    logger.info("Rows in duplicate groups:    %d", total_dupe_rows)
    logger.info("Rows that would be MERGED:   %d", total_would_merge)
    logger.info("Rows that survive as canonical: %d", len(groups))
    logger.info("=" * 70)

    # Per-city breakdown
    per_city: dict[str, dict] = {}
    for (city_id, _), group in dupe_groups.items():
        c = group[0].city
        per_city.setdefault(c, {"groups": 0, "rows": 0, "would_merge": 0})
        per_city[c]["groups"] += 1
        per_city[c]["rows"] += len(group)
        per_city[c]["would_merge"] += len(group) - 1

    logger.info("\nPER-CITY DUPLICATE COUNTS:")
    for c in sorted(per_city, key=lambda x: -per_city[x]["would_merge"]):
        info = per_city[c]
        logger.info("  %-25s groups=%-4d rows=%-4d would_merge=%d",
                    c, info["groups"], info["rows"], info["would_merge"])

    # Top 20 biggest duplicate groups
    biggest = sorted(dupe_groups.items(), key=lambda kv: -len(kv[1]))[:20]
    logger.info("\nTOP 20 LARGEST DUPLICATE GROUPS:")
    for (city_id, norm), group in biggest:
        logger.info("  [%s] normalized='%s' (%d rows)", group[0].city, norm, len(group))
        for r in group[:5]:
            logger.info("     - '%s' | cat=%s qs=%d src=%s",
                        (r.name or "")[:80], r.category, r.quality_score,
                        (r.source_url or "")[:60])
        if len(group) > 5:
            logger.info("     ... and %d more", len(group) - 5)


if __name__ == "__main__":
    asyncio.run(main())
