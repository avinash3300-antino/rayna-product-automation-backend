import json
import logging
from uuid import UUID

import httpx
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, NotFoundError
from app.db.models.activities import Activity
from app.db.models.reviews import ActivityReview
from app.integrations.claude_client import claude_client
from app.integrations.jina_client import jina_client

logger = logging.getLogger(__name__)

SEARCHAPI_BASE = "https://www.searchapi.io/api/v1/search"

REVIEW_EXTRACTION_PROMPT = """You are a review extraction specialist. Given raw web page content, extract real user reviews.

Return a JSON array of review objects with these fields:
- reviewer_name (string — the reviewer's display name)
- rating (number 1-5 or null if not shown)
- review_title (string or null)
- review_text (string — the full review text, min 20 chars)
- review_date (string or null — as shown on page, e.g. "March 2024", "2 weeks ago")
- verified (boolean — true if marked as verified/certified)
- language (string — ISO 639-1 code, default "en")

RULES:
- Extract at most {max_reviews} reviews
- Only include reviews with meaningful text (20+ chars)
- Do NOT fabricate reviews or names. Only extract what's on the page.
- Return ONLY valid JSON array, no markdown fences.
- If no reviews found, return empty array: []"""


async def get_reviews_for_activity(
    db: AsyncSession,
    activity_id: UUID,
) -> dict:
    """Get all stored reviews for an activity."""
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    result = await db.execute(
        select(ActivityReview)
        .where(ActivityReview.activity_id == activity_id)
        .order_by(ActivityReview.rating.desc().nullslast(), ActivityReview.created_at.desc())
    )
    reviews = list(result.scalars().all())

    # Calculate stats
    ratings = [float(r.rating) for r in reviews if r.rating is not None]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    platform_counts: dict[str, int] = {}
    for r in reviews:
        platform_counts[r.source_platform] = platform_counts.get(r.source_platform, 0) + 1

    return {
        "activity_id": activity_id,
        "total": len(reviews),
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "platform_counts": platform_counts,
        "reviews": reviews,
    }


async def scrape_reviews_for_activity(
    db: AsyncSession,
    activity_id: UUID,
    platforms: list[str] | None = None,
) -> dict:
    """Scrape reviews from multiple platforms for an activity."""
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    if platforms is None:
        platforms = ["google", "tripadvisor", "trustpilot"]

    all_reviews: list[dict] = []
    errors: list[str] = []

    for platform in platforms:
        try:
            if platform == "google":
                reviews = await _scrape_google_reviews(activity, max_reviews=10)
            elif platform == "tripadvisor":
                reviews = await _scrape_tripadvisor_reviews(activity, max_reviews=10)
            elif platform == "trustpilot":
                reviews = await _scrape_trustpilot_reviews(activity, max_reviews=10)
            else:
                continue

            for r in reviews:
                r["source_platform"] = platform
            all_reviews.extend(reviews)
            logger.info(
                "Scraped %d reviews from %s for '%s'",
                len(reviews), platform, activity.name,
            )
        except Exception as exc:
            logger.warning(
                "Failed to scrape %s reviews for '%s': %s",
                platform, activity.name, exc,
            )
            errors.append(f"{platform}: {exc}")

    # Filter out reviews with missing required fields
    all_reviews = [
        r for r in all_reviews
        if r.get("review_text") and len(r.get("review_text", "")) >= 10
    ]

    # Delete existing reviews and insert new ones
    if all_reviews:
        await db.execute(
            delete(ActivityReview).where(ActivityReview.activity_id == activity_id)
        )

        for r in all_reviews:
            review = ActivityReview(
                activity_id=activity_id,
                reviewer_name=r.get("reviewer_name") or "Anonymous",
                rating=r.get("rating"),
                review_title=r.get("review_title"),
                review_text=r.get("review_text", "")[:5000],
                review_date=r.get("review_date"),
                source_platform=r.get("source_platform", "unknown"),
                source_url=r.get("source_url"),
                verified=bool(r.get("verified", False)),
                language=r.get("language") or "en",
            )
            db.add(review)

        # Update activity review stats
        ratings = [r["rating"] for r in all_reviews if r.get("rating")]
        if ratings:
            activity.rating = round(sum(ratings) / len(ratings), 2)
            activity.review_count = len(all_reviews)

            # Rating distribution
            activity.rating_5 = sum(1 for x in ratings if x >= 4.5)
            activity.rating_4 = sum(1 for x in ratings if 3.5 <= x < 4.5)
            activity.rating_3 = sum(1 for x in ratings if x < 3.5)

            # Review snippets (top 5 short reviews)
            snippets = []
            for r in sorted(all_reviews, key=lambda x: x.get("rating", 0) or 0, reverse=True):
                text = r.get("review_text", "")
                if len(text) > 20:
                    snippets.append(text[:200])
                if len(snippets) >= 5:
                    break
            activity.review_snippets = snippets

        await db.flush()

    return {
        "activity_id": activity_id,
        "total_scraped": len(all_reviews),
        "platforms": {p: sum(1 for r in all_reviews if r.get("source_platform") == p) for p in platforms},
        "errors": errors,
    }


# ── Google Reviews (via SearchAPI) ───────────────────────────────────────


async def _scrape_google_reviews(activity: Activity, max_reviews: int = 10) -> list[dict]:
    """Scrape Google Maps reviews using SearchAPI."""
    # Step 1: Find the place on Google Maps
    query = f"{activity.name} {activity.city} {activity.country}"
    data_id = await _find_google_place(query)
    if not data_id:
        logger.info("No Google Maps place found for '%s'", activity.name)
        return []

    # Step 2: Get reviews for this place
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                SEARCHAPI_BASE,
                params={
                    "engine": "google_maps_reviews",
                    "data_id": data_id,
                    "api_key": settings.SEARCHAPI_KEY,
                    "num": max_reviews,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("SearchAPI google_maps_reviews failed: %s", exc)
        return []

    reviews = []
    for r in data.get("reviews", [])[:max_reviews]:
        text = r.get("snippet", "") or r.get("text", "")
        if not text or len(text) < 20:
            continue
        reviews.append({
            "reviewer_name": r.get("user", {}).get("name", "Google User"),
            "reviewer_avatar_url": r.get("user", {}).get("thumbnail"),
            "rating": r.get("rating"),
            "review_title": None,
            "review_text": text,
            "review_date": r.get("date"),
            "verified": r.get("is_local_guide", False),
            "language": "en",
            "source_url": r.get("link"),
        })
    return reviews


async def _find_google_place(query: str) -> str | None:
    """Search Google Maps for a place and return its data_id."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                SEARCHAPI_BASE,
                params={
                    "engine": "google_maps",
                    "q": query,
                    "api_key": settings.SEARCHAPI_KEY,
                },
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("local_results", [])
        if results:
            return results[0].get("data_id")
        return None
    except Exception as exc:
        logger.warning("Google Maps search failed for '%s': %s", query, exc)
        return None


# ── TripAdvisor Reviews (via Jina + Claude) ──────────────────────────────


async def _scrape_tripadvisor_reviews(activity: Activity, max_reviews: int = 10) -> list[dict]:
    """Find TripAdvisor page and extract reviews with Jina + Claude."""
    # Find TripAdvisor page via SearchAPI
    query = f"site:tripadvisor.com {activity.name} {activity.city}"
    url = await _find_review_page(query, "tripadvisor.com")
    if not url:
        logger.info("No TripAdvisor page found for '%s'", activity.name)
        return []

    return await _extract_reviews_from_url(url, "tripadvisor", max_reviews)


# ── Trustpilot Reviews (via Jina + Claude) ───────────────────────────────


async def _scrape_trustpilot_reviews(activity: Activity, max_reviews: int = 10) -> list[dict]:
    """Find Trustpilot page and extract reviews with Jina + Claude."""
    # For Trustpilot, search for the operator name or activity
    operator = activity.operator_name or activity.name
    query = f"site:trustpilot.com {operator} {activity.city}"
    url = await _find_review_page(query, "trustpilot.com")
    if not url:
        logger.info("No Trustpilot page found for '%s'", activity.name)
        return []

    return await _extract_reviews_from_url(url, "trustpilot", max_reviews)


# ── Shared Helpers ───────────────────────────────────────────────────────


async def _find_review_page(query: str, domain: str) -> str | None:
    """Search for a review page URL on a specific domain."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                SEARCHAPI_BASE,
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": settings.SEARCHAPI_KEY,
                    "num": 3,
                },
            )
            response.raise_for_status()
            data = response.json()

        for result in data.get("organic_results", []):
            url = result.get("link", "")
            if domain in url:
                return url
        return None
    except Exception as exc:
        logger.warning("Search for %s page failed: %s", domain, exc)
        return None


async def _extract_reviews_from_url(
    url: str, platform: str, max_reviews: int = 10
) -> list[dict]:
    """Read a review page with Jina and extract reviews with Claude."""
    try:
        page_content = await jina_client.clean_page(url)
        page_content = jina_client.clean_markdown(page_content)
    except Exception as exc:
        logger.warning("Jina failed to read %s: %s", url, exc)
        return []

    if not page_content or len(page_content) < 100:
        return []

    # Truncate to fit in Claude context
    page_content = page_content[:15000]

    prompt = f"""Extract reviews from this {platform} page.

Page URL: {url}

Page Content:
{page_content}

Extract up to {max_reviews} real reviews with rating, reviewer name, review text, and date."""

    try:
        response_text = await claude_client.generate(
            prompt=prompt,
            system=REVIEW_EXTRACTION_PROMPT.format(max_reviews=max_reviews),
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.1,
        )

        # Parse JSON — handle markdown fences
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        reviews = json.loads(text)
        if not isinstance(reviews, list):
            return []

        # Add source URL to each review
        for r in reviews:
            r["source_url"] = url

        return reviews[:max_reviews]

    except json.JSONDecodeError as exc:
        logger.warning("Claude returned invalid JSON for %s reviews: %s", platform, exc)
        return []
    except Exception as exc:
        logger.warning("Claude review extraction failed for %s: %s", platform, exc)
        return []
