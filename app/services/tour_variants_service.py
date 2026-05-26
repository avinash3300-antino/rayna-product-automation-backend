"""Tour variants service — scrape tour options/variants from source URLs."""

import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.activities import Activity
from app.integrations.claude_client import claude_client
from app.integrations.jina_client import jina_client
from app.integrations.apify_client import apify_client

logger = logging.getLogger(__name__)

TOUR_VARIANTS_EXTRACTION_PROMPT = """You are a tour variant extraction specialist. Given web page content from a travel/booking site, \
extract all tour options, variants, or package types available for this activity.

Return a JSON object with:
{
  "tour_variants": [
    {
      "name": "Tour + Lunch",
      "description": "Full guided tour including traditional lunch",
      "duration_minutes": 480,
      "price": {"amount": 85.00, "currency": "USD"},
      "includes": ["Lunch", "Guide", "Transport"],
      "excludes": ["Tips", "Personal expenses"],
      "is_default": false
    }
  ]
}

RULES FOR VARIANT EXTRACTION:
- Look for sections like "Options", "Select an option", "Tour options", "Choose your experience", "Package types", "What's included"
- Look for radio buttons, tabs, cards, or lists showing different tour configurations
- Each variant typically has a different name, price, and set of inclusions
- Common variant patterns:
  * With/without meals: "Tour + Lunch" vs "Tour Without Lunch"
  * Transport options: "Car + Guide" vs "Car + Audio Guide" vs "Group Bus"
  * Duration tiers: "Half Day" vs "Full Day"
  * Group size: "Private Tour" vs "Group Tour" vs "Small Group"
  * Access levels: "Standard" vs "VIP" vs "Skip-the-line"
  * Combo packages: "Tour Only" vs "Tour + Dinner Cruise" vs "Tour + Show"
  * Ticket types: "Adult" vs "Child" vs "Family" (only if these are separate tour options, NOT just pricing tiers)
- Extract the variant name EXACTLY as shown on the page
- Extract description if available (often a short summary under the variant name)
- Extract price if shown. Use the currency shown on the page. If no price visible, set price to null
- Extract duration_minutes if it differs per variant. If same as main activity or not shown, set to null
- Extract what's included per variant in the "includes" array
- Extract what's excluded per variant in the "excludes" array
- Mark is_default: true for the pre-selected or first/primary option
- If only ONE option exists with no alternatives, return an empty array
- If the page shows "Select a date to see options" but lists option NAMES, still extract those names
- Do NOT fabricate variants — only extract what's visible on the page
- Return ONLY valid JSON, no markdown fences or extra text
- If no variants/options are found at all, return {"tour_variants": []}"""


def _extract_json(text: str) -> dict | None:
    """Robustly extract JSON object from text that may contain extra content."""
    text = text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _identify_source(url: str) -> str:
    """Identify the booking platform from URL."""
    url_lower = url.lower()
    if "viator.com" in url_lower:
        return "Viator"
    elif "getyourguide.com" in url_lower:
        return "GetYourGuide"
    elif "tripadvisor.com" in url_lower:
        return "TripAdvisor"
    elif "klook.com" in url_lower:
        return "Klook"
    return "Unknown"


async def _extract_from_markdown(markdown: str) -> dict | None:
    """Use Claude to extract tour variants from markdown content."""
    try:
        source_hint = ""
        if "viator" in markdown.lower()[:500]:
            source_hint = "\nThis is a Viator page. Look for 'Choose an option' or 'Select option' sections with different tour packages."
        elif "getyourguide" in markdown.lower()[:500]:
            source_hint = "\nThis is a GetYourGuide page. Look for 'Options' or 'Select your option' sections."

        response_text = await claude_client.generate(
            prompt=f"Extract tour variants/options from this booking page:{source_hint}\n\n{markdown}",
            system=TOUR_VARIANTS_EXTRACTION_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            temperature=0.1,
        )

        data = _extract_json(response_text)
        if data is None:
            logger.warning("Claude returned unparseable response for tour variants")
        return data

    except Exception as exc:
        logger.warning("Tour variants extraction from markdown failed: %s", exc)
        return None


def _has_variants(data: dict | None) -> bool:
    """Check if extracted data contains meaningful variant info."""
    if not data:
        return False
    variants = data.get("tour_variants", [])
    return isinstance(variants, list) and len(variants) > 0


async def _extract_variants_from_url(url: str) -> dict | None:
    """Scrape a URL and extract tour variants. Jina first, then Apify fallback."""

    # --- Attempt 1: Jina Reader ---
    try:
        markdown = await jina_client.clean_page(url)
        if markdown and len(markdown) >= 100:
            data = await _extract_from_markdown(markdown[:15000])
            if _has_variants(data):
                logger.info("Jina+Claude extracted variants from %s", url)
                return data
    except Exception as exc:
        logger.warning("Jina failed for variants %s: %s", url, exc)

    # --- Attempt 2: Apify ---
    try:
        result = await apify_client.scrape_url(url)
        if result.get("success") and result.get("markdown"):
            markdown = result["markdown"]
            if len(markdown) >= 100:
                data = await _extract_from_markdown(markdown[:15000])
                if _has_variants(data):
                    logger.info("Apify+Claude extracted variants from %s", url)
                    return data
    except Exception as exc:
        logger.warning("Apify failed for variants %s: %s", url, exc)

    return None


async def scrape_variants_for_activity(
    db: AsyncSession,
    activity_id: UUID,
) -> dict:
    """Scrape tour variants from source URLs for an activity."""
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    source_urls = activity.source_urls or []
    if not source_urls:
        if activity.source_url:
            source_urls = [activity.source_url]
        else:
            return {"activity_id": str(activity_id), "message": "No source URLs", "updated": False}

    # Try each source URL
    variants_data = None
    used_url = None
    for url in source_urls[:3]:
        variants_data = await _extract_variants_from_url(url)
        if _has_variants(variants_data):
            used_url = url
            break

    if not variants_data or not _has_variants(variants_data):
        return {
            "activity_id": str(activity_id),
            "message": "No tour variants found in any source URL",
            "urls_tried": source_urls[:3],
            "updated": False,
        }

    new_variants = variants_data.get("tour_variants", [])
    old_variants = activity.tour_variants or []

    # Update if different
    old_names = sorted([v.get("name", "") for v in old_variants]) if old_variants else []
    new_names = sorted([v.get("name", "") for v in new_variants])

    if new_names != old_names:
        activity.tour_variants = new_variants
        return {
            "activity_id": str(activity_id),
            "url": used_url,
            "updated": True,
            "old_count": len(old_variants),
            "new_count": len(new_variants),
            "variants": [v.get("name") for v in new_variants],
        }

    return {
        "activity_id": str(activity_id),
        "url": used_url,
        "updated": False,
        "message": "Variants unchanged",
        "count": len(new_variants),
    }


async def bulk_scrape_variants(
    db: AsyncSession,
    city: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Scrape tour variants for multiple activities."""
    query = select(Activity).where(Activity.source_urls.isnot(None))
    if city:
        query = query.where(Activity.city.ilike(city))
    query = query.order_by(Activity.name).offset(offset).limit(limit)

    result = await db.execute(query)
    activities = list(result.scalars().all())

    results = []
    updated_count = 0
    failed_count = 0

    for activity in activities:
        source_urls = activity.source_urls or []
        if not source_urls:
            continue

        try:
            variants_data = None
            for url in source_urls[:3]:
                variants_data = await _extract_variants_from_url(url)
                if _has_variants(variants_data):
                    break

            if not variants_data or not _has_variants(variants_data):
                failed_count += 1
                results.append({
                    "activity_id": str(activity.id),
                    "name": activity.name,
                    "status": "no_variants",
                })
                continue

            new_variants = variants_data.get("tour_variants", [])
            activity.tour_variants = new_variants
            updated_count += 1

            results.append({
                "activity_id": str(activity.id),
                "name": activity.name,
                "status": "updated",
                "count": len(new_variants),
                "variants": [v.get("name") for v in new_variants],
            })

        except Exception as exc:
            failed_count += 1
            results.append({
                "activity_id": str(activity.id),
                "name": activity.name,
                "status": "error",
                "message": str(exc),
            })

        await asyncio.sleep(0.5)

    return {
        "processed": len(activities),
        "updated": updated_count,
        "failed": failed_count,
        "offset": offset,
        "limit": limit,
        "results": results,
    }
