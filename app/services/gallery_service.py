"""Gallery image scraping — extract image URLs from activity source pages."""
import logging
import re

from app.integrations.jina_client import jina_client
from app.integrations.playwright_scraper import playwright_scraper

logger = logging.getLogger(__name__)

# Patterns to skip (icons, logos, tracking pixels, tiny images)
SKIP_PATTERNS = (
    "favicon", "logo", "icon", "sprite", "pixel",
    "1x1", "tracking", "badge", "flag", "avatar",
    "data:image", "svg+xml", ".svg",
    "facebook.com", "twitter.com", "google.com/maps",
    "googletagmanager", "analytics", "ads",
    "app_download", "banner/app",
)

# Patterns that indicate high-quality gallery images
GOOD_PATTERNS = (
    "media/images", "media/photo", "photo-o/",
    "images/attractions", "images/tours",
    "/upload/", "/gallery/", "cdn-imgix",
    "cdn.getyourguide", "viator.com",
    "headout.com", "tacdn.com",
    "cloudinary.com", "imgix.net",
)


async def scrape_gallery_images(
    source_url: str,
    activity_name: str,
    max_images: int = 10,
) -> list[str]:
    """Scrape gallery image URLs from an activity's source page.

    Strategy: Jina first (handles anti-bot) → Playwright fallback.
    Returns a list of image URL strings.
    """
    if not source_url:
        return []

    image_urls = []

    # Strategy 1: Use Jina with images enabled
    try:
        markdown = await jina_client.clean_page(source_url, include_images=True)
        if markdown and len(markdown) > 200:
            image_urls = _extract_images_from_markdown(markdown)
            image_urls.extend(_extract_image_urls(markdown))
    except Exception as exc:
        logger.debug("Jina gallery fetch failed for %s: %s", source_url, exc)

    # Strategy 2: Playwright fallback if Jina didn't find enough
    if len(image_urls) < 3:
        try:
            html = await playwright_scraper.scrape_url(source_url, wait_ms=3000)
            if html and len(html) > 1000:
                pw_urls = _extract_image_urls(html)
                image_urls.extend(pw_urls)
        except Exception as exc:
            logger.debug("Playwright gallery fetch failed for %s: %s", source_url, exc)

    if not image_urls:
        return []

    # Score and rank images
    scored = []
    for url in image_urls:
        # Clean HTML entities
        url = url.replace("&amp;", "&")
        score = _score_image_url(url)
        if score > 0:
            scored.append((score, url))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate by base URL (ignore query params for dedup)
    seen = set()
    gallery = []
    for _, url in scored:
        base = url.split("?")[0]
        if base not in seen:
            seen.add(base)
            gallery.append(url)
        if len(gallery) >= max_images:
            break

    logger.info(
        "Extracted %d gallery images for '%s' from %s",
        len(gallery), activity_name, source_url,
    )
    return gallery


def _extract_images_from_markdown(markdown: str) -> list[str]:
    """Extract image URLs from markdown ![alt](url) syntax."""
    urls = []
    for match in re.finditer(r'!\[[^\]]*\]\(([^)\s]+)\)', markdown):
        url = match.group(1)
        if url.startswith("http"):
            urls.append(url)
    return urls


def _extract_image_urls(html: str) -> list[str]:
    """Extract all image URLs from HTML source."""
    urls = set()

    # <img src="..." /> and <img ... srcset="..." />
    for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE):
        url = match.group(1)
        if url.startswith("http"):
            urls.add(url)

    # srcset may contain multiple URLs
    for match in re.finditer(r'srcset=["\']([^"\']+)["\']', html, re.IGNORECASE):
        for part in match.group(1).split(","):
            part = part.strip().split(" ")[0]
            if part.startswith("http"):
                urls.add(part)

    # Background images in style
    for match in re.finditer(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)', html):
        urls.add(match.group(1))

    # Open Graph / meta images
    for match in re.finditer(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', html, re.IGNORECASE):
        url = match.group(1)
        if url.startswith("http"):
            urls.add(url)
    for match in re.finditer(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE):
        url = match.group(1)
        if url.startswith("http"):
            urls.add(url)

    # JSON-LD or inline JSON with image URLs
    for match in re.finditer(r'"(?:image|photo|thumbnail|src)":\s*"(https?://[^"]+)"', html):
        urls.add(match.group(1))

    return list(urls)


def _score_image_url(url: str) -> int:
    """Score an image URL for relevance. 0 = skip, higher = better."""
    lower = url.lower()

    # Skip unwanted images
    for pattern in SKIP_PATTERNS:
        if pattern in lower:
            return 0

    # Must be a real image format
    has_image_ext = any(
        ext in lower
        for ext in (".jpg", ".jpeg", ".png", ".webp", "format=webp", "format=jpg")
    )
    has_image_in_path = any(p in lower for p in ("/image", "/photo", "/media", "/upload"))

    if not has_image_ext and not has_image_in_path:
        return 0

    score = 1

    # Bonus for known CDN / gallery patterns
    for pattern in GOOD_PATTERNS:
        if pattern in lower:
            score += 3
            break

    # Bonus for large dimensions in URL
    size_match = re.search(r'[wh]=(\d+)', lower)
    if size_match:
        size = int(size_match.group(1))
        if size >= 800:
            score += 3
        elif size >= 400:
            score += 1
        elif size < 100:
            return 0  # Tiny image

    # Bonus for high-quality path indicators
    if any(kw in lower for kw in ("large", "original", "full", "detail", "hero")):
        score += 2

    # Penalty for thumbnail indicators
    if any(kw in lower for kw in ("thumb", "small", "tiny", "mini", "50x", "100x")):
        score -= 2

    return max(score, 0)
