import hashlib
import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activities import Activity, ActivityEmbedding
from app.integrations.claude_client import claude_client

logger = logging.getLogger(__name__)

MERGE_SYSTEM_PROMPT = """You are a travel content writer for Rayna Tours.
You receive MULTIPLE scraped descriptions of the SAME activity from different sources.
Your job is to write ONE ORIGINAL version that captures the best information from each source,
WITHOUT copying any phrasing verbatim.

RULES:
1. Read all source versions to understand the activity fully.
2. Extract KEY FACTS from each source (features, logistics, inclusions, etc.).
3. Write COMPLETELY ORIGINAL prose — new sentences, new structure, new phrasing.
4. If one source has richer detail on a topic, use those FACTS but rewrite them.
5. NEVER copy a sentence or distinctive phrase from any source.
6. Produce professional, engaging content worthy of a premium travel brand.

Return ONLY valid JSON with these fields:
- description_short (2-3 sentences, 150-200 chars)
- description_long (300-600 words, SEO-optimized, engaging)
- highlights (array of 4-8 strings)
- included (array of inclusions)
- excluded (array of exclusions)

Return null for any field you cannot determine. No markdown fences."""


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


async def _claude_merge_content(
    existing: Activity,
    new_data: dict,
) -> dict | None:
    """Use Claude to synthesize original content from multiple source versions.

    Returns dict with merged content fields, or None on failure.
    """
    content_fields = [
        "description_short", "description_long",
        "highlights", "included", "excluded",
    ]

    # Collect source versions
    source_a = {}
    source_b = {}
    has_content_to_merge = False

    for field in content_fields:
        old_val = getattr(existing, field, None)
        new_val = new_data.get(field)
        if old_val:
            source_a[field] = old_val
        if new_val:
            source_b[field] = new_val
        if old_val and new_val:
            has_content_to_merge = True

    if not has_content_to_merge:
        return None

    prompt = f"""Activity: {existing.name}
City: {existing.city}
Category: {existing.category}

═══ SOURCE A (existing record) ═══
Short description: {source_a.get('description_short', 'N/A')}
Long description: {(source_a.get('description_long') or 'N/A')[:2000]}
Highlights: {json.dumps(source_a.get('highlights') or [], indent=2)}
Included: {json.dumps(source_a.get('included') or [], indent=2)}
Excluded: {json.dumps(source_a.get('excluded') or [], indent=2)}

═══ SOURCE B (new scrape) ═══
Short description: {source_b.get('description_short', 'N/A')}
Long description: {(source_b.get('description_long') or 'N/A')[:2000]}
Highlights: {json.dumps(source_b.get('highlights') or [], indent=2)}
Included: {json.dumps(source_b.get('included') or [], indent=2)}
Excluded: {json.dumps(source_b.get('excluded') or [], indent=2)}

Synthesize ONE original version combining the best facts from both sources.
Do NOT copy phrasing from either source."""

    try:
        response = await claude_client.generate(
            prompt=prompt,
            system=MERGE_SYSTEM_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.4,
        )
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)
    except Exception as exc:
        logger.warning("Claude merge failed for %s: %s", existing.name, exc)
        return None


async def merge_or_save(
    db: AsyncSession,
    new_data: dict,
    existing_id: uuid.UUID | None,
    match_type: str | None,
) -> Activity:
    """Merge with existing or save new activity.

    If semantic near-duplicate: use Claude to synthesize original content
    from both source versions. Non-content fields use best-data-wins logic.
    If new: insert fresh record.
    """
    if existing_id and match_type == "semantic":
        existing = await db.get(Activity, existing_id)
        if existing:
            # ── Claude-based content merge ──────────────────────────
            merged = await _claude_merge_content(existing, new_data)
            if merged:
                content_fields = [
                    "description_short", "description_long",
                    "highlights", "included", "excluded",
                ]
                for field in content_fields:
                    value = merged.get(field)
                    if value is not None and hasattr(existing, field):
                        setattr(existing, field, value)
                # Reset status so enrichment re-runs on merged content
                existing.status = "draft"
                logger.info(
                    "Claude-merged content for activity %s from new source",
                    existing.id,
                )

            # ── Non-content fields: best data wins ──────────────────
            skip_fields = {
                "description_short", "description_long",
                "highlights", "included", "excluded",
                "id", "created_at", "updated_at", "status",
            }
            for field, new_val in new_data.items():
                if field in skip_fields:
                    continue
                if not hasattr(existing, field):
                    continue
                old_val = getattr(existing, field)
                if new_val is None:
                    continue
                if old_val is None:
                    setattr(existing, field, new_val)
                    continue
                # Keep higher review count
                if field == "review_count":
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
