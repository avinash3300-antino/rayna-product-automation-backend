"""Pricing service — scrape pricing from source URLs and convert to AED."""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.activities import Activity
from app.integrations.claude_client import claude_client
from app.integrations.jina_client import jina_client

logger = logging.getLogger(__name__)

# Approximate exchange rates to AED
EXCHANGE_RATES = {
    "AED": 1.0,
    "USD": 3.67,
    "GBP": 4.70,
    "EUR": 4.00,
    "INR": 0.044,
    "SAR": 0.98,
    "QAR": 1.01,
    "BHD": 9.74,
    "KWD": 11.97,
    "OMR": 9.53,
    "EGP": 0.075,
    "TRY": 0.11,
    "THB": 0.10,
}

PRICING_EXTRACTION_PROMPT = """You are a pricing data extraction specialist. Given web page content from a travel booking site, \
extract the current pricing information.

Return a JSON object with:
{
  "prices": [{"type": "adult"|"child"|"infant"|"group", "amount": number, "currency": "GBP"|"USD"|"EUR"|etc}],
  "price_from": number (lowest adult price),
  "currency": "string (3-letter ISO code as shown on page)",
  "price_type": "Per person"|"Per group"|"Per vehicle",
  "discount_pct": number or null,
  "original_price": number or null (pre-discount price if shown)
}

RULES:
- Extract EXACT prices as shown on the page — do NOT convert currencies
- If multiple pricing tiers exist, extract all of them
- Return ONLY valid JSON, no markdown fences or extra text
- If no prices found, return {"prices": [], "price_from": null, "currency": null}"""


def _identify_source(url: str) -> str:
    """Identify the booking platform from URL."""
    url_lower = url.lower()
    if "getyourguide" in url_lower:
        return "GetYourGuide"
    if "viator" in url_lower:
        return "Viator"
    if "tripadvisor" in url_lower:
        return "TripAdvisor"
    if "klook" in url_lower:
        return "Klook"
    if "tiqets" in url_lower:
        return "Tiqets"
    if "musement" in url_lower:
        return "Musement"
    return "Other"


def _convert_to_aed(amount: float, currency: str) -> float:
    """Convert a price to AED using stored exchange rates."""
    rate = EXCHANGE_RATES.get(currency.upper(), 1.0)
    return round(amount * rate, 2)


async def _extract_pricing_from_url(url: str) -> dict | None:
    """Scrape a single URL and extract pricing using Jina + Claude."""
    try:
        # Get page content via Jina
        markdown = await jina_client.clean_page(url)
        if not markdown or len(markdown) < 100:
            logger.warning("Jina returned too little content for %s", url)
            return None

        # Truncate to avoid token limits (pricing is usually near the top)
        markdown = markdown[:8000]

        # Extract pricing with Claude
        response_text = await claude_client.generate(
            prompt=f"Extract pricing from this booking page:\n\n{markdown}",
            system=PRICING_EXTRACTION_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            temperature=0.1,
        )

        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        return data

    except json.JSONDecodeError as exc:
        logger.warning("Claude returned invalid JSON for pricing from %s: %s", url, exc)
        return None
    except Exception as exc:
        logger.warning("Pricing extraction failed for %s: %s", url, exc)
        return None


async def scrape_pricing_for_activity(
    db: AsyncSession,
    activity_id: UUID,
) -> dict:
    """Scrape pricing from all source URLs for an activity."""
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    source_urls = activity.source_urls or []
    if not source_urls:
        return {"activity_id": str(activity_id), "message": "No source URLs", "scraped": 0}

    scraped_prices = []
    now = datetime.now(timezone.utc).isoformat()

    for url in source_urls[:3]:  # Limit to 3 URLs to avoid excessive API calls
        source = _identify_source(url)
        pricing_data = await _extract_pricing_from_url(url)

        if pricing_data and pricing_data.get("price_from") is not None:
            local_currency = pricing_data.get("currency", "USD")
            local_price = pricing_data["price_from"]
            aed_price = _convert_to_aed(local_price, local_currency)

            scraped_prices.append({
                "source": source,
                "url": url,
                "local_currency": local_currency,
                "local_price": local_price,
                "aed_price": aed_price,
                "prices": pricing_data.get("prices", []),
                "original_price": pricing_data.get("original_price"),
                "discount_pct": pricing_data.get("discount_pct"),
                "scraped_at": now,
            })

    # Update activity
    if scraped_prices:
        activity.scraped_prices = scraped_prices

        # Set local currency from first result
        first = scraped_prices[0]
        activity.local_currency = first["local_currency"]
        activity.price_local = first["local_price"]

        # Update price_from with the lowest AED price
        best_aed = min(p["aed_price"] for p in scraped_prices)
        activity.price_from = best_aed
        activity.currency = "AED"

    return {
        "activity_id": str(activity_id),
        "scraped": len(scraped_prices),
        "sources": [p["source"] for p in scraped_prices],
        "scraped_prices": scraped_prices,
    }
