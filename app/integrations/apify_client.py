import asyncio

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

BASE_URL = "https://api.apify.com/v2"


class ApifyClient:
    def __init__(self):
        self.token = settings.APIFY_API_TOKEN

    def _params(self) -> dict:
        return {"token": self.token}

    async def run_actor(self, actor_id: str, input_data: dict) -> dict:
        # Apify API requires ~ separator (not /) in actor IDs for URL path
        safe_actor_id = actor_id.replace("/", "~")
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{BASE_URL}/acts/{safe_actor_id}/runs",
                params=self._params(),
                json=input_data,
            )
            response.raise_for_status()
            return response.json()

    async def get_run_status(self, run_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/actor-runs/{run_id}",
                params=self._params(),
            )
            response.raise_for_status()
            return response.json()

    async def get_dataset_items(self, dataset_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{BASE_URL}/datasets/{dataset_id}/items",
                params=self._params(),
            )
            response.raise_for_status()
            return response.json()

    async def _poll_run(self, run_id: str, max_wait_seconds: int = 300) -> dict:
        """Poll an actor run until completion or timeout."""
        elapsed = 0
        while elapsed < max_wait_seconds:
            status_data = await self.get_run_status(run_id)
            status = status_data["data"]["status"]
            if status == "SUCCEEDED":
                return status_data
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise ExternalServiceError(
                    f"Apify run {run_id} ended with status {status}"
                )
            await asyncio.sleep(5)
            elapsed += 5
        raise ExternalServiceError(
            f"Apify run {run_id} timed out after {max_wait_seconds}s"
        )

    async def scrape_url(self, url: str) -> dict:
        """Scrape a single URL via Apify web-scraper actor.

        Returns {markdown: str, html: str, url: str, success: bool}.
        """
        run = await self.run_actor(
            "apify/website-content-crawler",
            {
                "startUrls": [{"url": url}],
                "maxCrawlPages": 1,
                "outputFormats": ["markdown"],
            },
        )
        run_id = run["data"]["id"]
        status_data = await self._poll_run(run_id, max_wait_seconds=120)
        dataset_id = status_data["data"]["defaultDatasetId"]
        items = await self.get_dataset_items(dataset_id)
        if not items:
            return {"markdown": "", "html": "", "url": url, "success": False}
        item = items[0]
        return {
            "markdown": item.get("markdown", item.get("text", "")),
            "html": item.get("html", ""),
            "url": item.get("url", url),
            "success": True,
        }

    async def scrape_listing_page(
        self, url: str, link_selector: str
    ) -> list[str]:
        """Extract all links matching link_selector from a page."""
        run = await self.run_actor(
            "apify/website-content-crawler",
            {
                "startUrls": [{"url": url}],
                "maxCrawlPages": 1,
                "outputFormats": ["markdown"],
            },
        )
        run_id = run["data"]["id"]
        status_data = await self._poll_run(run_id, max_wait_seconds=120)
        dataset_id = status_data["data"]["defaultDatasetId"]
        items = await self.get_dataset_items(dataset_id)
        links: list[str] = []
        for item in items:
            for link in item.get("links", []):
                href = link if isinstance(link, str) else link.get("href", "")
                if href and href.startswith("http"):
                    links.append(href)
        return links

    async def crawl_site(self, url: str, max_pages: int = 50) -> list[dict]:
        """Crawl a website starting from url, returning up to max_pages results."""
        run = await self.run_actor(
            "apify/website-content-crawler",
            {
                "startUrls": [{"url": url}],
                "maxCrawlPages": max_pages,
                "outputFormats": ["markdown"],
            },
        )
        run_id = run["data"]["id"]
        status_data = await self._poll_run(run_id, max_wait_seconds=600)
        dataset_id = status_data["data"]["defaultDatasetId"]
        items = await self.get_dataset_items(dataset_id)
        return [
            {
                "url": item.get("url", ""),
                "markdown": item.get("markdown", item.get("text", "")),
                "title": item.get("metadata", {}).get("title", ""),
            }
            for item in items
        ]


apify_client = ApifyClient()
