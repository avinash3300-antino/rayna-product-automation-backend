"""Regenerate FAQs for 103 London-with-options activities, using scraped
reviews as a signal for what customers actually care about.

For each activity:
  1. Pull activity data + up to 20 reviews (mix of platforms, prefer enriched_text)
  2. One Claude call: takes both, generates 12-15 FAQs
     - Question selection informed by review themes (what customers mention/ask about)
     - Answers grounded ONLY in the activity's structured data (no invention, no review quotes)
     - No OTA brand mentions
  3. Overwrite activities.faqs (with backup: activities.faqs_backup, JSON column)

Overwrites existing FAQs.
"""
import asyncio
import json
import logging
import os
import re
import sys

from sqlalchemy import select, text
from app.db.base import async_session_factory
from app.db.models.activities import Activity
from app.db.models.reviews import ProductReview
from app.integrations.claude_client import claude_client

LOCK_FILE = "/tmp/regen_faqs.pid"
SLEEP_BETWEEN_ACTIVITIES = 0.5
REVIEW_SAMPLE_PER_ACT = 20   # up to N reviews per activity fed to Claude
REVIEW_TEXT_TRUNCATE = 300   # per-review char cap in the prompt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("regen_faqs")

OTA_BRANDS = re.compile(
    r"\b(viator|getyourguide|gyg|tripadvisor|trustpilot|booking\.com|klook|"
    r"tiqets|civitatis|expedia|tours4fun|headout|musement|airbnb experiences)\b",
    re.IGNORECASE,
)

FAQ_SYSTEM_PROMPT = """You are an SEO content specialist for Rayna Tours (raynatours.com). \
Generate FAQs designed to rank well in Google and match how real users search.

You will be given:
  (a) STRUCTURED ACTIVITY DATA — the ONLY source of factual content for your ANSWERS.
  (b) A SAMPLE OF REAL CUSTOMER REVIEWS — use ONLY to identify which QUESTIONS matter \
(topics customers repeatedly mention, ask, or worry about).

SEO PRINCIPLES (mandatory):
- Frame questions as natural, conversational search queries (long-tail question format). \
Prefer "How", "What", "Is", "Can", "How much", "How long", "Do I need" openings.
- Include the activity name and/or the city ("London") in questions where it flows \
naturally — helps match searches like "[activity name] duration", "London [category] price".
- Cover the "People Also Ask" topics users search: pricing, duration, timing/start times, \
what's included, what to bring, meeting point, transportation/pickup, cancellation & refunds, \
accessibility, age limits, kids/families, group size, weather/rainy-day policy, food/drinks, \
dress code, photography, comparisons, safety.
- Answers: 2-4 sentences. FRONT-LOAD the direct answer in the first sentence. \
Use target keywords naturally (activity name, location, key features) — but do not stuff.

FACTUAL SAFETY:
- Answers must ONLY use facts from the structured activity data. Do NOT invent facts.
- If a question has no answer in the data, do NOT include that FAQ (skip it).
- Reviews are used ONLY for question selection (what customers care about). \
NEVER copy phrasing, quotes, or content from reviews into answers.

CONTENT SAFETY:
- Never mention OTA brands: Viator, GetYourGuide, GYG, TripAdvisor, Trustpilot, \
Booking.com, Klook, Tiqets, Civitatis, Expedia, Tours4Fun, Headout, Musement, \
Airbnb Experiences.
- Do NOT write the brand name "Rayna Tours" inside the FAQ text — keep it platform-neutral.

QUANTITY: 12-15 FAQs. Skip any question you can't answer from the data.

OUTPUT: JSON array of objects with exactly two keys — "question" (string) and "answer" \
(string). No markdown fences, no preamble, no explanation."""


def _build_activity_context(a: Activity) -> str:
    parts = [f"Name: {a.name}"]
    if getattr(a, "category", None): parts.append(f"Category: {a.category}")
    parts.append(f"Location: {a.city}, {a.country}")
    for attr in ("duration_minutes", "currency", "price_from",
                 "description_short", "description_long",
                 "highlights", "included", "excluded", "what_to_bring",
                 "important_notes", "cancellation_policy",
                 "free_cancellation", "instant_confirmation",
                 "meeting_point_name", "meeting_point_desc", "address",
                 "operating_days", "start_times", "languages",
                 "min_age", "fitness_level", "wheelchair_access",
                 "pickup_available", "dress_code_note",
                 "redemption_instructions"):
        val = getattr(a, attr, None)
        if val is None or val == "" or val is False:
            continue
        if isinstance(val, (list, tuple)):
            val = ", ".join(str(x) for x in val)
        parts.append(f"{attr}: {val}")
    return "\n".join(parts)


def _pick_review_sample(reviews: list[ProductReview]) -> list[str]:
    """Take up to N reviews, spread across platforms, prefer enriched_text.
    Truncate each. Skip any that still have OTA brand mentions."""
    by_plat: dict[str, list[ProductReview]] = {}
    for r in reviews:
        by_plat.setdefault(r.source_platform, []).append(r)
    ordered: list[ProductReview] = []
    # round-robin across platforms
    while any(by_plat.values()) and len(ordered) < REVIEW_SAMPLE_PER_ACT * 2:
        for p in list(by_plat.keys()):
            if by_plat[p]:
                ordered.append(by_plat[p].pop(0))
            if len(ordered) >= REVIEW_SAMPLE_PER_ACT * 2:
                break
    out = []
    for r in ordered:
        text = (r.enriched_text or r.review_text or "").strip()
        if not text or OTA_BRANDS.search(text):
            continue
        text = text[:REVIEW_TEXT_TRUNCATE]
        out.append(f"- ({r.source_platform}, {r.rating or 'n/a'}★) {text}")
        if len(out) >= REVIEW_SAMPLE_PER_ACT:
            break
    return out


def _parse_faqs(raw: str) -> list[dict] | None:
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    valid = []
    for it in data:
        if isinstance(it, dict) and it.get("question") and it.get("answer"):
            q = str(it["question"]).strip()
            a = str(it["answer"]).strip()
            if OTA_BRANDS.search(q) or OTA_BRANDS.search(a):
                # defense in depth — never publish an FAQ with a brand
                continue
            valid.append({"question": q, "answer": a})
    return valid


async def process_activity(act: Activity, reviews: list[ProductReview]) -> tuple[str, int]:
    """Returns (status, faq_count). status ∈ {'ok', 'no_reviews', 'no_parse', 'error'}."""
    review_sample = _pick_review_sample(reviews)
    if not review_sample:
        # fallback: no usable reviews. Still generate FAQs but note it.
        review_block = "(no clean reviews available — rely on activity data only)"
    else:
        review_block = "\n".join(review_sample)

    activity_block = _build_activity_context(act)
    user_prompt = (
        f"STRUCTURED ACTIVITY DATA:\n{activity_block}\n\n"
        f"SAMPLE CUSTOMER REVIEWS:\n{review_block}\n\n"
        "Now generate the FAQs."
    )
    try:
        raw = await claude_client.generate(
            prompt=user_prompt,
            system=FAQ_SYSTEM_PROMPT,
            model="claude-sonnet-4-6",
            max_tokens=3072,
            temperature=0.2,
        )
    except Exception as exc:
        log.error("  Claude failed for '%s': %s", act.name, str(exc)[:150])
        return ("error", 0)

    faqs = _parse_faqs(raw)
    if not faqs:
        log.error("  bad JSON for '%s'; raw head: %r", act.name, raw[:200])
        return ("no_parse", 0)

    # Overwrite. Backup was captured in activities.faqs_backup column (if it exists)
    # via a separate SQL migration below.
    act.faqs = faqs
    return ("ok", len(faqs))


async def main():
    # First: back up existing faqs to a JSON column faqs_backup (if not already backed up).
    async with async_session_factory() as db:
        # Add column if missing (safe idempotent)
        await db.execute(text(
            "ALTER TABLE activities ADD COLUMN IF NOT EXISTS faqs_backup JSONB"
        ))
        # Only backup for London-with-options activities where backup is currently NULL
        await db.execute(text("""
            UPDATE activities SET faqs_backup = faqs::jsonb
            WHERE LOWER(city) = 'london'
              AND tour_variants IS NOT NULL
              AND jsonb_array_length(tour_variants::jsonb) > 0
              AND faqs_backup IS NULL
              AND faqs IS NOT NULL
        """))
        await db.commit()
        log.info("Backup step: faqs → faqs_backup complete")

    async with async_session_factory() as db:
        ids = [r[0] for r in (await db.execute(text(
            "SELECT id FROM activities "
            "WHERE LOWER(city) = 'london' "
            "AND tour_variants IS NOT NULL "
            "AND jsonb_array_length(tour_variants::jsonb) > 0 "
            "ORDER BY name"
        ))).all()]

    log.info("Regenerating FAQs for %d activities", len(ids))
    stats = {"ok": 0, "no_parse": 0, "error": 0}
    for i, aid in enumerate(ids, 1):
        async with async_session_factory() as db:
            act = await db.get(Activity, aid)
            if not act:
                continue
            reviews = (await db.execute(
                select(ProductReview).where(
                    ProductReview.product_type == "activities",
                    ProductReview.product_id == aid,
                ).order_by(ProductReview.rating.desc().nullslast()).limit(80)
            )).scalars().all()

            status, n = await process_activity(act, list(reviews))
            stats[status] = stats.get(status, 0) + 1
            log.info("[%d/%d] %s → %s (%d FAQs)", i, len(ids), act.name[:50], status, n)
            if status == "ok":
                await db.commit()
        await asyncio.sleep(SLEEP_BETWEEN_ACTIVITIES)

    log.info("=" * 60)
    log.info("DONE — %s", stats)


def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            if os.path.exists(f"/proc/{pid}"):
                log.error("Another instance running (PID %d). Refusing.", pid)
                sys.exit(2)
        except (OSError, ValueError):
            pass
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


if __name__ == "__main__":
    acquire_lock()
    try:
        asyncio.run(main())
    finally:
        release_lock()
