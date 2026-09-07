"""1-year window retry for Headout variants.

Targets two groups:
1. Activities with headout_id but empty tour_variants (never got any inventory data)
2. Activities where some stored variants have has_inventory=false (partially empty)

Sweeps the full 52-week (~1 year) window for those, so variants that only
have inventory further out get captured.

Idempotent: only OVERWRITES tour_variants if the retry finds MORE inventory.
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
logger = logging.getLogger("hd_1year")

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
NUM_WINDOWS = 52   # ~1 year of 7-day windows
API_CONCURRENCY = 5


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
            except Exception:
                if attempt == retries - 1:
                    return None
                await asyncio.sleep(1.5 * (attempt + 1))
        return None


async def _fetch_products(client, sem, city_code):
    products, offset = [], 0
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
        "has_inventory": False, "price_from": None, "currency": "USD",
        "sample_slot": None, "person_types": [], "prices_by_person": {},
        "windows_checked": 0,
    }
    for start, end in _windows(NUM_WINDOWS):
        summary["windows_checked"] += 1
        data = await _get_json(
            client, sem,
            f"{HEADOUT_BASE}/api/v1/inventory/list-by/variant",
            {"variantId": variant_id, "startDateTime": f"{start}T00:00:00",
             "endDateTime": f"{end}T23:59:59", "currencyCode": "USD"},
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


async def _enrich_one(client, sem, activity_id, existing_variants, headout_product):
    """Only re-check variants whose current summary has has_inventory=false."""
    variants_from_api = headout_product.get("variants") or []
    if not variants_from_api:
        return activity_id, existing_variants, 0

    # Build index of existing summaries by variant id
    existing_by_id = {}
    if existing_variants:
        for s in existing_variants:
            if s and s.get("id"):
                existing_by_id[str(s["id"])] = s

    new_variants = []
    upgraded = 0
    for v in variants_from_api:
        vid = str(v.get("id") or "")
        vname = v.get("name") or ""
        if not vid:
            continue
        existing = existing_by_id.get(vid)
        if existing and existing.get("has_inventory"):
            # Already have inventory for this variant — keep as-is
            new_variants.append(existing)
            continue
        # Re-check with 52-week window
        summary = await _summarize_variant(client, sem, vid, vname)
        if summary.get("has_inventory") and (not existing or not existing.get("has_inventory")):
            upgraded += 1
        new_variants.append(summary)

    return activity_id, new_variants, upgraded


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    # Load target activities: empty variants OR any variant has_inventory=false
    async with async_session_factory() as db:
        result = await db.execute(text("""
            SELECT id, name, city, headout_id, tour_variants
            FROM activities
            WHERE headout_id IS NOT NULL
              AND deleted_at IS NULL AND merged_into_id IS NULL
              AND (
                    tour_variants IS NULL
                 OR tour_variants::text IN ('null','[]')
                 OR tour_variants::text LIKE '%"has_inventory": false%'
              )
            ORDER BY city, name
        """))
        rows = result.fetchall()

    logger.info("1-year retry on %d activities (some empty, some partial)", len(rows))

    per_city: dict[str, list] = {}
    for r in rows:
        per_city.setdefault(r.city, []).append(r)

    sem = asyncio.Semaphore(API_CONCURRENCY)
    total_variants_upgraded = 0
    total_activities_updated = 0

    async with httpx.AsyncClient() as client:
        for city_idx, (city, activities) in enumerate(per_city.items(), 1):
            city_code = CITY_TO_HEADOUT.get(city)
            if not city_code:
                continue
            logger.info("[%d/%d] === %s (%d activities) → %s ===",
                        city_idx, len(per_city), city, len(activities), city_code)
            products = await _fetch_products(client, sem, city_code)
            prod_by_id = {str(p.get("id")): p for p in products}

            tasks = []
            for a in activities:
                hp = prod_by_id.get(str(a.headout_id))
                if not hp:
                    continue
                existing = a.tour_variants if isinstance(a.tour_variants, list) else []
                tasks.append(_enrich_one(client, sem, a.id, existing, hp))

            if not tasks:
                continue
            results = await asyncio.gather(*tasks)

            city_updated = 0
            city_upgraded_variants = 0
            async with async_session_factory() as db:
                for aid, new_variants, upgraded in results:
                    if upgraded == 0:
                        continue
                    await db.execute(text(
                        "UPDATE activities SET tour_variants = CAST(:v AS JSON), "
                        "updated_at = NOW() WHERE id = :id"
                    ), {"v": json.dumps(new_variants), "id": aid})
                    total_activities_updated += 1
                    city_updated += 1
                    total_variants_upgraded += upgraded
                    city_upgraded_variants += upgraded
                await db.commit()
            logger.info("  [%s] activities upgraded=%d, variants promoted=%d (total activities=%d, variants=%d)",
                        city, city_updated, city_upgraded_variants,
                        total_activities_updated, total_variants_upgraded)

    logger.info("=" * 60)
    logger.info("GRAND TOTAL: activities_updated=%d, variants_promoted=%d",
                total_activities_updated, total_variants_upgraded)


if __name__ == "__main__":
    asyncio.run(main())
