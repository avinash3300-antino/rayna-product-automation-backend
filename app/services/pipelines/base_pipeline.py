"""Abstract base class for product-type pipelines.

Each product category (activities, cruises, yachts, etc.) implements
this interface so the master orchestrator can dispatch generically.
"""

import hashlib
import logging
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.scraping import ScrapeJob, ScrapeSource
from app.services.geocoding_service import geocode_activity
from app.services.image_service import fetch_and_upload_images

logger = logging.getLogger(__name__)


class BasePipeline(ABC):
    """Contract every product pipeline must fulfil."""

    product_type: str  # e.g. "activities", "cruises"

    # ── Abstract methods ────────────────────────────────────────────────

    @abstractmethod
    def get_extraction_prompt(self) -> str:
        """Return the Claude system prompt used for data extraction."""

    @abstractmethod
    async def save_extracted_products(
        self,
        db: AsyncSession,
        extracted: list[dict],
        source: ScrapeSource,
        job: ScrapeJob,
        city_name: str,
        country_name: str,
    ) -> dict:
        """Deduplicate & persist extracted items. Returns counts dict."""

    @abstractmethod
    async def enrich_product(self, db: AsyncSession, product) -> None:
        """Claude AI rewrite + enrichment for a single product."""

    @abstractmethod
    def calculate_quality_score(self, product) -> int:
        """Score 0-100 based on field completeness."""

    @abstractmethod
    async def run_post_enrichment(
        self,
        db: AsyncSession,
        product,
        errors: list[dict],
    ) -> None:
        """Gallery, geocoding, reviews for one product after enrichment."""

    @abstractmethod
    async def get_recently_saved_products(
        self,
        db: AsyncSession,
        city_id,
        started_at,
        limit: int,
    ) -> list:
        """Fetch recently saved draft products for enrichment."""

    # ── Shared concrete helpers ─────────────────────────────────────────

    @staticmethod
    def compute_dedup_hash(name: str, city: str, category: str) -> str:
        """MD5 hash of normalized name+city+category for exact-match dedup."""
        normalized = (
            f"{name.lower().strip()}_{city.lower().strip()}"
            f"_{category.lower().strip()}"
        )
        return hashlib.md5(normalized.encode()).hexdigest()

    @staticmethod
    def infer_currency(country_name: str) -> str:
        """Infer currency from country name."""
        mapping = {
            "united kingdom": "GBP", "england": "GBP", "uk": "GBP",
            "united states": "USD", "usa": "USD",
            "united arab emirates": "AED", "uae": "AED",
            "france": "EUR", "germany": "EUR", "italy": "EUR", "spain": "EUR",
            "netherlands": "EUR", "portugal": "EUR", "greece": "EUR",
            "thailand": "THB", "japan": "JPY", "turkey": "TRY",
            "india": "INR", "australia": "AUD", "singapore": "SGD",
            "malaysia": "MYR", "indonesia": "IDR",
            "egypt": "EGP", "oman": "OMR", "saudi arabia": "SAR",
            "qatar": "QAR", "bahrain": "BHD",
        }
        return mapping.get(country_name.lower().strip(), "USD")

    async def fetch_gallery(
        self, product, errors: list[dict],
    ) -> None:
        """Upload Freepik gallery images to S3."""
        if product.gallery_json:
            return
        try:
            gallery = await fetch_and_upload_images(
                product.name,
                product.city,
                str(product.id),
                product_type=self.product_type,
                num_images=8,
            )
            if gallery:
                product.gallery_json = gallery
                if not product.cover_image_url:
                    product.cover_image_url = gallery[0]["url"]
                logger.info(
                    "Gallery: %d images for '%s'",
                    len(gallery), product.name,
                )
        except Exception as exc:
            errors.append({
                "product_id": str(product.id),
                "error": str(exc),
                "step": "gallery",
            })
            logger.warning("Gallery failed for %s: %s", product.id, exc)

    async def geocode(
        self, product, errors: list[dict],
    ) -> None:
        """Resolve product location to lat/lng via Nominatim."""
        if product.lat != 0 and product.lng != 0:
            return
        try:
            coords = await geocode_activity(
                product.name, product.city, product.country,
                getattr(product, "address", None),
            )
            if coords["lat"] != 0:
                product.lat = coords["lat"]
                product.lng = coords["lng"]
                logger.info(
                    "Geocoded '%s': %s, %s",
                    product.name, coords["lat"], coords["lng"],
                )
        except Exception as exc:
            errors.append({
                "product_id": str(product.id),
                "error": str(exc),
                "step": "geocoding",
            })
            logger.warning("Geocoding failed for %s: %s", product.id, exc)
