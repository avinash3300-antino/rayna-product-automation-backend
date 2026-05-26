"""Availability service — scrape availability (start_times, operating_days) from source URLs."""

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

AVAILABILITY_EXTRACTION_PROMPT = """You are an availability data extraction specialist. Given web page content from a travel/booking site, \
extract the scheduling and availability information.

Return a JSON object with:
{
  "start_times": ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"],
  "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
}

CRITICAL RULES FOR START TIMES:
- Extract ALL start times / time slots shown on the page. Do NOT summarize or reduce them.
- If the page shows 8 time slots (e.g., 8:00 AM, 9:00 AM, 10:00 AM, 11:00 AM, 12:00 PM, 1:00 PM, 2:00 PM, 3:00 PM), return ALL 8 times.
- Convert to 24-hour HH:MM format: "8:00 AM" → "08:00", "1:00 PM" → "13:00", "3:00 PM" → "15:00"
- Look for time selectors, dropdowns, radio buttons, or lists showing available booking times
- Look for text like "Select time", "Choose a time slot", "Available times", "Departure times", "Tour starts at"
- If opening hours are shown as a range (e.g., "8:00 AM - 3:00 PM" or "Open 9am-5pm"), generate hourly slots from start to end (inclusive)
- If the page mentions specific departure/tour times (e.g., "Tours depart at 9am and 2pm"), extract those exact times
- NEVER skip or merge time slots — return every single one shown on the page

RULES FOR OPERATING DAYS:
- Use full names: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday
- If the page says "available daily", "every day", "daily", or lists no specific day restrictions, return all 7 days
- If the page says "weekdays only", return Monday through Friday
- If the page says "weekends only", return Saturday and Sunday
- If specific days are closed (e.g., "closed on Fridays"), return all days EXCEPT those
- Look for day selectors, calendar views, or text mentioning available days

GENERAL:
- Do NOT fabricate data — but DO infer operating days from context clues like "open daily except Friday"
- If truly no scheduling info is found, return empty arrays
- Return ONLY valid JSON, no markdown fences or extra text"""


def _extract_json(text: str) -> dict | None:
    """Robustly extract JSON object from text that may contain extra content."""
    text = text.strip()

    # Strip markdown fences
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

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first { and last } — extract just the JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


async def _extract_from_markdown(markdown: str) -> dict | None:
    """Use Claude to extract availability from markdown content."""
    try:
        response_text = await claude_client.generate(
            prompt=f"Extract availability/scheduling information from this booking page:\n\n{markdown}",
            system=AVAILABILITY_EXTRACTION_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            temperature=0.1,
        )

        data = _extract_json(response_text)
        if data is None:
            logger.warning("Claude returned unparseable response for availability")
        return data

    except Exception as exc:
        logger.warning("Availability extraction from markdown failed: %s", exc)
        return None


def _has_availability(data: dict | None) -> bool:
    """Check if extracted data contains meaningful availability info."""
    if not data:
        return False
    return bool(data.get("start_times")) or bool(data.get("operating_days"))


async def _extract_availability_from_url(url: str) -> dict | None:
    """Scrape a URL and extract availability. Tries Jina first, then Apify as fallback."""

    # --- Attempt 1: Jina Reader (fast, static content) ---
    try:
        markdown = await jina_client.clean_page(url)
        if markdown and len(markdown) >= 100:
            data = await _extract_from_markdown(markdown[:10000])
            if _has_availability(data):
                logger.info("Jina+Claude extracted availability from %s", url)
                return data
            logger.info("Jina returned content but no availability found for %s, trying Apify...", url)
        else:
            logger.info("Jina returned too little content for %s, trying Apify...", url)
    except Exception as exc:
        logger.warning("Jina failed for %s: %s, trying Apify...", url, exc)

    # --- Attempt 2: Apify (JavaScript-rendered content) ---
    try:
        result = await apify_client.scrape_url(url)
        if result.get("success") and result.get("markdown"):
            markdown = result["markdown"]
            if len(markdown) >= 100:
                data = await _extract_from_markdown(markdown[:10000])
                if _has_availability(data):
                    logger.info("Apify+Claude extracted availability from %s", url)
                    return data
                logger.info("Apify returned content but no availability found for %s", url)
            else:
                logger.warning("Apify returned too little content for %s", url)
        else:
            logger.warning("Apify scrape failed for %s", url)
    except Exception as exc:
        logger.warning("Apify failed for %s: %s", url, exc)

    return None


async def scrape_availability_for_activity(
    db: AsyncSession,
    activity_id: UUID,
) -> dict:
    """Scrape availability from source URLs for an activity.
    Tries each source URL until one returns valid availability data.
    """
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    source_urls = activity.source_urls or []
    if not source_urls:
        if activity.source_url:
            source_urls = [activity.source_url]
        else:
            return {
                "activity_id": str(activity_id),
                "message": "No source URLs",
                "updated": False,
            }

    # Try each source URL until we get availability data
    availability_data = None
    used_url = None
    for url in source_urls[:3]:
        availability_data = await _extract_availability_from_url(url)
        if _has_availability(availability_data):
            used_url = url
            break

    if not availability_data or not _has_availability(availability_data):
        return {
            "activity_id": str(activity_id),
            "message": "Could not extract availability from any source URL (tried Jina + Apify)",
            "urls_tried": source_urls[:3],
            "updated": False,
        }

    new_start_times = availability_data.get("start_times", [])
    new_operating_days = availability_data.get("operating_days", [])

    old_start_times = activity.start_times or []
    old_operating_days = activity.operating_days or []

    updated_fields = []

    if new_start_times and sorted(new_start_times) != sorted(old_start_times):
        activity.start_times = new_start_times
        updated_fields.append("start_times")

    if new_operating_days and sorted(new_operating_days) != sorted(old_operating_days):
        activity.operating_days = new_operating_days
        updated_fields.append("operating_days")

    return {
        "activity_id": str(activity_id),
        "url": used_url,
        "updated": len(updated_fields) > 0,
        "updated_fields": updated_fields,
        "old": {"start_times": old_start_times, "operating_days": old_operating_days},
        "new": {"start_times": new_start_times, "operating_days": new_operating_days},
    }


async def bulk_scrape_availability(
    db: AsyncSession,
    city: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Scrape availability for multiple activities. Processes sequentially to avoid rate limits.

    Uses Jina first (fast), falls back to Apify only when needed.
    """
    query = select(Activity).where(Activity.source_urls.isnot(None))
    if city:
        query = query.where(Activity.city.ilike(city))
    query = query.order_by(Activity.name).offset(offset).limit(limit)

    result = await db.execute(query)
    activities = list(result.scalars().all())

    total_query = select(Activity.id).where(Activity.source_urls.isnot(None))
    if city:
        total_query = total_query.where(Activity.city.ilike(city))
    total_result = await db.execute(total_query)
    total_count = len(total_result.all())

    results = []
    updated_count = 0
    failed_count = 0
    skipped_count = 0

    for activity in activities:
        source_urls = activity.source_urls or []
        if not source_urls:
            skipped_count += 1
            continue

        try:
            # Try each source URL until one returns data
            availability_data = None
            for url in source_urls[:3]:
                availability_data = await _extract_availability_from_url(url)
                if _has_availability(availability_data):
                    break

            if not availability_data:
                failed_count += 1
                results.append({
                    "activity_id": str(activity.id),
                    "name": activity.name,
                    "status": "failed",
                    "message": "No availability extracted",
                })
                continue

            new_start_times = availability_data.get("start_times", [])
            new_operating_days = availability_data.get("operating_days", [])

            old_start_times = activity.start_times or []
            old_operating_days = activity.operating_days or []

            changed = False
            if new_start_times and sorted(new_start_times) != sorted(old_start_times):
                activity.start_times = new_start_times
                changed = True
            if new_operating_days and sorted(new_operating_days) != sorted(old_operating_days):
                activity.operating_days = new_operating_days
                changed = True

            if changed:
                updated_count += 1

            results.append({
                "activity_id": str(activity.id),
                "name": activity.name,
                "status": "updated" if changed else "no_change",
                "old_times": old_start_times,
                "new_times": new_start_times,
                "old_days": old_operating_days,
                "new_days": new_operating_days,
            })

        except Exception as exc:
            failed_count += 1
            results.append({
                "activity_id": str(activity.id),
                "name": activity.name,
                "status": "error",
                "message": str(exc),
            })
            logger.warning("Bulk availability scrape failed for %s: %s", activity.name, exc)

        # Small delay between requests to be nice to APIs
        await asyncio.sleep(1)

    return {
        "total_activities": total_count,
        "processed": len(activities),
        "updated": updated_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "offset": offset,
        "limit": limit,
        "results": results,
    }
