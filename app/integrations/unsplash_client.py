import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

BASE_URL = "https://api.unsplash.com"


class UnsplashClient:
    def __init__(self):
        self.access_key = settings.UNSPLASH_ACCESS_KEY

    def _headers(self) -> dict:
        return {"Authorization": f"Client-ID {self.access_key}"}

    async def search_images(self, query: str, limit: int = 8) -> list[dict]:
        """Search Unsplash for stock photos.

        Returns list of {id, url, thumbnail_url, title, license_type}.
        """
        if not self.access_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{BASE_URL}/search/photos",
                    headers=self._headers(),
                    params={
                        "query": query,
                        "per_page": limit,
                        "orientation": "landscape",
                    },
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                return [
                    {
                        "id": r.get("id", ""),
                        "url": r.get("urls", {}).get("regular", "")
                        or r.get("urls", {}).get("full", ""),
                        "thumbnail_url": r.get("urls", {}).get("small", ""),
                        "title": r.get("alt_description", "")
                        or r.get("description", "")
                        or f"Unsplash photo {r.get('id', '')}",
                        "license_type": "unsplash",
                    }
                    for r in results
                ]
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                f"Unsplash search failed: {exc.response.status_code}"
            )
        except Exception as exc:
            raise ExternalServiceError(f"Unsplash error: {exc}")


unsplash_client = UnsplashClient()
