import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class OpsFreshnessRule(Base):
    __tablename__ = "ops_freshness_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    data_type: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    threshold_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    stale_action: Mapped[str] = mapped_column(String, nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class OpsProductFreshnessStatus(Base):
    __tablename__ = "ops_product_freshness_status"
    __table_args__ = (
        UniqueConstraint("product_id", "data_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False)
    data_type: Mapped[str] = mapped_column(String, nullable=False)
    last_checked_at = mapped_column(DateTime(timezone=True))
    last_updated_at = mapped_column(DateTime(timezone=True))
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False)
    action_status: Mapped[str | None] = mapped_column(String)

    product = relationship("CatalogProduct", foreign_keys=[product_id])


class OpsProductQualityCheck(Base):
    __tablename__ = "ops_product_quality_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False)
    check_type: Mapped[str] = mapped_column(String, nullable=False)
    check_status: Mapped[str] = mapped_column(String, nullable=False)
    details_json = mapped_column(JSON)
    checked_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product = relationship("CatalogProduct", foreign_keys=[product_id])


class OpsErrorQueue(Base):
    __tablename__ = "ops_error_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"))
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    stage: Mapped[str | None] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    status: Mapped[str] = mapped_column(String, nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    job = relationship("IngestionJob", foreign_keys=[job_id])
    assignee = relationship("AuthUser", foreign_keys=[assigned_to])


class OpsJobMetrics(Base):
    __tablename__ = "ops_job_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Numeric)
    metric_unit: Mapped[str | None] = mapped_column(String)
    recorded_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    job = relationship("IngestionJob", foreign_keys=[job_id])


class OpsNotification(Base):
    __tablename__ = "ops_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"), nullable=False)
    notification_type: Mapped[str | None] = mapped_column(String)
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="unread")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("AuthUser", foreign_keys=[user_id])


class OpsApiAudit(Base):
    __tablename__ = "ops_api_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    system_name: Mapped[str] = mapped_column(String, nullable=False)
    environment: Mapped[str] = mapped_column(String, nullable=False)
    bulk_upsert_supported: Mapped[bool | None] = mapped_column(Boolean)
    idempotency_supported: Mapped[bool | None] = mapped_column(Boolean)
    rollback_supported: Mapped[bool | None] = mapped_column(Boolean)
    staging_supported: Mapped[bool | None] = mapped_column(Boolean)
    audit_status: Mapped[str] = mapped_column(String, nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_at = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    reviewer = relationship("AuthUser", foreign_keys=[reviewed_by])
