import httpx

from app.core.exceptions import ExternalServiceError

JINA_READER_URL = "https://r.jina.ai"


class JinaClient:
    """Jina AI Reader — converts URLs to clean markdown. Free, no API key."""

    async def clean_page(self, url: str, include_images: bool = False) -> str:
        """Fetch a URL through Jina Reader and return clean markdown."""
        try:
            headers = {
                "Accept": "text/plain",
                "X-No-Cache": "true",
            }
            if include_images:
                headers["X-With-Images"] = "true"
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                response = await client.get(
                    f"{JINA_READER_URL}/{url}",
                    headers=headers,
                )
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                f"Jina Reader failed for {url}: {exc.response.status_code}"
            )
        except Exception as exc:
            raise ExternalServiceError(f"Jina Reader error: {exc}")

    def clean_markdown(self, raw_markdown: str) -> str:
        """Post-process markdown: strip nav, ads, footers, cookie banners."""
        if not raw_markdown:
            return ""
        lines = raw_markdown.split("\n")
        skip_patterns = [
            "cookie",
            "subscribe",
            "newsletter",
            "advertisement",
            "privacy policy",
            "terms of service",
            "sign up for",
            "follow us on",
        ]
        cleaned = []
        for line in lines:
            lower = line.lower().strip()
            if any(p in lower for p in skip_patterns):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()


jina_client = JinaClient()
