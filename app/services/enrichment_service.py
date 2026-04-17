import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ExternalServiceError
from app.db.models.activities import Activity
from app.integrations.claude_client import claude_client
from app.integrations.geocoding_client import geocoding_client
from app.services.image_service import fetch_and_upload_images

logger = logging.getLogger(__name__)

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
- description_long (300-600 words, professional English, SEO-optimized, engaging travel writing, COMPLETELY ORIGINAL)
- highlights (array of 4-8 bullet point strings — rewrite each in fresh, compelling language)
- included (array of what's included — rewrite clearly, do not copy source phrasing)
- excluded (array of what's excluded — rewrite clearly, do not copy source phrasing)

═══ SEO (always fill) ═══
- meta_title (max 60 chars, format: "{name} in {city} | Rayna Tours")
- meta_description (max 155 chars, compelling, includes keyword)
- focus_keyword (primary SEO keyword for this activity)

═══ DETAILS (fill if determinable) ═══
- what_to_bring (text or null)
- important_notes (text or null)
- cancellation_policy (text or null)
- cancellation_hours (integer or null — typically 24)
- fitness_level (Easy, Moderate, or Strenuous — or null)
- difficulty (Beginner, Intermediate, or Advanced — or null)
- languages (array of ISO 639-1 codes, e.g. ["en", "ar"])
- sub_category (string or null — e.g. "Snorkeling", "Museum Tour")

═══ LOCATION (fill if missing) ═══
- meeting_point_name (string or null)
- meeting_point_desc (string or null)
- address (string or null)

═══ SCHEDULING (fill if missing) ═══
- start_times (array of time strings or null)
- operating_days (array of day names or null)

═══ PRICING (fill from knowledge) ═══
- price_adult (number or null)
- price_child (number or null)
- price_original (number or null)

Return null for fields you cannot determine. Never fabricate factual data (prices, times, addresses).
Return ONLY valid JSON, no markdown fences."""


async def enrich_activity(
    db: AsyncSession,
    activity: Activity,
) -> Activity:
    """Enrich an activity using Claude AI, geocoding, and images.

    MANDATORY for every activity — Claude rewrites ALL text content from scratch.
    No scraped description ever goes into the final output as-is.
    """
    try:
        # ── Step 1: Claude content rewriting & enrichment ──────────────
        prompt = f"""Activity Name: {activity.name}
City: {activity.city}
Country: {activity.country}
Category: {activity.category}
Sub-category: {activity.sub_category or 'N/A'}
Activity Type: {activity.activity_type}
Price Adult: {activity.price_adult or 'N/A'} {activity.currency}
Duration: {activity.duration_minutes or 'N/A'} minutes
Source URL: {activity.source_url}

═══ RAW SCRAPED TEXT (use as REFERENCE ONLY — do NOT copy any phrasing) ═══

Scraped short description:
{activity.description_short or 'N/A'}

Scraped long description:
{(activity.description_long or 'N/A')[:3000]}

Scraped highlights:
{json.dumps(activity.highlights or [], indent=2) if activity.highlights else 'N/A'}

Scraped inclusions:
{json.dumps(activity.included or [], indent=2) if activity.included else 'N/A'}

Scraped exclusions:
{json.dumps(activity.excluded or [], indent=2) if activity.excluded else 'N/A'}

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

        # Parse Claude response
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        enriched = json.loads(text)

        # Content fields — ALWAYS overwrite with Claude's original rewrite
        content_fields = [
            "description_short",
            "description_long",
            "highlights",
            "included",
            "excluded",
        ]
        for field in content_fields:
            value = enriched.get(field)
            if value is not None and hasattr(activity, field):
                setattr(activity, field, value)

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
            if value is not None and hasattr(activity, field):
                setattr(activity, field, value)

        # Other fields — only fill if currently empty/null
        fill_if_empty_fields = [
            "what_to_bring",
            "important_notes",
            "cancellation_policy",
            "cancellation_hours",
            "fitness_level",
            "difficulty",
            "languages",
            "sub_category",
            "meeting_point_name",
            "meeting_point_desc",
            "address",
            "start_times",
            "operating_days",
            "price_adult",
            "price_child",
            "price_original",
        ]
        for field in fill_if_empty_fields:
            value = enriched.get(field)
            if value is not None and hasattr(activity, field):
                existing = getattr(activity, field)
                if not existing or existing == 0 or existing == [] or existing == "":
                    setattr(activity, field, value)

        # Mark status as enriched
        if activity.status == "draft":
            activity.status = "enriched"

        # ── Step 2: Geocoding (if needed) ─────────────────────────────
        if activity.address and (
            not activity.lat
            or not activity.lng
            or not activity.verified
        ):
            geo = await geocoding_client.geocode(
                activity.address, activity.city, activity.country
            )
            if geo:
                activity.lat = geo["lat"]
                activity.lng = geo["lng"]
                activity.verified = True

        # ── Step 3: Images (if missing) ───────────────────────────────
        if not activity.cover_image_url:
            images = await fetch_and_upload_images(
                activity.name,
                activity.city,
                str(activity.id),
                num_images=8,
            )
            if images:
                activity.cover_image_url = images[0]["url"]
                activity.gallery_json = images

        # ── Step 4: Reviews (if missing) ────────────────────────────
        if not activity.review_count or activity.review_count == 0:
            try:
                from app.services.review_service import scrape_reviews_for_activity
                await scrape_reviews_for_activity(db, activity.id)
            except Exception as rev_exc:
                logger.warning(
                    "Review scraping failed for activity %s: %s",
                    activity.id, rev_exc,
                )

        # ── Step 5: Recalculate quality score ─────────────────────────
        activity.quality_score = _calculate_quality_score(activity)
        activity.updated_at = datetime.now(timezone.utc)

        await db.flush()
        return activity

    except json.JSONDecodeError as exc:
        logger.error(
            "Claude returned invalid JSON for activity %s: %s",
            activity.id,
            exc,
        )
        raise ExternalServiceError(
            f"AI enrichment returned invalid JSON: {exc}"
        )
    except Exception as exc:
        logger.error(
            "Enrichment failed for activity %s: %s", activity.id, exc
        )
        raise ExternalServiceError(f"Enrichment failed: {exc}")


def _calculate_quality_score(activity: Activity) -> int:
    """Score 0-100 based on non-null Must-priority fields."""
    score = 0
    checks = [
        # Core identity (20 pts)
        (activity.name, 6),
        (activity.description_short, 5),
        (activity.description_long, 6),
        (activity.category, 3),
        # Content (12 pts)
        (activity.highlights, 4),
        (activity.included, 4),
        (activity.excluded, 4),
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
        # Media (12 pts)
        (activity.cover_image_url, 7),
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
