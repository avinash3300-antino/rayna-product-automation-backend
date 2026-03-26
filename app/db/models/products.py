import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CatalogProduct(Base):
    __tablename__ = "catalog_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str | None] = mapped_column(String, unique=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_sources.id"))
    source_record_key: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)
    publish_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    data_confidence: Mapped[float | None] = mapped_column(Numeric)
    attribute_completeness_pct: Mapped[float | None] = mapped_column(Numeric)
    created_by_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"))
    last_updated_by_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"))
    dedupe_hash: Mapped[str | None] = mapped_column(String)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    destination = relationship("CatalogDestination", foreign_keys=[destination_id])
    canonical_source = relationship("IngestionSource", foreign_keys=[canonical_source_id])
    created_by_job = relationship("IngestionJob", foreign_keys=[created_by_job_id])
    last_updated_by_job = relationship("IngestionJob", foreign_keys=[last_updated_by_job_id])
    versions: Mapped[list["CatalogProductVersion"]] = relationship(back_populates="product")
    status_history: Mapped[list["CatalogProductStatusHistory"]] = relationship(back_populates="product")
    hotel_detail: Mapped["CatalogHotelProduct | None"] = relationship("CatalogHotelProduct", back_populates="product", uselist=False)
    attraction_detail: Mapped["CatalogAttractionProduct | None"] = relationship("CatalogAttractionProduct", back_populates="product", uselist=False)
    transfer_detail: Mapped["CatalogTransferProduct | None"] = relationship("CatalogTransferProduct", back_populates="product", uselist=False)
    restaurant_detail: Mapped["CatalogRestaurantProduct | None"] = relationship("CatalogRestaurantProduct", back_populates="product", uselist=False)
    media: Mapped[list["CatalogProductMedia"]] = relationship("CatalogProductMedia", back_populates="product")
    faqs: Mapped[list["CatalogProductFaq"]] = relationship("CatalogProductFaq", back_populates="product")
    schema_markup: Mapped["CatalogProductSchemaMarkup | None"] = relationship("CatalogProductSchemaMarkup", back_populates="product", uselist=False)


class CatalogProductVersion(Base):
    __tablename__ = "catalog_product_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json = mapped_column(JSON, nullable=False)
    created_by_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product: Mapped["CatalogProduct"] = relationship(back_populates="versions")
    created_by_job = relationship("IngestionJob", foreign_keys=[created_by_job_id])
    created_by_user = relationship("AuthUser", foreign_keys=[created_by_user_id])


class CatalogProductStatusHistory(Base):
    __tablename__ = "catalog_product_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String)
    new_status: Mapped[str | None] = mapped_column(String)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    changed_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reason: Mapped[str | None] = mapped_column(Text)

    product: Mapped["CatalogProduct"] = relationship(back_populates="status_history")
    changer = relationship("AuthUser", foreign_keys=[changed_by])
