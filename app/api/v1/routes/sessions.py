from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_db
from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.sessions import SessionResponse
from app.services import session_service, user_service

router = APIRouter(prefix="/users", tags=["sessions"])


@router.get("/me/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current_user: CurrentUser,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current_session_id: UUID | None = getattr(request.state, "session_id", None)
    sessions = await session_service.get_user_sessions(db, current_user.id)
    await db.commit()

    items = []
    for s in sessions:
        items.append(SessionResponse(
            id=s.id,
            device=s.device,
            browser=s.browser,
            ip=s.ip_address,
            location=s.location,
            last_active=s.last_active_at,
            is_current=(s.id == current_session_id) if current_session_id else False,
        ))

    return items


@router.delete("/me/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: UUID,
    current_user: CurrentUser,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current_session_id: UUID | None = getattr(request.state, "session_id", None)

    if current_session_id and session_id == current_session_id:
        raise BadRequestError("Cannot revoke current session. Use logout instead.")

    deleted = await session_service.revoke_session(db, session_id, current_user.id)
    if not deleted:
        raise NotFoundError("Session not found")

    await user_service.write_audit(
        db, current_user.id, "auth_user_sessions", session_id, "session_revoked",
    )
    await db.commit()


@router.delete("/me/sessions", status_code=204)
async def revoke_all_sessions(
    current_user: CurrentUser,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current_session_id: UUID | None = getattr(request.state, "session_id", None)
    if not current_session_id:
        raise BadRequestError("No current session found")

    count = await session_service.revoke_all_except(db, current_user.id, current_session_id)

    await user_service.write_audit(
        db, current_user.id, "auth_user_sessions", current_user.id,
        "all_sessions_revoked", None, {"revoked_count": count},
    )
    await db.commit()
