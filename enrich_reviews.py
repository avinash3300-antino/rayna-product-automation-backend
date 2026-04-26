"""
Enrich all product reviews — adds enriched_text and enriched_reviewer_name.
"""

import json
import os
import time
import psycopg2
import anthropic

DATABASE_URL = "postgresql://postgres:Avinash1234@localhost:5432/rayna_db"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

ENRICH_SYSTEM_PROMPT = """You are a professional review editor for a premium travel company. \
You will receive a reviewer name and their review text. You must:

1. Rewrite the review to be more polished, grammatically correct, and professional \
while preserving the original sentiment, key facts, and rating context. \
Keep approximately the same length. Do NOT change the reviewer's opinion or add information not in the original.

2. Generate a realistic alternative reviewer name. The new name should be a completely different \
full name that sounds natural and believable. Keep the same general cultural/regional feel if apparent.

Return your response as valid JSON with exactly two keys:
{"enriched_text": "the rewritten review", "enriched_reviewer_name": "the new name"}

Return ONLY the JSON object, no markdown fences, no explanation."""


def enrich_review(client, name, text):
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        temperature=0.4,
        system=ENRICH_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Reviewer name: {name}\n\nOriginal review:\n{text}",
            }
        ],
    )
    raw = resp.content[0].text.strip()
    data = json.loads(raw)
    return data["enriched_text"], data["enriched_reviewer_name"]


def main():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Enrich reviews that don't have enriched_reviewer_name yet
    cur.execute("""
        SELECT id, reviewer_name, review_text
        FROM product_reviews
        WHERE enriched_reviewer_name IS NULL
          AND length(review_text) > 20
        ORDER BY created_at
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Found {total} reviews to enrich\n")

    enriched = 0
    failed = 0

    for i, (rid, name, text) in enumerate(rows, 1):
        short_name = (name[:30] if name else "Unknown").encode("ascii", "replace").decode()
        print(f"[{i}/{total}] {short_name}...", end=" ", flush=True)
        try:
            enriched_text, enriched_name = enrich_review(client, name, text)
            cur.execute(
                "UPDATE product_reviews SET enriched_text = %s, enriched_reviewer_name = %s WHERE id = %s",
                (enriched_text, enriched_name, rid),
            )
            conn.commit()
            enriched += 1
            print(f"OK -> {enriched_name}")
            # Rate limit: pause every 20 requests
            if i % 20 == 0:
                time.sleep(2)
        except Exception as e:
            failed += 1
            print(f"FAILED: {e}")
            conn.rollback()

    cur.close()
    conn.close()
    print(f"\nDone! Enriched: {enriched}, Failed: {failed}")


if __name__ == "__main__":
    main()
