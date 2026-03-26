import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    intelligence_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_destination_intelligence_runs.id"))
    ai_discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_discovery_runs.id"))
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    trigger_type: Mapped[str] = mapped_column(String, nullable=False)
    run_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at = mapped_column(DateTime(timezone=True))
    completed_at = mapped_column(DateTime(timezone=True))
    total_records_fetched: Mapped[int | None] = mapped_column(Integer)
    total_errors: Mapped[int | None] = mapped_column(Integer)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    destination = relationship("CatalogDestination", foreign_keys=[destination_id])
    intelligence_run = relationship("IngestionDestinationIntelligenceRun", foreign_keys=[intelligence_run_id])
    ai_discovery_run = relationship("AIDiscoveryRun", foreign_keys=[ai_discovery_run_id])
    trigger_user = relationship("AuthUser", foreign_keys=[triggered_by])
    job_sources: Mapped[list["IngestionJobSource"]] = relationship(back_populates="job")
    raw_records: Mapped[list["IngestionRawRecord"]] = relationship(back_populates="job")


class IngestionJobSource(Base):
    __tablename__ = "ingestion_job_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_sources.id"), nullable=False)
    product_category: Mapped[str] = mapped_column(String, nullable=False)
    priority_rank: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False)
    records_fetched: Mapped[int | None] = mapped_column(Integer)
    errors_count: Mapped[int | None] = mapped_column(Integer)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    job: Mapped["IngestionJob"] = relationship(back_populates="job_sources")
    source = relationship("IngestionSource", foreign_keys=[source_id])


class IngestionRawRecord(Base):
    __tablename__ = "ingestion_raw_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=False)
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_sources.id"), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String)
    source_url: Mapped[str | None] = mapped_column(Text)
    product_category_predicted: Mapped[str | None] = mapped_column(String)
    raw_payload = mapped_column(JSON)
    normalized_payload = mapped_column(JSON)
    data_confidence: Mapped[float | None] = mapped_column(Numeric)
    tos_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    dedupe_hash: Mapped[str | None] = mapped_column(String)
    ingestion_status: Mapped[str] = mapped_column(String, nullable=False)
    ingestion_origin: Mapped[str | None] = mapped_column(String)
    ai_discovery_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_discovery_seed_items.id", use_alter=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    job: Mapped["IngestionJob"] = relationship(back_populates="raw_records")
    destination = relationship("CatalogDestination", foreign_keys=[destination_id])
    source = relationship("IngestionSource", foreign_keys=[source_id])
    ai_discovery_item = relationship("AIDiscoverySeedItem", foreign_keys=[ai_discovery_item_id])
    media: Mapped[list["IngestionRawRecordMedia"]] = relationship(back_populates="raw_record")


class IngestionRawRecordMedia(Base):
    __tablename__ = "ingestion_raw_record_media"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    raw_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_raw_records.id"), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String)
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int | None] = mapped_column(Integer)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    raw_record: Mapped["IngestionRawRecord"] = relationship(back_populates="media")
