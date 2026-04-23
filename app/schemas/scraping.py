from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Discovery ─────────────────────────────────────────────────────────────


class SourceDiscoveryRequest(BaseModel):
    city_id: UUID
    category: str = Field(min_length=1, max_length=100)
    product_type: str = Field(default="activities", max_length=50)


class SourceDiscoveryRunResponse(BaseModel):
    id: UUID
    city_id: UUID
    category: str
    product_type: str = "activities"
    status: str
    ahrefs_results: dict | None = None
    searchapi_results: dict | None = None
    claude_synthesis: dict | None = None
    sources_found: int = 0
    sources_approved: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Sources ───────────────────────────────────────────────────────────────


class ScrapeSourceResponse(BaseModel):
    id: UUID
    city_id: UUID
    category: str
    product_type: str = "activities"
    source_name: str
    source_url: str
    tier: int
    authority_score: float | None = None
    approved: bool = False
    approved_at: datetime | None = None
    added_by: str
    is_active: bool = True
    last_scraped_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceApprovalRequest(BaseModel):
    source_ids: list[UUID]
    approved: bool


class AddSourceRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=500)
    source_name: str = Field(min_length=1, max_length=300)
    tier: int = Field(ge=1, le=2)


# ── Scraping Jobs ─────────────────────────────────────────────────────────


class ScrapeJobResponse(BaseModel):
    id: UUID
    discovery_run_id: UUID | None = None
    city_id: UUID
    category: str
    product_type: str = "activities"
    status: str
    source_id: UUID | None = None
    source_url: str
    scrape_type: str
    pages_scraped: int = 0
    records_found: int = 0
    records_saved: int = 0
    records_skipped_dup: int = 0
    records_enriched: int = 0
    errors_json: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScrapeJobTriggerRequest(BaseModel):
    discovery_run_id: UUID
    category: str = Field(min_length=1, max_length=100)
    product_type: str = Field(default="activities", max_length=50)
