"""Rebuild product tables: activities (expanded), cruises (new), shared reviews/embeddings, product_type on scraping tables.

Clean slate for activities-related tables. New cruise tables. Shared product_reviews and product_embeddings.

Revision ID: f7g8h9i0j1k2
Revises: e6f7g8h9i0j1
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "f7g8h9i0j1k2"
down_revision = "e6f7g8h9i0j1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. Drop old tables (clean slate — data can be deleted)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.drop_table("activity_embeddings")
    op.drop_table("activity_reviews")
    op.drop_table("activities")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. Recreate activities table with ALL fields from spec
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.create_table(
        "activities",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(300), unique=True, nullable=False),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("catalog_destinations.id"), nullable=False),
        # Classification
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("sub_category", sa.String(100)),
        sa.Column("activity_type", sa.String(100), nullable=False),
        sa.Column("tags", JSON),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        # Descriptions
        sa.Column("description_short", sa.Text, nullable=False),
        sa.Column("description_long", sa.Text, nullable=False),
        sa.Column("highlights", JSON, nullable=False),
        sa.Column("included", JSON, nullable=False),
        sa.Column("excluded", JSON, nullable=False),
        sa.Column("what_to_bring", sa.Text),
        sa.Column("important_notes", JSON),
        sa.Column("redemption_instructions", JSON),
        # Pricing
        sa.Column("price_adult", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_child", sa.Numeric(10, 2)),
        sa.Column("price_infant", sa.Numeric(10, 2)),
        sa.Column("price_group", sa.Numeric(10, 2)),
        sa.Column("price_original", sa.Numeric(10, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_type", sa.String(50), nullable=False),
        sa.Column("discount_pct", sa.Numeric(5, 2)),
        sa.Column("price_from", sa.Numeric(10, 2), nullable=False),
        # Duration & Scheduling
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("start_times", JSON, nullable=False),
        sa.Column("operating_days", JSON, nullable=False),
        sa.Column("instant_confirmation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("free_cancellation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cancellation_hours", sa.Integer),
        sa.Column("cancellation_policy", sa.Text),
        sa.Column("min_participants", sa.Integer),
        sa.Column("max_participants", sa.Integer),
        sa.Column("advance_booking_days", sa.Integer),
        # Location
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("city", sa.String(200), nullable=False),
        sa.Column("area", sa.String(200)),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("lat", sa.Numeric(10, 6), nullable=False),
        sa.Column("lng", sa.Numeric(10, 6), nullable=False),
        sa.Column("maps_link", sa.String(500)),
        sa.Column("meeting_point_name", sa.String(300)),
        sa.Column("meeting_point_desc", sa.Text),
        sa.Column("nearby_landmark", sa.String(300)),
        # Pickup
        sa.Column("pickup_available", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pickup_locations", JSON),
        sa.Column("hotel_pickup_included", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dropoff_available", sa.Boolean, nullable=False, server_default="false"),
        # Policies & Restrictions
        sa.Column("refund_policy_details", sa.Text),
        sa.Column("min_age", sa.Integer),
        sa.Column("max_age", sa.Integer),
        sa.Column("fitness_level", sa.String(50)),
        sa.Column("difficulty", sa.String(50)),
        sa.Column("pregnancy_restriction", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("wheelchair_access", sa.String(50)),
        sa.Column("languages", JSON, nullable=False),
        sa.Column("dress_code_note", sa.Text),
        # Media
        sa.Column("cover_image_url", sa.String(500)),
        sa.Column("gallery_json", JSON),
        sa.Column("video_url", sa.String(500)),
        # Reviews
        sa.Column("rating", sa.Numeric(3, 2)),
        sa.Column("review_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_5", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_4", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_3", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_2", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_1", sa.Integer, nullable=False, server_default="0"),
        sa.Column("review_snippets", JSON),
        # SEO
        sa.Column("meta_title", sa.String(60)),
        sa.Column("meta_description", sa.String(155)),
        sa.Column("focus_keyword", sa.String(200)),
        sa.Column("json_ld", JSON),
        sa.Column("canonical_url", sa.String(500)),
        # Source & Quality
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_urls", JSON),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("operator_name", sa.String(300)),
        sa.Column("operator_website", sa.String(500)),
        sa.Column("operator_established_year", sa.Integer),
        sa.Column("operator_certifications", JSON),
        sa.Column("verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dedup_hash", sa.String(32), unique=True, nullable=False),
        sa.Column("quality_score", sa.Integer, nullable=False, server_default="0"),
        # Catchall
        sa.Column("other_attributes", JSON),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_activities_city_id", "activities", ["city_id"])
    op.create_index("ix_activities_category", "activities", ["category"])
    op.create_index("ix_activities_status", "activities", ["status"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. Activity Timeline table
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.create_table(
        "catalog_activity_timeline",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("activity_id", UUID(as_uuid=True), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order", sa.Integer, nullable=False),
        sa.Column("time_label", sa.String(100)),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
    )
    op.create_index("ix_activity_timeline_activity_id", "catalog_activity_timeline", ["activity_id"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. Cruise Products table
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.create_table(
        "catalog_cruise_products",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(300), unique=True, nullable=False),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("catalog_destinations.id"), nullable=False),
        # Classification
        sa.Column("category", sa.String(100), nullable=False, server_default="Cruise"),
        sa.Column("sub_category", sa.String(100)),
        sa.Column("cruise_class", sa.String(100)),
        sa.Column("cruise_type", sa.String(100)),
        sa.Column("tags", JSON),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        # Descriptions
        sa.Column("description_short", sa.Text, nullable=False),
        sa.Column("description_long", sa.Text, nullable=False),
        sa.Column("highlights", JSON, nullable=False),
        sa.Column("included", JSON, nullable=False),
        sa.Column("excluded", JSON, nullable=False),
        sa.Column("what_to_bring", sa.Text),
        sa.Column("important_notes", JSON),
        sa.Column("redemption_instructions", JSON),
        # Pricing
        sa.Column("price_adult", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_child", sa.Numeric(10, 2)),
        sa.Column("price_infant", sa.Numeric(10, 2)),
        sa.Column("price_group", sa.Numeric(10, 2)),
        sa.Column("price_original", sa.Numeric(10, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_type", sa.String(50), nullable=False),
        sa.Column("discount_pct", sa.Numeric(5, 2)),
        sa.Column("price_from", sa.Numeric(10, 2), nullable=False),
        # Duration & Scheduling
        sa.Column("duration_hours", sa.Numeric(5, 1)),
        sa.Column("duration_days", sa.Integer),
        sa.Column("number_of_nights", sa.Integer, nullable=False, server_default="0"),
        sa.Column("departure_times", JSON),
        sa.Column("operating_days", JSON),
        sa.Column("seasonal_availability", sa.Text),
        sa.Column("boarding_time", sa.String(50)),
        sa.Column("instant_confirmation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("free_cancellation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cancellation_hours", sa.Integer),
        sa.Column("cancellation_policy", sa.Text),
        sa.Column("advance_booking_days", sa.Integer),
        # Location & Boarding
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("city", sa.String(200), nullable=False),
        sa.Column("area", sa.String(200)),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("lat", sa.Numeric(10, 6), nullable=False),
        sa.Column("lng", sa.Numeric(10, 6), nullable=False),
        sa.Column("maps_link", sa.String(500)),
        sa.Column("boarding_point_name", sa.String(300)),
        sa.Column("boarding_point_description", sa.Text),
        sa.Column("nearby_landmark", sa.String(300)),
        sa.Column("pickup_available", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pickup_points", JSON),
        # Vessel
        sa.Column("vessel_name", sa.String(300)),
        sa.Column("vessel_type", sa.String(100)),
        sa.Column("vessel_length_m", sa.Numeric(6, 1)),
        sa.Column("vessel_year_built", sa.Integer),
        sa.Column("vessel_capacity", sa.Integer),
        sa.Column("deck_count", sa.Integer),
        sa.Column("onboard_facilities", JSON),
        # Onboard Experience
        sa.Column("meal_included", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("meal_type", sa.String(100)),
        sa.Column("entertainment_included", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("entertainment_details", JSON),
        sa.Column("wifi_available", sa.Boolean, nullable=False, server_default="false"),
        # Route
        sa.Column("route_description", sa.Text),
        # Eligibility
        sa.Column("min_age", sa.Integer),
        sa.Column("max_age", sa.Integer),
        sa.Column("age_pricing_breaks", JSON),
        sa.Column("dress_code", sa.String(200)),
        sa.Column("wheelchair_accessible", sa.String(50)),
        sa.Column("languages", JSON),
        sa.Column("fitness_level", sa.String(50)),
        sa.Column("pregnancy_restriction", sa.Boolean, nullable=False, server_default="false"),
        # Operator
        sa.Column("operator_name", sa.String(300)),
        sa.Column("operator_website", sa.String(500)),
        sa.Column("operator_license_body", sa.String(300)),
        sa.Column("operator_established_year", sa.Integer),
        sa.Column("operator_fleet_size", sa.Integer),
        sa.Column("operator_certifications", JSON),
        # Media
        sa.Column("cover_image_url", sa.String(500)),
        sa.Column("gallery_json", JSON),
        sa.Column("video_url", sa.String(500)),
        # Reviews
        sa.Column("rating", sa.Numeric(3, 2)),
        sa.Column("review_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_5", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_4", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_3", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_2", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_1", sa.Integer, nullable=False, server_default="0"),
        sa.Column("review_snippets", JSON),
        # SEO
        sa.Column("meta_title", sa.String(60)),
        sa.Column("meta_description", sa.String(155)),
        sa.Column("focus_keyword", sa.String(200)),
        sa.Column("json_ld", JSON),
        sa.Column("canonical_url", sa.String(500)),
        # Source & Quality
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_urls", JSON),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dedup_hash", sa.String(32), unique=True, nullable=False),
        sa.Column("quality_score", sa.Integer, nullable=False, server_default="0"),
        # Catchall
        sa.Column("other_attributes", JSON),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cruise_products_city_id", "catalog_cruise_products", ["city_id"])
    op.create_index("ix_cruise_products_status", "catalog_cruise_products", ["status"])
    op.create_index("ix_cruise_products_cruise_type", "catalog_cruise_products", ["cruise_type"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. Cruise Itinerary
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.create_table(
        "catalog_cruise_itinerary",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("cruise_id", UUID(as_uuid=True), sa.ForeignKey("catalog_cruise_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order", sa.Integer, nullable=False),
        sa.Column("day_number", sa.Integer),
        sa.Column("time_label", sa.String(100)),
        sa.Column("port_or_stop", sa.String(300)),
        sa.Column("description", sa.Text),
        sa.Column("shore_excursion_available", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_cruise_itinerary_cruise_id", "catalog_cruise_itinerary", ["cruise_id"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. Cruise Cabins
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.create_table(
        "catalog_cruise_cabins",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("cruise_id", UUID(as_uuid=True), sa.ForeignKey("catalog_cruise_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cabin_type", sa.String(100), nullable=False),
        sa.Column("cabin_count", sa.Integer),
        sa.Column("max_occupancy", sa.Integer),
        sa.Column("amenities", JSON),
        sa.Column("description", sa.Text),
    )
    op.create_index("ix_cruise_cabins_cruise_id", "catalog_cruise_cabins", ["cruise_id"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 7. Cruise Pricing Tiers
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.create_table(
        "catalog_cruise_pricing_tiers",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("cruise_id", UUID(as_uuid=True), sa.ForeignKey("catalog_cruise_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cabin_type", sa.String(100), nullable=False),
        sa.Column("price_adult", sa.Numeric(10, 2)),
        sa.Column("price_child", sa.Numeric(10, 2)),
        sa.Column("price_infant", sa.Numeric(10, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("includes_description", sa.Text),
    )
    op.create_index("ix_cruise_pricing_tiers_cruise_id", "catalog_cruise_pricing_tiers", ["cruise_id"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 8. Shared Product Reviews
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.create_table(
        "product_reviews",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("product_type", sa.String(50), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_name", sa.String(200), nullable=False),
        sa.Column("reviewer_avatar_url", sa.String(500)),
        sa.Column("rating", sa.Numeric(3, 2)),
        sa.Column("review_title", sa.String(500)),
        sa.Column("review_text", sa.Text, nullable=False),
        sa.Column("review_date", sa.String(100)),
        sa.Column("source_platform", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(500)),
        sa.Column("verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("language", sa.String(10), nullable=False, server_default="'en'"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_product_reviews_type_id", "product_reviews", ["product_type", "product_id"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 9. Shared Product Embeddings
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "product_embeddings",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("product_type", sa.String(50), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", sa.Text, nullable=False),  # Will be vector(1536) at ORM level
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_product_embeddings_type_id", "product_embeddings", ["product_type", "product_id"], unique=True)
    # Change embedding column to vector type
    op.execute("ALTER TABLE product_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 10. Add product_type to scraping tables
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    op.add_column("source_discovery_runs", sa.Column("product_type", sa.String(50), nullable=False, server_default="activities"))
    op.add_column("scrape_sources", sa.Column("product_type", sa.String(50), nullable=False, server_default="activities"))
    op.add_column("scrape_jobs", sa.Column("product_type", sa.String(50), nullable=False, server_default="activities"))


def downgrade() -> None:
    # Remove product_type from scraping tables
    op.drop_column("scrape_jobs", "product_type")
    op.drop_column("scrape_sources", "product_type")
    op.drop_column("source_discovery_runs", "product_type")

    # Drop new tables
    op.drop_table("product_embeddings")
    op.drop_table("product_reviews")
    op.drop_table("catalog_cruise_pricing_tiers")
    op.drop_table("catalog_cruise_cabins")
    op.drop_table("catalog_cruise_itinerary")
    op.drop_table("catalog_cruise_products")
    op.drop_table("catalog_activity_timeline")
    op.drop_table("activities")

    # Note: downgrade does NOT recreate the old activities/reviews/embeddings tables.
    # This is a destructive migration.
