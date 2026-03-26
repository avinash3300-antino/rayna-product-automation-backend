from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.base import get_async_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncSession:
    async for session in get_async_session():
        yield session


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    payload = decode_access_token(token)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise UnauthorizedError()
    # Placeholder: replace with actual user lookup once User model exists
    return {"id": user_id, "role": payload.get("role", "viewer")}


def role_guard(*allowed_roles: str):
    async def _guard(current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
        if current_user["role"] not in allowed_roles:
            raise ForbiddenError()
        return current_user
    return _guard


DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[dict, Depends(get_current_user)]
