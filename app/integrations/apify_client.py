import httpx

from app.core.config import settings

BASE_URL = "https://api.apify.com/v2"


class ApifyClient:
    def __init__(self):
        self.token = settings.APIFY_API_TOKEN

    def _params(self) -> dict:
        return {"token": self.token}

    async def run_actor(self, actor_id: str, input_data: dict) -> dict:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{BASE_URL}/acts/{actor_id}/runs",
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


apify_client = ApifyClient()
