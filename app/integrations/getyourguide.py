import httpx

from app.core.config import settings

BASE_URL = "https://api.getyourguide.com/1"


class GetYourGuideClient:
    def __init__(self):
        self.api_key = settings.GETYOURGUIDE_API_KEY

    def _headers(self) -> dict:
        return {"X-Access-Token": self.api_key, "Accept": "application/json"}

    async def search_tours(self, query: str, location: str = "Dubai") -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/tours",
                headers=self._headers(),
                params={"q": query, "location": location},
            )
            response.raise_for_status()
            return response.json()

    async def get_tour(self, tour_id: int) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/tours/{tour_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()


gyg_client = GetYourGuideClient()
