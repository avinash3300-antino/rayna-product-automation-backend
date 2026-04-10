import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class SourceDiscoveryRun(Base):
    __tablename__ = "source_discovery_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    city_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_destinations.id"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="pending"
    )
    ahrefs_results = mapped_column(JSON, nullable=True)
    searchapi_results = mapped_column(JSON, nullable=True)
    claude_synthesis = mapped_column(JSON, nullable=True)
    sources_found: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    sources_approved: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.id")
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    destination = relationship("CatalogDestination", foreign_keys=[city_id])
    trigger_user = relationship("AuthUser", foreign_keys=[triggered_by])
    sources: Mapped[list["ScrapeSource"]] = relationship(
        back_populates="discovery_run"
    )


class ScrapeSource(Base):
    __tablename__ = "scrape_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    city_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_destinations.id"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    source_name: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    authority_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.id")
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    added_by: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    last_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # FK to discovery run
    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_discovery_runs.id")
    )

    destination = relationship("CatalogDestination", foreign_keys=[city_id])
    approver = relationship("AuthUser", foreign_keys=[approved_by])
    discovery_run: Mapped["SourceDiscoveryRun | None"] = relationship(
        back_populates="sources"
    )
    jobs: Mapped[list["ScrapeJob"]] = relationship(back_populates="source")


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_discovery_runs.id")
    )
    city_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_destinations.id"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="pending"
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scrape_sources.id")
    )
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    scrape_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pages_scraped: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    records_found: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    records_saved: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    records_skipped_dup: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    records_enriched: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    errors_json = mapped_column(JSON, nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.id")
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    destination = relationship("CatalogDestination", foreign_keys=[city_id])
    source: Mapped["ScrapeSource | None"] = relationship(
        back_populates="jobs"
    )
    trigger_user = relationship("AuthUser", foreign_keys=[triggered_by])
    discovery_run = relationship(
        "SourceDiscoveryRun", foreign_keys=[discovery_run_id]
    )


class AhrefsCache(Base):
    __tablename__ = "ahrefs_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    query_term: Mapped[str] = mapped_column(String(500), nullable=False)
    city_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_destinations.id")
    )
    results_json = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SearchCache(Base):
    __tablename__ = "search_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    query_term: Mapped[str] = mapped_column(String(500), nullable=False)
    city_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_destinations.id")
    )
    results_json = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
