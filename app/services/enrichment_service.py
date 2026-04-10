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

ENRICHMENT_SYSTEM_PROMPT = """You are a travel content specialist for Rayna Tours.
Given raw scraped data about a travel activity, produce a JSON object with these fields:

CONTENT (always fill these):
- description_long (300-600 words, professional English, SEO-optimized)
- highlights (array of 4-8 bullet point strings)
- included (array of what's included strings)
- excluded (array of what's excluded strings)

SEO (always fill these):
- meta_title (max 60 chars, format: "{name} in {city} | Rayna Tours")
- meta_description (max 155 chars, compelling, includes keyword)
- focus_keyword (primary SEO keyword for this activity)

DETAILS (fill if you can determine):
- what_to_bring (text or null)
- important_notes (text or null)
- cancellation_policy (text or null)
- cancellation_hours (integer or null — typical hours before start for free cancellation, commonly 24)
- fitness_level (Easy, Moderate, or Strenuous — or null)
- difficulty (Beginner, Intermediate, or Advanced — or null)
- languages (array of ISO 639-1 codes, e.g. ["en", "ar"])
- sub_category (string or null — specific sub-type, e.g. "Snorkeling", "Museum Tour")

LOCATION (fill if missing from extracted data):
- meeting_point_name (string or null — common meeting/start point for this activity)
- meeting_point_desc (string or null — directions to the meeting point)
- address (string or null — best known address for this activity)

SCHEDULING (fill if missing — use typical values for this type of activity):
- start_times (array of time strings or null — typical departure times)
- operating_days (array of day names or null — typical operating days)

PRICING (fill from your knowledge of this specific activity):
- price_adult (number or null — typical adult price for this activity in the given currency)
- price_child (number or null — estimate ~60-70% of adult price if child pricing is common)
- price_original (number or null — original price if a discount is known)

CRITICAL: Return null for any field you cannot determine. Never fabricate data.
Return ONLY valid JSON, no markdown fences."""


async def enrich_activity(
    db: AsyncSession,
    activity: Activity,
) -> Activity:
    """Enrich an activity using Claude AI, geocoding, and images.

    Called when quality_score < 60 or description_long is under 100 words.
    """
    try:
        # ── Step 1: Claude enrichment ─────────────────────────────────
        prompt = f"""Activity Name: {activity.name}
City: {activity.city}
Country: {activity.country}
Category: {activity.category}
Sub-category: {activity.sub_category or 'N/A'}
Activity Type: {activity.activity_type}
Price Adult: {activity.price_adult or 'N/A'} {activity.currency}
Duration: {activity.duration_minutes or 'N/A'} minutes
Source URL: {activity.source_url}

Current short description:
{activity.description_short or 'N/A'}

Current long description:
{(activity.description_long or 'N/A')[:3000]}

Please enrich this activity with complete, accurate information.
Fill in any missing fields based on your knowledge of this activity and location."""

        response_text = await claude_client.generate(
            prompt=prompt,
            system=ENRICHMENT_SYSTEM_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.3,
        )

        # Parse Claude response
        enriched = json.loads(response_text)

        # Apply enriched fields (only overwrite if current value is empty)
        enrichable_fields = [
            "description_long",
            "highlights",
            "included",
            "excluded",
            "meta_title",
            "meta_description",
            "focus_keyword",
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
        # Truncate SEO fields to column limits
        if "meta_title" in enriched and enriched["meta_title"]:
            enriched["meta_title"] = enriched["meta_title"][:60]
        if "meta_description" in enriched and enriched["meta_description"]:
            enriched["meta_description"] = enriched["meta_description"][:155]
        if "focus_keyword" in enriched and enriched["focus_keyword"]:
            enriched["focus_keyword"] = enriched["focus_keyword"][:100]

        for field in enrichable_fields:
            value = enriched.get(field)
            if value is not None and hasattr(activity, field):
                existing = getattr(activity, field)
                # Only overwrite if existing value is empty/null/default
                if not existing or existing == 0 or existing == [] or existing == "":
                    setattr(activity, field, value)

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

        # ── Step 4: Recalculate quality score ─────────────────────────
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
