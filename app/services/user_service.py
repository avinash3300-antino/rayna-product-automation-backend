import logging
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.db.models.audit import AuditAuditLog
from app.db.models.auth import AuthRole, AuthUser, AuthUserRole

logger = logging.getLogger(__name__)


async def get_user_by_email(db: AsyncSession, email: str) -> AuthUser | None:
    result = await db.execute(
        select(AuthUser)
        .options(selectinload(AuthUser.user_roles).selectinload(AuthUserRole.role))
        .where(AuthUser.email == email)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> AuthUser | None:
    result = await db.execute(
        select(AuthUser)
        .options(selectinload(AuthUser.user_roles).selectinload(AuthUserRole.role))
        .where(AuthUser.id == user_id)
    )
    return result.scalar_one_or_none()


def get_user_roles(user: AuthUser) -> list[str]:
    return [ur.role.code for ur in user.user_roles]


def user_to_dict(user: AuthUser) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "job_title": user.job_title,
        "department": user.department,
        "phone": user.phone,
        "timezone": user.timezone,
        "status": user.status,
    }


async def list_users(
    db: AsyncSession,
    search: str | None = None,
    status: str | None = None,
    role: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[AuthUser], int]:
    query = (
        select(AuthUser)
        .options(selectinload(AuthUser.user_roles).selectinload(AuthUserRole.role))
    )
    count_query = select(func.count(AuthUser.id))

    if search:
        pattern = f"%{search}%"
        query = query.where(
            (AuthUser.full_name.ilike(pattern)) | (AuthUser.email.ilike(pattern))
        )
        count_query = count_query.where(
            (AuthUser.full_name.ilike(pattern)) | (AuthUser.email.ilike(pattern))
        )

    if status:
        query = query.where(AuthUser.status == status)
        count_query = count_query.where(AuthUser.status == status)

    if role:
        query = query.join(AuthUser.user_roles).join(AuthUserRole.role).where(AuthRole.code == role)
        count_query = count_query.join(AuthUser.user_roles).join(AuthUserRole.role).where(AuthRole.code == role)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(AuthUser.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    users = list(result.scalars().unique().all())

    return users, total


async def create_user(
    db: AsyncSession,
    full_name: str,
    email: str,
    role_codes: list[str],
    created_by: uuid.UUID,
) -> tuple[AuthUser, str]:
    existing = await get_user_by_email(db, email)
    if existing:
        raise ConflictError(f"User with email {email} already exists")

    temp_password = secrets.token_urlsafe(12)
    logger.info("Temp password for %s: %s", email, temp_password)

    user = AuthUser(
        email=email,
        full_name=full_name,
        password_hash=hash_password(temp_password),
        status="active",
    )
    db.add(user)
    await db.flush()

    await assign_roles(db, user.id, role_codes, created_by)
    await write_audit(
        db,
        actor_id=created_by,
        entity_type="auth_users",
        entity_id=user.id,
        action="created",
        old_data=None,
        new_data={"email": email, "full_name": full_name, "roles": role_codes},
    )
    await db.commit()

    user = await get_user_by_id(db, user.id)
    return user, temp_password


async def update_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: dict,
    updated_by: uuid.UUID,
) -> AuthUser:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found")

    old_data = user_to_dict(user)
    role_codes = data.pop("roles", None)

    for field, value in data.items():
        if value is not None and hasattr(user, field):
            setattr(user, field, value)

    if role_codes is not None:
        await assign_roles(db, user_id, role_codes, updated_by)

    await write_audit(
        db,
        actor_id=updated_by,
        entity_type="auth_users",
        entity_id=user_id,
        action="updated",
        old_data=old_data,
        new_data=data | ({"roles": role_codes} if role_codes is not None else {}),
    )
    await db.commit()
    return await get_user_by_id(db, user_id)


async def assign_roles(
    db: AsyncSession,
    user_id: uuid.UUID,
    role_codes: list[str],
    assigned_by: uuid.UUID,
) -> None:
    # Remove existing roles
    existing = await db.execute(
        select(AuthUserRole).where(AuthUserRole.user_id == user_id)
    )
    for ur in existing.scalars().all():
        await db.delete(ur)

    # Assign new roles
    for code in role_codes:
        role_result = await db.execute(
            select(AuthRole).where(AuthRole.code == code)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise BadRequestError(f"Role '{code}' does not exist")
        db.add(AuthUserRole(user_id=user_id, role_id=role.id, assigned_by=assigned_by))

    await db.flush()


async def write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    old_data: dict | None = None,
    new_data: dict | None = None,
) -> None:
    log = AuditAuditLog(
        actor_user_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_data=old_data,
        new_data=new_data,
    )
    db.add(log)
    await db.flush()
