import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

BASE_URL = "https://www.searchapi.io/api/v1/search"


class SearchAPIClient:
    def __init__(self):
        self.api_key = settings.SEARCHAPI_KEY

    async def search(self, query: str, num_results: int = 20) -> list[dict]:
        """Google search via SearchAPI.

        Returns list of {title, url, snippet, position}.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    BASE_URL,
                    params={
                        "engine": "google",
                        "q": query,
                        "api_key": self.api_key,
                        "num": num_results,
                    },
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("organic_results", [])
                return [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("link", ""),
                        "snippet": r.get("snippet", ""),
                        "position": r.get("position", 0),
                    }
                    for r in results
                ]
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                f"SearchAPI request failed: {exc.response.status_code}"
            )
        except Exception as exc:
            raise ExternalServiceError(f"SearchAPI error: {exc}")


searchapi_client = SearchAPIClient()
