import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CatalogTransferProduct(Base):
    __tablename__ = "catalog_transfer_products"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), primary_key=True)
    transfer_type: Mapped[str | None] = mapped_column(String)
    origin_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_locations.id"))
    destination_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_locations.id"))
    vehicle_type: Mapped[str | None] = mapped_column(String)
    minimum_pax: Mapped[int | None] = mapped_column(Integer)
    maximum_pax: Mapped[int | None] = mapped_column(Integer)
    typical_duration: Mapped[str | None] = mapped_column(String)
    pricing_model: Mapped[str | None] = mapped_column(String)
    net_rate: Mapped[float | None] = mapped_column(Numeric)
    currency_code: Mapped[str | None] = mapped_column(String)
    meet_and_greet_included: Mapped[bool | None] = mapped_column(Boolean)
    twenty_four_seven_available: Mapped[bool | None] = mapped_column(Boolean)
    flight_monitoring: Mapped[bool | None] = mapped_column(Boolean)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    product = relationship("CatalogProduct", back_populates="transfer_detail")
    origin_location = relationship("CatalogLocation", foreign_keys=[origin_location_id])
    destination_location = relationship("CatalogLocation", foreign_keys=[destination_location_id])
