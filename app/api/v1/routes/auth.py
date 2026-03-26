from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.models.auth import AuthUser
from app.schemas.auth import LoginRequest, LoginResponse, RefreshRequest, UserBrief
from app.schemas.users import UserResponse, RoleResponse
from app.services.user_service import get_user_by_email, get_user_roles

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_user_response(user: AuthUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        job_title=user.job_title,
        department=user.department,
        phone=user.phone,
        timezone=user.timezone,
        status=user.status,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=[RoleResponse.model_validate(ur.role) for ur in user.user_roles],
    )


def _build_login_response(user: AuthUser, token: str) -> LoginResponse:
    roles = get_user_roles(user)
    return LoginResponse(
        access_token=token,
        user=UserBrief(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=roles,
            status=user.status,
        ),
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if user.status != "active":
        raise ForbiddenError("Account is not active")

    roles = get_user_roles(user)
    token = create_access_token(data={"sub": str(user.id), "roles": roles})

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return _build_login_response(user, token)


@router.post("/logout")
async def logout(current_user: CurrentUser):
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser):
    return _build_user_response(current_user)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    from uuid import UUID
    from app.services.user_service import get_user_by_id

    payload = decode_access_token(body.token)
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError()

    user = await get_user_by_id(db, UUID(user_id))
    if not user or user.status != "active":
        raise UnauthorizedError("User inactive or not found")

    roles = get_user_roles(user)
    new_token = create_access_token(data={"sub": str(user.id), "roles": roles})
    return _build_login_response(user, new_token)
