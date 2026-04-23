"""Scraping service — shared scraping & extraction utilities.

scrape_source() is product-type agnostic (Jina→Apify→Playwright chain).
extract_products() delegates to the pipeline's extraction prompt via Claude.
"""

import json
import logging

from app.core.exceptions import ExternalServiceError
from app.db.models.scraping import ScrapeSource
from app.integrations.apify_client import apify_client
from app.integrations.claude_client import claude_client
from app.integrations.jina_client import jina_client
from app.integrations.playwright_scraper import playwright_scraper

logger = logging.getLogger(__name__)


async def scrape_source(source: ScrapeSource) -> list[dict]:
    """Scrape a source URL and return cleaned markdown pages.

    Strategy: Jina Reader first → Apify fallback → Playwright last resort.
    Returns list of {url, clean_markdown, source_type} dicts.
    """
    url = source.source_url

    # Attempt 1: Jina Reader (free, no API key, handles most sites)
    try:
        clean_md = await jina_client.clean_page(url)
        clean_md = jina_client.clean_markdown(clean_md)
        if clean_md and len(clean_md) > 200:
            logger.info("Jina Reader succeeded for %s (%d chars)", url, len(clean_md))
            return [
                {
                    "url": url,
                    "clean_markdown": clean_md,
                    "source_type": "jina",
                }
            ]
        logger.warning("Jina Reader returned too little content for %s, trying Apify.", url)
    except Exception as exc:
        logger.warning("Jina Reader failed for %s: %s. Trying Apify.", url, exc)

    # Attempt 2: Apify crawl (uses credits)
    try:
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

    # Attempt 3: Playwright fallback (headless browser)
    try:
        html = await playwright_scraper.scrape_url(url)
        try:
            clean_md = await jina_client.clean_page(url)
            clean_md = jina_client.clean_markdown(clean_md)
        except Exception:
            clean_md = html[:20000]

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


async def extract_products(
    clean_markdown: str,
    source_url: str,
    extraction_prompt: str,
) -> list[dict]:
    """Use Claude to extract product data from cleaned markdown.

    The extraction_prompt is provided by the specific pipeline (activity/cruise/etc.).
    """
    prompt = f"""Source URL: {source_url}

Page content:
{clean_markdown[:12000]}

Extract all products/experiences from this page."""

    try:
        response_text = await claude_client.generate(
            prompt=prompt,
            system=extraction_prompt,
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            temperature=0.2,
        )

        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Truncated response — recover complete objects
            last_brace = text.rfind("}")
            if last_brace > 0:
                truncated = text[: last_brace + 1] + "]"
                try:
                    result = json.loads(truncated)
                    logger.warning(
                        "Recovered %d items from truncated JSON for %s",
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


# ── Backward compatibility ──────────────────────────────────────────────

async def extract_activities(
    clean_markdown: str,
    source_url: str,
) -> list[dict]:
    """Legacy wrapper — uses activity extraction prompt."""
    from app.services.pipelines.activity_pipeline import EXTRACTION_SYSTEM_PROMPT
    return await extract_products(clean_markdown, source_url, EXTRACTION_SYSTEM_PROMPT)
