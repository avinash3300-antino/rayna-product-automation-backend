import httpx

from app.core.config import settings

BASE_URL = "https://api.viator.com/partner"


class ViatorClient:
    def __init__(self):
        self.api_key = settings.VIATOR_API_KEY

    def _headers(self) -> dict:
        return {"exp-api-key": self.api_key, "Accept": "application/json"}

    async def search_products(self, destination_id: int, query: str = "") -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{BASE_URL}/products/search",
                headers=self._headers(),
                json={"destId": destination_id, "text": query},
            )
            response.raise_for_status()
            return response.json()

    async def get_product(self, product_code: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/products/{product_code}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()


viator_client = ViatorClient()
