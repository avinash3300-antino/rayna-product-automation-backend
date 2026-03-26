import uuid

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class AuditAuditLog(Base):
    __tablename__ = "audit_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("auth_users.id"))
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    old_data = mapped_column(JSON)
    new_data = mapped_column(JSON)
    metadata_ = mapped_column("metadata", JSON)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    actor = relationship("AuthUser", foreign_keys=[actor_user_id])
