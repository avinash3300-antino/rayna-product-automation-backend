import hashlib
import json
import logging

import httpx
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
CACHE_TTL = 30 * 24 * 3600  # 30 days in seconds


class GeocodingClient:
    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True
            )
        return self._redis

    def _cache_key(self, address: str) -> str:
        digest = hashlib.md5(
            address.lower().strip().encode()
        ).hexdigest()
        return f"geocode:{digest}"

    async def geocode(
        self, address: str, city: str = "", country: str = ""
    ) -> dict | None:
        """Geocode an address.

        Returns {lat: float, lng: float, formatted_address: str} or None.
        Results are cached in Redis for 30 days.
        """
        full_address = ", ".join(
            filter(None, [address.strip(), city.strip(), country.strip()])
        )
        if not full_address:
            return None

        cache_key = self._cache_key(full_address)

        # Check Redis cache
        try:
            r = await self._get_redis()
            cached = await r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Redis cache read failed: %s", exc)

        # Call Google Geocoding API
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    BASE_URL,
                    params={"address": full_address, "key": self.api_key},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                f"Geocoding API failed: {exc.response.status_code}"
            )
        except Exception as exc:
            raise ExternalServiceError(f"Geocoding error: {exc}")

        if data.get("status") != "OK" or not data.get("results"):
            return None

        result = data["results"][0]
        location = result["geometry"]["location"]
        geo = {
            "lat": round(location["lat"], 6),
            "lng": round(location["lng"], 6),
            "formatted_address": result.get("formatted_address", ""),
        }

        # Cache for 30 days
        try:
            r = await self._get_redis()
            await r.setex(cache_key, CACHE_TTL, json.dumps(geo))
        except Exception as exc:
            logger.warning("Redis cache write failed: %s", exc)

        return geo


geocoding_client = GeocodingClient()
