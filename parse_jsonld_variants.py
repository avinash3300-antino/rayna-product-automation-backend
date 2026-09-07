"""Extract variant/offer data from JSON-LD blocks on source URLs.

For each activity without tour_variants:
1. Fetch source_url with browser User-Agent
2. Parse all <script type="application/ld+json"> blocks
3. Extract variant info from schema.org Offer/Product/Event/ItemList
4. Store as tour_variants (real data — no LLM guessing)

Pilot mode by default (--limit N).

Usage:
  python parse_jsonld_variants.py --limit 50           # pilot (50 activities)
  python parse_jsonld_variants.py --limit 0            # full sweep
  python parse_jsonld_variants.py --city Bangkok       # single city
"""
import argparse
import asyncio
import json
import logging
import re
from collections import defaultdict
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("jsonld")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

API_CONCURRENCY = 4
PER_DOMAIN_MIN_DELAY = 0.6

_domain_last_call: dict[str, float] = {}


def _root_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _extract_jsonld_blocks(html: str) -> list:
    """Return list of parsed JSON-LD dicts from HTML."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")
    blocks = []
    for s in scripts:
        try:
            raw = (s.string or s.get_text() or "").strip()
            if not raw:
                continue
            obj = json.loads(raw)
            if isinstance(obj, list):
                blocks.extend(obj)
            else:
                blocks.append(obj)
        except (json.JSONDecodeError, TypeError):
            continue
    return blocks


def _walk(obj):
    """Recursively yield all dicts in a nested JSON structure."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def _extract_variants(blocks: list) -> list:
    """Look for schema.org Offers with useful pricing/availability info."""
    variants = []
    seen_names = set()
    for block in blocks:
        for node in _walk(block):
            t = node.get("@type") if isinstance(node, dict) else None
            if not t:
                continue
            # Normalize @type to list
            types = t if isinstance(t, list) else [t]
            # Interesting shapes: Offer, AggregateOffer.offers[], Product.offers, Event with subEvent
            if any(x in ("Offer", "TripOffer") for x in types):
                name = (node.get("name") or node.get("description") or "").strip()
                price = node.get("price") or node.get("lowPrice") or node.get("highPrice")
                currency = node.get("priceCurrency") or node.get("currency") or "USD"
                availability = node.get("availability") or None
                if name and name not in seen_names:
                    seen_names.add(name)
                    variants.append({
                        "name": name[:250],
                        "price_from": _to_num(price),
                        "currency": currency,
                        "availability": availability,
                        "source": "jsonld",
                        "has_inventory": bool(_to_num(price)),
                    })
            elif "Product" in types and node.get("hasVariant"):
                # Product with variants
                for v in (node.get("hasVariant") or []):
                    if not isinstance(v, dict):
                        continue
                    name = (v.get("name") or "").strip()
                    if name and name not in seen_names:
                        seen_names.add(name)
                        variants.append({
                            "name": name[:250], "source": "jsonld",
                            "has_inventory": False, "price_from": None,
                        })
    return variants


def _to_num(x):
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


async def _fetch_html(client, sem, url: str) -> str | None:
    """Fetch URL with polite per-domain rate limit."""
    domain = _root_domain(url)
    async with sem:
        import time
        now = time.time()
        wait = PER_DOMAIN_MIN_DELAY - (now - _domain_last_call.get(domain, 0))
        if wait > 0:
            await asyncio.sleep(wait)
        _domain_last_call[domain] = time.time()
        try:
            r = await client.get(url, headers=HEADERS, timeout=25, follow_redirects=True)
            if r.status_code >= 400:
                return None
            return r.text
        except Exception:
            return None


async def _process_activity(client, sem, activity_id, source_url, source_urls, counts):
    from app.db.base import async_session_factory
    from sqlalchemy import text

    urls_to_try = []
    if source_url:
        urls_to_try.append(source_url)
    for u in (source_urls or []):
        if u and u not in urls_to_try:
            urls_to_try.append(u)

    combined_variants = []
    seen = set()
    for url in urls_to_try:
        html = await _fetch_html(client, sem, url)
        counts["fetched"] += 1
        if html is None:
            counts["fetch_failed"] += 1
            continue
        blocks = _extract_jsonld_blocks(html)
        counts["jsonld_blocks"] += len(blocks)
        vs = _extract_variants(blocks)
        for v in vs:
            if v["name"] not in seen:
                seen.add(v["name"])
                combined_variants.append(v)

    if not combined_variants:
        counts["no_variants_found"] += 1
        return

    # Persist
    try:
        async with async_session_factory() as db:
            await db.execute(
                text("UPDATE activities SET tour_variants = CAST(:v AS JSON), "
                     "updated_at = NOW() WHERE id = :id"),
                {"v": json.dumps(combined_variants), "id": activity_id},
            )
            await db.commit()
            counts["updated"] += 1
            counts["variants_added"] += len(combined_variants)
    except Exception as exc:
        logger.warning("db update failed %s: %s", activity_id, exc)


async def main(limit: int, city_filter: str | None):
    from app.db.base import async_session_factory
    from sqlalchemy import text

    query = """
        SELECT id, name, city, source_url, source_urls
        FROM activities
        WHERE deleted_at IS NULL AND merged_into_id IS NULL
          AND (tour_variants IS NULL OR tour_variants::text IN ('null','[]'))
          AND source_url IS NOT NULL
    """
    params = {}
    if city_filter:
        query += " AND city = :city"
        params["city"] = city_filter
    if limit and limit > 0:
        query += f" ORDER BY random() LIMIT {int(limit)}"
    else:
        query += " ORDER BY city, name"

    async with async_session_factory() as db:
        result = await db.execute(text(query), params)
        rows = result.fetchall()

    logger.info("JSON-LD sweep on %d activities (limit=%d, city=%s)",
                len(rows), limit, city_filter)

    counts = defaultdict(int)
    per_domain_counts = defaultdict(lambda: defaultdict(int))

    sem = asyncio.Semaphore(API_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        tasks = [
            _process_activity(client, sem, r.id, r.source_url, r.source_urls, counts)
            for r in rows
        ]
        # Progress in batches
        BATCH = 50
        for i in range(0, len(tasks), BATCH):
            batch = tasks[i : i + BATCH]
            await asyncio.gather(*batch)
            logger.info("Progress %d/%d — updated=%d, no_variants=%d, fetch_fail=%d, blocks=%d",
                        i + len(batch), len(rows),
                        counts["updated"], counts["no_variants_found"],
                        counts["fetch_failed"], counts["jsonld_blocks"])

    logger.info("=" * 60)
    logger.info("FINAL: fetched=%d fetch_failed=%d jsonld_blocks=%d updated=%d "
                "no_variants=%d variants_added=%d",
                counts["fetched"], counts["fetch_failed"], counts["jsonld_blocks"],
                counts["updated"], counts["no_variants_found"], counts["variants_added"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--city", type=str, default=None)
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.city))
