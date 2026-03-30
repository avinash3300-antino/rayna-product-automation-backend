import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class AuthUserSession(Base):
    __tablename__ = "auth_user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device: Mapped[str | None] = mapped_column(String(255))
    browser: Mapped[str | None] = mapped_column(String(255))
    os: Mapped[str | None] = mapped_column(String(255))
    user_agent_raw: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    location: Mapped[str | None] = mapped_column(String(255))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_active_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["AuthUser"] = relationship(back_populates="sessions", foreign_keys=[user_id])
