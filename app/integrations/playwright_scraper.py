import logging

from playwright.async_api import async_playwright

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class PlaywrightScraper:
    """Fallback scraper using headless Chromium via Playwright."""

    async def scrape_url(
        self,
        url: str,
        wait_ms: int = 3000,
        timeout: int = 30000,
        wait_until: str = "networkidle",
        stealth: bool = False,
    ) -> str:
        """Navigate to a URL and return the fully rendered HTML.

        Defaults preserve existing behavior. Callers hitting heavy SPA pages
        (Viator, GetYourGuide) can pass a larger timeout and looser wait
        strategy, e.g. timeout=90000, wait_until="domcontentloaded".

        Set stealth=True to apply playwright-stealth patches that bypass
        common headless-browser detection (works on GetYourGuide; does NOT
        bypass DataDome on Viator).
        """
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=settings.PLAYWRIGHT_HEADLESS
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                if stealth:
                    from playwright_stealth import Stealth
                    await Stealth().apply_stealth_async(context)
                page = await context.new_page()
                try:
                    await page.goto(
                        url, wait_until=wait_until, timeout=timeout
                    )
                    await page.wait_for_timeout(wait_ms)
                    html = await page.content()
                    return html
                finally:
                    await context.close()
                    await browser.close()
        except Exception as exc:
            logger.error("Playwright scrape failed for %s: %s", url, exc)
            raise ExternalServiceError(
                f"Playwright scrape failed for {url}: {exc}"
            )

    async def scrape_listing_links(
        self, url: str, link_selector: str
    ) -> list[str]:
        """Extract all href values matching a CSS selector from a page."""
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=settings.PLAYWRIGHT_HEADLESS
                )
                page = await browser.new_page()
                try:
                    await page.goto(
                        url, wait_until="networkidle", timeout=30000
                    )
                    await page.wait_for_timeout(2000)
                    links = await page.eval_on_selector_all(
                        link_selector, "els => els.map(e => e.href)"
                    )
                    return [l for l in links if l and l.startswith("http")]
                finally:
                    await browser.close()
        except Exception as exc:
            logger.error(
                "Playwright link extraction failed for %s: %s", url, exc
            )
            raise ExternalServiceError(
                f"Playwright link extraction failed for {url}: {exc}"
            )


playwright_scraper = PlaywrightScraper()
