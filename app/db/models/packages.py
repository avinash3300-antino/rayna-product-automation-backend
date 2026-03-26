import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class PricingPackageType(Base):
    __tablename__ = "pricing_package_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    default_margin_pct: Mapped[float | None] = mapped_column(Numeric)
    min_nights: Mapped[int | None] = mapped_column(Integer)
    max_nights: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    rules: Mapped[list["PricingPackageRule"]] = relationship(back_populates="package_type")
    packages: Mapped[list["PricingPackage"]] = relationship(back_populates="package_type")


class PricingPackageRule(Base):
    __tablename__ = "pricing_package_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    package_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_package_types.id"), nullable=False)
    rule_name: Mapped[str] = mapped_column(String, nullable=False)
    rule_json = mapped_column(JSON, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    package_type: Mapped["PricingPackageType"] = relationship(back_populates="rules")
    creator = relationship("AuthUser", foreign_keys=[created_by])


class PricingPackage(Base):
    __tablename__ = "pricing_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    destination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_destinations.id"), nullable=False)
    package_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_package_types.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str | None] = mapped_column(String, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    duration_label: Mapped[str | None] = mapped_column(String)
    nights: Mapped[int | None] = mapped_column(Integer)
    days: Mapped[int | None] = mapped_column(Integer)
    short_description: Mapped[str | None] = mapped_column(Text)
    long_description: Mapped[str | None] = mapped_column(Text)
    inclusions: Mapped[str | None] = mapped_column(Text)
    exclusions: Mapped[str | None] = mapped_column(Text)
    from_price: Mapped[float | None] = mapped_column(Numeric)
    currency_code: Mapped[str | None] = mapped_column(String)
    base_cost: Mapped[float | None] = mapped_column(Numeric)
    margin_pct: Mapped[float | None] = mapped_column(Numeric)
    floor_price: Mapped[float | None] = mapped_column(Numeric)
    display_price: Mapped[float | None] = mapped_column(Numeric)
    manual_price_override: Mapped[float | None] = mapped_column(Numeric)
    pricing_status: Mapped[str | None] = mapped_column(String)
    created_by_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    approved_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    destination = relationship("CatalogDestination", foreign_keys=[destination_id])
    package_type: Mapped["PricingPackageType"] = relationship(back_populates="packages")
    created_by_job = relationship("IngestionJob", foreign_keys=[created_by_job_id])
    approver = relationship("AuthUser", foreign_keys=[approved_by])
    components: Mapped[list["PricingPackageComponent"]] = relationship(back_populates="package")
    tags: Mapped[list["PricingPackageTag"]] = relationship(back_populates="package")
    media: Mapped[list["PricingPackageMedia"]] = relationship(back_populates="package")
    itinerary_days: Mapped[list["PricingPackageItineraryDay"]] = relationship(back_populates="package")
    generation_runs: Mapped[list["PricingPackageGenerationRun"]] = relationship(back_populates="package")
    price_calculations: Mapped[list["PricingPackagePriceCalculation"]] = relationship(back_populates="package")


class PricingPackageComponent(Base):
    __tablename__ = "pricing_package_components"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_packages.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False)
    component_type: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer)
    nights: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int | None] = mapped_column(Integer)
    pricing_basis: Mapped[str | None] = mapped_column(String)
    base_cost: Mapped[float | None] = mapped_column(Numeric)
    currency_code: Mapped[str | None] = mapped_column(String)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    package: Mapped["PricingPackage"] = relationship(back_populates="components")
    product = relationship("CatalogProduct", foreign_keys=[product_id])


class PricingPackageTag(Base):
    __tablename__ = "pricing_package_tags"

    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_packages.id"), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_tags.id"), primary_key=True)

    package: Mapped["PricingPackage"] = relationship(back_populates="tags")
    tag = relationship("CatalogTag", foreign_keys=[tag_id])


class PricingPackageMedia(Base):
    __tablename__ = "pricing_package_media"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_packages.id"), nullable=False)
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sort_order: Mapped[int | None] = mapped_column(Integer)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    package: Mapped["PricingPackage"] = relationship(back_populates="media")


class PricingPackageItineraryDay(Base):
    __tablename__ = "pricing_package_itinerary_days"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_packages.id"), nullable=False)
    day_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)

    package: Mapped["PricingPackage"] = relationship(back_populates="itinerary_days")


class PricingPackageGenerationRun(Base):
    __tablename__ = "pricing_package_generation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_packages.id"), nullable=False)
    generation_type: Mapped[str | None] = mapped_column(String)
    input_payload = mapped_column(JSON)
    output_payload = mapped_column(JSON)
    status: Mapped[str | None] = mapped_column(String)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    package: Mapped["PricingPackage"] = relationship(back_populates="generation_runs")


class PricingPackagePriceCalculation(Base):
    __tablename__ = "pricing_package_price_calculations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pricing_packages.id"), nullable=False)
    calculation_status: Mapped[str] = mapped_column(String, nullable=False)
    base_cost: Mapped[float | None] = mapped_column(Numeric)
    margin_pct: Mapped[float | None] = mapped_column(Numeric)
    floor_price: Mapped[float | None] = mapped_column(Numeric)
    display_price: Mapped[float | None] = mapped_column(Numeric)
    override_price: Mapped[float | None] = mapped_column(Numeric)
    component_snapshot = mapped_column(JSON)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    package: Mapped["PricingPackage"] = relationship(back_populates="price_calculations")
