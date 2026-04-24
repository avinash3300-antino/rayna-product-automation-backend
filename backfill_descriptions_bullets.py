"""Backfill long descriptions to bullet-point format.

Uses Claude AI to convert paragraph-style descriptions to
HTML bullet-point format (<ul><li>...</li></ul>).
"""

import asyncio
import logging
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import async_session_factory
from app.db.models.activities import Activity
from app.integrations.claude_client import claude_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 5
DELAY_BETWEEN_BATCHES = 2  # seconds

SYSTEM_PROMPT = """You are a professional travel content formatter. Convert the given activity description \
into a clean bullet-point format using HTML <ul><li> tags.

Rules:
- Extract the key selling points, features, and details from the text
- Each bullet should be a concise, complete sentence (15-30 words)
- Aim for 6-12 bullet points that capture the essential information
- Preserve all factual details (times, prices, locations, inclusions)
- Use <ul><li>...</li></ul> HTML format
- Do NOT include any text outside the <ul> tags
- Do NOT add <p> tags, headings, or any other HTML
- Each <li> should start with a bold action phrase in <strong> tags
- Example: <li><strong>Explore iconic landmarks</strong> — Visit the Tower of London and enjoy skip-the-line access.</li>
- Return ONLY the <ul>...</ul> HTML, nothing else"""


async def convert_description(description: str, activity_name: str) -> str | None:
    """Convert a single description to bullet points using Claude."""
    try:
        result = await claude_client.generate(
            prompt=f"Activity: {activity_name}\n\nConvert this description to bullet points:\n\n{description}",
            system=SYSTEM_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            temperature=0.3,
        )
        # Validate it looks like bullet HTML
        text = result.strip()
        if text.startswith("<ul>") and text.endswith("</ul>"):
            return text
        # Try to extract <ul> block if extra text around it
        start = text.find("<ul>")
        end = text.rfind("</ul>")
        if start >= 0 and end > start:
            return text[start : end + 5]
        logger.warning("Claude didn't return valid <ul> HTML for %s", activity_name)
        return None
    except Exception as exc:
        logger.error("Claude error for %s: %s", activity_name, exc)
        return None


async def main():
    async with async_session_factory() as db:
        # Find activities with long descriptions that are NOT already in bullet format
        stmt = select(Activity).where(
            Activity.description_long.isnot(None),
            Activity.description_long != "",
            ~Activity.description_long.like("<ul>%"),
        )
        result = await db.execute(stmt)
        activities = result.scalars().all()

        total = len(activities)
        logger.info("Found %d activities needing bullet-point conversion", total)

        if total == 0:
            logger.info("Nothing to do.")
            return

        success = 0
        skipped = 0
        failed = 0

        for i, activity in enumerate(activities, 1):
            bullet_html = await convert_description(
                activity.description_long, activity.name
            )

            if bullet_html:
                activity.description_long = bullet_html
                success += 1
                logger.info("[%d/%d] Converted: %s", i, total, activity.name[:60])
            else:
                skipped += 1
                logger.warning("[%d/%d] Skipped: %s", i, total, activity.name[:60])

            # Commit in batches
            if i % BATCH_SIZE == 0:
                await db.commit()
                logger.info(
                    "Committed batch %d — success: %d, skipped: %d",
                    i // BATCH_SIZE, success, skipped,
                )
                await asyncio.sleep(DELAY_BETWEEN_BATCHES)

        # Final commit
        await db.commit()
        logger.info(
            "Done. Success: %d, Skipped: %d, Failed: %d, Total: %d",
            success, skipped, failed, total,
        )


if __name__ == "__main__":
    asyncio.run(main())
