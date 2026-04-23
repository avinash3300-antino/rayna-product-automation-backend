import logging

from app.integrations.freepik_client import freepik_client
from app.integrations.pexels_client import pexels_client
from app.integrations.unsplash_client import unsplash_client
from app.services.s3_service import upload_from_url

logger = logging.getLogger(__name__)

MIN_GALLERY_IMAGES = 8


async def _search_freepik(query: str, limit: int) -> list[dict]:
    """Search Freepik, return results or empty list on failure."""
    try:
        return await freepik_client.search_images(query, limit=limit)
    except Exception as exc:
        logger.warning("Freepik search failed for '%s': %s", query, exc)
        return []


async def _search_pexels(query: str, limit: int) -> list[dict]:
    """Search Pexels, return results or empty list on failure."""
    try:
        return await pexels_client.search_images(query, limit=limit)
    except Exception as exc:
        logger.warning("Pexels search failed for '%s': %s", query, exc)
        return []


async def _search_unsplash(query: str, limit: int) -> list[dict]:
    """Search Unsplash, return results or empty list on failure."""
    try:
        return await unsplash_client.search_images(query, limit=limit)
    except Exception as exc:
        logger.warning("Unsplash search failed for '%s': %s", query, exc)
        return []


async def _search_all_sources(query: str, limit: int) -> list[dict]:
    """Search Freepik -> Pexels -> Unsplash, return first successful results."""
    # Try Freepik first
    results = await _search_freepik(query, limit)
    if results:
        return results

    # Fallback to Pexels
    results = await _search_pexels(query, limit)
    if results:
        return results

    # Fallback to Unsplash
    results = await _search_unsplash(query, limit)
    return results


async def fetch_and_upload_images(
    product_name: str,
    city: str,
    product_id: str,
    product_type: str = "activities",
    num_images: int = 8,
) -> list[dict]:
    """Search Freepik/Pexels/Unsplash -> upload to Cloudinary -> return image metadata.

    Tries multiple search queries with fallback across image providers
    to ensure minimum 8 images.
    Returns list of {url, alt_text, s3_key} dicts.
    """
    num_images = max(num_images, MIN_GALLERY_IMAGES)

    # Try progressively broader searches to get enough images
    search_queries = [
        f"{product_name} {city}",
        f"{product_name} tourism",
        f"{city} travel tourism",
    ]

    all_results: list[dict] = []
    seen_urls: set[str] = set()

    for query in search_queries:
        if len(all_results) >= num_images:
            break
        results = await _search_all_sources(query, limit=num_images)
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    if not all_results:
        return []

    gallery: list[dict] = []

    for i, img in enumerate(all_results[:num_images]):
        image_url = img.get("url", "")
        if not image_url:
            continue

        s3_key = f"{product_type}/{product_id}/gallery/{i}.webp"

        try:
            s3_url = await upload_from_url(
                source_url=image_url,
                key=s3_key,
                resize=(1200, 800),
            )

            gallery.append(
                {
                    "url": s3_url,
                    "alt_text": f"{product_name} - image {i + 1}",
                    "s3_key": s3_key,
                }
            )
        except Exception as exc:
            logger.warning(
                "Upload failed for image %d: %s", i, exc
            )
            continue

    return gallery
