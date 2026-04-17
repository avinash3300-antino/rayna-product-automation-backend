"""Geocoding service — resolve activity locations to lat/lng using Nominatim."""
import logging

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


async def geocode_activity(
    activity_name: str,
    city: str,
    country: str,
    address: str | None = None,
) -> dict:
    """Geocode an activity location using Nominatim (OpenStreetMap).

    Returns {"lat": float, "lng": float} or {"lat": 0, "lng": 0} on failure.
    """
    # Strip city prefix from activity name (e.g., "Cairo: Pyramids Tour" → "Pyramids Tour")
    clean_name = activity_name
    if ":" in clean_name:
        clean_name = clean_name.split(":", 1)[1].strip()

    # Build search queries in order of specificity
    queries = []
    if address and address.lower() != city.lower() and len(address) > len(city):
        queries.append(f"{address}, {city}, {country}")
    queries.append(f"{clean_name}, {city}, {country}")
    queries.append(f"{city}, {country}")  # Fallback to city center

    headers = {"User-Agent": "RaynaTours/1.0 (product-automation)"}

    for query in queries:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    NOMINATIM_URL,
                    params={"q": query, "format": "json", "limit": 1},
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            if data:
                lat = round(float(data[0]["lat"]), 6)
                lng = round(float(data[0]["lon"]), 6)
                return {"lat": lat, "lng": lng}

        except Exception as exc:
            logger.warning("Geocoding failed for '%s': %s", query, exc)

    logger.info("Geocoding returned no results for '%s'", activity_name)
    return {"lat": 0, "lng": 0}
