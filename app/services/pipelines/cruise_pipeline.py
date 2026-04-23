"""Cruise-specific pipeline: extraction prompt, save, enrich, quality score."""

import json
import logging
from datetime import datetime, timedelta, timezone

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cruises import (
    CruiseCabin,
    CruiseItinerary,
    CruisePricingTier,
    CruiseProduct,
)
from app.db.models.scraping import ScrapeJob, ScrapeSource
from app.integrations.claude_client import claude_client
from app.services.dedup_service import check_duplicate, merge_or_save
from app.services.pipelines.base_pipeline import BasePipeline
from app.services.review_service import scrape_reviews_for_product

logger = logging.getLogger(__name__)

CRUISE_EXTRACTION_PROMPT = """You are a data extraction specialist for cruise & boat experiences.
Given a cleaned markdown page, extract ALL cruises/boat tours/sailing experiences as a JSON array.
Each item MUST have these fields (return null if not found — NEVER fabricate):

CORE IDENTITY:
- name (string, required — full display title, clean of emojis/special chars)
- raw_description_short (2-3 sentences EXACTLY as found — extract verbatim)
- raw_description_long (full description EXACTLY as found — combine all paragraphs)
- sub_category (Dinner Cruise, River Cruise, Ocean Cruise, Luxury Cruise, Dhow Cruise, Yacht Cruise, Sightseeing Cruise, Sunset Cruise, Party Cruise, Fishing Trip)
- cruise_class (Economy, Standard, Premium, Luxury — or null)
- cruise_type (dinner, sightseeing, overnight, multi-day, party, fishing, sunset — or null)

PRICING (extract numbers only, no currency symbols):
- price_adult (number or null — lowest advertised adult price)
- price_child (number or null)
- price_original (number or null — pre-discount price)
- currency (3-letter ISO code)
- price_type (Per person, Per group, Per cabin — default "Per person")
- discount_pct (number 0-100 or null)

DURATION & SCHEDULE:
- duration_hours (number or null — e.g. 2.5 for "2.5 hours")
- duration_days (integer or null — for multi-day cruises)
- number_of_nights (integer or null — for overnight cruises)
- departure_times (array of time strings or null — e.g. ["18:00", "21:00"])
- boarding_time (string or null — e.g. "17:30")
- operating_days (array of day names or null)
- seasonal_availability (string or null — e.g. "October to April")
- free_cancellation (boolean)
- instant_confirmation (boolean)
- cancellation_hours (integer or null)

LOCATION & BOARDING:
- address (string or null — full address, NOT just city)
- boarding_point_name (string or null — e.g. "Dubai Marina Pier 7")
- boarding_point_description (string or null — directions)
- pickup_available (boolean)
- pickup_points (array of strings or null — pickup locations)

VESSEL:
- vessel_name (string or null)
- vessel_type (Dhow, Yacht, Catamaran, Riverboat, Cruise Ship, Speedboat, Sailboat — or null)
- vessel_length_m (number or null)
- vessel_year_built (integer or null)
- vessel_capacity (integer or null — max guests)
- deck_count (integer or null)
- onboard_facilities (array of strings or null — e.g. ["Air-conditioned lower deck", "Open-air upper deck", "Live cooking station"])

ONBOARD EXPERIENCE:
- meal_included (boolean)
- meal_type (Buffet, Set Menu, A La Carte, BBQ — or null)
- entertainment_included (boolean)
- entertainment_details (array of strings or null — e.g. ["Live Tanoura dance", "DJ music"])
- wifi_available (boolean or null)

ITINERARY (extract if present):
- itinerary (array of objects or null — each: {order, day_number (null for same-day), time_label, port_or_stop, description, shore_excursion_available})

CABINS (for overnight cruises):
- cabins (array of objects or null — each: {cabin_type, cabin_count, max_occupancy, amenities: [], description})

PRICING TIERS (cabin-based pricing):
- pricing_tiers (array or null — each: {cabin_type, price_adult, price_child, price_infant, currency, includes_description})

ROUTE:
- route_description (string or null — the route taken e.g. "Dubai Marina → Palm Jumeirah → Ain Dubai → Atlantis → return")

ELIGIBILITY:
- min_age (integer or null)
- age_pricing_breaks (object or null — e.g. {"child_free_under": 4, "child_50pct_under": 12})
- dress_code (string or null)
- wheelchair_accessible (Yes, No, Partially — or null)
- languages (array of ISO codes or null)

REVIEWS:
- rating (number 0-5 or null)
- review_count (integer or null)

CONTENT (extract verbatim):
- raw_highlights (array of 4-8 strings EXACTLY as found)
- raw_included (array of strings EXACTLY as found)
- raw_excluded (array of strings EXACTLY as found)

OPERATOR:
- operator_name (string or null)
- operator_website (string or null)
- operator_license_body (string or null — e.g. "Dubai Maritime City Authority")
- operator_fleet_size (integer or null)

OTHER:
- redemption_instructions (array of strings or null)
- source_url (string or null)
- cover_image_url (string or null — full URL of main image)

═══ EXTRACTION QUALITY RULES ═══
1. All "raw_" prefixed fields must contain VERBATIM text.
2. For listing pages, extract EACH cruise separately.
3. For detail pages, extract EVERYTHING thoroughly.
4. NEVER fabricate prices, ratings, vessel specs, or capacity numbers.
5. Convert durations: "2 hour cruise" → duration_hours: 2, "3 nights" → number_of_nights: 3.

Return ONLY a valid JSON array. If no cruises found, return []."""

CRUISE_ENRICHMENT_PROMPT = """You are a professional travel content writer for Rayna Tours.
Your job is to take RAW SCRAPED text about a cruise/boat experience and produce COMPLETELY ORIGINAL content.

═══ COPYRIGHT & ORIGINALITY RULES (NON-NEGOTIABLE) ═══
1. NEVER copy any sentence from the scraped source text.
2. Every description MUST be written in your own words from scratch.
3. Use the scraped text ONLY as factual reference.
4. The output must pass a plagiarism check.

═══ CONTENT FIELDS (MANDATORY — always rewrite) ═══
- description_short (2-3 compelling sentences, 150-200 chars, original marketing copy)
- description_long (300-600 words, professional, engaging cruise experience writing, ORIGINAL)
- highlights (array of 4-8 strings — rewrite each compellingly)
- included (array — rewrite clearly)
- excluded (array — rewrite clearly)

═══ ITINERARY (fill if data available) ═══
- itinerary (array of objects: [{order, day_number, time_label, port_or_stop, description}])

═══ SEO (always fill) ═══
- meta_title (max 60 chars, format: "{name} in {city} | Rayna Tours")
- meta_description (max 155 chars)
- focus_keyword (primary SEO keyword)

═══ DETAILS (fill if determinable) ═══
- what_to_bring (text or null)
- important_notes (array of strings or null)
- redemption_instructions (array of step strings or null)
- cancellation_policy (text or null)
- cancellation_hours (integer or null)
- route_description (string or null)
- dress_code (string or null)
- languages (array of ISO codes)
- sub_category (string or null)

═══ VESSEL (fill if available) ═══
- onboard_facilities (array of strings or null)
- entertainment_details (array of strings or null)

═══ OPERATOR (fill if available) ═══
- operator_website (string or null)
- operator_license_body (string or null)
- operator_established_year (integer or null)
- operator_certifications (array or null)

═══ LOCATION (fill if missing) ═══
- boarding_point_name (string or null)
- boarding_point_description (string or null)
- address (string or null)

Return null for fields you cannot determine. Never fabricate factual data.
Return ONLY valid JSON, no markdown fences."""


class CruisePipeline(BasePipeline):
    product_type = "cruises"

    def get_extraction_prompt(self) -> str:
        return CRUISE_EXTRACTION_PROMPT

    async def save_extracted_products(
        self,
        db: AsyncSession,
        extracted: list[dict],
        source: ScrapeSource,
        job: ScrapeJob,
        city_name: str,
        country_name: str,
    ) -> dict:
        counts = {"found": len(extracted), "saved": 0, "skipped_dup": 0}

        for item in extracted:
            name = (item.get("name") or "").strip()
            if not name:
                continue

            city = item.get("city") or city_name
            category = item.get("category") or "Cruise"
            raw_desc_short = item.get("raw_description_short") or ""
            raw_desc_long = item.get("raw_description_long") or ""
            raw_highlights = item.get("raw_highlights") or []
            raw_included = item.get("raw_included") or []
            raw_excluded = item.get("raw_excluded") or []

            # Dedup check
            dedup_result = await check_duplicate(
                db, name, city, category, raw_desc_short,
                product_type="cruises",
                city_id=source.city_id,
            )
            if dedup_result["is_duplicate"]:
                if dedup_result["match_type"] == "semantic":
                    merge_data = {
                        "description_short": raw_desc_short,
                        "description_long": raw_desc_long,
                        "highlights": raw_highlights,
                        "included": raw_included,
                        "excluded": raw_excluded,
                        "price_adult": item.get("price_adult"),
                        "price_child": item.get("price_child"),
                        "price_original": item.get("price_original"),
                        "rating": item.get("rating"),
                        "review_count": item.get("review_count"),
                        "source_url": item.get("source_url") or source.source_url,
                    }
                    try:
                        await merge_or_save(
                            db, merge_data,
                            dedup_result["existing_id"],
                            dedup_result["match_type"],
                            product_type="cruises",
                        )
                        counts["skipped_dup"] += 1
                    except Exception as exc:
                        logger.warning("Merge failed for cruise '%s': %s", name, exc)
                        counts["skipped_dup"] += 1
                else:
                    counts["skipped_dup"] += 1
                continue

            # Generate unique slug
            slug = slugify(f"{name}-{city}")
            base_slug = slug
            counter = 1
            while True:
                existing_slug = await db.execute(
                    select(CruiseProduct.id).where(CruiseProduct.slug == slug)
                )
                if not existing_slug.scalar_one_or_none():
                    break
                slug = f"{base_slug}-{counter}"
                counter += 1

            cruise = CruiseProduct(
                name=name,
                slug=slug,
                city_id=source.city_id,
                category="Cruise",
                sub_category=item.get("sub_category"),
                cruise_class=item.get("cruise_class"),
                cruise_type=item.get("cruise_type"),
                tags=item.get("tags"),
                status="draft",
                description_short=raw_desc_short or name,
                description_long=raw_desc_long or "",
                highlights=raw_highlights,
                included=raw_included,
                excluded=raw_excluded,
                important_notes=item.get("important_notes"),
                redemption_instructions=item.get("redemption_instructions"),
                price_adult=item.get("price_adult") or 0,
                price_child=item.get("price_child"),
                price_original=item.get("price_original"),
                currency="AED",
                price_type=item.get("price_type") or "Per person",
                discount_pct=item.get("discount_pct"),
                price_from=item.get("price_adult") or 0,
                duration_hours=item.get("duration_hours"),
                duration_days=item.get("duration_days"),
                number_of_nights=item.get("number_of_nights") or 0,
                departure_times=item.get("departure_times"),
                boarding_time=item.get("boarding_time"),
                operating_days=item.get("operating_days"),
                seasonal_availability=item.get("seasonal_availability"),
                free_cancellation=item.get("free_cancellation") or False,
                instant_confirmation=item.get("instant_confirmation") or False,
                cancellation_hours=item.get("cancellation_hours"),
                advance_booking_days=item.get("advance_booking_days"),
                country=country_name or "Unknown",
                city=city,
                address=item.get("address") or city,
                lat=item.get("lat") or 0,
                lng=item.get("lng") or 0,
                boarding_point_name=item.get("boarding_point_name"),
                boarding_point_description=item.get("boarding_point_description"),
                pickup_available=item.get("pickup_available") or False,
                pickup_points=item.get("pickup_points"),
                # Vessel
                vessel_name=item.get("vessel_name"),
                vessel_type=item.get("vessel_type"),
                vessel_length_m=item.get("vessel_length_m"),
                vessel_year_built=item.get("vessel_year_built"),
                vessel_capacity=item.get("vessel_capacity"),
                deck_count=item.get("deck_count"),
                onboard_facilities=item.get("onboard_facilities"),
                # Onboard
                meal_included=item.get("meal_included") or False,
                meal_type=item.get("meal_type"),
                entertainment_included=item.get("entertainment_included") or False,
                entertainment_details=item.get("entertainment_details"),
                wifi_available=item.get("wifi_available") or False,
                # Route
                route_description=item.get("route_description"),
                # Eligibility
                min_age=item.get("min_age"),
                age_pricing_breaks=item.get("age_pricing_breaks"),
                dress_code=item.get("dress_code"),
                wheelchair_accessible=item.get("wheelchair_accessible"),
                languages=item.get("languages") or ["en"],
                # Operator
                operator_name=item.get("operator_name"),
                operator_website=item.get("operator_website"),
                operator_license_body=item.get("operator_license_body"),
                operator_fleet_size=item.get("operator_fleet_size"),
                # Media
                cover_image_url=item.get("cover_image_url"),
                # Source
                source_url=item.get("source_url") or source.source_url,
                source_urls=[item.get("source_url") or source.source_url],
                source_type=job.scrape_type,
                dedup_hash=self.compute_dedup_hash(name, city, category),
                quality_score=0,
                rating=item.get("rating"),
                review_count=item.get("review_count") or 0,
            )
            db.add(cruise)
            await db.flush()

            # Save itinerary
            for it in (item.get("itinerary") or []):
                step = CruiseItinerary(
                    cruise_id=cruise.id,
                    order=it.get("order", 0),
                    day_number=it.get("day_number"),
                    time_label=it.get("time_label"),
                    port_or_stop=it.get("port_or_stop"),
                    description=it.get("description"),
                    shore_excursion_available=it.get("shore_excursion_available", False),
                )
                db.add(step)

            # Save cabins
            for cab in (item.get("cabins") or []):
                cabin = CruiseCabin(
                    cruise_id=cruise.id,
                    cabin_type=cab.get("cabin_type", "Standard"),
                    cabin_count=cab.get("cabin_count"),
                    max_occupancy=cab.get("max_occupancy"),
                    amenities=cab.get("amenities"),
                    description=cab.get("description"),
                )
                db.add(cabin)

            # Save pricing tiers
            for pt in (item.get("pricing_tiers") or []):
                tier = CruisePricingTier(
                    cruise_id=cruise.id,
                    cabin_type=pt.get("cabin_type", "Standard"),
                    price_adult=pt.get("price_adult"),
                    price_child=pt.get("price_child"),
                    price_infant=pt.get("price_infant"),
                    currency=pt.get("currency") or cruise.currency,
                    includes_description=pt.get("includes_description"),
                )
                db.add(tier)

            counts["saved"] += 1

        await db.flush()
        return counts

    async def enrich_product(self, db: AsyncSession, product: CruiseProduct) -> None:
        prompt = f"""Cruise Name: {product.name}
City: {product.city}
Country: {product.country}
Sub-category: {product.sub_category or 'N/A'}
Cruise Type: {product.cruise_type or 'N/A'}
Vessel Type: {product.vessel_type or 'N/A'}
Price Adult: {product.price_adult or 'N/A'} {product.currency}
Duration: {product.duration_hours or 'N/A'} hours, {product.number_of_nights or 0} nights
Source URL: {product.source_url}

═══ RAW SCRAPED TEXT (use as REFERENCE ONLY — do NOT copy) ═══

Short description:
{product.description_short or 'N/A'}

Long description:
{(product.description_long or 'N/A')[:3000]}

Highlights:
{json.dumps(product.highlights or [], indent=2) if product.highlights else 'N/A'}

Inclusions:
{json.dumps(product.included or [], indent=2) if product.included else 'N/A'}

Exclusions:
{json.dumps(product.excluded or [], indent=2) if product.excluded else 'N/A'}

Onboard facilities:
{json.dumps(product.onboard_facilities or [], indent=2) if product.onboard_facilities else 'N/A'}

═══ INSTRUCTIONS ═══
1. Read the scraped text to understand this cruise experience.
2. Write COMPLETELY ORIGINAL content — new sentences, new phrasing.
3. Fill in all missing fields based on knowledge of cruises in {product.city}.
4. Produce professional, engaging cruise experience content for Rayna Tours."""

        response_text = await claude_client.generate(
            prompt=prompt,
            system=CRUISE_ENRICHMENT_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.4,
        )

        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        enriched = json.loads(text)

        # Content fields — ALWAYS overwrite
        for field in ["description_short", "description_long", "highlights", "included", "excluded"]:
            value = enriched.get(field)
            if value is not None and hasattr(product, field):
                setattr(product, field, value)

        # Itinerary — overwrite if provided
        itinerary_data = enriched.get("itinerary")
        if itinerary_data and isinstance(itinerary_data, list):
            for existing in list(product.itinerary):
                await db.delete(existing)
            await db.flush()
            for it in itinerary_data:
                step = CruiseItinerary(
                    cruise_id=product.id,
                    order=it.get("order", 0),
                    day_number=it.get("day_number"),
                    time_label=it.get("time_label"),
                    port_or_stop=it.get("port_or_stop"),
                    description=it.get("description"),
                    shore_excursion_available=it.get("shore_excursion_available", False),
                )
                db.add(step)

        # SEO fields — ALWAYS overwrite
        for field in ["meta_title", "meta_description", "focus_keyword"]:
            value = enriched.get(field)
            if value is not None and hasattr(product, field):
                if field == "meta_title":
                    value = value[:60]
                elif field == "meta_description":
                    value = value[:155]
                elif field == "focus_keyword":
                    value = value[:100]
                setattr(product, field, value)

        # Other fields — fill if empty
        fill_if_empty = [
            "what_to_bring", "important_notes", "redemption_instructions",
            "cancellation_policy", "cancellation_hours",
            "route_description", "dress_code", "languages", "sub_category",
            "onboard_facilities", "entertainment_details",
            "operator_website", "operator_license_body",
            "operator_established_year", "operator_certifications",
            "boarding_point_name", "boarding_point_description", "address",
            "departure_times", "operating_days",
        ]
        for field in fill_if_empty:
            value = enriched.get(field)
            if value is not None and hasattr(product, field):
                existing = getattr(product, field)
                if not existing or existing == 0 or existing == [] or existing == "":
                    setattr(product, field, value)

        if product.status == "draft":
            product.status = "enriched"

        product.quality_score = self.calculate_quality_score(product)
        product.updated_at = datetime.now(timezone.utc)
        await db.flush()

    def calculate_quality_score(self, cruise: CruiseProduct) -> int:
        score = 0
        checks = [
            # Core identity (20 pts)
            (cruise.name, 6),
            (cruise.description_short, 5),
            (cruise.description_long, 6),
            (cruise.sub_category, 3),
            # Content (14 pts)
            (cruise.highlights, 4),
            (cruise.included, 4),
            (cruise.excluded, 4),
            (cruise.itinerary if hasattr(cruise, "itinerary") else None, 2),
            # Pricing (10 pts)
            (cruise.price_adult, 4),
            (cruise.price_child, 2),
            (cruise.currency, 2),
            (cruise.price_original, 2),
            # Duration & scheduling (10 pts)
            (cruise.duration_hours, 3),
            (cruise.departure_times, 2),
            (cruise.boarding_time, 2),
            (cruise.free_cancellation is not None, 1),
            (cruise.instant_confirmation is not None, 1),
            (cruise.operating_days, 1),
            # Location (10 pts)
            (cruise.address and cruise.address != cruise.city, 3),
            (cruise.lat and cruise.lng, 3),
            (cruise.boarding_point_name, 2),
            (cruise.pickup_available is not None, 2),
            # Vessel (10 pts)
            (cruise.vessel_name, 2),
            (cruise.vessel_type, 2),
            (cruise.vessel_capacity, 2),
            (cruise.onboard_facilities, 2),
            (cruise.deck_count, 2),
            # Onboard (6 pts)
            (cruise.meal_included is not None, 2),
            (cruise.meal_type, 2),
            (cruise.entertainment_included is not None, 2),
            # Media (8 pts)
            (cruise.cover_image_url, 4),
            (cruise.gallery_json, 4),
            # SEO (7 pts)
            (cruise.meta_title, 3),
            (cruise.meta_description, 2),
            (cruise.focus_keyword, 2),
            # Social proof (5 pts)
            (cruise.rating, 3),
            (cruise.review_count, 2),
        ]
        for value, points in checks:
            if value:
                score += points
        return min(score, 100)

    async def run_post_enrichment(
        self,
        db: AsyncSession,
        product: CruiseProduct,
        errors: list[dict],
    ) -> None:
        await self.fetch_gallery(product, errors)
        await self.geocode(product, errors)

        if not product.review_snippets:
            try:
                await scrape_reviews_for_product(
                    db, product.id,
                    product_type="cruises",
                    product_name=product.name,
                    product_city=product.city,
                    product_country=product.country,
                    operator_name=product.operator_name,
                    platforms=["google", "tripadvisor"],
                )
            except Exception as exc:
                errors.append({
                    "product_id": str(product.id),
                    "error": str(exc),
                    "step": "reviews",
                })
                logger.warning("Review scrape failed for cruise %s: %s", product.id, exc)

        await db.flush()

    async def get_recently_saved_products(
        self,
        db: AsyncSession,
        city_id,
        started_at,
        limit: int,
    ) -> list:
        cutoff = started_at - timedelta(seconds=30)
        result = await db.execute(
            select(CruiseProduct)
            .where(
                CruiseProduct.city_id == city_id,
                CruiseProduct.status == "draft",
                CruiseProduct.created_at >= cutoff,
            )
            .order_by(CruiseProduct.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
