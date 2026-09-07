import uuid

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CatalogDestination(Base):
    __tablename__ = "catalog_destinations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[str | None] = mapped_column(String)
    country_name: Mapped[str | None] = mapped_column(String)
    country_flag: Mapped[str | None] = mapped_column(String)
    region_name: Mapped[str | None] = mapped_column(String)
    city_name: Mapped[str | None] = mapped_column(String)
    timezone: Mapped[str | None] = mapped_column(String)
    latitude: Mapped[float | None] = mapped_column(Numeric)
    longitude: Mapped[float | None] = mapped_column(Numeric)
    enabled_categories = mapped_column(JSON, server_default='["hotels","attractions","transfers","restaurants"]')
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    locations: Mapped[list["CatalogLocation"]] = relationship(back_populates="destination")


class CatalogLocation(Base):
    __tablename__ = "catalog_locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    address_text: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Numeric)
    longitude: Mapped[float | None] = mapped_column(Numeric)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    destination: Mapped["CatalogDestination"] = relationship(back_populates="locations")


class DestinationSuggestedCategory(Base):
    __tablename__ = "destination_suggested_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_destinations.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = mapped_column(DateTime(timezone=True), nullable=True)
