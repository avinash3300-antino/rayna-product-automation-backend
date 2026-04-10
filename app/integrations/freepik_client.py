import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

BASE_URL = "https://api.freepik.com/v1"


class FreepikClient:
    def __init__(self):
        self.api_key = settings.FREEPIK_API_KEY

    def _headers(self) -> dict:
        return {
            "x-freepik-api-key": self.api_key,
            "Accept": "application/json",
        }

    async def search_images(
        self, query: str, limit: int = 8
    ) -> list[dict]:
        """Search Freepik for stock photos.

        Returns list of {id, url, thumbnail_url, title, license_type}.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{BASE_URL}/resources",
                    headers=self._headers(),
                    params={
                        "locale": "en-US",
                        "page": 1,
                        "limit": limit,
                        "term": query,
                        "filters[content_type][photo]": 1,
                    },
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("data", [])
                return [
                    {
                        "id": str(r.get("id", "")),
                        "url": (
                            r.get("image", {})
                            .get("source", {})
                            .get("url", "")
                        ),
                        "thumbnail_url": (
                            r.get("thumbnails", [{}])[0].get("url", "")
                            if r.get("thumbnails")
                            else ""
                        ),
                        "title": r.get("title", ""),
                        "license_type": r.get("licenses", [{}])[0].get(
                            "type", "freepik"
                        )
                        if r.get("licenses")
                        else "freepik",
                    }
                    for r in results
                ]
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                f"Freepik search failed: {exc.response.status_code}"
            )
        except Exception as exc:
            raise ExternalServiceError(f"Freepik error: {exc}")

    async def download_image(self, image_url: str) -> bytes:
        """Download image bytes from a URL."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(image_url)
                response.raise_for_status()
                return response.content
        except Exception as exc:
            raise ExternalServiceError(
                f"Freepik image download failed: {exc}"
            )


freepik_client = FreepikClient()
