import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class ContentDestinationKeywordSet(Base):
    __tablename__ = "content_destination_keyword_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    intelligence_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_destination_intelligence_runs.id"))
    keyword_set_json = mapped_column(JSON, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    destination = relationship("CatalogDestination", foreign_keys=[destination_id])
    intelligence_run = relationship("IngestionDestinationIntelligenceRun", foreign_keys=[intelligence_run_id])


class ContentProductContent(Base):
    __tablename__ = "content_product_content"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), unique=True, nullable=False)
    primary_keyword: Mapped[str | None] = mapped_column(Text)
    secondary_keywords = mapped_column(ARRAY(String))
    short_description: Mapped[str | None] = mapped_column(Text)
    long_description: Mapped[str | None] = mapped_column(Text)
    meta_title: Mapped[str | None] = mapped_column(String)
    meta_description: Mapped[str | None] = mapped_column(String)
    content_hash: Mapped[str | None] = mapped_column(String)
    seo_status: Mapped[str | None] = mapped_column(String)
    generated_by_model: Mapped[str | None] = mapped_column(String)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    approved_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    product = relationship("CatalogProduct", foreign_keys=[product_id])
    approver = relationship("AuthUser", foreign_keys=[approved_by])


class ContentContentGenerationRun(Base):
    __tablename__ = "content_content_generation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"))
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String)
    input_payload = mapped_column(JSON)
    output_payload = mapped_column(JSON)
    generation_status: Mapped[str] = mapped_column(String, nullable=False)
    regeneration_attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product = relationship("CatalogProduct", foreign_keys=[product_id])
    job = relationship("IngestionJob", foreign_keys=[job_id])


class ContentContentReviewQueue(Base):
    __tablename__ = "content_content_review_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), unique=True, nullable=False)
    content_generation_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("content_content_generation_runs.id"), nullable=False)
    queue_status: Mapped[str] = mapped_column(String, nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    product = relationship("CatalogProduct", foreign_keys=[product_id])
    content_generation_run = relationship("ContentContentGenerationRun", foreign_keys=[content_generation_run_id])
    assignee = relationship("AuthUser", foreign_keys=[assigned_to])
    reviewer = relationship("AuthUser", foreign_keys=[reviewed_by])
    review_actions: Mapped[list["ContentContentReviewAction"]] = relationship(back_populates="review_queue")


class ContentContentReviewAction(Base):
    __tablename__ = "content_content_review_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    content_review_queue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("content_content_review_queue.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    action_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String)
    new_status: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    regeneration_attempt: Mapped[int | None] = mapped_column(Integer)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    review_queue: Mapped["ContentContentReviewQueue"] = relationship(back_populates="review_actions")
    actor = relationship("AuthUser", foreign_keys=[action_by])
