"""Merge GlobalTix VARIANT NAMES into existing activities. No new products.

Per user direction 2026-07-30: GlobalTix is used ONLY to enrich existing DB rows
with variant options. If a GlobalTix product doesn't match an existing DB row
by normalized name, it is SKIPPED — no new activity is created.

Flow per country:
1. List all GlobalTix products via /api/product/list (paginated size=500)
2. For each product in a target city:
   - Match against active DB rows by dedup_hash (city-scoped)
   - If NO match: skip
   - If match:
     - Append globaltix URL to source_urls[]
     - Set globaltix_id
     - Use fromPrice for competitor_price if not already set
     - Fetch /api/product/options?id=<id> → append variant NAMES to tour_variants

Usage: python ingest_globaltix.py
"""
import asyncio
import json
import logging
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_gt")

GT_BASE = os.environ.get("GLOBALTIX_BASE", "https://stg-api.globaltix.com")
GT_AGENT = os.environ["GLOBALTIX_AGENT"]
GT_USER = os.environ["GLOBALTIX_USERNAME"]
GT_KEY = os.environ["GLOBALTIX_API_KEY"]

# Countries → which of OUR DB cities we want to check for
COUNTRIES = {
    "AE": ["Dubai", "Abu Dhabi", "Fujairah"],
    "SA": ["Riyadh", "Jeddah"],
    "OM": ["Muscat"],
    "EG": ["Cairo"],
    "TR": ["Istanbul"],
    "GB": ["London"],
    "FR": ["Paris"],
    "CH": ["Zurich", "Lucerne"],
    "NL": ["Amsterdam"],
    "IT": ["Rome"],
    "ES": ["Barcelona"],
    "VN": ["Ho Chi Minh City", "Hanoi"],
    "JP": ["Tokyo", "Osaka"],
    "KR": ["Seoul"],
    "SG": ["Singapore"],
    "MY": ["Kuala Lumpur", "Langkawi"],
    "ID": ["Bali"],
    "MV": ["Male", "South Male Atoll"],
    "TH": ["Bangkok", "Phuket"],
    "MU": ["Port Louis"],
    "US": ["New York", "Orlando", "Washington DC", "Los Angeles"],
}

API_CONCURRENCY = 5
DB_BATCH_SIZE = 20

_token = None
_token_expiry = 0.0


async def _auth(client) -> str:
    """Get / refresh bearer token."""
    global _token, _token_expiry
    if _token and time.time() < (_token_expiry - 600):
        return _token
    r = await client.post(
        f"{GT_BASE}/api/auth/authorize",
        headers={
            "x-api-key": f"{GT_AGENT}/{GT_KEY}",
            "x-api-agent": GT_AGENT,
            "Content-Type": "application/json",
        },
        json={"username": GT_USER},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json().get("data") or {}
    _token = data["accessToken"]
    _token_expiry = time.time() + 86400  # 24h per docs
    return _token


async def _gt_get(client, sem, path, params=None):
    async with sem:
        for attempt in range(3):
            try:
                headers = {
                    "Authorization": f"Bearer {await _auth(client)}",
                    "x-api-agent": GT_AGENT,
                    "Accept-Version": "1.0",
                    "Accept": "application/json",
                }
                r = await client.get(f"{GT_BASE}{path}", params=params,
                                     headers=headers, timeout=45)
                if r.status_code == 401:
                    global _token
                    _token = None
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as exc:
                if attempt == 2:
                    logger.debug("gt_get %s failed: %s", path, exc)
                    return None
                await asyncio.sleep(1.5 * (attempt + 1))
        return None


async def _fetch_products_for_country(client, sem, country_code):
    products, page = [], 0
    while True:
        data = await _gt_get(client, sem, "/api/product/list",
                             {"countryCode": country_code, "page": page, "size": 500})
        if not data:
            break
        items = data.get("data") or []
        if not items:
            break
        products.extend(items)
        if len(items) < 500:
            break
        page += 1
    return products


async def _fetch_options(client, sem, product_id):
    data = await _gt_get(client, sem, "/api/product/options",
                         {"id": product_id, "isDynamicPrice": "false"})
    return (data or {}).get("data") or []


async def _upsert_product(db, city_id, city_name, product, counts, client, sem):
    """Match GT product to DB; merge or create; then attach variant names."""
    from app.services.dedup_service import compute_dedupe_hash
    from sqlalchemy import text

    name = (product.get("name") or "").strip()
    if not name:
        counts["skipped"] += 1
        return

    gt_id = product.get("id")
    from_price = product.get("fromPrice")
    currency = product.get("currency") or "USD"
    category = product.get("category") or "Landmark Tickets"
    keywords = product.get("keywords") or ""
    merchant = ((product.get("merchant") or {}).get("name") or "").strip()

    # GlobalTix doesn't publish a canonical URL — construct a stable synthetic
    # ref using the product ID; downstream systems can render this to their
    # own product page URL if needed.
    gt_url = f"https://globaltix.com/product/{gt_id}"

    dedup_hash = compute_dedupe_hash(name, city_name, category)

    # Early exit if this globaltix_id was ALREADY merged (has variants).
    # Makes re-runs of already-processed countries flash through.
    check = await db.execute(text(
        "SELECT 1 FROM activities WHERE globaltix_id = :gid "
        "AND tour_variants IS NOT NULL AND tour_variants::text NOT IN ('null','[]') "
        "AND deleted_at IS NULL AND merged_into_id IS NULL LIMIT 1"
    ), {"gid": gt_id})
    if check.first():
        counts["already_done"] = counts.get("already_done", 0) + 1
        return

    # DB match FIRST — skip options fetch entirely if no match (saves ~70% of API calls)
    existing = await db.execute(text(
        "SELECT id, source_urls, source_url, tour_variants, competitor_price "
        "FROM activities WHERE globaltix_id = :gid "
        "AND deleted_at IS NULL AND merged_into_id IS NULL LIMIT 1"
    ), {"gid": gt_id})
    row = existing.first()

    if row is None:
        existing = await db.execute(text(
            "SELECT id, source_urls, source_url, tour_variants, competitor_price "
            "FROM activities WHERE dedup_hash = :h "
            "AND deleted_at IS NULL AND merged_into_id IS NULL LIMIT 1"
        ), {"h": dedup_hash})
        row = existing.first()

    if row is None:
        # No match → skip. Do NOT fetch options (saves an API call per no-match).
        counts["no_match"] += 1
        return

    # Match found — NOW fetch variants (only if worth it)
    variants = await _fetch_options(client, sem, gt_id)
    variant_summaries = [
        {"id": str(v.get("id")), "name": v.get("name") or "",
         "source": "globaltix", "has_inventory": False, "price_from": None}
        for v in variants if v.get("id")
    ]

    # Merge into existing DB row
    cur_urls = row.source_urls if isinstance(row.source_urls, list) else (
        [row.source_url] if row.source_url else []
    )
    if gt_url and gt_url not in cur_urls:
        cur_urls.append(gt_url)

    # Merge tour_variants: existing (Headout etc.) + new GT names, dedup by id
    cur_variants = row.tour_variants if isinstance(row.tour_variants, list) else []
    seen_ids = {str((v or {}).get("id") or "") for v in cur_variants}
    merged_variants = list(cur_variants)
    variants_added = 0
    for v in variant_summaries:
        if v["id"] not in seen_ids:
            merged_variants.append(v)
            seen_ids.add(v["id"])
            variants_added += 1

    # Only overwrite competitor_price if not set from Headout
    await db.execute(text("""
        UPDATE activities SET
            source_urls = CAST(:urls AS JSON),
            globaltix_id = COALESCE(globaltix_id, :gid),
            competitor_price = COALESCE(competitor_price, :cp),
            competitor_price_currency = COALESCE(competitor_price_currency, :ccur),
            tour_variants = CAST(:tv AS JSON),
            updated_at = NOW()
        WHERE id = :id
    """), {
        "urls": json.dumps(cur_urls), "gid": gt_id,
        "cp": from_price, "ccur": currency,
        "tv": json.dumps(merged_variants) if merged_variants else None,
        "id": row.id,
    })
    counts["merged"] += 1
    counts["variants_added"] += variants_added


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    async with async_session_factory() as db:
        result = await db.execute(text(
            "SELECT id, name, city_name FROM catalog_destinations WHERE status='active'"
        ))
        dests = result.fetchall()
    dest_by_city = {(d.city_name or d.name): d for d in dests}

    sem = asyncio.Semaphore(API_CONCURRENCY)
    grand = {"merged": 0, "no_match": 0, "skipped": 0, "variants_added": 0, "unmapped_city": 0}

    async with httpx.AsyncClient() as client:
        for country_idx, (cc, target_cities) in enumerate(COUNTRIES.items(), 1):
            logger.info("[%d/%d] === country=%s target_cities=%s ===",
                        country_idx, len(COUNTRIES), cc, target_cities)
            try:
                products = await _fetch_products_for_country(client, sem, cc)
            except Exception as exc:
                logger.error("fetch products %s failed: %s", cc, exc)
                continue
            logger.info("  fetched %d products from %s", len(products), cc)

            # Filter to products in target cities
            target_lower = {c.lower() for c in target_cities}
            relevant = [
                p for p in products
                if (p.get("city") or "").lower() in target_lower
            ]
            logger.info("  %d relevant products for target cities", len(relevant))

            counts = {"merged": 0, "no_match": 0, "skipped": 0, "variants_added": 0}

            for i, product in enumerate(relevant, 1):
                gt_city = product.get("city") or ""
                # Match GT city to DB city (case-insensitive)
                db_city_key = next(
                    (c for c in target_cities if c.lower() == gt_city.lower()),
                    None,
                )
                if not db_city_key or db_city_key not in dest_by_city:
                    counts["skipped"] += 1
                    grand["unmapped_city"] += 1
                    continue
                dest = dest_by_city[db_city_key]

                try:
                    async with async_session_factory() as db:
                        await _upsert_product(
                            db, dest.id, db_city_key, product, counts,
                            client, sem,
                        )
                        await db.commit()
                except Exception as exc:
                    logger.warning("upsert failed for '%s': %s",
                                   (product.get("name") or "")[:60], exc)
                    counts["skipped"] += 1

                if i % 100 == 0:
                    logger.info("  [%s] %d/%d relevant processed (merged=%d, no_match=%d, +variants=%d)",
                                cc, i, len(relevant), counts["merged"], counts["no_match"], counts["variants_added"])

            logger.info("[%s] DONE: merged=%d no_match=%d skipped=%d variants_added=%d",
                        cc, counts["merged"], counts["no_match"], counts["skipped"], counts["variants_added"])
            for k in ("merged", "no_match", "skipped", "variants_added"):
                grand[k] += counts[k]

    logger.info("=" * 60)
    logger.info("GRAND TOTAL: merged=%d, no_match=%d, skipped=%d, variants_added=%d, unmapped_city=%d",
                grand["merged"], grand["no_match"], grand["skipped"], grand["variants_added"], grand["unmapped_city"])


if __name__ == "__main__":
    asyncio.run(main())
