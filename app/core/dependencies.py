from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.base import get_async_session
from app.db.models.auth import AuthUser
from app.services.user_service import get_user_by_id, get_user_roles

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncSession:
    async for session in get_async_session():
        yield session


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> AuthUser:
    payload = decode_access_token(token)
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedError()
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise UnauthorizedError()

    # Session validation
    session_id_str: str | None = payload.get("session_id")
    if session_id_str:
        try:
            session_id = UUID(session_id_str)
        except ValueError:
            raise UnauthorizedError()

        from app.services.session_service import get_session_by_id, update_last_active

        session = await get_session_by_id(db, session_id)
        if not session or session.user_id != user_id:
            raise UnauthorizedError("Session revoked or invalid")

        now = datetime.now(timezone.utc)
        if session.expires_at and session.expires_at.replace(tzinfo=timezone.utc) < now:
            raise UnauthorizedError("Session expired")

        # Throttled last_active_at update (once per 60 seconds)
        last_active = session.last_active_at.replace(tzinfo=timezone.utc) if session.last_active_at else now
        if (now - last_active).total_seconds() > 60:
            await update_last_active(db, session_id)
            await db.commit()

        request.state.session_id = session_id
    else:
        # Legacy tokens without session_id (pre-migration)
        request.state.session_id = None

    user = await get_user_by_id(db, user_id)
    if not user or user.status != "active":
        raise UnauthorizedError("User inactive or not found")
    return user


def require_role(*allowed_roles: str):
    async def _guard(
        current_user: Annotated[AuthUser, Depends(get_current_user)],
    ) -> AuthUser:
        user_roles = get_user_roles(current_user)
        if not any(r in allowed_roles for r in user_roles):
            raise ForbiddenError()
        return current_user
    return _guard


DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
