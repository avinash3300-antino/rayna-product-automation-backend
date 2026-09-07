"""Generate timelines for the 18 London-with-options activities currently
missing a `catalog_activity_timeline` entry.

For each activity:
  1. Load activity data + up to 15 reviews (mix of platforms, brand-clean).
  2. Ask Claude to produce a chronological timeline (4-8 steps).
  3. Delete any existing timeline rows (idempotency) and insert new steps.

Steps schema (catalog_activity_timeline): order, time_label, title, description.
"""
import asyncio
import json
import logging
import os
import re
import sys

from sqlalchemy import delete, select, text
from app.db.base import async_session_factory
from app.db.models.activities import Activity, ActivityTimeline
from app.db.models.reviews import ProductReview
from app.integrations.claude_client import claude_client

LOCK_FILE = "/tmp/gen_timeline_for_18.pid"
REVIEW_SAMPLE_PER_ACT = 15
REVIEW_TEXT_TRUNCATE = 300
SLEEP_BETWEEN_ACTIVITIES = 0.5

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("gen_timeline")

OTA_BRANDS = re.compile(
    r"\b(viator|getyourguide|gyg|tripadvisor|trustpilot|booking\.com|klook|"
    r"tiqets|civitatis|expedia|tours4fun|headout|musement|airbnb experiences)\b",
    re.IGNORECASE,
)

TIMELINE_SYSTEM_PROMPT = """You are an SEO content specialist for Rayna Tours (raynatours.com). \
Generate a chronological timeline of what a customer experiences during this activity.

You will be given:
  (a) STRUCTURED ACTIVITY DATA — the ONLY source of factual content.
  (b) SAMPLE CUSTOMER REVIEWS — use ONLY to inform WHICH moments/experiences to highlight \
(what customers noticed, appreciated, or mentioned). Do NOT copy review text.

OUTPUT SCHEMA — JSON array of 4 to 8 objects, ordered chronologically. Each object has:
  - "order": integer starting at 1 (sequential)
  - "time_label": string (e.g. "Arrival", "First 30 min", "Mid-experience", "Departure", \
"Hour 1", "09:00" — pick natural labels; keep short, under 30 chars)
  - "title": string — a short SEO-friendly step name (3–10 words). Include the activity \
name or key landmark where it flows naturally.
  - "description": string — 1–3 sentences describing what happens at this step, drawn \
from the activity data. Use natural keywords (activity name, location) for SEO.

FACTUAL RULES:
- Every fact in title/description MUST be derivable from the activity data. Do NOT invent.
- For non-tour experiences (lounge access, standalone tickets, passes, meals) produce a \
reasonable arrival → main experience → departure flow using the details you do have.
- If the activity has no meaningful chronological structure, produce a minimal 3-step \
flow ("Entry", "Experience", "Departure") — never fabricate travel routes.

CONTENT SAFETY:
- Never mention OTA brand names (Viator, GetYourGuide, TripAdvisor, Trustpilot, \
Booking.com, Klook, Tiqets, Civitatis, Expedia, Headout, Musement, Airbnb Experiences).
- Do NOT write the brand name "Rayna Tours" in step text.

OUTPUT: JSON array only. No markdown fences, no preamble."""


def _build_activity_context(a: Activity) -> str:
    parts = [f"Name: {a.name}"]
    if getattr(a, "category", None): parts.append(f"Category: {a.category}")
    parts.append(f"Location: {a.city}, {a.country}")
    for attr in ("duration_minutes", "currency", "price_from",
                 "description_short", "description_long",
                 "highlights", "included", "excluded", "what_to_bring",
                 "important_notes", "cancellation_policy",
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
    by_plat: dict[str, list[ProductReview]] = {}
    for r in reviews:
        by_plat.setdefault(r.source_platform, []).append(r)
    ordered: list[ProductReview] = []
    while any(by_plat.values()) and len(ordered) < REVIEW_SAMPLE_PER_ACT * 2:
        for p in list(by_plat.keys()):
            if by_plat[p]:
                ordered.append(by_plat[p].pop(0))
            if len(ordered) >= REVIEW_SAMPLE_PER_ACT * 2:
                break
    out = []
    for r in ordered:
        txt = (r.enriched_text or r.review_text or "").strip()
        if not txt or OTA_BRANDS.search(txt):
            continue
        out.append(f"- ({r.source_platform}, {r.rating or 'n/a'}★) {txt[:REVIEW_TEXT_TRUNCATE]}")
        if len(out) >= REVIEW_SAMPLE_PER_ACT:
            break
    return out


def _parse_steps(raw: str) -> list[dict] | None:
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
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        desc = str(it.get("description", "")).strip()
        if not title:
            continue
        if OTA_BRANDS.search(title) or OTA_BRANDS.search(desc):
            continue  # defense in depth
        step = {
            "order": int(it.get("order", len(valid) + 1)),
            "time_label": str(it.get("time_label", "")).strip()[:100] or None,
            "title": title[:300],
            "description": desc if desc else None,
        }
        valid.append(step)
    return valid


async def main():
    async with async_session_factory() as db:
        ids = [r[0] for r in (await db.execute(text("""
            WITH lwo AS (
              SELECT id, name FROM activities
              WHERE LOWER(city) = 'london'
                AND tour_variants IS NOT NULL
                AND jsonb_array_length(tour_variants::jsonb) > 0
            ),
            t_agg AS (SELECT activity_id FROM catalog_activity_timeline GROUP BY activity_id)
            SELECT lwo.id FROM lwo LEFT JOIN t_agg ON t_agg.activity_id = lwo.id
            WHERE t_agg.activity_id IS NULL
            ORDER BY lwo.name
        """))).all()]

    log.info("Generating timelines for %d activities without one", len(ids))
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
                ).order_by(ProductReview.rating.desc().nullslast()).limit(60)
            )).scalars().all()

            review_sample = _pick_review_sample(list(reviews))
            review_block = "\n".join(review_sample) if review_sample else \
                "(no clean reviews available — use activity data only)"

            user_prompt = (
                f"STRUCTURED ACTIVITY DATA:\n{_build_activity_context(act)}\n\n"
                f"SAMPLE CUSTOMER REVIEWS:\n{review_block}\n\n"
                "Now generate the chronological timeline JSON."
            )

            try:
                raw = await claude_client.generate(
                    prompt=user_prompt,
                    system=TIMELINE_SYSTEM_PROMPT,
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    temperature=0.2,
                )
            except Exception as exc:
                log.error("[%d/%d] %s → CLAUDE ERROR: %s", i, len(ids), act.name[:50], str(exc)[:120])
                stats["error"] += 1
                continue

            steps = _parse_steps(raw)
            if not steps:
                log.error("[%d/%d] %s → BAD JSON. head: %r", i, len(ids), act.name[:50], raw[:150])
                stats["no_parse"] += 1
                continue

            # Delete any existing (defensive — we selected only rows w/o timeline
            # but a concurrent write could race). Then insert.
            await db.execute(delete(ActivityTimeline).where(ActivityTimeline.activity_id == aid))
            for idx, s in enumerate(steps, 1):
                db.add(ActivityTimeline(
                    activity_id=aid,
                    order=idx,
                    time_label=s.get("time_label"),
                    title=s["title"],
                    description=s.get("description"),
                ))
            await db.commit()

            log.info("[%d/%d] %s → OK (%d steps)", i, len(ids), act.name[:50], len(steps))
            stats["ok"] += 1

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
