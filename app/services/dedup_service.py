import hashlib
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activities import Activity, ActivityEmbedding

logger = logging.getLogger(__name__)


def compute_dedupe_hash(name: str, city: str, category: str) -> str:
    """MD5 hash of normalized name+city+category for exact-match dedup."""
    normalized = (
        f"{name.lower().strip()}_{city.lower().strip()}"
        f"_{category.lower().strip()}"
    )
    return hashlib.md5(normalized.encode()).hexdigest()


async def find_exact_duplicate(
    db: AsyncSession,
    dedup_hash: str,
) -> Activity | None:
    """Find an existing activity with the same dedup hash."""
    result = await db.execute(
        select(Activity).where(Activity.dedup_hash == dedup_hash)
    )
    return result.scalar_one_or_none()


async def find_semantic_duplicate(
    db: AsyncSession,
    embedding: list[float],
    threshold: float = 0.92,
) -> tuple[Activity | None, float]:
    """Find semantically similar activity using pgvector cosine distance.

    Returns (activity, similarity_score) or (None, 0.0).
    """
    result = await db.execute(
        select(
            ActivityEmbedding.activity_id,
            (
                1 - ActivityEmbedding.embedding.cosine_distance(embedding)
            ).label("similarity"),
        )
        .order_by(ActivityEmbedding.embedding.cosine_distance(embedding))
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None, 0.0

    similarity = float(row.similarity)
    if similarity >= threshold:
        activity = await db.get(Activity, row.activity_id)
        return activity, similarity

    return None, similarity


async def check_duplicate(
    db: AsyncSession,
    name: str,
    city: str,
    category: str,
    description: str,
    embedding: list[float] | None = None,
) -> dict:
    """Check if an activity is a duplicate.

    Returns {is_duplicate: bool, match_type: str|None, existing_id: UUID|None}.
    """
    # Layer 1: MD5 hash check
    dedup_hash = compute_dedupe_hash(name, city, category)
    exact = await find_exact_duplicate(db, dedup_hash)
    if exact:
        return {
            "is_duplicate": True,
            "match_type": "exact",
            "existing_id": exact.id,
        }

    # Layer 2: Semantic similarity (only if embedding provided)
    if embedding:
        semantic_match, score = await find_semantic_duplicate(
            db, embedding, threshold=0.92
        )
        if semantic_match:
            return {
                "is_duplicate": True,
                "match_type": "semantic",
                "existing_id": semantic_match.id,
            }

    return {
        "is_duplicate": False,
        "match_type": None,
        "existing_id": None,
    }


async def get_embedding(text: str) -> list[float]:
    """Get text embedding from OpenAI text-embedding-3-small."""
    import openai
    from app.core.config import settings

    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],  # Truncate to avoid token limits
    )
    return response.data[0].embedding


async def merge_or_save(
    db: AsyncSession,
    new_data: dict,
    existing_id: uuid.UUID | None,
    match_type: str | None,
) -> Activity:
    """Merge with existing or save new activity.

    If semantic near-duplicate: keep better data from each.
    If new: insert fresh record.
    """
    if existing_id and match_type == "semantic":
        existing = await db.get(Activity, existing_id)
        if existing:
            # Merge: best data wins
            for field, new_val in new_data.items():
                if not hasattr(existing, field):
                    continue
                old_val = getattr(existing, field)
                if new_val is None:
                    continue
                if old_val is None:
                    setattr(existing, field, new_val)
                    continue
                # Keep longer descriptions
                if field in ("description_long", "description_short"):
                    if isinstance(new_val, str) and isinstance(old_val, str):
                        if len(new_val) > len(old_val):
                            setattr(existing, field, new_val)
                # Keep higher review count
                elif field == "review_count":
                    if (new_val or 0) > (old_val or 0):
                        setattr(existing, field, new_val)
                # Keep more gallery images
                elif field == "gallery_json":
                    if isinstance(new_val, list) and isinstance(old_val, list):
                        if len(new_val) > len(old_val):
                            setattr(existing, field, new_val)
            await db.flush()
            return existing

    # Create new activity
    activity = Activity(**new_data)
    db.add(activity)
    await db.flush()

    # Compute and store embedding
    try:
        text_for_embed = f"{new_data.get('name', '')}. {new_data.get('description_short', '')}"
        embedding = await get_embedding(text_for_embed)
        emb = ActivityEmbedding(
            activity_id=activity.id,
            embedding=embedding,
        )
        db.add(emb)
        await db.flush()
    except Exception as exc:
        logger.warning(
            "Failed to compute embedding for activity %s: %s",
            activity.id,
            exc,
        )

    return activity
