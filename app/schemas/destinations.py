from datetime import datetime
from typing import Generic, Sequence, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: Sequence[T]
    total: int
    page: int
    per_page: int
    total_pages: int


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Location schemas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LocationResponse(BaseModel):
    id: UUID
    destination_id: UUID
    name: str
    type: str
    address_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=100)
    address_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: str | None = Field(default=None, min_length=1, max_length=100)
    address_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Summary / aggregation schemas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ProductCountSummary(BaseModel):
    hotels: int = 0
    attractions: int = 0
    transfers: int = 0
    restaurants: int = 0
    total: int = 0


class IngestionJobBrief(BaseModel):
    id: UUID
    status: str
    run_type: str
    trigger_type: str
    total_records_fetched: int | None = None
    total_errors: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LastIngestionRunBrief(BaseModel):
    date: datetime | None = None
    status: str
    records_processed: int = 0
    duration_ms: int = 0


class CategoryPipelineStatus(BaseModel):
    category: str
    total: int = 0
    draft: int = 0
    enriched: int = 0
    review_ready: int = 0
    approved: int = 0
    published: int = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Destination response schemas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class DestinationListItem(BaseModel):
    id: UUID
    code: str | None = None
    name: str
    country_code: str | None = None
    country_name: str | None = None
    country_flag: str | None = None
    region_name: str | None = None
    city_name: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    status: str
    enabled_categories: list[str] = ["hotels", "attractions", "transfers", "restaurants"]
    created_at: datetime
    updated_at: datetime
    location_count: int = 0
    product_counts: ProductCountSummary = ProductCountSummary()
    last_ingestion_run: LastIngestionRunBrief | None = None


class DestinationDetail(BaseModel):
    id: UUID
    code: str | None = None
    name: str
    country_code: str | None = None
    country_name: str | None = None
    country_flag: str | None = None
    region_name: str | None = None
    city_name: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    status: str
    enabled_categories: list[str] = ["hotels", "attractions", "transfers", "restaurants"]
    created_at: datetime
    updated_at: datetime
    locations: list[LocationResponse] = []
    recent_ingestion_jobs: list[IngestionJobBrief] = []
    pipeline_status: list[CategoryPipelineStatus] = []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Destination input schemas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class DestinationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    country_name: str | None = Field(default=None, max_length=255)
    country_flag: str | None = Field(default=None, max_length=10)
    region_name: str | None = Field(default=None, max_length=255)
    city_name: str | None = Field(default=None, max_length=255)
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    enabled_categories: list[str] | None = None


class DestinationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    country_name: str | None = None
    country_flag: str | None = None
    region_name: str | None = None
    city_name: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    enabled_categories: list[str] | None = None


class DestinationStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=50)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Stats overview
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class DestinationStatsOverview(BaseModel):
    total_destinations: int = 0
    active_destinations: int = 0
    total_products: ProductCountSummary = ProductCountSummary()
    products_published: int = 0
    products_in_pipeline: int = 0
