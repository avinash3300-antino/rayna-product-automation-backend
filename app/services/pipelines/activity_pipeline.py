"""Activity-specific pipeline: extraction prompt, save, enrich, quality score."""

import json
import logging
from datetime import datetime, timedelta, timezone

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activities import Activity, ActivityTimeline
from app.db.models.scraping import ScrapeJob, ScrapeSource
from app.integrations.claude_client import claude_client
from app.services.dedup_service import check_duplicate, merge_or_save
from app.services.pipelines.base_pipeline import BasePipeline
from app.services.review_service import scrape_reviews_for_product

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a data extraction specialist for travel activities.
Given a cleaned markdown page, extract ALL travel activities/tours/experiences as a JSON array.
Each item MUST have these fields (return null if not found — NEVER fabricate):

CORE IDENTITY:
- name (string, required — full display title, clean of emojis/special chars)
- raw_description_short (2-3 sentences EXACTLY as found on the page — extract verbatim, do NOT rephrase)
- raw_description_long (full description EXACTLY as found on the page — extract verbatim, do NOT rephrase.
  Combine all descriptive paragraphs found — include overview, what-to-expect sections, itinerary text.)
- category (one of: Sightseeing Tours, Landmark Tickets, Museum & Gallery, Thames River, Day Trips, Harry Potter & Film, Food & Drink, Shows & Entertainment, Passes & Combos, Transfers, Sports & Outdoor, Night Tours, Family & Kids, Luxury & Private, Seasonal & Events)
- sub_category (string or null — more specific, e.g. "Hop-on Hop-off Bus", "Walking Tour", "Skip-the-Line", "Studio Tour", "Pub Crawl", "Theatre Tickets", "Airport Transfer", "Stadium Tour", "Ghost Tour", "Zoo Visit")
- activity_type (Group tour, Private tour, Self-guided, Transfer-included, Attraction, Experience, Pass/Combo, Show/Event)

PRICING (ALL prices MUST be converted to AED):
- price_adult (number in AED — convert if source is GBP×4.7, USD×3.67, EUR×4.0, INR×0.044, JPY×0.025, EGP×0.075. "from" price counts, prefer lowest advertised adult price)
- price_child (number in AED or null — child ticket price if listed, typically age 3-11)
- price_original (number in AED or null — original pre-discount price if strikethrough/crossed-out shown)
- currency (ALWAYS "AED" — Rayna Tours uses AED exclusively)
- price_type (Per person, Per group, Per vehicle — default "Per person")
- discount_pct (number 0-100 or null — percentage discount if shown)

BOOKING & AVAILABILITY:
- duration_minutes (integer or null — convert: "2 hours"→120, "half day"→240, "full day"→480, "3h 30m"→210)
- free_cancellation (boolean — true if "free cancellation" mentioned anywhere)
- instant_confirmation (boolean — true if "instant confirmation" or "instant booking" mentioned)
- cancellation_hours (integer or null — hours before start for free cancellation, e.g. 24)
- start_times (array of time strings like "09:00", "14:00" or null — look for departure/pickup times)
- operating_days (array of day names like "Mon","Tue","Wed" or null — look for "available daily" → all 7 days)
- min_age (integer or null — minimum age requirement)

LOCATION:
- address (string or null — full street address, NOT just the city name)
- meeting_point_name (string or null — e.g. "Main entrance of Tower of London")
- meeting_point_desc (string or null — directions to meeting point)
- pickup_available (boolean — true if hotel/location pickup is mentioned)
- hotel_pickup_included (boolean — true if hotel pickup is specifically included free)

REVIEWS:
- rating (number 0-5 or null — convert from other scales: "4.5/5"→4.5, "9/10"→4.5)
- review_count (integer or null — extract "1,234 reviews" → 1234)

CONTENT (extract verbatim):
- raw_highlights (array of 4-8 strings EXACTLY as found — look for bullet points, key features, "why choose this")
- raw_included (array of strings EXACTLY as found — what's included: transport, meals, tickets, guide, etc.)
- raw_excluded (array of strings EXACTLY as found — what's not included)

TIMELINE / ITINERARY (extract if present):
- timeline (array of objects or null — each: {order: int, time_label: string or null, title: string, description: string or null})
  Look for "What you do", "Itinerary", "Schedule", ordered steps/stops.

OPERATOR & OTHER:
- languages (array of ISO codes like "en","ar","fr" or null)
- operator_name (string or null — company running the activity)
- operator_website (string or null — operator's website URL)
- operator_established_year (integer or null — year operator was established)
- redemption_instructions (array of strings or null — how to redeem voucher, e.g. "Show mobile voucher at entrance")
- dress_code_note (string or null — any dress code requirements)
- source_url (string or null — URL of this specific activity page)
- cover_image_url (string or null — URL of the main hero/cover image, must be a full URL)

═══ EXTRACTION QUALITY RULES ═══
1. All "raw_" prefixed fields must contain VERBATIM text from the source page.
   Do NOT clean up, rephrase, or improve them — extract exactly what the page says.
2. For listing pages with many activities, extract EACH one separately with whatever data is available.
3. For detail pages with one activity, extract EVERYTHING available — be thorough.
4. Prefer SPECIFIC data over generic: "Desert Safari in Dubai" is better than "Safari Tour".
5. If price is shown as a range like "$50-$100", use the lower value for price_adult.
6. Extract duration even from vague text: "morning tour" → 240, "2-3 hours" → 150.
7. NEVER make up prices, ratings, or addresses. Only extract what's on the page.

Return ONLY a valid JSON array. If no activities found, return []."""

ENRICHMENT_SYSTEM_PROMPT = """You are a professional travel content writer for Rayna Tours.
Your job is to take RAW SCRAPED text from third-party websites and produce COMPLETELY ORIGINAL content.

═══ COPYRIGHT & ORIGINALITY RULES (NON-NEGOTIABLE) ═══
1. NEVER copy any sentence, phrase, or distinctive wording from the scraped source text.
2. Every description, highlight, inclusion, and exclusion MUST be written in your own words from scratch.
3. Use the scraped text ONLY as factual reference material — extract the FACTS, then write ORIGINAL prose.
4. If multiple source descriptions are provided, synthesize the best information from all into ONE original piece.
5. The output must pass a plagiarism check — no phrasing should match any source verbatim.

═══ CONTENT FIELDS (MANDATORY — always rewrite from scratch) ═══
- description_short (2-3 compelling sentences, 150-200 chars, original marketing copy for Rayna Tours)
- description_long (HTML formatted with bullet points: use <ul><li> lists to organize key aspects of the activity. Start with a 1-2 sentence intro paragraph, then use bullet-point sections for highlights, experience details, and practical info. 300-600 words total, professional English, SEO-optimized, COMPLETELY ORIGINAL)
- highlights (array of 4-8 bullet point strings — rewrite each in fresh, compelling language)
- included (array of what's included — rewrite clearly, do not copy source phrasing)
- excluded (array of what's excluded — rewrite clearly, do not copy source phrasing)

═══ TIMELINE (always fill if itinerary data available) ═══
- timeline (array of objects: [{order, time_label, title, description}] — rewrite descriptions originally)

═══ SEO (always fill) ═══
- meta_title (max 60 chars, format: "{name} in {city} | Rayna Tours")
- meta_description (max 155 chars, compelling, includes keyword)
- focus_keyword (primary SEO keyword for this activity)

═══ DETAILS (fill if determinable) ═══
- what_to_bring (text or null)
- important_notes (array of strings or null — key things travellers should know)
- redemption_instructions (array of step strings or null)
- cancellation_policy (text or null)
- cancellation_hours (integer or null — typically 24)
- fitness_level (Easy, Moderate, or Strenuous — or null)
- difficulty (Beginner, Intermediate, or Advanced — or null)
- languages (array of ISO 639-1 codes, e.g. ["en", "ar"])
- sub_category (string or null — e.g. "Snorkeling", "Museum Tour")
- dress_code_note (string or null)

═══ OPERATOR (fill if available) ═══
- operator_website (string or null)
- operator_established_year (integer or null)
- operator_certifications (array of strings or null)

═══ LOCATION (fill if missing) ═══
- meeting_point_name (string or null)
- meeting_point_desc (string or null)
- address (string or null)

═══ SCHEDULING (fill if missing) ═══
- start_times (array of time strings or null)
- operating_days (array of day names or null)

═══ PRICING (fill from knowledge — ALL prices MUST be in AED) ═══
- price_adult (number in AED or null — if source is GBP multiply by ~4.7, USD by ~3.67, EUR by ~4.0, EGP by ~0.075)
- price_child (number in AED or null)
- price_original (number in AED or null)

Return null for fields you cannot determine. Never fabricate factual data (times, addresses).
For pricing, convert to AED if the source currency is different.
Return ONLY valid JSON, no markdown fences."""


class ActivityPipeline(BasePipeline):
    product_type = "activities"

    def get_extraction_prompt(self) -> str:
        return EXTRACTION_SYSTEM_PROMPT

    async def save_extracted_products(
        self,
        db: AsyncSession,
        extracted: list[dict],
        source: ScrapeSource,
        job: ScrapeJob,
        city_name: str,
        country_name: str,
    ) -> dict:
        """Save extracted activities with dedup. Returns counts dict."""
        counts = {"found": len(extracted), "saved": 0, "skipped_dup": 0}

        for item in extracted:
            name = (item.get("name") or "").strip()
            if not name:
                continue

            city = item.get("city") or city_name
            category = item.get("category") or source.category
            raw_desc_short = item.get("raw_description_short") or item.get("description_short") or ""
            raw_desc_long = item.get("raw_description_long") or item.get("description_long") or ""
            raw_highlights = item.get("raw_highlights") or item.get("highlights") or []
            raw_included = item.get("raw_included") or item.get("included") or []
            raw_excluded = item.get("raw_excluded") or item.get("excluded") or []

            # Dedup check
            dedup_result = await check_duplicate(
                db, name, city, category, raw_desc_short,
                product_type="activities",
                city_id=source.city_id,
            )
            if dedup_result["is_duplicate"]:
                new_source_url = item.get("source_url") or source.source_url

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
                        "gallery_json": item.get("gallery_json"),
                        "cover_image_url": item.get("cover_image_url"),
                        "start_times": item.get("start_times"),
                        "operating_days": item.get("operating_days"),
                        "address": item.get("address"),
                        "meeting_point_name": item.get("meeting_point_name"),
                        "source_url": new_source_url,
                    }
                    try:
                        await merge_or_save(
                            db, merge_data,
                            dedup_result["existing_id"],
                            dedup_result["match_type"],
                            product_type="activities",
                        )
                        counts["skipped_dup"] += 1
                    except Exception as exc:
                        logger.warning("Merge failed for '%s': %s", name, exc)
                        counts["skipped_dup"] += 1
                else:
                    # Exact duplicate — still merge the source URL
                    try:
                        existing = await db.get(Activity, dedup_result["existing_id"])
                        if existing and new_source_url:
                            current_urls = existing.source_urls or [existing.source_url]
                            if new_source_url not in current_urls:
                                existing.source_urls = current_urls + [new_source_url]
                                logger.info(
                                    "Added source URL to exact dup '%s': %s",
                                    name, new_source_url,
                                )
                                await db.flush()
                    except Exception as exc:
                        logger.warning("Source URL merge failed for '%s': %s", name, exc)
                    counts["skipped_dup"] += 1
                continue

            # Generate unique slug
            slug = slugify(f"{name}-{city}")
            base_slug = slug
            counter = 1
            while True:
                existing_slug = await db.execute(
                    select(Activity.id).where(Activity.slug == slug)
                )
                if not existing_slug.scalar_one_or_none():
                    break
                slug = f"{base_slug}-{counter}"
                counter += 1

            activity = Activity(
                name=name,
                slug=slug,
                city_id=source.city_id,
                category=category,
                sub_category=item.get("sub_category"),
                activity_type=item.get("activity_type") or "Group tour",
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
                price_from=item.get("price_adult") or item.get("price_from") or 0,
                duration_minutes=item.get("duration_minutes") or 0,
                free_cancellation=item.get("free_cancellation") or False,
                instant_confirmation=item.get("instant_confirmation") or False,
                cancellation_hours=item.get("cancellation_hours"),
                start_times=item.get("start_times") or [],
                operating_days=item.get("operating_days") or [],
                min_age=item.get("min_age"),
                country=country_name or "Unknown",
                city=city,
                address=item.get("address") or city,
                lat=item.get("lat") or 0,
                lng=item.get("lng") or 0,
                meeting_point_name=item.get("meeting_point_name"),
                meeting_point_desc=item.get("meeting_point_desc"),
                pickup_available=item.get("pickup_available") or False,
                hotel_pickup_included=item.get("hotel_pickup_included") or False,
                languages=item.get("languages") or ["en"],
                cover_image_url=item.get("cover_image_url"),
                source_url=item.get("source_url") or source.source_url,
                source_urls=[item.get("source_url") or source.source_url],
                source_type=job.scrape_type,
                operator_name=item.get("operator_name"),
                operator_website=item.get("operator_website"),
                operator_established_year=item.get("operator_established_year"),
                dress_code_note=item.get("dress_code_note"),
                dedup_hash=self.compute_dedup_hash(name, city, category),
                quality_score=0,
                rating=item.get("rating"),
                review_count=item.get("review_count") or 0,
            )
            db.add(activity)
            await db.flush()

            # Save timeline items if extracted
            timeline_items = item.get("timeline") or []
            for ti in timeline_items:
                step = ActivityTimeline(
                    activity_id=activity.id,
                    order=ti.get("order", 0),
                    time_label=ti.get("time_label"),
                    title=ti.get("title", ""),
                    description=ti.get("description"),
                )
                db.add(step)

            counts["saved"] += 1

        await db.flush()
        return counts

    async def enrich_product(self, db: AsyncSession, product: Activity) -> None:
        """Enrich an activity using Claude AI, geocoding, and images."""
        prompt = f"""Activity Name: {product.name}
City: {product.city}
Country: {product.country}
Category: {product.category}
Sub-category: {product.sub_category or 'N/A'}
Activity Type: {product.activity_type}
Price Adult: {product.price_adult or 'N/A'} {product.currency}
Duration: {product.duration_minutes or 'N/A'} minutes
Source URL: {product.source_url}

═══ RAW SCRAPED TEXT (use as REFERENCE ONLY — do NOT copy any phrasing) ═══

Scraped short description:
{product.description_short or 'N/A'}

Scraped long description:
{(product.description_long or 'N/A')[:3000]}

Scraped highlights:
{json.dumps(product.highlights or [], indent=2) if product.highlights else 'N/A'}

Scraped inclusions:
{json.dumps(product.included or [], indent=2) if product.included else 'N/A'}

Scraped exclusions:
{json.dumps(product.excluded or [], indent=2) if product.excluded else 'N/A'}

═══ INSTRUCTIONS ═══
1. Read the scraped text above to understand what this activity offers.
2. Write COMPLETELY ORIGINAL content — new sentences, new phrasing, new structure.
3. Do NOT copy or closely paraphrase any sentence from the scraped text.
4. Fill in all missing fields based on your knowledge of this activity and location.
5. Produce professional, engaging travel content worthy of Rayna Tours."""

        response_text = await claude_client.generate(
            prompt=prompt,
            system=ENRICHMENT_SYSTEM_PROMPT,
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

        # Timeline — overwrite if provided
        timeline_data = enriched.get("timeline")
        if timeline_data and isinstance(timeline_data, list):
            # Clear existing timeline (use query to avoid lazy-load)
            from sqlalchemy import delete as sa_delete
            await db.execute(
                sa_delete(ActivityTimeline).where(
                    ActivityTimeline.activity_id == product.id
                )
            )
            await db.flush()
            for ti in timeline_data:
                step = ActivityTimeline(
                    activity_id=product.id,
                    order=ti.get("order", 0),
                    time_label=ti.get("time_label"),
                    title=ti.get("title", ""),
                    description=ti.get("description"),
                )
                db.add(step)

        # SEO fields — ALWAYS overwrite
        seo_fields = ["meta_title", "meta_description", "focus_keyword"]
        if "meta_title" in enriched and enriched["meta_title"]:
            enriched["meta_title"] = enriched["meta_title"][:60]
        if "meta_description" in enriched and enriched["meta_description"]:
            enriched["meta_description"] = enriched["meta_description"][:155]
        if "focus_keyword" in enriched and enriched["focus_keyword"]:
            enriched["focus_keyword"] = enriched["focus_keyword"][:100]
        for field in seo_fields:
            value = enriched.get(field)
            if value is not None and hasattr(product, field):
                setattr(product, field, value)

        # Other fields — only fill if currently empty/null
        fill_if_empty_fields = [
            "what_to_bring", "important_notes", "redemption_instructions",
            "cancellation_policy", "cancellation_hours",
            "fitness_level", "difficulty", "languages", "sub_category",
            "dress_code_note", "operator_website", "operator_established_year",
            "operator_certifications",
            "meeting_point_name", "meeting_point_desc", "address",
            "start_times", "operating_days",
            "price_adult", "price_child", "price_original",
        ]
        for field in fill_if_empty_fields:
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

    def calculate_quality_score(self, activity: Activity) -> int:
        """Score 0-100 based on non-null Must-priority fields."""
        score = 0
        checks = [
            # Core identity (20 pts)
            (activity.name, 6),
            (activity.description_short, 5),
            (activity.description_long, 6),
            (activity.category, 3),
            # Content (14 pts)
            (activity.highlights, 4),
            (activity.included, 4),
            (activity.excluded, 4),
            (None, 2),  # timeline is a relationship — skip to avoid lazy-load
            # Pricing (14 pts)
            (activity.price_adult, 6),
            (activity.price_child, 2),
            (activity.price_type, 2),
            (activity.currency, 2),
            (activity.price_original, 2),
            # Scheduling & policies (12 pts)
            (activity.duration_minutes, 3),
            (activity.free_cancellation is not None, 2),
            (activity.instant_confirmation is not None, 2),
            (activity.cancellation_hours, 2),
            (activity.operating_days, 1),
            (activity.start_times, 1),
            (activity.min_age is not None, 1),
            # Location (14 pts)
            (activity.address and activity.address != activity.city, 4),
            (activity.lat and activity.lng, 4),
            (activity.meeting_point_name, 3),
            (activity.pickup_available is not None, 3),
            # Media (10 pts)
            (activity.cover_image_url, 5),
            (activity.gallery_json, 5),
            # SEO (8 pts)
            (activity.meta_title, 3),
            (activity.meta_description, 3),
            (activity.focus_keyword, 2),
            # Social proof (5 pts)
            (activity.rating, 3),
            (activity.review_count, 2),
            # Misc (3 pts)
            (activity.languages, 1),
            (activity.verified, 1),
            (activity.cancellation_policy, 1),
        ]
        for value, points in checks:
            if value:
                score += points
        return min(score, 100)

    async def run_post_enrichment(
        self,
        db: AsyncSession,
        product: Activity,
        errors: list[dict],
    ) -> None:
        """Gallery, geocoding, reviews for one activity."""
        await self.fetch_gallery(product, errors)
        await self.geocode(product, errors)

        if not product.review_snippets:
            try:
                await scrape_reviews_for_product(
                    db, product.id,
                    product_type="activities",
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
                logger.warning("Review scrape failed for %s: %s", product.id, exc)

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
            select(Activity)
            .where(
                Activity.city_id == city_id,
                Activity.status == "draft",
                Activity.created_at >= cutoff,
            )
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
