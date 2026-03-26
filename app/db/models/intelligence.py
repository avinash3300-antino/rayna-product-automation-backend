import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class IngestionDestinationIntelligenceRun(Base):
    __tablename__ = "ingestion_destination_intelligence_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    trigger_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at = mapped_column(DateTime(timezone=True))
    completed_at = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    approved_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    destination = relationship("CatalogDestination", foreign_keys=[destination_id])
    trigger_user = relationship("AuthUser", foreign_keys=[triggered_by])
    approver = relationship("AuthUser", foreign_keys=[approved_by])
    keywords: Mapped[list["IngestionDestinationKeyword"]] = relationship(back_populates="intelligence_run")
    paa_questions: Mapped[list["IngestionDestinationPaaQuestion"]] = relationship(back_populates="intelligence_run")
    discovery_candidates: Mapped[list["IngestionSourceDiscoveryCandidate"]] = relationship(back_populates="intelligence_run")
    approved_source_list: Mapped["IngestionApprovedSourceList | None"] = relationship(back_populates="intelligence_run", uselist=False)


class IngestionDestinationKeyword(Base):
    __tablename__ = "ingestion_destination_keywords"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    intelligence_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_destination_intelligence_runs.id"), nullable=False)
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    product_category: Mapped[str] = mapped_column(String, nullable=False)
    search_intent: Mapped[str | None] = mapped_column(String)
    search_volume: Mapped[int | None] = mapped_column(Integer)
    keyword_difficulty: Mapped[float | None] = mapped_column(Numeric)
    ctr_estimate: Mapped[float | None] = mapped_column(Numeric)
    rank_order: Mapped[int | None] = mapped_column(Integer)
    peak_months = mapped_column(ARRAY(String))
    off_peak_months = mapped_column(ARRAY(String))
    seasonal_trend_json = mapped_column(JSON)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    intelligence_run: Mapped["IngestionDestinationIntelligenceRun"] = relationship(back_populates="keywords")
    destination = relationship("CatalogDestination", foreign_keys=[destination_id])


class IngestionDestinationPaaQuestion(Base):
    __tablename__ = "ingestion_destination_paa_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    intelligence_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_destination_intelligence_runs.id"), nullable=False)
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rank_order: Mapped[int | None] = mapped_column(Integer)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    intelligence_run: Mapped["IngestionDestinationIntelligenceRun"] = relationship(back_populates="paa_questions")
    destination = relationship("CatalogDestination", foreign_keys=[destination_id])


class IngestionSourceDiscoveryCandidate(Base):
    __tablename__ = "ingestion_source_discovery_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    intelligence_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_destination_intelligence_runs.id"), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String)
    website_url: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(String)
    domain_authority: Mapped[float | None] = mapped_column(Numeric)
    keyword_overlap_pct: Mapped[float | None] = mapped_column(Numeric)
    data_structure_score: Mapped[float | None] = mapped_column(Numeric)
    freshness_score: Mapped[float | None] = mapped_column(Numeric)
    tos_status: Mapped[str | None] = mapped_column(String)
    overall_score: Mapped[float | None] = mapped_column(Numeric)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    intelligence_run: Mapped["IngestionDestinationIntelligenceRun"] = relationship(back_populates="discovery_candidates")


class IngestionApprovedSourceList(Base):
    __tablename__ = "ingestion_approved_source_lists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    intelligence_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_destination_intelligence_runs.id"), unique=True, nullable=False)
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    approved_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    intelligence_run: Mapped["IngestionDestinationIntelligenceRun"] = relationship(back_populates="approved_source_list")
    destination = relationship("CatalogDestination", foreign_keys=[destination_id])
    approver = relationship("AuthUser", foreign_keys=[approved_by])
    items: Mapped[list["IngestionApprovedSourceListItem"]] = relationship(back_populates="approved_source_list")
    audits: Mapped[list["IngestionApprovedSourceListAudit"]] = relationship(back_populates="approved_source_list")


class IngestionApprovedSourceListItem(Base):
    __tablename__ = "ingestion_approved_source_list_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    approved_source_list_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_approved_source_lists.id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_sources.id"), nullable=False)
    product_category: Mapped[str] = mapped_column(String, nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Numeric)
    tos_status: Mapped[str | None] = mapped_column(String)
    ingestion_method: Mapped[str | None] = mapped_column(String)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    approved_source_list: Mapped["IngestionApprovedSourceList"] = relationship(back_populates="items")
    source = relationship("IngestionSource", foreign_keys=[source_id])


class IngestionApprovedSourceListAudit(Base):
    __tablename__ = "ingestion_approved_source_list_audit"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    approved_source_list_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_approved_source_lists.id"), nullable=False)
    source_list_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_approved_source_list_items.id"))
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    old_priority_rank: Mapped[int | None] = mapped_column(Integer)
    new_priority_rank: Mapped[int | None] = mapped_column(Integer)
    old_values = mapped_column(JSON)
    new_values = mapped_column(JSON)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    changed_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    approved_source_list: Mapped["IngestionApprovedSourceList"] = relationship(back_populates="audits")
    source_list_item = relationship("IngestionApprovedSourceListItem", foreign_keys=[source_list_item_id])
    changer = relationship("AuthUser", foreign_keys=[changed_by])
