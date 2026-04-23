import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

BASE_URL = "https://api.pexels.com/v1"


class PexelsClient:
    def __init__(self):
        self.api_key = settings.PEXELS_API_KEY

    def _headers(self) -> dict:
        return {"Authorization": self.api_key}

    async def search_images(self, query: str, limit: int = 8) -> list[dict]:
        """Search Pexels for stock photos.

        Returns list of {id, url, thumbnail_url, title, license_type}.
        """
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{BASE_URL}/search",
                    headers=self._headers(),
                    params={
                        "query": query,
                        "per_page": limit,
                        "orientation": "landscape",
                    },
                )
                response.raise_for_status()
                data = response.json()
                photos = data.get("photos", [])
                return [
                    {
                        "id": str(p.get("id", "")),
                        "url": p.get("src", {}).get("large2x", "")
                        or p.get("src", {}).get("original", ""),
                        "thumbnail_url": p.get("src", {}).get("medium", ""),
                        "title": p.get("alt", "") or f"Pexels photo {p.get('id', '')}",
                        "license_type": "pexels",
                    }
                    for p in photos
                ]
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                f"Pexels search failed: {exc.response.status_code}"
            )
        except Exception as exc:
            raise ExternalServiceError(f"Pexels error: {exc}")


pexels_client = PexelsClient()
