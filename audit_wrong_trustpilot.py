"""Audit each (activity, Trustpilot source_url_domain) pair for the 103 London
activities. Use Claude to judge whether the domain is actually the operator/
venue behind the tour. Delete all trustpilot reviews for mismatched pairs.

Prints a dry-run first, then applies the deletes if APPLY=1 env var set.
"""
import asyncio
import json
import logging
import os
import re
import sys

from sqlalchemy import text
from app.db.base import async_session_factory
from app.integrations.claude_client import claude_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("audit_tp")

APPLY = os.environ.get("APPLY") == "1"

SYSTEM_PROMPT = """You judge whether a Trustpilot company page matches the \
business behind a tourism activity. Output ONLY a JSON object:
  {"match": true|false, "confidence": 0.0-1.0, "reason": "one short sentence"}

RULES:
- match=true only if the Trustpilot domain plausibly IS the tour operator, \
booking site, venue, or its parent brand for THIS activity.
- Cross-city or cross-country mismatches (e.g. Paris pass for a London tour, \
Southampton company for a London tour) → match=false.
- Completely unrelated categories (theatre companies for a pub crawl, \
software license sites, chauffeur services for walking tours) → match=false.
- Popular multi-activity operators (Big Bus, Golden Tours, Secret Food Tours, \
Bateaux London, City Wonders, Wonders of London) → match=true only if the \
activity name/category aligns with what that operator does.
- No prose, no markdown fences, no explanation outside the JSON."""


async def judge(activity_name: str, activity_category: str, domain: str) -> dict:
    prompt = (
        f"Activity name: {activity_name}\n"
        f"Activity category: {activity_category}\n"
        f"City: London\n"
        f"Trustpilot company page: https://www.trustpilot.com/review/{domain}\n\n"
        "Is this the correct Trustpilot page for this activity? Output the JSON now."
    )
    try:
        out = await claude_client.generate(
            prompt=prompt, system=SYSTEM_PROMPT,
            model="claude-sonnet-4-6",
            max_tokens=200, temperature=0.0,
        )
        t = out.strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[1] if "\n" in t else t[3:]
            if t.endswith("```"):
                t = t[:-3]
        return json.loads(t.strip())
    except Exception as e:
        return {"match": True, "confidence": 0.0, "reason": f"error: {e}"}


async def main():
    async with async_session_factory() as db:
        rows = (await db.execute(text("""
            WITH lwo AS (
              SELECT id, name, category FROM activities
              WHERE LOWER(city) = 'london'
                AND tour_variants IS NOT NULL
                AND jsonb_array_length(tour_variants::jsonb) > 0
            )
            SELECT
              lwo.id AS activity_id,
              lwo.name,
              lwo.category,
              regexp_replace(
                regexp_replace(pr.source_url, 'https?://[^/]*/review/', ''),
                '[/?].*$', ''
              ) AS tp_domain,
              COUNT(*) AS n_reviews,
              MIN(pr.source_url) AS sample_url
            FROM lwo
            JOIN product_reviews pr ON pr.product_id = lwo.id
            WHERE pr.product_type = 'activities'
              AND pr.source_platform = 'trustpilot'
              AND pr.source_url LIKE '%trustpilot.com/review/%'
            GROUP BY lwo.id, lwo.name, lwo.category, tp_domain
            ORDER BY lwo.name
        """))).all()

    log.info("Evaluating %d (activity, trustpilot_domain) pairs", len(rows))

    to_delete: list[tuple[str, str, int]] = []  # (activity_id, domain, count)
    kept = 0

    for r in rows:
        aid, name, category, domain, n_reviews, sample_url = r
        verdict = await judge(name, category or "", domain)
        mark = "✓ keep" if verdict.get("match") else "✗ DELETE"
        log.info("%s  %s → %s (n=%d)  %s",
                 mark, name[:40].ljust(40), domain[:35],
                 n_reviews, verdict.get("reason", "")[:80])
        if not verdict.get("match"):
            to_delete.append((str(aid), domain, n_reviews))
        else:
            kept += 1

    total_del = sum(n for _, _, n in to_delete)
    log.info("=" * 60)
    log.info("Would DELETE %d reviews across %d mismatched (activity, domain) pairs",
             total_del, len(to_delete))
    log.info("Keeping %d pairs (%d reviews)", kept,
             sum(r[4] for r in rows) - total_del)

    if not APPLY:
        log.info("Dry run — set APPLY=1 to actually delete")
        return

    # Apply deletes
    async with async_session_factory() as db:
        deleted_total = 0
        for aid, domain, expected in to_delete:
            res = await db.execute(text("""
                DELETE FROM product_reviews
                WHERE product_type = 'activities'
                  AND product_id = :aid
                  AND source_platform = 'trustpilot'
                  AND (
                    source_url LIKE '%/review/' || :d
                    OR source_url LIKE '%/review/' || :d || '/%'
                    OR source_url LIKE '%/review/' || :d || '?%'
                  )
            """), {"aid": aid, "d": domain})
            deleted_total += res.rowcount or 0
        await db.commit()
        log.info("APPLIED — deleted %d rows", deleted_total)


asyncio.run(main())
