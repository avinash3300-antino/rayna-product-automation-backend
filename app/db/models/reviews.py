import uuid
from datetime import datetime

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class ProductReview(Base):
    """Shared reviews table for all product types (activities, cruises, yachts, etc.)."""
    __tablename__ = "product_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    product_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "activities", "cruises", "yachts", etc.
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    # ── Review Content ───────────────────────────────────────────────────
    reviewer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewer_avatar_url: Mapped[str | None] = mapped_column(String(500))
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    review_title: Mapped[str | None] = mapped_column(String(500))
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    enriched_text: Mapped[str | None] = mapped_column(Text)
    review_date: Mapped[str | None] = mapped_column(String(100))

    # ── Source ───────────────────────────────────────────────────────────
    source_platform: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # google, tripadvisor, trustpilot
    source_url: Mapped[str | None] = mapped_column(String(500))
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="'en'"
    )

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_product_reviews_type_id", "product_type", "product_id"),
    )


class ProductEmbedding(Base):
    """Shared embeddings table for semantic dedup across all product types."""
    __tablename__ = "product_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    product_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    embedding = mapped_column(
        Vector(1536) if Vector else Text, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_product_embeddings_type_id", "product_type", "product_id", unique=True),
    )
