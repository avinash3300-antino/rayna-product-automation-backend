import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class IngestionSource(Base):
    __tablename__ = "ingestion_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_code: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str | None] = mapped_column(String)
    base_url: Mapped[str | None] = mapped_column(Text)
    ingestion_method: Mapped[str] = mapped_column(String, nullable=False)
    default_priority: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    terms_policy: Mapped["IngestionSourceTermsPolicy | None"] = relationship(back_populates="source", uselist=False)
    category_coverages: Mapped[list["IngestionSourceCategoryCoverage"]] = relationship(back_populates="source")
    legal_checklists: Mapped[list["IngestionSourceLegalChecklist"]] = relationship(back_populates="source")


class IngestionSourceTermsPolicy(Base):
    __tablename__ = "ingestion_source_terms_policy"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_sources.id"), unique=True, nullable=False)
    tos_status: Mapped[str] = mapped_column(String, nullable=False)
    review_status: Mapped[str] = mapped_column(String, nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_at = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    source: Mapped["IngestionSource"] = relationship(back_populates="terms_policy")
    reviewer = relationship("AuthUser", foreign_keys=[reviewed_by])


class IngestionSourceCategoryCoverage(Base):
    __tablename__ = "ingestion_source_category_coverage"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_sources.id"), primary_key=True)
    product_category: Mapped[str] = mapped_column(String, primary_key=True)

    source: Mapped["IngestionSource"] = relationship(back_populates="category_coverages")


class IngestionSourceLegalChecklist(Base):
    __tablename__ = "ingestion_source_legal_checklists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_sources.id"), nullable=False)
    checklist_status: Mapped[str] = mapped_column(String, nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_at = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    source: Mapped["IngestionSource"] = relationship(back_populates="legal_checklists")
    reviewer = relationship("AuthUser", foreign_keys=[reviewed_by])
    items: Mapped[list["IngestionSourceLegalChecklistItem"]] = relationship(back_populates="legal_checklist")


class IngestionSourceLegalChecklistItem(Base):
    __tablename__ = "ingestion_source_legal_checklist_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    legal_checklist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_source_legal_checklists.id"), nullable=False)
    item_code: Mapped[str] = mapped_column(String, nullable=False)
    item_label: Mapped[str] = mapped_column(String, nullable=False)
    item_status: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    legal_checklist: Mapped["IngestionSourceLegalChecklist"] = relationship(back_populates="items")
