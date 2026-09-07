"""Print the exact FAQ v2 system prompt + one filled-in user prompt to stdout.

Usage:
  python show_faq_prompt.py                  # just the system prompt
  python show_faq_prompt.py --with-sample    # + one sample user prompt from a tier-0 activity
"""
import argparse
import asyncio


async def _sample_user_prompt():
    from app.db.base import async_session_factory
    from app.services.faq_service_v2 import (
        FAQ_SYSTEM_PROMPT_V2, BRAND_USP_HINT, _build_activity_context_v2,
    )
    from app.db.models.activities import Activity
    from sqlalchemy import select, text

    async with async_session_factory() as db:
        r = await db.execute(text("""
          SELECT id FROM activities
          WHERE deleted_at IS NULL AND merged_into_id IS NULL
            AND tour_variants IS NOT NULL AND tour_variants::text NOT IN ('null','[]')
            AND gallery_json IS NOT NULL AND gallery_json::text NOT IN ('null','[]')
            AND length(description_long) > 500
          ORDER BY random() LIMIT 1
        """))
        aid = r.scalar()
        r = await db.execute(select(Activity).where(Activity.id == aid))
        a = r.scalar_one()

    ctx = _build_activity_context_v2(a)
    user_prompt = f"""{BRAND_USP_HINT}

Activity data:
---
{ctx}
---

Generate the FAQs now. Return ONLY the JSON array."""
    return a.name, a.city, user_prompt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-sample", action="store_true")
    args = parser.parse_args()

    from app.services.faq_service_v2 import FAQ_SYSTEM_PROMPT_V2
    print("=" * 80)
    print("FAQ v2 — SYSTEM PROMPT")
    print("=" * 80)
    print(FAQ_SYSTEM_PROMPT_V2)

    if args.with_sample:
        name, city, up = asyncio.run(_sample_user_prompt())
        print()
        print("=" * 80)
        print(f"USER PROMPT (sample activity: {name!r} / {city})")
        print("=" * 80)
        print(up)


if __name__ == "__main__":
    main()
