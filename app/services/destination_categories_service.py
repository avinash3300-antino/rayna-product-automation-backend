"""Per-destination suggested categories — AI generation + DB cache + user CRUD."""

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ExternalServiceError, NotFoundError
from app.db.models.destinations import CatalogDestination, DestinationSuggestedCategory
from app.integrations.claude_client import claude_client

logger = logging.getLogger(__name__)


PROMPT_SYSTEM = """You are a travel product expert. For a given destination and product type,
suggest as many relevant booking categories as you can think of — anything tourists
actually search for and book online.

Return ONLY a JSON array of 30-50 short category names (2-5 words each), covering:
- Major landmarks and signature attractions
- Day trips and excursions from this destination
- Adventure / outdoor activities
- Cultural and food experiences
- Shows and entertainment
- Transport experiences (cruises, scenic rides, transfers)
- Family / kids friendly options
- Spa, wellness, leisure
- Niche or specialty tours that are popular here

No prose, no markdown fences, just the JSON array. Be exhaustive but avoid
duplicates and avoid overly generic names like "Tours" or "Things to Do".

Good examples for Bangkok activities:
["Floating Markets", "Grand Palace Tours", "Thai Cooking Classes", "Tuk Tuk Tours",
 "Muay Thai Experience", "Ayutthaya Day Trips", "Temple Tours", "Chao Phraya Cruises",
 "Night Markets", "Cabaret Shows", "Thai Massage & Spa", "Khao San Road Tours",
 "Erawan Shrine Visits", "Damnoen Saduak Tours", "Maeklong Railway Market",
 "Snake Farm Visits", "Chatuchak Market Tours", "Rooftop Bar Experiences",
 "Bangkok Walking Tours", "Bike Tours", "Foodie Tours", "River Sunset Cruises",
 "Klong Boat Tours", "Jim Thompson House", "Wat Arun Visits", ...]

Bad examples (too generic): ["Tours", "Activities", "Things to Do"]
Bad examples (too long): ["The famous floating markets of Bangkok where you can buy"]"""


async def _list_active(
    db: AsyncSession, destination_id: uuid.UUID, product_type: str
) -> list[DestinationSuggestedCategory]:
    q = (
        select(DestinationSuggestedCategory)
        .where(
            and_(
                DestinationSuggestedCategory.destination_id == destination_id,
                DestinationSuggestedCategory.product_type == product_type,
                DestinationSuggestedCategory.deleted_at.is_(None),
            )
        )
        .order_by(DestinationSuggestedCategory.created_at)
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def _generate_with_claude(city_name: str, country_name: str, product_type: str) -> list[str]:
    prompt = (
        f"Destination: {city_name}, {country_name}\n"
        f"Product type: {product_type}\n\n"
        "Suggest as many relevant booking categories as you can — aim for 30-50."
    )

    try:
        response_text = await claude_client.generate(
            prompt=prompt,
            system=PROMPT_SYSTEM,
            model="claude-sonnet-4-6",
            max_tokens=3000,
            temperature=0.6,
        )
    except Exception as exc:
        raise ExternalServiceError(f"Claude category suggestion failed: {exc}") from exc

    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Claude returned non-JSON for categories: %s", text[:200])
        raise ExternalServiceError("Could not parse category suggestions from AI") from exc

    if not isinstance(data, list):
        raise ExternalServiceError("AI response was not a JSON array")

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or len(name) > 200:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)

    return cleaned[:60]


async def list_or_generate(
    db: AsyncSession,
    destination_id: uuid.UUID,
    product_type: str,
) -> list[DestinationSuggestedCategory]:
    """Return active categories; if none exist, generate via Claude and persist."""
    existing = await _list_active(db, destination_id, product_type)
    if existing:
        return existing

    destination = await db.get(CatalogDestination, destination_id)
    if not destination:
        raise NotFoundError("Destination not found")

    city_name = destination.city_name or destination.name
    country_name = destination.country_name or ""

    names = await _generate_with_claude(city_name, country_name, product_type)
    if not names:
        return []

    rows = [
        DestinationSuggestedCategory(
            destination_id=destination_id,
            product_type=product_type,
            name=name,
            source="ai",
        )
        for name in names
    ]
    db.add_all(rows)
    await db.commit()

    return await _list_active(db, destination_id, product_type)


async def regenerate_ai(
    db: AsyncSession,
    destination_id: uuid.UUID,
    product_type: str,
) -> list[DestinationSuggestedCategory]:
    """Soft-delete existing AI categories, then regenerate. User categories untouched."""
    destination = await db.get(CatalogDestination, destination_id)
    if not destination:
        raise NotFoundError("Destination not found")

    now = datetime.now(timezone.utc)
    await db.execute(
        update(DestinationSuggestedCategory)
        .where(
            and_(
                DestinationSuggestedCategory.destination_id == destination_id,
                DestinationSuggestedCategory.product_type == product_type,
                DestinationSuggestedCategory.source == "ai",
                DestinationSuggestedCategory.deleted_at.is_(None),
            )
        )
        .values(deleted_at=now)
    )
    await db.commit()

    return await list_or_generate(db, destination_id, product_type)


async def add_user_category(
    db: AsyncSession,
    destination_id: uuid.UUID,
    name: str,
    product_type: str,
    actor_id: uuid.UUID,
) -> DestinationSuggestedCategory:
    """Add a user-defined category. If an active one with same name already exists, return it.
    If a soft-deleted one exists, undelete and flip source to user."""
    destination = await db.get(CatalogDestination, destination_id)
    if not destination:
        raise NotFoundError("Destination not found")

    name = name.strip()
    if not name:
        raise ValueError("Category name cannot be empty")

    q = select(DestinationSuggestedCategory).where(
        and_(
            DestinationSuggestedCategory.destination_id == destination_id,
            DestinationSuggestedCategory.product_type == product_type,
            DestinationSuggestedCategory.name.ilike(name),
        )
    )
    result = await db.execute(q)
    existing = result.scalar_one_or_none()

    if existing:
        if existing.deleted_at is not None:
            existing.deleted_at = None
            existing.source = "user"
            existing.created_by = actor_id
        await db.commit()
        await db.refresh(existing)
        return existing

    row = DestinationSuggestedCategory(
        destination_id=destination_id,
        product_type=product_type,
        name=name,
        source="user",
        created_by=actor_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_category(
    db: AsyncSession,
    category_id: uuid.UUID,
) -> None:
    row = await db.get(DestinationSuggestedCategory, category_id)
    if not row:
        raise NotFoundError("Category not found")
    if row.deleted_at is None:
        row.deleted_at = datetime.now(timezone.utc)
    await db.commit()
