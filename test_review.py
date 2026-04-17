"""Quick test: Jina + Claude review extraction from one GYG page."""
import asyncio
import json
import os
import sys

os.environ.setdefault("ENVIRONMENT", "production")
sys.stdout.reconfigure(encoding="utf-8")


async def test():
    from app.integrations.jina_client import jina_client
    from app.integrations.claude_client import claude_client

    url = "https://www.getyourguide.com/cairo-l92/cairo-grand-egyptian-museum-pyramids-sphinx-tour-lunch-t851104/"

    print("1. Reading page with Jina...", flush=True)
    content = await jina_client.clean_page(url)
    content = jina_client.clean_markdown(content)
    print(f"   Page length: {len(content)} chars", flush=True)

    content = content[:20000]

    print("2. Extracting reviews with Claude...", flush=True)
    prompt = f"""Extract user reviews from this tour/activity listing page.

Activity: Cairo: Grand Egyptian Museum, Pyramids, Sphinx Tour & Lunch
Source: {url}

Page Content:
{content}

Extract up to 10 real reviews with rating, reviewer name, review text, and date."""

    system = """You are a review extraction specialist. Given raw web page content from a tour/activity listing, extract real user reviews.

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

    response_text = await claude_client.generate(
        prompt=prompt,
        system=system,
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
    print(f"   Extracted {len(reviews)} reviews", flush=True)
    for r in reviews[:3]:
        name = r.get("reviewer_name", "?")
        rating = r.get("rating", "?")
        snippet = r.get("review_text", "")[:80]
        print(f"   - {name}: {rating}/5 - {snippet}...", flush=True)


if __name__ == "__main__":
    asyncio.run(test())
