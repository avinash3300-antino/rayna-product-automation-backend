import logging
import re
import secrets
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_db, require_role
from app.core.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.db.models.audit import AuditAuditLog
from app.db.models.auth import AuthUser
from app.schemas.users import (
    AuditLogResponse,
    PaginatedResponse,
    PasswordChange,
    ProfileUpdate,
    RoleResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services import cloudinary_service, user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

ADMIN_ROLES = ("admin",)
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^a-zA-Z\d]).{8,}$")


def _build_user_response(user: AuthUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        job_title=user.job_title,
        department=user.department,
        phone=user.phone,
        timezone=user.timezone,
        profile_picture_url=user.profile_picture_url,
        status=user.status,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=[RoleResponse.model_validate(ur.role) for ur in user.user_roles],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /me routes — MUST come before /{user_id} to avoid path collision
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/me/activity", response_model=PaginatedResponse[AuditLogResponse])
async def my_activity(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    action_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
):
    query = select(AuditAuditLog).where(AuditAuditLog.actor_user_id == current_user.id)
    count_q = select(sa_func.count(AuditAuditLog.id)).where(AuditAuditLog.actor_user_id == current_user.id)

    if action_type:
        query = query.where(AuditAuditLog.action == action_type)
        count_q = count_q.where(AuditAuditLog.action == action_type)
    if date_from:
        query = query.where(AuditAuditLog.created_at >= date_from)
        count_q = count_q.where(AuditAuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditAuditLog.created_at <= date_to)
        count_q = count_q.where(AuditAuditLog.created_at <= date_to)

    total = (await db.execute(count_q)).scalar_one()
    query = query.order_by(AuditAuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    logs = (await db.execute(query)).scalars().all()

    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.patch("/me/profile", response_model=UserResponse)
async def update_profile(
    body: ProfileUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    old_data = user_service.user_to_dict(current_user)

    for field, value in data.items():
        setattr(current_user, field, value)

    await user_service.write_audit(
        db, current_user.id, "auth_users", current_user.id, "updated", old_data, data,
    )
    await db.commit()

    user = await user_service.get_user_by_id(db, current_user.id)
    return _build_user_response(user)


@router.patch("/me/password")
async def change_password(
    body: PasswordChange,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise UnauthorizedError("Current password is incorrect")
    if body.new_password != body.confirm_password:
        raise BadRequestError("Passwords do not match")
    if not PASSWORD_PATTERN.match(body.new_password):
        raise BadRequestError(
            "Password must be at least 8 characters with uppercase, lowercase, number, and special character"
        )

    current_user.password_hash = hash_password(body.new_password)
    await user_service.write_audit(
        db, current_user.id, "auth_users", current_user.id, "password_changed", None, None,
    )
    await db.commit()
    return {"message": "Password updated"}


@router.post("/me/profile-picture", response_model=UserResponse)
async def upload_profile_picture(
    file: UploadFile,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    try:
        url = await cloudinary_service.upload_profile_picture(file, str(current_user.id))
    except ValueError as e:
        raise BadRequestError(str(e))

    old_data = user_service.user_to_dict(current_user)
    current_user.profile_picture_url = url

    await user_service.write_audit(
        db, current_user.id, "auth_users", current_user.id,
        "profile_picture_updated", old_data, {"profile_picture_url": url},
    )
    await db.commit()

    user = await user_service.get_user_by_id(db, current_user.id)
    return _build_user_response(user)


@router.delete("/me/profile-picture", response_model=UserResponse)
async def delete_profile_picture(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if not current_user.profile_picture_url:
        raise BadRequestError("No profile picture to delete")

    old_data = user_service.user_to_dict(current_user)
    await cloudinary_service.delete_profile_picture(str(current_user.id))
    current_user.profile_picture_url = None

    await user_service.write_audit(
        db, current_user.id, "auth_users", current_user.id,
        "profile_picture_deleted", old_data, {"profile_picture_url": None},
    )
    await db.commit()

    user = await user_service.get_user_by_id(db, current_user.id)
    return _build_user_response(user)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Admin routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
    search: str | None = Query(None),
    status: str | None = Query(None),
    role: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    users, total = await user_service.list_users(db, search, status, role, page, per_page)
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        items=[_build_user_response(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.post("/invite", response_model=UserResponse, status_code=201)
async def invite_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
):
    user, _temp_pw = await user_service.create_user(
        db,
        full_name=body.full_name,
        email=body.email,
        role_codes=body.roles,
        created_by=current_user.id,
    )
    return _build_user_response(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
):
    user = await user_service.get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found")
    return _build_user_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
):
    data = body.model_dump(exclude_unset=True)
    user = await user_service.update_user(db, user_id, data, current_user.id)
    return _build_user_response(user)


@router.patch("/{user_id}/password-reset")
async def reset_password(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
):
    user = await user_service.get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found")

    temp_pw = secrets.token_urlsafe(12)
    logger.info("Password reset for %s: %s", user.email, temp_pw)

    user.password_hash = hash_password(temp_pw)
    await user_service.write_audit(
        db, current_user.id, "auth_users", user_id, "password_reset", None, None,
    )
    await db.commit()
    return {"message": "Password reset. Temp password logged."}
