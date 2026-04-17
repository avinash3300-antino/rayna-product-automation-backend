"""Scrape reviews from source URLs (GYG, Viator, Headout) using Jina + Claude."""
import asyncio
import json
import logging
import os
import sys
import uuid

os.environ.setdefault("ENVIRONMENT", "production")
sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

REVIEW_SYSTEM = """You are a review extraction specialist. Given raw web page content from a tour/activity listing, extract real user reviews.

Return a JSON array of review objects with these fields:
- reviewer_name (string)
- rating (number 1-5 or null)
- review_title (string or null)
- review_text (string, min 20 chars)
- review_date (string or null)
- verified (boolean)

RULES:
- Extract at most 10 reviews
- Only include reviews with meaningful text (20+ chars)
- Do NOT fabricate reviews. Only extract what is on the page.
- Return ONLY valid JSON array, no markdown fences.
- If no reviews found, return empty array: []"""


async def extract_reviews_for_one(act_name, source_url):
    """Extract reviews for a single activity (no DB access)."""
    from app.integrations.jina_client import jina_client
    from app.integrations.claude_client import claude_client

    # Read the source page
    content = await jina_client.clean_page(source_url)
    content = jina_client.clean_markdown(content)

    if not content or len(content) < 200:
        return []

    content = content[:20000]

    prompt = f"""Extract user reviews from this tour/activity listing page.

Activity: {act_name}
Source: {source_url}

Page Content:
{content}

Extract up to 10 real reviews with rating, reviewer name, review text, and date."""

    response_text = await claude_client.generate(
        prompt=prompt,
        system=REVIEW_SYSTEM,
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0.1,
    )

    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    reviews = json.loads(text)
    if not isinstance(reviews, list):
        return []

    return [r for r in reviews if r.get("review_text") and len(r.get("review_text", "")) >= 10]


async def main():
    from sqlalchemy import select, delete

    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.db.models.reviews import ActivityReview

    city_id = uuid.UUID("941c503c-82a0-4a76-80ae-f8bb78cd7437")  # Cairo

    # Load all activities first
    async with async_session_factory() as db:
        result = await db.execute(
            select(Activity).where(Activity.city_id == city_id)
        )
        activities = list(result.scalars().all())
        # Collect the data we need
        act_data = []
        for act in activities:
            act_data.append({
                "id": act.id,
                "name": act.name,
                "source_url": act.source_url,
                "has_snippets": bool(act.review_snippets),
            })
    print(f"Found {len(act_data)} Cairo activities", flush=True)

    count = 0
    for i, ad in enumerate(act_data, 1):
        print(f"\n[{i}/{len(act_data)}] {ad['name']}", flush=True)

        if ad["has_snippets"]:
            print("  Already has review snippets, skipping", flush=True)
            continue

        if not ad["source_url"]:
            print("  No source URL, skipping", flush=True)
            continue

        # Extract reviews (outside DB session) with timeout
        try:
            reviews = await asyncio.wait_for(
                extract_reviews_for_one(ad["name"], ad["source_url"]),
                timeout=120,
            )
        except asyncio.TimeoutError:
            print("  Timeout (120s), skipping", flush=True)
            continue
        except json.JSONDecodeError as exc:
            print(f"  JSON parse error: {exc}", flush=True)
            continue
        except Exception as exc:
            print(f"  Error: {exc}", flush=True)
            continue

        if not reviews:
            print("  No reviews extracted", flush=True)
            continue

        # Determine platform
        url = ad["source_url"].lower()
        if "getyourguide" in url:
            platform = "getyourguide"
        elif "viator" in url:
            platform = "viator"
        elif "headout" in url:
            platform = "headout"
        else:
            platform = "web"

        # Save to DB in a separate session
        async with async_session_factory() as db:
            activity = await db.get(Activity, ad["id"])

            await db.execute(
                delete(ActivityReview).where(ActivityReview.activity_id == ad["id"])
            )

            for r in reviews:
                review = ActivityReview(
                    activity_id=ad["id"],
                    reviewer_name=r.get("reviewer_name") or "Anonymous",
                    rating=r.get("rating"),
                    review_title=r.get("review_title"),
                    review_text=r.get("review_text", "")[:5000],
                    review_date=r.get("review_date"),
                    source_platform=platform,
                    source_url=ad["source_url"],
                    verified=bool(r.get("verified", False)),
                    language="en",
                )
                db.add(review)

            # Update review_snippets
            snippets = []
            for r in sorted(reviews, key=lambda x: x.get("rating", 0) or 0, reverse=True):
                text = r.get("review_text", "")
                if len(text) > 20:
                    snippets.append(text[:200])
                if len(snippets) >= 5:
                    break
            activity.review_snippets = snippets

            await db.commit()

        count += 1
        print(f"  OK: {len(reviews)} reviews ({platform}), {len(snippets)} snippets saved", flush=True)

        # Rate limit
        await asyncio.sleep(2)

    print(f"\n=== Done: {count}/{len(act_data)} activities got reviews ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
