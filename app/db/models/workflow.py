import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class WorkflowClassificationResult(Base):
    __tablename__ = "workflow_classification_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    raw_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_raw_records.id"), unique=True, nullable=False)
    classifier_model: Mapped[str] = mapped_column(String, nullable=False)
    predicted_category: Mapped[str] = mapped_column(String, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    routing_action: Mapped[str] = mapped_column(String, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    raw_record = relationship("IngestionRawRecord", foreign_keys=[raw_record_id])
    review_queue: Mapped["WorkflowClassificationReviewQueue | None"] = relationship(back_populates="classification_result", uselist=False)


class WorkflowClassificationReviewQueue(Base):
    __tablename__ = "workflow_classification_review_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    raw_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_raw_records.id"), unique=True, nullable=False)
    classification_result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_classification_results.id"), nullable=False)
    queue_status: Mapped[str] = mapped_column(String, nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    final_category: Mapped[str | None] = mapped_column(String)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    raw_record = relationship("IngestionRawRecord", foreign_keys=[raw_record_id])
    classification_result: Mapped["WorkflowClassificationResult"] = relationship(back_populates="review_queue")
    assignee = relationship("AuthUser", foreign_keys=[assigned_to])
    reviewer = relationship("AuthUser", foreign_keys=[reviewed_by])
    review_actions: Mapped[list["WorkflowClassificationReviewAction"]] = relationship(back_populates="review_queue")


class WorkflowClassificationReviewAction(Base):
    __tablename__ = "workflow_classification_review_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    classification_review_queue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_classification_review_queue.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    action_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String)
    new_status: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    review_queue: Mapped["WorkflowClassificationReviewQueue"] = relationship(back_populates="review_actions")
    actor = relationship("AuthUser", foreign_keys=[action_by])


class WorkflowAttributeMappingRun(Base):
    __tablename__ = "workflow_attribute_mapping_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    raw_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_raw_records.id"), unique=True, nullable=False)
    classification_result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_classification_results.id"), nullable=False)
    target_category: Mapped[str] = mapped_column(String, nullable=False)
    mapping_status: Mapped[str] = mapped_column(String, nullable=False)
    required_fields_count: Mapped[int | None] = mapped_column(Integer)
    mapped_fields_count: Mapped[int | None] = mapped_column(Integer)
    missing_fields_count: Mapped[int | None] = mapped_column(Integer)
    completeness_pct: Mapped[float | None] = mapped_column(Numeric)
    mapped_payload = mapped_column(JSON)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    raw_record = relationship("IngestionRawRecord", foreign_keys=[raw_record_id])
    classification_result = relationship("WorkflowClassificationResult", foreign_keys=[classification_result_id])
    enrichment_queue: Mapped["WorkflowAttributeEnrichmentQueue | None"] = relationship(back_populates="attribute_mapping_run", uselist=False)


class WorkflowAttributeEnrichmentQueue(Base):
    __tablename__ = "workflow_attribute_enrichment_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    raw_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_raw_records.id"), unique=True, nullable=False)
    attribute_mapping_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_attribute_mapping_runs.id"), nullable=False)
    queue_status: Mapped[str] = mapped_column(String, nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_at = mapped_column(DateTime(timezone=True))
    missing_fields = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    raw_record = relationship("IngestionRawRecord", foreign_keys=[raw_record_id])
    attribute_mapping_run: Mapped["WorkflowAttributeMappingRun"] = relationship(back_populates="enrichment_queue")
    assignee = relationship("AuthUser", foreign_keys=[assigned_to])
    reviewer = relationship("AuthUser", foreign_keys=[reviewed_by])
