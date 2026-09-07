"""Review service — shared across all product types."""

import json
import logging
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.db.models.activities import Activity
from app.db.models.cruises import CruiseProduct
from app.db.models.reviews import ProductReview
from app.integrations.claude_client import claude_client
from app.integrations.gemini_client import gemini_client
from app.integrations.jina_client import jina_client

logger = logging.getLogger(__name__)

SEARCHAPI_BASE = "https://www.searchapi.io/api/v1/search"

# Maps product_type → SQLAlchemy model
MODEL_REGISTRY: dict[str, type] = {
    "activities": Activity,
    "cruises": CruiseProduct,
}

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
- If no reviews found, return empty array: []

CONTENT SAFETY (these reviews are published on raynatours.com):
- SKIP any review whose text mentions a third-party booking platform or OTA brand by name. Forbidden brands include (case-insensitive): Viator, GetYourGuide, GYG, TripAdvisor, Trustpilot, Booking.com, Booking, Klook, Tiqets, Civitatis, Expedia, Tours4Fun, Headout, Musement, Airbnb Experiences, Tiqet.
- SKIP reviews that read like a review of the booking platform itself ("the website was easy", "customer service responded quickly") rather than the tour/experience.
- Do not extract reviewer_name values that are clearly the platform name."""


def _get_model(product_type: str):
    model = MODEL_REGISTRY.get(product_type)
    if model is None:
        raise ValueError(f"Unknown product_type '{product_type}' for reviews")
    return model


async def get_reviews_for_product(
    db: AsyncSession,
    product_id: UUID,
    product_type: str = "activities",
) -> dict:
    """Get all stored reviews for a product."""
    model = _get_model(product_type)
    product = await db.get(model, product_id)
    if not product:
        raise NotFoundError(f"{product_type} product not found")

    result = await db.execute(
        select(ProductReview)
        .where(
            ProductReview.product_type == product_type,
            ProductReview.product_id == product_id,
        )
        .order_by(ProductReview.rating.desc().nullslast(), ProductReview.created_at.desc())
    )
    reviews = list(result.scalars().all())

    ratings = [float(r.rating) for r in reviews if r.rating is not None]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    platform_counts: dict[str, int] = {}
    for r in reviews:
        platform_counts[r.source_platform] = platform_counts.get(r.source_platform, 0) + 1

    return {
        "product_id": product_id,
        "product_type": product_type,
        "total": len(reviews),
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "platform_counts": platform_counts,
        "reviews": reviews,
    }


async def scrape_reviews_for_product(
    db: AsyncSession,
    product_id: UUID,
    product_type: str = "activities",
    product_name: str | None = None,
    product_city: str | None = None,
    product_country: str | None = None,
    operator_name: str | None = None,
    platforms: list[str] | None = None,
) -> dict:
    """Scrape reviews from multiple platforms for any product type."""
    model = _get_model(product_type)
    product = await db.get(model, product_id)
    if not product:
        raise NotFoundError(f"{product_type} product not found")

    # Use product attrs if not explicitly passed
    name = product_name or product.name
    city = product_city or product.city
    country = product_country or product.country
    op_name = operator_name or getattr(product, "operator_name", None)

    if platforms is None:
        platforms = ["google", "tripadvisor", "trustpilot"]

    all_reviews: list[dict] = []
    errors: list[str] = []

    for platform in platforms:
        try:
            if platform == "google":
                reviews = await _scrape_google_reviews(name, city, country, max_reviews=10)
            elif platform == "tripadvisor":
                reviews = await _scrape_tripadvisor_reviews(name, city, max_reviews=10)
            elif platform == "trustpilot":
                reviews = await _scrape_trustpilot_reviews(op_name or name, city, max_reviews=10)
            else:
                continue

            for r in reviews:
                r["source_platform"] = platform
            all_reviews.extend(reviews)
            logger.info(
                "Scraped %d reviews from %s for '%s'",
                len(reviews), platform, name,
            )
        except Exception as exc:
            logger.warning(
                "Failed to scrape %s reviews for '%s': %s",
                platform, name, exc,
            )
            errors.append(f"{platform}: {exc}")

    # Filter
    all_reviews = [
        r for r in all_reviews
        if r.get("review_text") and len(r.get("review_text", "")) >= 10
    ]

    # Delete existing reviews and insert new ones
    if all_reviews:
        await db.execute(
            delete(ProductReview).where(
                ProductReview.product_type == product_type,
                ProductReview.product_id == product_id,
            )
        )

        for r in all_reviews:
            review = ProductReview(
                product_type=product_type,
                product_id=product_id,
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

        # Update product review stats
        ratings = [r["rating"] for r in all_reviews if r.get("rating")]
        if ratings:
            product.rating = round(sum(ratings) / len(ratings), 2)
            product.review_count = len(all_reviews)

            product.rating_5 = sum(1 for x in ratings if x >= 4.5)
            product.rating_4 = sum(1 for x in ratings if 3.5 <= x < 4.5)
            product.rating_3 = sum(1 for x in ratings if x < 3.5)
            if hasattr(product, "rating_2"):
                product.rating_2 = 0
            if hasattr(product, "rating_1"):
                product.rating_1 = 0

            # Review snippets (top 5 short reviews)
            snippets = []
            for r in sorted(all_reviews, key=lambda x: x.get("rating", 0) or 0, reverse=True):
                text = r.get("review_text", "")
                if len(text) > 20:
                    snippets.append(text[:200])
                if len(snippets) >= 5:
                    break
            product.review_snippets = snippets

        await db.flush()

    return {
        "product_id": product_id,
        "product_type": product_type,
        "total_scraped": len(all_reviews),
        "platforms": {p: sum(1 for r in all_reviews if r.get("source_platform") == p) for p in platforms},
        "errors": errors,
    }


# ── Backward compatibility aliases ──────────────────────────────────────


async def get_reviews_for_activity(db: AsyncSession, activity_id: UUID) -> dict:
    return await get_reviews_for_product(db, activity_id, product_type="activities")


async def scrape_reviews_for_activity(
    db: AsyncSession,
    activity_id: UUID,
    platforms: list[str] | None = None,
) -> dict:
    return await scrape_reviews_for_product(
        db, activity_id, product_type="activities", platforms=platforms,
    )


# ── Google Reviews (via SearchAPI) ───────────────────────────────────────


async def _scrape_google_reviews(
    product_name: str,
    city: str,
    country: str,
    max_reviews: int = 10,
) -> list[dict]:
    """Scrape Google Maps reviews using SearchAPI, paginated up to max_reviews.

    SearchAPI's google_maps_reviews endpoint returns up to ~8 reviews per call.
    We paginate via next_page_token until we reach max_reviews or run out.
    """
    query = f"{product_name} {city} {country}"
    data_id = await _find_google_place(query)
    if not data_id:
        logger.info("No Google Maps place found for '%s'", product_name)
        return []

    collected: list[dict] = []
    next_token: str | None = None
    max_pages = 6  # 6 pages * ~8 = ~48 max
    seen_texts: set[str] = set()

    for page in range(max_pages):
        params: dict = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": settings.SEARCHAPI_KEY,
        }
        if next_token:
            params["next_page_token"] = next_token

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(SEARCHAPI_BASE, params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            if page == 0:
                logger.warning("SearchAPI google_maps_reviews failed: %s", exc)
            break

        raw = data.get("reviews", []) or []
        for r in raw:
            text = r.get("snippet", "") or r.get("text", "")
            if not text or len(text) < 20:
                continue
            key = text[:120]
            if key in seen_texts:
                continue
            seen_texts.add(key)
            collected.append({
                "reviewer_name": (r.get("user") or {}).get("name", "Google User"),
                "reviewer_avatar_url": (r.get("user") or {}).get("thumbnail"),
                "rating": r.get("rating"),
                "review_title": None,
                "review_text": text,
                "review_date": r.get("date"),
                "verified": bool(r.get("is_local_guide", False)),
                "language": "en",
                "source_url": r.get("link"),
            })
            if len(collected) >= max_reviews:
                return collected

        next_token = (data.get("pagination") or {}).get("next_page_token") or data.get("next_page_token")
        if not next_token:
            break

    return collected


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


async def _scrape_tripadvisor_reviews(
    product_name: str,
    city: str,
    max_reviews: int = 10,
    provider: str = "claude",
) -> list[dict]:
    """Find TripAdvisor page and extract reviews."""
    query = f"site:tripadvisor.com {product_name} {city}"
    url = await _find_review_page(query, "tripadvisor.com")
    if not url:
        logger.info("No TripAdvisor page found for '%s'", product_name)
        return []
    return await _extract_reviews_from_url(url, "tripadvisor", max_reviews, provider=provider)


# ── Trustpilot Reviews (via Jina + Claude) ───────────────────────────────


async def _scrape_trustpilot_reviews(
    operator_or_name: str,
    city: str,
    max_reviews: int = 10,
    provider: str = "claude",
) -> list[dict]:
    """Find Trustpilot page and extract reviews."""
    query = f"site:trustpilot.com {operator_or_name} {city}"
    url = await _find_review_page(query, "trustpilot.com")
    if not url:
        logger.info("No Trustpilot page found for '%s'", operator_or_name)
        return []
    return await _extract_reviews_from_url(url, "trustpilot", max_reviews, provider=provider)


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
    url: str, platform: str, max_reviews: int = 10, provider: str = "claude"
) -> list[dict]:
    """Read a review page with Jina and extract reviews with an LLM.

    provider="claude" (default, uses Haiku 4.5) or "gemini" (uses gemini-flash-latest).
    """
    try:
        page_content = await jina_client.clean_page(url)
        page_content = jina_client.clean_markdown(page_content)
    except Exception as exc:
        logger.warning("Jina failed to read %s: %s", url, exc)
        return []

    if not page_content or len(page_content) < 100:
        return []

    # More context for a bigger review haul
    page_content = page_content[:25000]

    prompt = f"""Extract reviews from this {platform} page.

Page URL: {url}

Page Content:
{page_content}

Extract up to {max_reviews} real reviews with rating, reviewer name, review text, and date."""

    try:
        if provider == "gemini":
            response_text = await gemini_client.generate(
                prompt=prompt,
                system=REVIEW_EXTRACTION_PROMPT.format(max_reviews=max_reviews),
                model="gemini-flash-latest",
                max_tokens=16000,
                temperature=0.1,
            )
        else:
            response_text = await claude_client.generate(
                prompt=prompt,
                system=REVIEW_EXTRACTION_PROMPT.format(max_reviews=max_reviews),
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                temperature=0.1,
            )

        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        reviews = json.loads(text)
        if not isinstance(reviews, list):
            return []

        for r in reviews:
            r["source_url"] = url

        return reviews[:max_reviews]

    except json.JSONDecodeError as exc:
        # Try to salvage by truncating to last complete '}' before the error
        try:
            cutoff = text.rfind("},")
            if cutoff > 100:
                salvaged = text[: cutoff + 1] + "]"
                reviews = json.loads(salvaged)
                if isinstance(reviews, list):
                    for r in reviews:
                        r["source_url"] = url
                    logger.info("%s extraction salvaged %d reviews after JSON truncation", platform, len(reviews))
                    return reviews[:max_reviews]
        except Exception:
            pass
        logger.warning("LLM returned invalid JSON for %s reviews: %s", platform, exc)
        return []
    except Exception as exc:
        logger.warning("LLM review extraction failed for %s: %s", platform, exc)
        return []


# ── Review Enrichment (Claude rewrite) ───────────────────────────────────

ENRICH_SYSTEM_PROMPT = """You are a professional review editor for Rayna Tours (raynatours.com), a premium travel company. \
Rewrite the following user review to be more polished, grammatically correct, and professional \
while preserving the original sentiment, key facts, and rating context. \
Keep approximately the same length. Do NOT change the reviewer's opinion or add information \
not in the original.

CONTENT SAFETY (mandatory):
- REMOVE every mention of third-party booking platforms or OTA brands. Forbidden brands (case-insensitive): \
Viator, GetYourGuide, GYG, TripAdvisor, Trustpilot, Booking.com, Booking, Klook, Tiqets, Civitatis, \
Expedia, Tours4Fun, Headout, Musement, Airbnb Experiences.
- Replace brand references with generic phrasing: "I booked through Viator" → "I booked the tour"; \
"the GetYourGuide app" → "the booking confirmation"; "TripAdvisor said" → "reviews said".
- Do not introduce the name "Rayna Tours" either — keep the review platform-neutral.
- If after removing brand references the review becomes empty or meaningless, return the exact string \
"__SKIP__" so the caller knows to drop it.

Return ONLY the rewritten review text (or "__SKIP__"), nothing else."""


async def enrich_single_review(original_text: str, provider: str = "gemini") -> str | None:
    """Rewrite a single review.

    Returns:
      * str  — successful rewrite
      * None — model returned __SKIP__ (intentional drop)

    Raises on API failures (rate limit, credit depleted, network error) so
    callers can distinguish real skips from transient errors.
    provider="gemini" (default, cheap) or "claude" (Haiku 4.5).
    """
    prompt = f"Original review:\n\n{original_text}\n\nRewrite this review professionally:"
    if provider == "gemini":
        result = await gemini_client.generate(
            prompt=prompt,
            system=ENRICH_SYSTEM_PROMPT,
            model="gemini-flash-latest",
            max_tokens=1024,
            temperature=0.3,
            json_mode=False,  # plain-text enrichment, not JSON
        )
    else:
        result = await claude_client.generate(
            prompt=prompt,
            system=ENRICH_SYSTEM_PROMPT,
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0.3,
        )
    cleaned = (result or "").strip()
    if cleaned == "__SKIP__" or "__SKIP__" in cleaned[:20]:
        return None
    if not cleaned:
        # Empty output — treat as transient, not a skip
        raise RuntimeError("enrich returned empty text")
    return cleaned


async def enrich_reviews_for_product(
    db: AsyncSession,
    product_id: UUID,
    product_type: str = "activities",
) -> dict:
    """Enrich all un-enriched reviews for a product using Claude AI."""
    stmt = select(ProductReview).where(
        ProductReview.product_type == product_type,
        ProductReview.product_id == product_id,
        ProductReview.enriched_text.is_(None),
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()

    enriched_count = 0
    failed_count = 0

    for review in reviews:
        enriched = await enrich_single_review(review.review_text)
        if enriched:
            review.enriched_text = enriched
            enriched_count += 1
        else:
            failed_count += 1

    return {
        "product_id": str(product_id),
        "total_reviews": len(reviews),
        "enriched": enriched_count,
        "failed": failed_count,
    }
