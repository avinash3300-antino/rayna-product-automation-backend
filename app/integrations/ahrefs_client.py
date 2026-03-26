import httpx

from app.core.config import settings

BASE_URL = "https://api.ahrefs.com/v3"


class AhrefsClient:
    def __init__(self):
        self.token = settings.AHREFS_API_TOKEN

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    async def get_keyword_metrics(self, keywords: list[str], country: str = "ae") -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{BASE_URL}/keywords-explorer/overview",
                headers=self._headers(),
                json={"keywords": keywords, "country": country},
            )
            response.raise_for_status()
            return response.json()

    async def get_search_volume(self, keyword: str, country: str = "ae") -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/keywords-explorer/volume",
                headers=self._headers(),
                params={"keyword": keyword, "country": country},
            )
            response.raise_for_status()
            return response.json()


ahrefs_client = AhrefsClient()
