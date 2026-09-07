"""Ingest products from Headout Partner API into activities table.

For each city in our DB that maps to a Headout cityCode:
1. Fetch all products via /api/public/v2/products/
2. For each product:
   - Compute dedup_hash using our normalized-name formula
   - Match against active DB rows (WHERE dedup_hash=? AND deleted_at IS NULL AND merged_into_id IS NULL)
   - If match: append canonicalUrl to source_urls[], set competitor_price/net_price/headout_id
   - If no match: create new activity

Idempotent: rerunning won't duplicate; existing headout_id causes UPDATE.

Usage: python ingest_headout.py
"""
import asyncio
import json
import logging
import os
import time
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_headout")

HEADOUT_KEY = os.environ["HEADOUT_API_KEY"]
HEADOUT_BASE = os.environ.get("HEADOUT_BASE", "https://www.sandbox-headout.com")
HEADOUT_HDR = {"Headout-Auth": HEADOUT_KEY, "Accept": "application/json"}

# DB city name → Headout cityCode. Only cities in Headout's verified catalog.
CITY_TO_HEADOUT = {
    "Bangkok": "BANGKOK",
    "Phuket": "PHUKET",
    "Dubai": "DUBAI",
    "Singapore": "SINGAPORE",
    "Kuala Lumpur": "KUALA_LUMPUR",
    "Langkawi": "LANGKAWI",
    "Bali": "BALI",
    "Ho Chi Minh City": "HO_CHI_MINH_CITY",
    "Hanoi": "HANOI",
    "Tokyo": "TOKYO",
    "Osaka": "OSAKA",
    "Seoul": "SEOUL",
    "Cairo": "CAIRO",
    "Istanbul": "ISTANBUL",
    "London": "LONDON",
    "Paris": "PARIS",
    "Zurich": "ZURICH",
    "Lucerne": "LUCERNE",
    "Amsterdam": "AMSTERDAM",
    "Rome": "ROME",
    "Barcelona": "BARCELONA",
    "New York": "NEW_YORK",
    "Orlando": "ORLANDO",
    "Washington DC": "WASHINGTON_DC",
    "Los Angeles": "LOS_ANGELES",
    "Port Louis": "MAURITIUS",   # Headout groups Mauritius under one cityCode
}


def _fetch_products(client: httpx.Client, city_code: str, page_size: int = 50) -> list[dict]:
    products = []
    offset = 0
    while True:
        for attempt in range(4):
            try:
                r = client.get(
                    f"{HEADOUT_BASE}/api/public/v2/products/",
                    params={"cityCode": city_code, "offset": offset, "limit": page_size},
                    headers=HEADOUT_HDR, timeout=30,
                )
                r.raise_for_status()
                break
            except (httpx.ReadTimeout, httpx.HTTPStatusError) as exc:
                if attempt == 3:
                    raise
                logger.warning("HTTP error for %s offset=%d (attempt %d): %s — backoff",
                               city_code, offset, attempt + 1, exc)
                time.sleep(2 * (attempt + 1))
        data = r.json()
        items = data.get("products") or []
        if not items:
            break
        products.extend(items)
        total = data.get("total") or 0
        if len(products) >= total:
            break
        offset += page_size
        time.sleep(0.15)
    return products


async def _upsert_product(db, city_id, city_name, headout: dict, counts: dict):
    """Match against existing DB row, else insert new."""
    from app.services.dedup_service import compute_dedupe_hash, normalize_name
    from sqlalchemy import text

    name = (headout.get("name") or "").strip()
    if not name:
        counts["skipped"] += 1
        return

    headout_id = str(headout.get("id") or "")
    canonical_url = (headout.get("canonicalUrl") or "").strip()
    dedup_hash = compute_dedupe_hash(name, city_name, headout.get("primaryCategory", {}).get("name") or "")

    pricing = headout.get("pricing") or {}
    competitor_price = pricing.get("headoutSellingPrice")
    net_price = pricing.get("netPrice")
    currency = pricing.get("currency") or "USD"

    content = headout.get("content") or {}
    short_summary = (content.get("shortSummary") or "")[:1000]
    highlights_html = content.get("highlightsHtml") or ""

    reviews = headout.get("reviewsSummary") or {}
    rating = reviews.get("averageRating")
    review_count = reviews.get("ratingsCount")

    # listingPrice.minimumPrice may be a dict {originalPrice, finalPrice, ...}
    # or a bare number depending on the product; normalise to a scalar.
    listing = headout.get("listingPrice") or {}
    min_p = listing.get("minimumPrice")
    if isinstance(min_p, dict):
        price_from = min_p.get("finalPrice") or min_p.get("originalPrice") or competitor_price
    else:
        price_from = min_p or competitor_price

    primary_cat = (headout.get("primaryCategory") or {}).get("name") or "Landmark Tickets"

    # First try to match on headout_id (already ingested)
    existing = await db.execute(text(
        "SELECT id, source_urls, source_url FROM activities "
        "WHERE headout_id = :hid AND deleted_at IS NULL AND merged_into_id IS NULL LIMIT 1"
    ), {"hid": headout_id})
    row = existing.first()

    # Then try match on dedup_hash (same product from a different source)
    if row is None:
        existing = await db.execute(text(
            "SELECT id, source_urls, source_url FROM activities "
            "WHERE dedup_hash = :h AND deleted_at IS NULL AND merged_into_id IS NULL LIMIT 1"
        ), {"h": dedup_hash})
        row = existing.first()

    if row is not None:
        # Merge: append canonicalUrl, update prices + headout_id
        current_urls = row.source_urls if isinstance(row.source_urls, list) else (
            [row.source_url] if row.source_url else []
        )
        merged_urls = list(current_urls)
        if canonical_url and canonical_url not in merged_urls:
            merged_urls.append(canonical_url)

        await db.execute(text("""
            UPDATE activities SET
                source_urls = CAST(:urls AS JSON),
                headout_id = COALESCE(headout_id, :hid),
                competitor_price = COALESCE(:cp, competitor_price),
                competitor_price_currency = COALESCE(:ccur, competitor_price_currency),
                net_price = COALESCE(:np, net_price),
                updated_at = NOW()
            WHERE id = :id
        """), {
            "urls": json.dumps(merged_urls), "hid": headout_id,
            "cp": competitor_price, "ccur": currency, "np": net_price,
            "id": row.id,
        })
        counts["merged"] += 1
        return

    # Create new activity
    from slugify import slugify
    base_slug = slugify(f"{name}-{city_name}")
    slug = base_slug
    n = 1
    while True:
        exists = await db.execute(text("SELECT 1 FROM activities WHERE slug = :s"), {"s": slug})
        if not exists.first():
            break
        n += 1
        slug = f"{base_slug}-{n}"

    # Derive optional fields
    start_loc = headout.get("startLocation") or {}
    country = start_loc.get("country") or ""
    lat = start_loc.get("latitude") or 0
    lng = start_loc.get("longitude") or 0
    duration_minutes = 0  # Headout list endpoint doesn't return duration; leave 0

    await db.execute(text("""
        INSERT INTO activities (
            id, name, slug, city_id, category, activity_type,
            status, source_type, source_url, source_urls,
            description_short, description_long,
            highlights, included, excluded,
            price_adult, currency, price_type, price_from,
            duration_minutes, start_times, operating_days,
            country, city, address, lat, lng, languages,
            quality_score, dedup_hash,
            headout_id, competitor_price, competitor_price_currency, net_price,
            rating, review_count
        ) VALUES (
            gen_random_uuid(), :name, :slug, :city_id, :cat, 'tour',
            'draft', 'headout_api', :src_url, CAST(:urls AS JSON),
            :short, :long,
            CAST('[]' AS JSON), CAST('[]' AS JSON), CAST('[]' AS JSON),
            :cp, :ccur, 'Per person', :pf,
            :dur, CAST('[]' AS JSON), CAST('[]' AS JSON),
            :country, :city, '', :lat, :lng, CAST('["en"]' AS JSON),
            :qs, :h,
            :hid, :cp, :ccur, :np,
            :rating, :rc
        )
    """), {
        "name": name, "slug": slug, "city_id": city_id,
        "cat": primary_cat, "src_url": canonical_url or "https://www.headout.com",
        "urls": json.dumps([canonical_url] if canonical_url else []),
        "short": short_summary or "", "long": highlights_html or "",
        "cp": competitor_price, "ccur": currency,
        "pf": price_from or 0, "dur": duration_minutes,
        "country": country, "city": city_name,
        "lat": lat, "lng": lng,
        "qs": 85, "h": dedup_hash, "hid": headout_id,
        "np": net_price, "rating": rating, "rc": review_count,
    })
    counts["created"] += 1


async def main():
    from app.db.base import async_session_factory
    from sqlalchemy import text

    grand_total = {"merged": 0, "created": 0, "skipped": 0, "no_headout_map": 0}

    async with async_session_factory() as db:
        # Load all destinations with active activities
        res = await db.execute(text(
            "SELECT id, name, city_name FROM catalog_destinations "
            "WHERE status = 'active' ORDER BY name"
        ))
        dests = res.fetchall()

    logger.info("Found %d destinations to check against Headout", len(dests))

    with httpx.Client() as client:
        for dest in dests:
            city_name = dest.city_name or dest.name
            city_code = CITY_TO_HEADOUT.get(dest.name) or CITY_TO_HEADOUT.get(city_name)
            if not city_code:
                logger.info("[SKIP] %s — not in Headout cityCode map", dest.name)
                grand_total["no_headout_map"] += 1
                continue

            logger.info("=" * 60)
            logger.info("[FETCH] %s → cityCode=%s", dest.name, city_code)
            try:
                products = _fetch_products(client, city_code)
                logger.info("[FETCH] %s: %d products", dest.name, len(products))
            except Exception as exc:
                logger.error("[FETCH FAILED] %s: %s", city_code, exc)
                continue

            counts = {"merged": 0, "created": 0, "skipped": 0}
            for i, product in enumerate(products, 1):
                # Fresh session per product so one failure doesn't taint the batch
                try:
                    async with async_session_factory() as db:
                        await _upsert_product(db, dest.id, city_name, product, counts)
                        await db.commit()
                except Exception as exc:
                    logger.warning("Upsert failed for '%s': %s",
                                   (product.get("name") or "")[:60], exc)
                    counts["skipped"] += 1
                if i % 50 == 0:
                    logger.info("[%s] %d/%d processed (merged=%d created=%d)",
                                dest.name, i, len(products), counts["merged"], counts["created"])

            logger.info("[DONE] %s: merged=%d created=%d skipped=%d",
                        dest.name, counts["merged"], counts["created"], counts["skipped"])
            for k in ("merged", "created", "skipped"):
                grand_total[k] += counts[k]

    logger.info("=" * 60)
    logger.info("GRAND TOTAL: merged=%d, created=%d, skipped=%d, no_headout_map=%d",
                grand_total["merged"], grand_total["created"],
                grand_total["skipped"], grand_total["no_headout_map"])


if __name__ == "__main__":
    asyncio.run(main())
