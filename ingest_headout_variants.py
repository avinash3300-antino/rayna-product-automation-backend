"""Async version — enrich Headout activities with variant-level pricing + availability.

Speedup vs the sync version:
- httpx.AsyncClient with semaphore(5) for API concurrency (within Headout's rate limit)
- Batch DB commits: 20 activities per transaction
- Same per-variant logic: up to 3 date windows, early-stop on first data

Idempotent: skips activities that already have tour_variants populated.

Usage: python ingest_headout_variants.py
"""
import asyncio
import json
import logging
import os
from datetime import date, timedelta

import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("hd_variants")

HEADOUT_KEY = os.environ["HEADOUT_API_KEY"]
HEADOUT_BASE = os.environ.get("HEADOUT_BASE", "https://www.sandbox-headout.com")
HEADOUT_HDR = {"Headout-Auth": HEADOUT_KEY, "Accept": "application/json"}

CITY_TO_HEADOUT = {
    "Bangkok": "BANGKOK", "Phuket": "PHUKET", "Dubai": "DUBAI",
    "Singapore": "SINGAPORE", "Kuala Lumpur": "KUALA_LUMPUR",
    "Langkawi": "LANGKAWI", "Bali": "BALI",
    "Ho Chi Minh City": "HO_CHI_MINH_CITY", "Hanoi": "HANOI",
    "Tokyo": "TOKYO", "Osaka": "OSAKA", "Seoul": "SEOUL",
    "Cairo": "CAIRO", "Istanbul": "ISTANBUL",
    "London": "LONDON", "Paris": "PARIS", "Zurich": "ZURICH",
    "Lucerne": "LUCERNE", "Amsterdam": "AMSTERDAM",
    "Rome": "ROME", "Barcelona": "BARCELONA",
    "New York": "NEW_YORK", "Orlando": "ORLANDO",
    "Washington DC": "WASHINGTON_DC", "Los Angeles": "LOS_ANGELES",
    "Port Louis": "MAURITIUS",
}

API_CONCURRENCY = 5      # Headout says ~5 req/sec sustained safe
DB_BATCH_SIZE = 20
NUM_WINDOWS = 3          # 21 days ahead, early-stop on first with data


def _windows(n: int):
    today = date.today()
    for i in range(n):
        start = today + timedelta(days=i * 7)
        end = start + timedelta(days=6)
        yield start.isoformat(), end.isoformat()


def _pick_adult(persons):
    for want in ("ADULT_NON_RESIDENT", "ADULT_RESIDENT", "ADULT", "GENERAL"):
        for p in persons:
            if (p.get("type") or "") == want:
                return p
    return persons[0] if persons else None


async def _get_json(client, sem, url, params, retries=3):
    async with sem:
        for attempt in range(retries):
            try:
                r = await client.get(url, params=params, headers=HEADOUT_HDR, timeout=30)
                r.raise_for_status()
                return r.json()
            except Exception as exc:
                if attempt == retries - 1:
                    logger.debug("api %s [attempt %d]: %s", url, attempt + 1, exc)
                    return None
                await asyncio.sleep(1.5 * (attempt + 1))
        return None


async def _fetch_products_for_city(client, sem, city_code):
    products = []
    offset = 0
    while True:
        data = await _get_json(client, sem,
                               f"{HEADOUT_BASE}/api/public/v2/products/",
                               {"cityCode": city_code, "offset": offset, "limit": 50})
        if not data:
            break
        items = data.get("products") or []
        if not items:
            break
        products.extend(items)
        if len(products) >= (data.get("total") or 0):
            break
        offset += 50
    return products


async def _summarize_variant(client, sem, variant_id, variant_name):
    summary = {
        "id": str(variant_id), "name": variant_name,
        "has_inventory": False,
        "price_from": None, "currency": "USD",
        "sample_slot": None,
        "person_types": [], "prices_by_person": {},
        "windows_checked": 0,
    }
    for start, end in _windows(NUM_WINDOWS):
        summary["windows_checked"] += 1
        data = await _get_json(
            client, sem,
            f"{HEADOUT_BASE}/api/v1/inventory/list-by/variant",
            {
                "variantId": variant_id,
                "startDateTime": f"{start}T00:00:00",
                "endDateTime": f"{end}T23:59:59",
                "currencyCode": "USD",
            },
        )
        if not data:
            continue
        items = data.get("items") or []
        if not items:
            continue
        summary["has_inventory"] = True
        first = items[0]
        summary["sample_slot"] = first.get("startDateTime")
        pricing = first.get("pricing") or {}
        persons = pricing.get("persons") or []
        summary["person_types"] = list({p.get("type") for p in persons if p.get("type")})
        prices = {}
        for p in persons:
            t = p.get("type")
            if not t:
                continue
            prices[t] = {
                "final": p.get("headoutSellingPrice") or p.get("price"),
                "original": p.get("originalPrice"),
                "net": p.get("netPrice"),
            }
        summary["prices_by_person"] = prices
        adult = _pick_adult(persons)
        if adult:
            summary["price_from"] = adult.get("headoutSellingPrice") or adult.get("price")
        return summary
    return summary


async def _enrich_activity(client, sem, activity_id, headout_product):
    """Return (activity_id, variant_summaries_json_str) or (activity_id, None) on fail."""
    variants = headout_product.get("variants") or []
    if not variants:
        return activity_id, None
    tasks = [
        _summarize_variant(client, sem, v.get("id"), v.get("name") or "")
        for v in variants if v.get("id")
    ]
    summaries = await asyncio.gather(*tasks, return_exceptions=False)
    return activity_id, summaries if summaries else None


async def _persist_batch(pairs):
    """UPDATE activities.tour_variants for a batch. pairs = [(activity_id, summaries), ...]."""
    if not pairs:
        return 0
    from app.db.base import async_session_factory
    from sqlalchemy import text
    updated = 0
    async with async_session_factory() as db:
        for activity_id, summaries in pairs:
            if not summaries:
                continue
            try:
                await db.execute(
                    text("UPDATE activities SET tour_variants = CAST(:v AS JSON), "
                         "updated_at = NOW() WHERE id = :id"),
                    {"v": json.dumps(summaries), "id": activity_id},
                )
                updated += 1
            except Exception as exc:
                logger.warning("persist %s failed: %s", activity_id, exc)
        await db.commit()
    return updated


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    async with async_session_factory() as db:
        result = await db.execute(text("""
            SELECT id, name, city, headout_id
            FROM activities
            WHERE headout_id IS NOT NULL
              AND deleted_at IS NULL AND merged_into_id IS NULL
              AND (tour_variants IS NULL OR tour_variants::text IN ('null','[]'))
            ORDER BY city, name
        """))
        rows = result.fetchall()

    logger.info("Loaded %d activities needing variant enrichment", len(rows))

    per_city: dict[str, list] = {}
    for r in rows:
        per_city.setdefault(r.city, []).append(r)

    total_updated = 0
    total_skipped = 0
    sem = asyncio.Semaphore(API_CONCURRENCY)

    async with httpx.AsyncClient() as client:
        for city_idx, (city, activities) in enumerate(per_city.items(), 1):
            city_code = CITY_TO_HEADOUT.get(city)
            if not city_code:
                logger.info("[%d/%d] SKIP %s (no Headout code)", city_idx, len(per_city), city)
                total_skipped += len(activities)
                continue

            logger.info("[%d/%d] === %s (%d activities) → %s ===",
                        city_idx, len(per_city), city, len(activities), city_code)
            try:
                products = await _fetch_products_for_city(client, sem, city_code)
            except Exception as exc:
                logger.error("product list failed for %s: %s", city, exc)
                total_skipped += len(activities)
                continue

            prod_by_id = {str(p.get("id")): p for p in products}

            batch: list = []
            enrich_tasks: list = []
            city_updated = 0

            async def flush(_batch):
                nonlocal city_updated, total_updated
                n = await _persist_batch(_batch)
                city_updated += n
                total_updated += n

            for ai, a in enumerate(activities, 1):
                hp = prod_by_id.get(str(a.headout_id))
                if not hp:
                    total_skipped += 1
                    continue
                enrich_tasks.append((a.id, hp))

                # Process in chunks of DB_BATCH_SIZE
                if len(enrich_tasks) >= DB_BATCH_SIZE or ai == len(activities):
                    results = await asyncio.gather(*[
                        _enrich_activity(client, sem, aid, hp) for aid, hp in enrich_tasks
                    ])
                    await flush(results)
                    logger.info("  [%s] %d/%d activities processed (updated_city=%d, total=%d)",
                                city, ai, len(activities), city_updated, total_updated)
                    enrich_tasks = []

            logger.info("[%s] done — updated %d", city, city_updated)

    logger.info("=" * 60)
    logger.info("GRAND TOTAL: updated=%d, skipped=%d", total_updated, total_skipped)


if __name__ == "__main__":
    asyncio.run(main())
