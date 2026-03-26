import httpx

from app.core.config import settings

BASE_URL = "https://distribution-xml.booking.com/json"


class BookingComClient:
    def __init__(self):
        self.affiliate_id = settings.BOOKING_COM_AFFILIATE_ID
        self.api_key = settings.BOOKING_COM_API_KEY

    def _auth(self) -> tuple[str, str]:
        return (self.affiliate_id, self.api_key)

    async def search_attractions(self, city: str, country: str = "ae") -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/bookings.getAttractions",
                auth=self._auth(),
                params={"city": city, "country": country},
            )
            response.raise_for_status()
            return response.json()

    async def get_attraction_details(self, attraction_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/bookings.getAttractionDetails",
                auth=self._auth(),
                params={"attraction_id": attraction_id},
            )
            response.raise_for_status()
            return response.json()


booking_client = BookingComClient()
