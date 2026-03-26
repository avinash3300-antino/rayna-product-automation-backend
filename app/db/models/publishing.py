import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class PublishingPushBatch(Base):
    __tablename__ = "publishing_push_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=False)
    environment: Mapped[str] = mapped_column(String, nullable=False)
    batch_status: Mapped[str] = mapped_column(String, nullable=False)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    triggered_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = mapped_column(DateTime(timezone=True))
    records_created: Mapped[int | None] = mapped_column(Integer)
    records_updated: Mapped[int | None] = mapped_column(Integer)
    records_failed: Mapped[int | None] = mapped_column(Integer)

    job = relationship("IngestionJob", foreign_keys=[job_id])
    trigger_user = relationship("AuthUser", foreign_keys=[triggered_by])
    approver = relationship("AuthUser", foreign_keys=[approved_by])
    items: Mapped[list["PublishingPushBatchItem"]] = relationship(back_populates="push_batch")
    approval: Mapped["PublishingBatchApproval | None"] = relationship(back_populates="push_batch", uselist=False)
    rollback_batches: Mapped[list["PublishingRollbackBatch"]] = relationship(back_populates="original_push_batch")


class PublishingPushBatchItem(Base):
    __tablename__ = "publishing_push_batch_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    push_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publishing_push_batches.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    external_record_id: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    push_batch: Mapped["PublishingPushBatch"] = relationship(back_populates="items")


class PublishingBatchApproval(Base):
    __tablename__ = "publishing_batch_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    push_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publishing_push_batches.id"), unique=True, nullable=False)
    approval_status: Mapped[str] = mapped_column(String, nullable=False)
    diff_summary = mapped_column(JSON)
    approval_notes: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    approved_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    push_batch: Mapped["PublishingPushBatch"] = relationship(back_populates="approval")
    approver = relationship("AuthUser", foreign_keys=[approved_by])


class PublishingRollbackBatch(Base):
    __tablename__ = "publishing_rollback_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    original_push_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publishing_push_batches.id"), nullable=False)
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    initiated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reason: Mapped[str | None] = mapped_column(Text)
    rollback_status: Mapped[str] = mapped_column(String, nullable=False)
    completed_at = mapped_column(DateTime(timezone=True))

    original_push_batch: Mapped["PublishingPushBatch"] = relationship(back_populates="rollback_batches")
    initiator = relationship("AuthUser", foreign_keys=[initiated_by])
    items: Mapped[list["PublishingRollbackBatchItem"]] = relationship(back_populates="rollback_batch")


class PublishingRollbackBatchItem(Base):
    __tablename__ = "publishing_rollback_batch_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    rollback_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publishing_rollback_batches.id"), nullable=False)
    push_batch_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publishing_push_batch_items.id"), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rollback_action: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String)
    completed_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rollback_batch: Mapped["PublishingRollbackBatch"] = relationship(back_populates="items")
    push_batch_item = relationship("PublishingPushBatchItem", foreign_keys=[push_batch_item_id])
