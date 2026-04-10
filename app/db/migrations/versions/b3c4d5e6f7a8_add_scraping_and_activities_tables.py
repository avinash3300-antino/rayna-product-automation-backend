"""add scraping and activities tables

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: pgvector extension + activity_embeddings table will be added
    # in a separate migration once pgvector is installed on the DB server.

    # ── source_discovery_runs ────────────────────────────────────────────
    op.create_table(
        "source_discovery_runs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("catalog_destinations.id"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("ahrefs_results", JSON, nullable=True),
        sa.Column("searchapi_results", JSON, nullable=True),
        sa.Column("claude_synthesis", JSON, nullable=True),
        sa.Column("sources_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sources_approved", sa.Integer, nullable=False, server_default="0"),
        sa.Column("triggered_by", UUID(as_uuid=True), sa.ForeignKey("auth_users.id"), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── scrape_sources ───────────────────────────────────────────────────
    op.create_table(
        "scrape_sources",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("catalog_destinations.id"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("source_name", sa.String(300), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("tier", sa.Integer, nullable=False),
        sa.Column("authority_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("approved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("auth_users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("added_by", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("discovery_run_id", UUID(as_uuid=True), sa.ForeignKey("source_discovery_runs.id"), nullable=True),
    )

    # ── scrape_jobs ──────────────────────────────────────────────────────
    op.create_table(
        "scrape_jobs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("discovery_run_id", UUID(as_uuid=True), sa.ForeignKey("source_discovery_runs.id"), nullable=True),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("catalog_destinations.id"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("scrape_sources.id"), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("scrape_type", sa.String(50), nullable=False),
        sa.Column("pages_scraped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_saved", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_skipped_dup", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_enriched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors_json", JSON, nullable=True),
        sa.Column("triggered_by", UUID(as_uuid=True), sa.ForeignKey("auth_users.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── activities ───────────────────────────────────────────────────────
    op.create_table(
        "activities",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(300), unique=True, nullable=False),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("catalog_destinations.id"), nullable=False),
        # Classification
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("sub_category", sa.String(100), nullable=True),
        sa.Column("activity_type", sa.String(100), nullable=False),
        sa.Column("tags", JSON, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        # Descriptions
        sa.Column("description_short", sa.Text, nullable=False),
        sa.Column("description_long", sa.Text, nullable=False),
        sa.Column("highlights", JSON, nullable=False),
        sa.Column("included", JSON, nullable=False),
        sa.Column("excluded", JSON, nullable=False),
        sa.Column("what_to_bring", sa.Text, nullable=True),
        sa.Column("important_notes", sa.Text, nullable=True),
        # Pricing
        sa.Column("price_adult", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_child", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_infant", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_group", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_original", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_type", sa.String(50), nullable=False),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("price_from", sa.Numeric(10, 2), nullable=False),
        # Duration & Scheduling
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("start_times", JSON, nullable=False),
        sa.Column("operating_days", JSON, nullable=False),
        sa.Column("instant_confirmation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("free_cancellation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cancellation_hours", sa.Integer, nullable=True),
        sa.Column("cancellation_policy", sa.Text, nullable=True),
        sa.Column("min_participants", sa.Integer, nullable=True),
        sa.Column("max_participants", sa.Integer, nullable=True),
        sa.Column("advance_booking_days", sa.Integer, nullable=True),
        # Location
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("city", sa.String(200), nullable=False),
        sa.Column("area", sa.String(200), nullable=True),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("lat", sa.Numeric(10, 6), nullable=False),
        sa.Column("lng", sa.Numeric(10, 6), nullable=False),
        sa.Column("maps_link", sa.String(500), nullable=True),
        sa.Column("meeting_point_name", sa.String(300), nullable=True),
        sa.Column("meeting_point_desc", sa.Text, nullable=True),
        sa.Column("nearby_landmark", sa.String(300), nullable=True),
        # Pickup & Dropoff
        sa.Column("pickup_available", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pickup_locations", JSON, nullable=True),
        sa.Column("hotel_pickup_included", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dropoff_available", sa.Boolean, nullable=False, server_default="false"),
        # Policies & Restrictions
        sa.Column("refund_policy_details", sa.Text, nullable=True),
        sa.Column("min_age", sa.Integer, nullable=True),
        sa.Column("max_age", sa.Integer, nullable=True),
        sa.Column("fitness_level", sa.String(50), nullable=True),
        sa.Column("difficulty", sa.String(50), nullable=True),
        sa.Column("pregnancy_restriction", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("wheelchair_access", sa.String(50), nullable=True),
        sa.Column("languages", JSON, nullable=False),
        # Images & Media
        sa.Column("cover_image_url", sa.String(500), nullable=True),
        sa.Column("gallery_json", JSON, nullable=True),
        sa.Column("video_url", sa.String(500), nullable=True),
        # Reviews & Ratings
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("review_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_5", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_4", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_3", sa.Integer, nullable=False, server_default="0"),
        sa.Column("review_snippets", JSON, nullable=True),
        # SEO
        sa.Column("meta_title", sa.String(60), nullable=True),
        sa.Column("meta_description", sa.String(155), nullable=True),
        sa.Column("focus_keyword", sa.String(200), nullable=True),
        sa.Column("json_ld", JSON, nullable=True),
        sa.Column("canonical_url", sa.String(500), nullable=True),
        # Source & Data Quality
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("operator_name", sa.String(300), nullable=True),
        sa.Column("verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dedup_hash", sa.String(32), unique=True, nullable=False),
        sa.Column("quality_score", sa.Integer, nullable=False, server_default="0"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # NOTE: activity_embeddings table skipped — requires pgvector extension.
    # Will be created in a future migration once pgvector is installed.

    # ── ahrefs_cache ─────────────────────────────────────────────────────
    op.create_table(
        "ahrefs_cache",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("query_term", sa.String(500), nullable=False),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("catalog_destinations.id"), nullable=True),
        sa.Column("results_json", JSON, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── search_cache ─────────────────────────────────────────────────────
    op.create_table(
        "search_cache",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("query_term", sa.String(500), nullable=False),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("catalog_destinations.id"), nullable=True),
        sa.Column("results_json", JSON, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── Useful indexes ───────────────────────────────────────────────────
    op.create_index("ix_activities_city_id", "activities", ["city_id"])
    op.create_index("ix_activities_category", "activities", ["category"])
    op.create_index("ix_activities_status", "activities", ["status"])
    op.create_index("ix_activities_dedup_hash", "activities", ["dedup_hash"])
    op.create_index("ix_scrape_sources_city_id", "scrape_sources", ["city_id"])
    op.create_index("ix_scrape_jobs_city_id", "scrape_jobs", ["city_id"])


def downgrade() -> None:
    op.drop_index("ix_scrape_jobs_city_id")
    op.drop_index("ix_scrape_sources_city_id")
    op.drop_index("ix_activities_dedup_hash")
    op.drop_index("ix_activities_status")
    op.drop_index("ix_activities_category")
    op.drop_index("ix_activities_city_id")
    op.drop_table("search_cache")
    op.drop_table("ahrefs_cache")
    op.drop_table("activities")
    op.drop_table("scrape_jobs")
    op.drop_table("scrape_sources")
    op.drop_table("source_discovery_runs")
