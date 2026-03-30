from datetime import datetime
from typing import Generic, Sequence, TypeVar
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: Sequence[T]
    total: int
    page: int
    per_page: int
    total_pages: int


class RoleResponse(BaseModel):
    id: UUID
    code: str
    name: str

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    job_title: str | None = None
    department: str | None = None
    phone: str | None = None
    timezone: str | None = None
    profile_picture_url: str | None = None
    status: str
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    roles: list[RoleResponse] = []

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    roles: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    job_title: str | None = None
    status: str | None = None
    roles: list[str] | None = None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    job_title: str | None = None
    department: str | None = None
    phone: str | None = None
    timezone: str | None = None
    profile_picture_url: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
    confirm_password: str


class AuditLogResponse(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    old_data: dict | None = None
    new_data: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
