"""Drop unused legacy tables

Revision ID: g8h9i0j1k2l3
Revises: f7g8h9i0j1k2
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g8h9i0j1k2l3"
down_revision: str = "f7g8h9i0j1k2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# All legacy tables to drop, ordered so child tables (with FKs) are dropped first.
TABLES_TO_DROP = [
    # ── Publishing ──
    "publishing_rollback_batch_items",
    "publishing_rollback_batches",
    "publishing_batch_approvals",
    "publishing_push_batch_items",
    "publishing_push_batches",
    # ── Packages ──
    "pricing_package_price_calculations",
    "pricing_package_generation_runs",
    "pricing_package_itinerary_days",
    "pricing_package_media",
    "pricing_package_tags",
    "pricing_package_components",
    "pricing_packages",
    "pricing_package_rules",
    "pricing_package_types",
    # ── Ops ──
    "ops_api_audits",
    "ops_notifications",
    "ops_job_metrics",
    "ops_error_queue",
    "ops_product_quality_checks",
    "ops_product_freshness_status",
    "ops_freshness_rules",
    "ops_booking_source_health_checks",
    # ── Booking Sources ──
    "catalog_product_booking_sources",
    "catalog_booking_sources",
    # ── Tags ──
    "catalog_product_tag_suggestions",
    "catalog_product_tags",
    "catalog_tags",
    "catalog_tag_dimensions",
    # ── Content ──
    "content_content_review_actions",
    "content_content_review_queue",
    "content_content_generation_runs",
    "content_product_content",
    "content_destination_keyword_sets",
    # ── Product Shared ──
    "catalog_product_schema_markup",
    "catalog_product_faqs",
    "catalog_product_media",
    # ── Restaurants ──
    "catalog_restaurant_operating_hours",
    "catalog_restaurant_product_cuisines",
    "catalog_restaurant_cuisines_master",
    "catalog_restaurant_products",
    # ── Transfers ──
    "catalog_transfer_products",
    # ── Attractions ──
    "catalog_attraction_ticket_types",
    "catalog_attraction_operating_hours",
    "catalog_attraction_products",
    # ── Hotels ──
    "catalog_hotel_product_amenities",
    "catalog_hotel_amenities_master",
    "catalog_hotel_board_types",
    "catalog_hotel_room_types",
    "catalog_hotel_products",
    # ── Products (generic) ──
    "catalog_product_status_history",
    "catalog_product_versions",
    "catalog_products",
    # ── Workflow ──
    "workflow_attribute_enrichment_queue",
    "workflow_attribute_mapping_runs",
    "workflow_classification_review_actions",
    "workflow_classification_review_queue",
    "workflow_classification_results",
    # ── Ingestion ──
    "ingestion_raw_record_media",
    "ingestion_raw_records",
    "ingestion_job_sources",
    "ingestion_jobs",
    # ── Intelligence ──
    "ingestion_approved_source_list_audit",
    "ingestion_approved_source_list_items",
    "ingestion_approved_source_lists",
    "ingestion_source_discovery_candidates",
    "ingestion_destination_paa_questions",
    "ingestion_destination_keywords",
    "ingestion_destination_intelligence_runs",
    # ── Sources (ingestion) ──
    "ingestion_source_legal_checklist_items",
    "ingestion_source_legal_checklists",
    "ingestion_source_category_coverage",
    "ingestion_source_terms_policy",
    "ingestion_sources",
    # ── AI Discovery (old) ──
    "ai_discovery_review_actions",
    "ai_discovery_seed_items",
    "ai_discovery_destination_candidates",
    "ai_discovery_runs",
]


def upgrade() -> None:
    for table in TABLES_TO_DROP:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    # These tables were unused legacy tables. No downgrade path provided.
    pass
