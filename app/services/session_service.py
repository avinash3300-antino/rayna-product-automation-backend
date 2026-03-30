import ipaddress
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from user_agents import parse as parse_ua

from app.core.config import settings
from app.db.models.sessions import AuthUserSession

logger = logging.getLogger(__name__)

_geo_cache: dict[str, tuple[str, float]] = {}
_GEO_CACHE_TTL = 300  # 5 minutes


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def parse_user_agent(ua_string: str | None) -> dict:
    if not ua_string:
        return {"device": "Unknown", "browser": "Unknown", "os": "Unknown"}

    ua = parse_ua(ua_string)
    device = "PC" if ua.is_pc else (str(ua.device.family) or "Unknown")
    browser_version = ua.browser.version_string
    browser = f"{ua.browser.family} {browser_version}" if browser_version else str(ua.browser.family)
    os_version = ua.os.version_string
    os_name = f"{ua.os.family} {os_version}" if os_version else str(ua.os.family)

    return {
        "device": device or "Unknown",
        "browser": browser or "Unknown",
        "os": os_name or "Unknown",
    }


def _is_private_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


async def get_ip_location(ip: str | None) -> str:
    if not ip or _is_private_ip(ip):
        return "Local Network"

    now = time.time()
    if ip in _geo_cache:
        cached_location, cached_at = _geo_cache[ip]
        if now - cached_at < _GEO_CACHE_TTL:
            return cached_location

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"http://ip-api.com/json/{ip}?fields=city,country")
            if resp.status_code == 200:
                data = resp.json()
                city = data.get("city", "")
                country = data.get("country", "")
                location = f"{city}, {country}".strip(", ") or "Unknown"
                _geo_cache[ip] = (location, now)
                return location
    except Exception as exc:
        logger.warning("GeoIP lookup failed for %s: %s", ip, exc)

    return "Unknown"


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthUserSession:
    ua_info = parse_user_agent(user_agent)
    location = await get_ip_location(ip_address)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    session = AuthUserSession(
        user_id=user_id,
        device=ua_info["device"],
        browser=ua_info["browser"],
        os=ua_info["os"],
        user_agent_raw=user_agent,
        ip_address=ip_address,
        location=location,
        expires_at=expires_at,
    )
    db.add(session)
    await db.flush()
    return session


async def get_session_by_id(db: AsyncSession, session_id: uuid.UUID) -> AuthUserSession | None:
    result = await db.execute(
        select(AuthUserSession).where(AuthUserSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_user_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[AuthUserSession]:
    now = datetime.now(timezone.utc)

    # Cleanup expired sessions on read
    await db.execute(
        delete(AuthUserSession).where(
            AuthUserSession.user_id == user_id,
            AuthUserSession.expires_at < now,
        )
    )

    result = await db.execute(
        select(AuthUserSession)
        .where(AuthUserSession.user_id == user_id)
        .order_by(AuthUserSession.last_active_at.desc())
    )
    return list(result.scalars().all())


async def revoke_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        delete(AuthUserSession).where(
            AuthUserSession.id == session_id,
            AuthUserSession.user_id == user_id,
        )
    )
    return result.rowcount > 0


async def revoke_all_except(db: AsyncSession, user_id: uuid.UUID, keep_session_id: uuid.UUID) -> int:
    result = await db.execute(
        delete(AuthUserSession).where(
            AuthUserSession.user_id == user_id,
            AuthUserSession.id != keep_session_id,
        )
    )
    return result.rowcount


async def update_last_active(db: AsyncSession, session_id: uuid.UUID) -> None:
    session = await get_session_by_id(db, session_id)
    if session:
        session.last_active_at = datetime.now(timezone.utc)


async def extend_session_expiry(db: AsyncSession, session_id: uuid.UUID) -> None:
    session = await get_session_by_id(db, session_id)
    if session:
        session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
