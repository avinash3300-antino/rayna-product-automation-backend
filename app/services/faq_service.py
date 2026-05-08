import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activities import Activity
from app.integrations.claude_client import claude_client

logger = logging.getLogger(__name__)

FAQ_SYSTEM_PROMPT = """You are a travel content expert for RaynaTours. Generate helpful, accurate FAQs for a tourism activity based on its details.

Rules:
- Generate 8-12 FAQs that a potential customer would genuinely ask before booking.
- Cover: booking/cancellation, what's included/excluded, accessibility, duration, meeting point, pricing, tips, and restrictions.
- Answers must be factual — only use information from the provided activity data. Do not invent facts.
- Keep answers concise (2-4 sentences each).
- Write in a friendly, professional tone.
- Return ONLY a JSON array of objects with "question" and "answer" keys. No markdown, no explanation."""


def _build_activity_context(activity: Activity) -> str:
    """Build a text summary of activity data for the FAQ prompt."""
    parts = [
        f"Name: {activity.name}",
        f"Category: {activity.category}",
        f"Location: {activity.city}, {activity.country}",
        f"Duration: {activity.duration_minutes} minutes",
        f"Price from: {activity.currency} {activity.price_from}",
    ]

    if activity.description_short:
        parts.append(f"Short description: {activity.description_short}")
    if activity.description_long:
        parts.append(f"Full description: {activity.description_long}")
    if activity.highlights:
        parts.append(f"Highlights: {', '.join(activity.highlights)}")
    if activity.included:
        parts.append(f"Included: {', '.join(activity.included)}")
    if activity.excluded:
        parts.append(f"Excluded: {', '.join(activity.excluded)}")
    if activity.what_to_bring:
        parts.append(f"What to bring: {activity.what_to_bring}")
    if activity.important_notes:
        parts.append(f"Important notes: {', '.join(activity.important_notes)}")
    if activity.cancellation_policy:
        parts.append(f"Cancellation policy: {activity.cancellation_policy}")
    if activity.free_cancellation:
        parts.append("Free cancellation available")
    if activity.instant_confirmation:
        parts.append("Instant confirmation")
    if activity.meeting_point_name:
        parts.append(f"Meeting point: {activity.meeting_point_name}")
    if activity.meeting_point_desc:
        parts.append(f"Meeting point details: {activity.meeting_point_desc}")
    if activity.address:
        parts.append(f"Address: {activity.address}")
    if activity.operating_days:
        parts.append(f"Operating days: {', '.join(activity.operating_days)}")
    if activity.start_times:
        parts.append(f"Start times: {', '.join(activity.start_times)}")
    if activity.languages:
        parts.append(f"Languages: {', '.join(activity.languages)}")
    if activity.min_age is not None:
        parts.append(f"Minimum age: {activity.min_age}")
    if activity.fitness_level:
        parts.append(f"Fitness level: {activity.fitness_level}")
    if activity.wheelchair_access:
        parts.append(f"Wheelchair access: {activity.wheelchair_access}")
    if activity.pickup_available:
        parts.append("Hotel pickup available")
    if activity.dress_code_note:
        parts.append(f"Dress code: {activity.dress_code_note}")
    if activity.redemption_instructions:
        parts.append(f"Redemption: {', '.join(activity.redemption_instructions)}")

    return "\n".join(parts)


async def generate_faqs_for_activity(
    db: AsyncSession, activity_id: UUID
) -> list[dict]:
    """Generate FAQs for an activity using Claude AI and save them."""
    result = await db.execute(
        select(Activity).where(Activity.id == activity_id)
    )
    activity = result.scalar_one_or_none()
    if not activity:
        raise ValueError(f"Activity {activity_id} not found")

    context = _build_activity_context(activity)
    prompt = f"Generate FAQs for this activity:\n\n{context}"

    raw = await claude_client.generate(
        prompt=prompt,
        system=FAQ_SYSTEM_PROMPT,
        max_tokens=4096,
        temperature=0.5,
    )

    # Parse JSON response
    try:
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        faqs = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        logger.error("Failed to parse FAQ response: %s", raw[:500])
        raise ValueError("Failed to generate FAQs — invalid AI response")

    if not isinstance(faqs, list):
        raise ValueError("FAQs response is not a list")

    # Validate structure
    validated = []
    for item in faqs:
        if isinstance(item, dict) and "question" in item and "answer" in item:
            validated.append({
                "question": str(item["question"]),
                "answer": str(item["answer"]),
            })

    activity.faqs = validated
    await db.flush()

    return validated
