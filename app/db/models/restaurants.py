import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CatalogRestaurantProduct(Base):
    __tablename__ = "catalog_restaurant_products"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), primary_key=True)
    cuisine_type_summary: Mapped[str | None] = mapped_column(Text)
    address_text: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Numeric)
    longitude: Mapped[float | None] = mapped_column(Numeric)
    price_range: Mapped[str | None] = mapped_column(String)
    avg_spend_per_person: Mapped[float | None] = mapped_column(Numeric)
    currency_code: Mapped[str | None] = mapped_column(String)
    reservation_required: Mapped[bool | None] = mapped_column(Boolean)
    halal_certified: Mapped[str | None] = mapped_column(String)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    product = relationship("CatalogProduct", back_populates="restaurant_detail")
    cuisines: Mapped[list["CatalogRestaurantProductCuisine"]] = relationship(back_populates="restaurant_product")
    operating_hours: Mapped[list["CatalogRestaurantOperatingHours"]] = relationship(back_populates="restaurant_product")


class CatalogRestaurantCuisinesMaster(Base):
    __tablename__ = "catalog_restaurant_cuisines_master"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class CatalogRestaurantProductCuisine(Base):
    __tablename__ = "catalog_restaurant_product_cuisines"

    restaurant_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_restaurant_products.product_id"), primary_key=True)
    cuisine_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_restaurant_cuisines_master.id"), primary_key=True)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    restaurant_product: Mapped["CatalogRestaurantProduct"] = relationship(back_populates="cuisines")
    cuisine: Mapped["CatalogRestaurantCuisinesMaster"] = relationship()


class CatalogRestaurantOperatingHours(Base):
    __tablename__ = "catalog_restaurant_operating_hours"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    restaurant_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_restaurant_products.product_id"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    open_time = mapped_column(Time)
    close_time = mapped_column(Time)
    closed_flag: Mapped[bool | None] = mapped_column(Boolean)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    restaurant_product: Mapped["CatalogRestaurantProduct"] = relationship(back_populates="operating_hours")
