from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SessionResponse(BaseModel):
    id: UUID
    device: str | None = None
    browser: str | None = None
    ip: str | None = None
    location: str | None = None
    last_active: datetime
    is_current: bool = False

    model_config = {"from_attributes": True}
