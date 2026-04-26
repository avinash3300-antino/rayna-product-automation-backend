"""
Convert existing plain-text description_long to HTML bullet-point format.
Uses Claude AI to intelligently restructure each description.
"""

import os
import sys
import time
import psycopg2
import anthropic

DATABASE_URL = "postgresql://postgres:Avinash1234@localhost:5432/rayna_db"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

CONVERT_PROMPT = """Convert this activity description into HTML bullet-point format.

Rules:
- Start with a short 1-2 sentence intro paragraph wrapped in <p> tags
- Then organize the rest into bullet-point sections using <ul><li> tags
- Group related points: experience highlights, what you'll see/do, practical details
- Use <strong> for section labels inside list items if needed
- Keep ALL the original information — do NOT remove any facts
- Do NOT add any new information that wasn't in the original
- Output ONLY the HTML, no markdown fences, no explanation
- Keep it professional and engaging

Input description:
{description}"""


def convert_description(client, text):
    """Use Claude to convert a plain text description to HTML bullets."""
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": CONVERT_PROMPT.format(description=text)}],
    )
    return resp.content[0].text.strip()


def main():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Get all activities with plain-text descriptions (no HTML tags)
    cur.execute("""
        SELECT id, name, description_long
        FROM activities
        WHERE description_long IS NOT NULL
          AND description_long != ''
          AND description_long NOT LIKE '%<ul>%'
        ORDER BY name
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Found {total} activities to convert\n")

    converted = 0
    failed = 0

    for i, (aid, name, desc) in enumerate(rows, 1):
        print(f"[{i}/{total}] {name[:60]}...", end=" ", flush=True)
        try:
            html = convert_description(client, desc)
            cur.execute(
                "UPDATE activities SET description_long = %s WHERE id = %s",
                (html, aid),
            )
            conn.commit()
            converted += 1
            print("OK")
            # Small delay to avoid rate limits
            if i % 10 == 0:
                time.sleep(1)
        except Exception as e:
            failed += 1
            print(f"FAILED: {e}")
            conn.rollback()

    cur.close()
    conn.close()
    print(f"\nDone! Converted: {converted}, Failed: {failed}")


if __name__ == "__main__":
    main()
