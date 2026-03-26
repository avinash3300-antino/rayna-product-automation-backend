import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CatalogHotelProduct(Base):
    __tablename__ = "catalog_hotel_products"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), primary_key=True)
    star_rating: Mapped[int | None] = mapped_column(Integer)
    property_type: Mapped[str | None] = mapped_column(String)
    address_text: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Numeric)
    longitude: Mapped[float | None] = mapped_column(Numeric)
    check_in_time = mapped_column(Time)
    check_out_time = mapped_column(Time)
    cancellation_policy: Mapped[str | None] = mapped_column(String)
    net_rate_from: Mapped[float | None] = mapped_column(Numeric)
    currency_code: Mapped[str | None] = mapped_column(String)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    product = relationship("CatalogProduct", back_populates="hotel_detail")
    room_types: Mapped[list["CatalogHotelRoomType"]] = relationship(back_populates="hotel_product")
    board_types: Mapped[list["CatalogHotelBoardType"]] = relationship(back_populates="hotel_product")
    amenities: Mapped[list["CatalogHotelProductAmenity"]] = relationship(back_populates="hotel_product")


class CatalogHotelRoomType(Base):
    __tablename__ = "catalog_hotel_room_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    hotel_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_hotel_products.product_id"), nullable=False)
    room_type: Mapped[str] = mapped_column(String, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    hotel_product: Mapped["CatalogHotelProduct"] = relationship(back_populates="room_types")


class CatalogHotelBoardType(Base):
    __tablename__ = "catalog_hotel_board_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    hotel_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_hotel_products.product_id"), nullable=False)
    board_type: Mapped[str] = mapped_column(String, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    hotel_product: Mapped["CatalogHotelProduct"] = relationship(back_populates="board_types")


class CatalogHotelAmenitiesMaster(Base):
    __tablename__ = "catalog_hotel_amenities_master"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)


class CatalogHotelProductAmenity(Base):
    __tablename__ = "catalog_hotel_product_amenities"

    hotel_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_hotel_products.product_id"), primary_key=True)
    amenity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_hotel_amenities_master.id"), primary_key=True)
    assigned_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    hotel_product: Mapped["CatalogHotelProduct"] = relationship(back_populates="amenities")
    amenity: Mapped["CatalogHotelAmenitiesMaster"] = relationship()
