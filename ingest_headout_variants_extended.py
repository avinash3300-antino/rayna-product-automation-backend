"""3a: Re-run Headout variant enrichment for the ~80 activities where the
initial 21-day window returned no inventory. Widens to full 60 days (9 windows).

Only touches activities that:
- Have headout_id set
- Have NULL or empty tour_variants
- Are in a mapped Headout city
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
logger = logging.getLogger("hd_extended")

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
NUM_WINDOWS = 9
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
            except Exception as exc:
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


async def _enrich(client, sem, aid, hp):
    variants = hp.get("variants") or []
    if not variants:
        return aid, None
    tasks = [
        _summarize_variant(client, sem, v.get("id"), v.get("name") or "")
        for v in variants if v.get("id")
    ]
    summaries = await asyncio.gather(*tasks)
    return aid, summaries if summaries else None


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
            ORDER BY city
        """))
        rows = result.fetchall()

    logger.info("Extended sweep on %d Headout activities still missing options", len(rows))

    per_city: dict[str, list] = {}
    for r in rows:
        per_city.setdefault(r.city, []).append(r)

    sem = asyncio.Semaphore(API_CONCURRENCY)
    total_updated = 0

    async with httpx.AsyncClient() as client:
        for city, activities in per_city.items():
            city_code = CITY_TO_HEADOUT.get(city)
            if not city_code:
                logger.info("SKIP %s (no map)", city)
                continue
            logger.info("=== %s (%d activities) ===", city, len(activities))
            products = await _fetch_products(client, sem, city_code)
            prod_by_id = {str(p.get("id")): p for p in products}

            tasks = []
            for a in activities:
                hp = prod_by_id.get(str(a.headout_id))
                if hp:
                    tasks.append(_enrich(client, sem, a.id, hp))

            if not tasks:
                continue
            results = await asyncio.gather(*tasks)

            # Persist
            async with async_session_factory() as db:
                for aid, summaries in results:
                    if not summaries:
                        continue
                    # only save if at least one variant found inventory
                    if not any(s.get("has_inventory") for s in summaries):
                        continue
                    await db.execute(text(
                        "UPDATE activities SET tour_variants = CAST(:v AS JSON), "
                        "updated_at = NOW() WHERE id = :id"
                    ), {"v": json.dumps(summaries), "id": aid})
                    total_updated += 1
                await db.commit()
            logger.info("  [%s] updated=%d (running total=%d)", city, len(tasks), total_updated)

    logger.info("=" * 60)
    logger.info("GRAND TOTAL: updated=%d", total_updated)


if __name__ == "__main__":
    asyncio.run(main())
