import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class CatalogTagDimension(Base):
    __tablename__ = "catalog_tag_dimensions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int | None] = mapped_column(Integer)

    tags: Mapped[list["CatalogTag"]] = relationship(back_populates="dimension")


class CatalogTag(Base):
    __tablename__ = "catalog_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    dimension_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_tag_dimensions.id"), nullable=False)
    parent_tag_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_tags.id"))
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    dimension: Mapped["CatalogTagDimension"] = relationship(back_populates="tags")
    parent_tag: Mapped["CatalogTag | None"] = relationship(remote_side=[id])
    children: Mapped[list["CatalogTag"]] = relationship(back_populates="parent_tag")


class CatalogProductTag(Base):
    __tablename__ = "catalog_product_tags"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_tags.id"), primary_key=True)
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    assigned_method: Mapped[str] = mapped_column(String, nullable=False)
    assigned_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product = relationship("CatalogProduct", foreign_keys=[product_id])
    tag = relationship("CatalogTag", foreign_keys=[tag_id])
    assigned_by_user = relationship("AuthUser", foreign_keys=[assigned_by_user_id])


class CatalogProductTagSuggestion(Base):
    __tablename__ = "catalog_product_tag_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_tags.id"), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Numeric)
    suggestion_source: Mapped[str | None] = mapped_column(String)
    suggestion_status: Mapped[str | None] = mapped_column(String)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    reviewed_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product = relationship("CatalogProduct", foreign_keys=[product_id])
    tag = relationship("CatalogTag", foreign_keys=[tag_id])
    reviewer = relationship("AuthUser", foreign_keys=[reviewed_by])
