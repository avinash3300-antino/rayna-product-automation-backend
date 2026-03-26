import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CatalogAttractionProduct(Base):
    __tablename__ = "catalog_attraction_products"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), primary_key=True)
    attraction_type: Mapped[str | None] = mapped_column(String)
    address_text: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Numeric)
    longitude: Mapped[float | None] = mapped_column(Numeric)
    typical_visit_duration: Mapped[str | None] = mapped_column(String)
    minimum_age: Mapped[int | None] = mapped_column(Integer)
    ticket_price_from: Mapped[float | None] = mapped_column(Numeric)
    ticket_price_to: Mapped[float | None] = mapped_column(Numeric)
    currency_code: Mapped[str | None] = mapped_column(String)
    includes_text: Mapped[str | None] = mapped_column(Text)
    excludes_text: Mapped[str | None] = mapped_column(Text)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    product = relationship("CatalogProduct", back_populates="attraction_detail")
    operating_hours: Mapped[list["CatalogAttractionOperatingHours"]] = relationship(back_populates="attraction_product")
    ticket_types: Mapped[list["CatalogAttractionTicketType"]] = relationship(back_populates="attraction_product")


class CatalogAttractionOperatingHours(Base):
    __tablename__ = "catalog_attraction_operating_hours"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    attraction_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_attraction_products.product_id"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    open_time = mapped_column(Time)
    close_time = mapped_column(Time)
    closed_flag: Mapped[bool | None] = mapped_column(Boolean)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    attraction_product: Mapped["CatalogAttractionProduct"] = relationship(back_populates="operating_hours")


class CatalogAttractionTicketType(Base):
    __tablename__ = "catalog_attraction_ticket_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    attraction_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_attraction_products.product_id"), nullable=False)
    ticket_type: Mapped[str] = mapped_column(String, nullable=False)
    price_from: Mapped[float | None] = mapped_column(Numeric)
    price_to: Mapped[float | None] = mapped_column(Numeric)
    currency_code: Mapped[str | None] = mapped_column(String)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    attraction_product: Mapped["CatalogAttractionProduct"] = relationship(back_populates="ticket_types")
