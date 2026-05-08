from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class StatusBreakdown(BaseModel):
    draft: int = 0
    enriched: int = 0
    review_ready: int = 0
    approved: int = 0
    published: int = 0


class KpiStats(BaseModel):
    total_products: int = 0
    total_activities: int = 0
    total_cruises: int = 0
    by_status: StatusBreakdown = StatusBreakdown()
    active_scrape_jobs: int = 0
    is_scraping_running: bool = False


class PipelineStage(BaseModel):
    id: str
    label: str
    count: int = 0


class RecentJobItem(BaseModel):
    id: UUID
    destination: str
    category: str
    product_type: str = "activities"
    status: str
    records_found: int = 0
    records_saved: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    duration_ms: int = 0


class ProductsByDestinationItem(BaseModel):
    destination: str
    count: int = 0


class ProductsByCategoryItem(BaseModel):
    category: str
    count: int = 0


class DashboardStatsResponse(BaseModel):
    kpi: KpiStats = KpiStats()
    pipeline_stages: list[PipelineStage] = []
    recent_jobs: list[RecentJobItem] = []
    products_by_destination: list[ProductsByDestinationItem] = []
    products_by_category: dict[str, list[ProductsByCategoryItem]] = {}
