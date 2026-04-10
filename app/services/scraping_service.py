import json
import logging
from datetime import datetime, timezone

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ExternalServiceError
from app.db.models.activities import Activity
from app.db.models.scraping import ScrapeJob, ScrapeSource
from app.integrations.apify_client import apify_client
from app.integrations.claude_client import claude_client
from app.integrations.jina_client import jina_client
from app.integrations.playwright_scraper import playwright_scraper
from app.services.dedup_service import check_duplicate, compute_dedupe_hash

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a data extraction specialist for travel activities.
Given a cleaned markdown page, extract ALL travel activities/tours/experiences as a JSON array.
Each item MUST have these fields (return null if not found — NEVER fabricate):

CORE IDENTITY:
- name (string, required — full display title)
- description_short (2-3 sentences, 150-200 characters)
- description_long (full description if available, 300-600 words)
- category (Adventure, Cultural, Water Sports, Nature, Day Trip, Wellness, Entertainment)
- sub_category (string or null — e.g. "Snorkeling", "Museum Tour", "Cooking Class")
- activity_type (Group tour, Private tour, Self-guided, Transfer-included)

PRICING:
- price_adult (number or null)
- price_child (number or null — child ticket price if listed, typically age 3-11)
- price_original (number or null — original pre-discount price if strikethrough shown)
- currency (3-letter ISO code — detect from page symbols: £=GBP, $=USD, €=EUR, د.إ=AED)
- price_type (Per person, Per group, Per vehicle — default "Per person")
- discount_pct (number 0-100 or null — percentage discount if shown)

BOOKING & AVAILABILITY:
- duration_minutes (integer or null)
- free_cancellation (boolean — true if "free cancellation" mentioned anywhere)
- instant_confirmation (boolean — true if "instant confirmation" or "instant booking" mentioned)
- cancellation_hours (integer or null — hours before start for free cancellation, e.g. 24)
- start_times (array of time strings like "09:00", "14:00" or null)
- operating_days (array of day names like "Mon","Tue","Wed" or null)
- min_age (integer or null — minimum age requirement)

LOCATION:
- address (string or null — full street address)
- meeting_point_name (string or null — e.g. "Main entrance of Tower of London")
- meeting_point_desc (string or null — directions to meeting point)
- pickup_available (boolean — true if hotel/location pickup is mentioned)
- hotel_pickup_included (boolean — true if hotel pickup is specifically included free)

REVIEWS:
- rating (number 0-5 or null)
- review_count (integer or null)

CONTENT:
- highlights (array of 4-8 strings or null)
- included (array of strings or null — what's included)
- excluded (array of strings or null — what's not included)

OTHER:
- languages (array of ISO codes like "en","fr" or null)
- operator_name (string or null — company running the activity)
- source_url (string or null — URL of this specific activity page)
- cover_image_url (string or null — URL of the main hero/cover image on the page)

Return ONLY a valid JSON array. If no activities found, return []."""


async def scrape_source(source: ScrapeSource) -> list[dict]:
    """Scrape a source URL and return cleaned markdown pages.

    Strategy: Apify first → Playwright fallback → Jina clean.
    Returns list of {url, clean_markdown, source_type} dicts.
    """
    url = source.source_url
    source_type = "apify"

    try:
        # Attempt 1: Apify crawl
        pages = await apify_client.crawl_site(url, max_pages=50)
        results = []
        for page in pages:
            markdown = page.get("markdown", "")
            if markdown:
                clean = jina_client.clean_markdown(markdown)
                results.append(
                    {
                        "url": page.get("url", url),
                        "clean_markdown": clean,
                        "source_type": "apify",
                    }
                )
        if results:
            return results
    except Exception as exc:
        logger.warning(
            "Apify crawl failed for %s: %s. Falling back to Playwright.",
            url,
            exc,
        )
        source_type = "playwright"

    # Attempt 2: Playwright fallback
    try:
        html = await playwright_scraper.scrape_url(url)
        # Clean via Jina
        try:
            clean_md = await jina_client.clean_page(url)
            clean_md = jina_client.clean_markdown(clean_md)
        except Exception:
            clean_md = html[:20000]  # Raw HTML as last resort

        return [
            {
                "url": url,
                "clean_markdown": clean_md,
                "source_type": "playwright",
            }
        ]
    except Exception as exc:
        logger.error("All scraping methods failed for %s: %s", url, exc)
        raise ExternalServiceError(
            f"All scraping methods failed for {url}"
        )


async def extract_activities(
    clean_markdown: str,
    source_url: str,
) -> list[dict]:
    """Use Claude to extract activity data from cleaned markdown."""
    prompt = f"""Source URL: {source_url}

Page content:
{clean_markdown[:12000]}

Extract all travel activities, tours, or experiences from this page."""

    try:
        response_text = await claude_client.generate(
            prompt=prompt,
            system=EXTRACTION_SYSTEM_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            temperature=0.2,
        )

        # Parse JSON (handle markdown fences if Claude wraps them)
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Truncated response — recover complete objects from the array
            last_brace = text.rfind("}")
            if last_brace > 0:
                truncated = text[: last_brace + 1] + "]"
                try:
                    result = json.loads(truncated)
                    logger.warning(
                        "Recovered %d activities from truncated JSON for %s",
                        len(result),
                        source_url,
                    )
                    return result
                except json.JSONDecodeError:
                    pass
            logger.error(
                "Claude returned invalid JSON for extraction from %s",
                source_url,
            )
            return []
    except Exception as exc:
        logger.error("Extraction failed for %s: %s", source_url, exc)
        return []


def _infer_currency(country_name: str) -> str:
    """Infer currency from country name when extraction didn't get it."""
    mapping = {
        "united kingdom": "GBP", "england": "GBP", "uk": "GBP",
        "united states": "USD", "usa": "USD",
        "united arab emirates": "AED", "uae": "AED",
        "france": "EUR", "germany": "EUR", "italy": "EUR", "spain": "EUR",
        "netherlands": "EUR", "portugal": "EUR", "greece": "EUR",
        "thailand": "THB", "japan": "JPY", "turkey": "TRY",
        "india": "INR", "australia": "AUD", "singapore": "SGD",
        "malaysia": "MYR", "indonesia": "IDR",
        "egypt": "EGP", "oman": "OMR", "saudi arabia": "SAR",
        "qatar": "QAR", "bahrain": "BHD",
    }
    return mapping.get(country_name.lower().strip(), "USD")


async def save_extracted_activities(
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
        description = item.get("description_short") or ""

        # Dedup check
        dedup_result = await check_duplicate(
            db, name, city, category, description
        )
        if dedup_result["is_duplicate"]:
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
            description_short=item.get("description_short") or name,
            description_long=item.get("description_long") or "",
            highlights=item.get("highlights") or [],
            included=item.get("included") or [],
            excluded=item.get("excluded") or [],
            price_adult=item.get("price_adult") or 0,
            price_child=item.get("price_child"),
            price_original=item.get("price_original"),
            currency=item.get("currency") or _infer_currency(country_name),
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
            source_type=job.scrape_type,
            operator_name=item.get("operator_name"),
            dedup_hash=compute_dedupe_hash(name, city, category),
            quality_score=0,
            rating=item.get("rating"),
            review_count=item.get("review_count") or 0,
        )
        db.add(activity)
        counts["saved"] += 1

    await db.flush()
    return counts
