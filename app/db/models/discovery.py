import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class AIDiscoveryRun(Base):
    __tablename__ = "ai_discovery_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    triggered_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"), nullable=False)
    raw_input: Mapped[str] = mapped_column(String, nullable=False)
    confirmed_destination_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"))
    destination_search_status: Mapped[str] = mapped_column(String, nullable=False)
    seed_generation_status: Mapped[str | None] = mapped_column(String)
    categories_requested = mapped_column(ARRAY(String), nullable=False)
    ai_model_used: Mapped[str | None] = mapped_column(String)
    ahrefs_used: Mapped[bool | None] = mapped_column(Boolean)
    approved_sources_used: Mapped[bool | None] = mapped_column(Boolean)
    total_items_generated: Mapped[int | None] = mapped_column(Integer)
    total_items_approved: Mapped[int | None] = mapped_column(Integer)
    total_items_rejected: Mapped[int | None] = mapped_column(Integer)
    total_items_pushed: Mapped[int | None] = mapped_column(Integer)
    run_status: Mapped[str] = mapped_column(String, nullable=False)
    started_at = mapped_column(DateTime(timezone=True))
    seed_generation_started_at = mapped_column(DateTime(timezone=True))
    seed_generation_completed_at = mapped_column(DateTime(timezone=True))
    pm_review_started_at = mapped_column(DateTime(timezone=True))
    completed_at = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    triggered_by_user = relationship("AuthUser", foreign_keys=[triggered_by])
    confirmed_destination = relationship("CatalogDestination", foreign_keys=[confirmed_destination_id])
    destination_candidates: Mapped[list["AIDiscoveryDestinationCandidate"]] = relationship(back_populates="discovery_run")
    seed_items: Mapped[list["AIDiscoverySeedItem"]] = relationship(back_populates="discovery_run")
    review_actions: Mapped[list["AIDiscoveryReviewAction"]] = relationship(back_populates="discovery_run")


class AIDiscoveryDestinationCandidate(Base):
    __tablename__ = "ai_discovery_destination_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    discovery_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_discovery_runs.id"), nullable=False)
    candidate_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    destination_name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String)
    timezone: Mapped[str | None] = mapped_column(String)
    latitude: Mapped[float | None] = mapped_column(Numeric)
    longitude: Mapped[float | None] = mapped_column(Numeric)
    ai_confidence_score: Mapped[float | None] = mapped_column(Numeric)
    ai_reasoning: Mapped[str | None] = mapped_column(Text)
    is_selected: Mapped[bool | None] = mapped_column(Boolean)
    selected_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    discovery_run: Mapped["AIDiscoveryRun"] = relationship(back_populates="destination_candidates")


class AIDiscoverySeedItem(Base):
    __tablename__ = "ai_discovery_seed_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    discovery_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_discovery_runs.id"), nullable=False)
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    area: Mapped[str | None] = mapped_column(String)
    seed_payload_json = mapped_column(JSON, nullable=False)
    ai_confidence_score: Mapped[float | None] = mapped_column(Numeric)
    ai_notes: Mapped[str | None] = mapped_column(Text)
    ahrefs_search_volume: Mapped[int | None] = mapped_column(Integer)
    ai_generation_model: Mapped[str | None] = mapped_column(String)
    sort_order: Mapped[int | None] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String, nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_at = mapped_column(DateTime(timezone=True))
    pm_edits_json = mapped_column(JSON)
    pm_notes: Mapped[str | None] = mapped_column(Text)
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_raw_records.id", use_alter=True))
    pushed_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    discovery_run: Mapped["AIDiscoveryRun"] = relationship(back_populates="seed_items")
    destination = relationship("CatalogDestination")
    reviewer = relationship("AuthUser", foreign_keys=[reviewed_by])
    raw_record = relationship("IngestionRawRecord", foreign_keys=[raw_record_id])
    review_actions: Mapped[list["AIDiscoveryReviewAction"]] = relationship(back_populates="seed_item")


class AIDiscoveryReviewAction(Base):
    __tablename__ = "ai_discovery_review_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    discovery_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_discovery_runs.id"), nullable=False)
    seed_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_discovery_seed_items.id"))
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    action_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"), nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    item_count: Mapped[int | None] = mapped_column(Integer)
    old_values = mapped_column(JSON)
    new_values = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    discovery_run: Mapped["AIDiscoveryRun"] = relationship(back_populates="review_actions")
    seed_item: Mapped["AIDiscoverySeedItem | None"] = relationship(back_populates="review_actions")
    actor = relationship("AuthUser", foreign_keys=[action_by])
