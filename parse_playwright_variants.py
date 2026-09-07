"""Playwright-based variant extraction for direct-operator source URLs.

For each activity WITHOUT tour_variants whose source_url domain is a direct
operator (not a major OTA), load the page in headless Chromium, wait for JS,
then extract JSON-LD + common option/pricing DOM patterns.

Real data only — no LLM inference.

Usage:
  python parse_playwright_variants.py --limit 30       # pilot
  python parse_playwright_variants.py --limit 0        # full sweep
"""
import argparse
import asyncio
import json
import logging
import re
from collections import defaultdict
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("pw_variants")

# Major OTAs to EXCLUDE (already covered by Headout/GT, and heavy anti-bot)
EXCLUDE_DOMAINS = [
    "viator.com", "getyourguide.com", "klook.com", "tripadvisor.com",
    "headout.com", "booking.com", "expedia.com", "tiqets.com",
    "musement.com", "civitatis.com", "airbnb.com", "trip.com",
    "globaltix.com", "sandbox-headout.com",
]

CONCURRENCY = 3  # 3 parallel browsers is safe on a Mac
PAGE_TIMEOUT_MS = 20000
WAIT_AFTER_LOAD_MS = 1500

# JSON-LD variant extraction (same rules as parse_jsonld_variants.py)
def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def _to_num(x):
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _extract_variants_from_jsonld(blocks: list) -> list:
    variants = []
    seen = set()
    for block in blocks:
        for node in _walk(block):
            if not isinstance(node, dict):
                continue
            t = node.get("@type")
            if not t:
                continue
            types = t if isinstance(t, list) else [t]
            if any(x in ("Offer", "TripOffer") for x in types):
                name = (node.get("name") or node.get("description") or "").strip()
                price = node.get("price") or node.get("lowPrice") or node.get("highPrice")
                currency = node.get("priceCurrency") or node.get("currency") or "USD"
                availability = node.get("availability") or None
                if name and name not in seen:
                    seen.add(name)
                    variants.append({
                        "name": name[:250],
                        "price_from": _to_num(price),
                        "currency": currency,
                        "availability": availability,
                        "source": "playwright_jsonld",
                        "has_inventory": bool(_to_num(price)),
                    })
            elif "Product" in types and node.get("hasVariant"):
                for v in (node.get("hasVariant") or []):
                    if not isinstance(v, dict):
                        continue
                    name = (v.get("name") or "").strip()
                    if name and name not in seen:
                        seen.add(name)
                        variants.append({
                            "name": name[:250], "source": "playwright_jsonld",
                            "has_inventory": False, "price_from": None,
                        })
    return variants


async def _extract_dom_variants(page) -> list:
    """Best-effort DOM-based variant extraction.

    Look for common patterns: <select> option lists near price/tour keywords,
    ticket-type cards, tour package lists. Very site-specific; return empty
    if nothing obvious.
    """
    js = r"""
    () => {
      const results = [];
      const seen = new Set();

      // Pattern 1: <select> options mentioning 'Ticket', 'Tour', 'Package'
      document.querySelectorAll('select').forEach(sel => {
        const label = (sel.getAttribute('name') || sel.getAttribute('id') || '').toLowerCase();
        if (!/ticket|tour|package|option|variant|type|pass/i.test(label)) return;
        sel.querySelectorAll('option').forEach(opt => {
          const t = (opt.textContent || '').trim();
          if (t && t.length > 3 && t.length < 200 && !seen.has(t)) {
            seen.add(t);
            results.push({name: t, source: 'playwright_dom_select'});
          }
        });
      });

      // Pattern 2: radio buttons for ticket types
      document.querySelectorAll('input[type="radio"]').forEach(r => {
        const label = (r.getAttribute('name') || '').toLowerCase();
        if (!/ticket|tour|package|option|variant|type|pass/i.test(label)) return;
        const parent = r.closest('label') || r.parentElement;
        if (parent) {
          const t = (parent.textContent || '').replace(/\s+/g,' ').trim();
          if (t && t.length > 3 && t.length < 200 && !seen.has(t)) {
            seen.add(t);
            results.push({name: t, source: 'playwright_dom_radio'});
          }
        }
      });

      return results;
    }
    """
    try:
        rows = await page.evaluate(js)
        return [
            {**r, "has_inventory": False, "price_from": None, "currency": "USD"}
            for r in (rows or [])[:20]
        ]
    except Exception:
        return []


async def _process(browser, activity_id, source_urls, counts, sem):
    async with sem:
        combined = []
        seen_names = set()
        for url in source_urls[:2]:  # try up to 2 URLs
            context = None
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/121.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                try:
                    await page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                    await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
                except PWTimeoutError:
                    counts["timeout"] += 1
                    continue
                except Exception as exc:
                    counts["nav_fail"] += 1
                    continue

                # JSON-LD blocks
                try:
                    jsonld_texts = await page.evaluate(
                        "() => Array.from(document.querySelectorAll('script[type=\"application/ld+json\"]')).map(s => s.textContent)"
                    )
                except Exception:
                    jsonld_texts = []

                blocks = []
                for txt in jsonld_texts or []:
                    if not txt:
                        continue
                    try:
                        obj = json.loads(txt)
                        if isinstance(obj, list):
                            blocks.extend(obj)
                        else:
                            blocks.append(obj)
                    except json.JSONDecodeError:
                        continue

                jsonld_variants = _extract_variants_from_jsonld(blocks)
                counts["jsonld_blocks"] += len(blocks)
                if jsonld_variants:
                    counts["jsonld_hits"] += 1

                # DOM-based
                dom_variants = await _extract_dom_variants(page)
                if dom_variants:
                    counts["dom_hits"] += 1

                for v in jsonld_variants + dom_variants:
                    n = v.get("name") or ""
                    if n and n not in seen_names:
                        seen_names.add(n)
                        combined.append(v)
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

        counts["processed"] += 1

        if not combined:
            counts["no_variants"] += 1
            return

        # Persist
        try:
            from app.db.base import async_session_factory
            from sqlalchemy import text
            async with async_session_factory() as db:
                await db.execute(
                    text("UPDATE activities SET tour_variants = CAST(:v AS JSON), "
                         "updated_at = NOW() WHERE id = :id"),
                    {"v": json.dumps(combined), "id": activity_id},
                )
                await db.commit()
            counts["updated"] += 1
            counts["variants_added"] += len(combined)
        except Exception as exc:
            logger.warning("DB update failed for %s: %s", activity_id, exc)


def _domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_direct_operator(url: str) -> bool:
    d = _domain_of(url)
    return not any(bad in d for bad in EXCLUDE_DOMAINS)


async def main(limit: int):
    from app.db.base import async_session_factory
    from sqlalchemy import text

    async with async_session_factory() as db:
        result = await db.execute(text("""
            SELECT id, name, city, source_url, source_urls
            FROM activities
            WHERE deleted_at IS NULL AND merged_into_id IS NULL
              AND (tour_variants IS NULL OR tour_variants::text IN ('null','[]'))
              AND source_url IS NOT NULL
        """))
        rows = result.fetchall()

    # Filter to direct-operator source_urls only
    filtered = []
    for r in rows:
        urls = []
        if r.source_url and _is_direct_operator(r.source_url):
            urls.append(r.source_url)
        for u in (r.source_urls or []):
            if u and _is_direct_operator(u) and u not in urls:
                urls.append(u)
        if urls:
            filtered.append((r.id, urls))

    if limit and limit > 0:
        import random
        random.shuffle(filtered)
        filtered = filtered[:limit]

    logger.info("Playwright pilot: %d activities on direct-operator sites (limit=%d)",
                len(filtered), limit)

    counts = defaultdict(int)
    sem = asyncio.Semaphore(CONCURRENCY)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            BATCH = 20
            for i in range(0, len(filtered), BATCH):
                batch = filtered[i : i + BATCH]
                tasks = [
                    _process(browser, aid, urls, counts, sem)
                    for aid, urls in batch
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(
                    "Progress %d/%d — updated=%d, no_variants=%d, timeout=%d, nav_fail=%d, jsonld_hits=%d, dom_hits=%d",
                    i + len(batch), len(filtered),
                    counts["updated"], counts["no_variants"],
                    counts["timeout"], counts["nav_fail"],
                    counts["jsonld_hits"], counts["dom_hits"],
                )
        finally:
            await browser.close()

    logger.info("=" * 60)
    logger.info(
        "FINAL: processed=%d updated=%d no_variants=%d timeout=%d nav_fail=%d "
        "jsonld_blocks=%d jsonld_hits=%d dom_hits=%d variants_added=%d",
        counts["processed"], counts["updated"], counts["no_variants"],
        counts["timeout"], counts["nav_fail"], counts["jsonld_blocks"],
        counts["jsonld_hits"], counts["dom_hits"], counts["variants_added"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(main(args.limit))
