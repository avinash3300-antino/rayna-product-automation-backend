import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CatalogBookingSource(Base):
    __tablename__ = "catalog_booking_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_sources.id"))
    code: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    booking_mode: Mapped[str] = mapped_column(String, nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String)
    contact_phone: Mapped[str | None] = mapped_column(String)
    margin_priority_score: Mapped[float | None] = mapped_column(Numeric)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    source = relationship("IngestionSource", foreign_keys=[source_id])
    product_booking_sources: Mapped[list["CatalogProductBookingSource"]] = relationship(back_populates="booking_source")
    health_checks: Mapped[list["OpsBookingSourceHealthCheck"]] = relationship(back_populates="booking_source")


class CatalogProductBookingSource(Base):
    __tablename__ = "catalog_product_booking_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False)
    booking_source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_booking_sources.id"), nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String, nullable=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    assigned_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product = relationship("CatalogProduct", foreign_keys=[product_id])
    booking_source: Mapped["CatalogBookingSource"] = relationship(back_populates="product_booking_sources")
    assigner = relationship("AuthUser", foreign_keys=[assigned_by])


class OpsBookingSourceHealthCheck(Base):
    __tablename__ = "ops_booking_source_health_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    booking_source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_booking_sources.id"), nullable=False)
    health_status: Mapped[str] = mapped_column(String, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    checked_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    booking_source: Mapped["CatalogBookingSource"] = relationship(back_populates="health_checks")
