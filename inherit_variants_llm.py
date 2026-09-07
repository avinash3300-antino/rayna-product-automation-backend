"""LLM-verified fuzzy match — inherit REAL variants from Headout/GT products
to scraped-source activities that appear to be the SAME real-world product.

Approach:
1. For each scraped activity without tour_variants:
   - Find same-city candidates that HAVE variants AND have headout_id or globaltix_id
   - Rank by name similarity (word overlap)
   - Ask Claude Haiku: "Are these the SAME product?"
   - If confidence=HIGH: copy variants into scraped activity (marked as fuzzy_matched)
2. Never cross city. Never accept medium/low confidence.
3. Variant data itself is REAL (from Headout/GT); only the MATCH is LLM-inferred.

Usage:
  python inherit_variants_llm.py --limit 100     # pilot
  python inherit_variants_llm.py --limit 0       # full sweep
"""
import argparse
import asyncio
import json
import logging
import re
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("fuzzy_inherit")

CLAUDE_CONCURRENCY = 8
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are strictly comparing two travel activity products.
Determine if they represent the SAME real-world product (same underlying experience/tour).

Return ONLY valid JSON, no other text:
{"same_product": true|false, "confidence": "high"|"medium"|"low", "reason": "<one short sentence>"}

Rules:
- Return same_product=true, confidence=high ONLY if you are VERY sure:
  * Same specific attraction/experience
  * Same core inclusions (both fast-track OR both guided; not one fast-track and one dinner+tour)
  * Same duration category (both ~2h, or both full-day; not one 1h and other 8h)
- Return same_product=false if key attributes differ (duration, inclusions, meal, transport)
- Return confidence=medium if ambiguous
- Return confidence=low if unclear

Examples of same_product=true:
- "Vatican Museums Skip-the-Line Ticket" vs "Vatican: Fast-Track Entry Ticket" (both fast-track ticket)
- "Bosphorus Cruise 2 Hours" vs "2-Hour Bosphorus Boat Tour" (both 2h cruise)

Examples of same_product=false:
- "Vatican Museums Ticket" vs "Vatican Museums Guided Tour with Lunch" (bare ticket vs guided+meal)
- "Colosseum Entry" vs "Colosseum + Roman Forum Combo" (single vs combo)"""

# Tokenizer for candidate ranking
_STOP = {"the", "and", "with", "of", "in", "to", "for", "a", "an", "at",
         "tour", "tours", "ticket", "tickets", "experience", "entry",
         "pass", "guided", "self-guided", "combo"}


def _tokens(name: str) -> set[str]:
    s = re.sub(r"[^\w\s]", " ", (name or "").lower())
    return {w for w in s.split() if w and w not in _STOP and len(w) > 2}


def _keyword_score(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


async def _find_candidates(db, city_id, scraped_name, exclude_id):
    """Return list of (activity_id, name, tour_variants) — top matches by keyword overlap."""
    from sqlalchemy import text
    result = await db.execute(text("""
        SELECT id, name, tour_variants
        FROM activities
        WHERE city_id = :city_id
          AND id != :exclude
          AND (headout_id IS NOT NULL OR globaltix_id IS NOT NULL)
          AND tour_variants IS NOT NULL
          AND tour_variants::text NOT IN ('null','[]')
          AND deleted_at IS NULL AND merged_into_id IS NULL
    """), {"city_id": city_id, "exclude": exclude_id})
    rows = result.fetchall()
    scored = []
    for r in rows:
        score = _keyword_score(scraped_name, r.name)
        if score > 0.3:  # minimum overlap to consider
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:3]]  # top 3


async def _ask_claude_match(client, sem, prod_a: dict, prod_b: dict):
    async with sem:
        prompt = f"""Product A (needs options):
Name: {prod_a['name']}
City: {prod_a['city']}
Category: {prod_a.get('category','')}
Description: {(prod_a.get('desc') or '')[:200]}

Product B (has options):
Name: {prod_b['name']}
City: {prod_b['city']}
Category: {prod_b.get('category','')}
Description: {(prod_b.get('desc') or '')[:200]}
"""
        for attempt in range(3):
            try:
                r = await client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=200,
                    temperature=0.0,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                text_ = r.content[0].text.strip()
                # Strip ``` fences
                if text_.startswith("```"):
                    text_ = text_.split("\n", 1)[1] if "\n" in text_ else text_[3:]
                    if text_.endswith("```"):
                        text_ = text_[:-3]
                    text_ = text_.strip()
                return json.loads(text_)
            except Exception as exc:
                if attempt == 2:
                    return None
                await asyncio.sleep(0.5 * (attempt + 1))


async def _process_one(client, sem, a, counts):
    """Return True if we inherited variants for this activity."""
    from app.db.base import async_session_factory

    async with async_session_factory() as db:
        candidates = await _find_candidates(db, a["city_id"], a["name"], a["id"])

    if not candidates:
        counts["no_candidates"] += 1
        return False

    for cand in candidates:
        prod_a = {
            "name": a["name"], "city": a["city"],
            "category": a.get("category"), "desc": a.get("desc"),
        }
        prod_b = {
            "name": cand.name, "city": a["city"],
            "category": "", "desc": "",  # we don't fetch these for candidates to save queries
        }
        result = await _ask_claude_match(client, sem, prod_a, prod_b)
        if not result:
            counts["llm_error"] += 1
            continue
        counts["llm_calls"] += 1

        if result.get("same_product") is True and result.get("confidence") == "high":
            # Inherit variants — tag as fuzzy_matched
            existing_variants = cand.tour_variants if isinstance(cand.tour_variants, list) else []
            inherited = []
            for v in existing_variants:
                if not isinstance(v, dict):
                    continue
                new_v = dict(v)
                new_v["source"] = f"fuzzy_matched_from_{new_v.get('source','headout')}"
                new_v["fuzzy_source_id"] = str(cand.id)
                inherited.append(new_v)

            if not inherited:
                continue

            try:
                from sqlalchemy import text
                async with async_session_factory() as db:
                    await db.execute(
                        text("UPDATE activities SET tour_variants = CAST(:v AS JSON), "
                             "updated_at = NOW() WHERE id = :id"),
                        {"v": json.dumps(inherited), "id": a["id"]},
                    )
                    await db.commit()
                counts["inherited"] += 1
                counts["variants_inherited"] += len(inherited)
                return True
            except Exception as exc:
                logger.warning("db update failed for %s: %s", a["id"], exc)
                return False

    counts["no_high_confidence_match"] += 1
    return False


async def main(limit: int):
    from app.db.base import async_session_factory
    from sqlalchemy import text
    from anthropic import AsyncAnthropic
    import os
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ["ANTHROPIC_API_KEY"]
    client = AsyncAnthropic(api_key=api_key)

    async with async_session_factory() as db:
        query = """
            SELECT id, name, city, city_id, category,
                   COALESCE(description_short, '') AS desc
            FROM activities
            WHERE (tour_variants IS NULL OR tour_variants::text IN ('null','[]'))
              AND headout_id IS NULL
              AND globaltix_id IS NULL
              AND deleted_at IS NULL AND merged_into_id IS NULL
              AND source_url IS NOT NULL
        """
        if limit and limit > 0:
            query += f" ORDER BY random() LIMIT {int(limit)}"
        result = await db.execute(text(query))
        rows = result.fetchall()

    activities = [
        {"id": r.id, "name": r.name, "city": r.city, "city_id": r.city_id,
         "category": r.category, "desc": r.desc}
        for r in rows
    ]
    logger.info("Fuzzy-match sweep on %d scraped activities without options (limit=%d)",
                len(activities), limit)

    counts = defaultdict(int)
    sem = asyncio.Semaphore(CLAUDE_CONCURRENCY)

    BATCH = 50
    for i in range(0, len(activities), BATCH):
        batch = activities[i : i + BATCH]
        tasks = [_process_one(client, sem, a, counts) for a in batch]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(
            "Progress %d/%d — inherited=%d, no_high_conf=%d, no_candidates=%d, llm_calls=%d",
            i + len(batch), len(activities),
            counts["inherited"], counts["no_high_confidence_match"],
            counts["no_candidates"], counts["llm_calls"],
        )

    logger.info("=" * 60)
    logger.info(
        "FINAL: inherited=%d, variants_inherited=%d, no_high_conf=%d, "
        "no_candidates=%d, llm_calls=%d, llm_errors=%d",
        counts["inherited"], counts["variants_inherited"],
        counts["no_high_confidence_match"], counts["no_candidates"],
        counts["llm_calls"], counts["llm_error"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(main(args.limit))
