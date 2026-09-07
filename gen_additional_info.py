"""Populate an `additional_info` JSONB column on the 103 London activities.

The column stores the AdditionalInformation payload the booking system expects:
  SoloFriendly, SeniorFriendly, KidsFriendly, SelfGuided, SwimmingRequired,
  PassportRequired, SeasonalOnly, PrivateOptions, TimeOfDay (int),
  BestSuited (int), TicketType, Transfer, MealIncluded, InstantConfirmation,
  WheelchairOK, PregnantGuestsOK

Strategy:
  1. Add the column (idempotent ALTER TABLE).
  2. For each activity, use Claude once with the activity data + a small review
     sample to infer all 13 subjective flags plus the two int enums. Include
     three deterministic flags we already have from DB columns.
  3. Validate + store JSON on the row.
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

LOCK_FILE = "/tmp/gen_additional_info.pid"
REVIEW_SAMPLE_PER_ACT = 10
REVIEW_TEXT_TRUNCATE = 250
SLEEP_BETWEEN_ACTIVITIES = 0.4

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("addl_info")

OTA_BRANDS = re.compile(
    r"\b(viator|getyourguide|gyg|tripadvisor|trustpilot|booking\.com|klook|"
    r"tiqets|civitatis|expedia|tours4fun|headout|musement|airbnb experiences)\b",
    re.IGNORECASE,
)

FLAG_KEYS = {
    # boolean fields
    "SoloFriendly", "SeniorFriendly", "KidsFriendly", "SelfGuided",
    "SwimmingRequired", "PassportRequired", "SeasonalOnly", "PrivateOptions",
    "TicketType", "Transfer", "MealIncluded",
    # integer enums
    "TimeOfDay", "BestSuited",
}

SYSTEM_PROMPT = """You infer travel-activity metadata flags from structured tour data. \
Output ONE JSON object with these exact keys and types — no markdown, no prose:

  "SoloFriendly": bool — accommodates solo travelers (yes if group/scheduled tours, walking tours, \
                        museum tickets, cruises; no if strictly couples-only or dinner-for-two).
  "SeniorFriendly": bool — true if fitness is Low/Easy, walking is minimal, or seating provided.
  "KidsFriendly": bool — true if no minimum age or min_age <= 7 AND the activity is not a bar \
                        crawl/adult-only nightlife.
  "SelfGuided": bool — true only if the activity name/description explicitly says self-guided, \
                       audio-guided, or app-guided (no live guide).
  "SwimmingRequired": bool — true only if swimming/water immersion is essential.
  "PassportRequired": bool — true only if crossing international borders (rare for city tours).
  "SeasonalOnly": bool — true if operates only in a specific season (Christmas markets, festive \
                        lights, summer-only cruise).
  "PrivateOptions": bool — true if any tour_variant is private (name contains "private" or \
                        "custom") OR the activity is a private tour.
  "TicketType": bool — true if the activity is essentially a ticket / entry pass with no guide \
                       or transport (SEA LIFE, Madame Tussauds, aquarium ticket, pass, lounge).
  "Transfer": bool — true if hotel pickup OR any transportation is included.
  "MealIncluded": bool — true if food/meal is included in the price.
  "TimeOfDay": int — 0=all-day/flexible, 1=morning, 2=afternoon, 3=evening, 4=night. Base on \
                     the activity's typical start times and character.
  "BestSuited": int — 0=all-audiences, 1=families, 2=couples, 3=solo/individual, 4=groups, \
                     5=business. Pick the SINGLE best match.

Rules:
- Output ONLY the JSON object. No markdown fences, no explanation, no leading text.
- Use booleans, not strings. Use integers 0-5 for the enums.
- Never emit any OTA brand name (Viator, GetYourGuide, TripAdvisor, Trustpilot, Booking.com, etc.).
- Be conservative — default to false when data is ambiguous."""


def _build_activity_context(a: Activity) -> str:
    parts = [f"Name: {a.name}"]
    for attr in ("category", "sub_category", "activity_type",
                 "description_short", "description_long",
                 "duration_minutes", "start_times", "operating_days",
                 "meeting_point_name", "meeting_point_desc",
                 "highlights", "included", "excluded", "important_notes",
                 "languages", "min_age", "max_age", "fitness_level",
                 "wheelchair_access", "pregnancy_restriction",
                 "pickup_available", "hotel_pickup_included",
                 "has_transport", "has_meals", "is_package",
                 "dress_code_note"):
        val = getattr(a, attr, None)
        if val is None or val == "" or val is False:
            continue
        if isinstance(val, (list, tuple)):
            val = ", ".join(str(x) for x in val)
        parts.append(f"{attr}: {val}")
    # include variant names (Claude uses these for PrivateOptions inference)
    variants = getattr(a, "tour_variants", None) or []
    if isinstance(variants, list) and variants:
        names = [v.get("name") for v in variants if isinstance(v, dict) and v.get("name")]
        if names:
            parts.append(f"tour_variants_names: {', '.join(names)}")
    return "\n".join(parts)


def _pick_review_sample(reviews: list[ProductReview]) -> list[str]:
    out = []
    for r in reviews:
        txt = (r.enriched_text or r.review_text or "").strip()
        if not txt or OTA_BRANDS.search(txt):
            continue
        out.append(f"- ({r.rating or 'n/a'}★) {txt[:REVIEW_TEXT_TRUNCATE]}")
        if len(out) >= REVIEW_SAMPLE_PER_ACT:
            break
    return out


def _parse_flags(raw: str) -> dict | None:
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    # normalise / coerce
    out = {}
    for key in FLAG_KEYS:
        v = obj.get(key)
        if key in {"TimeOfDay", "BestSuited"}:
            try:
                iv = int(v)
                out[key] = max(0, min(5, iv))
            except (ValueError, TypeError):
                out[key] = 0
        else:
            out[key] = bool(v) if isinstance(v, (bool, int)) else False
    return out


async def main():
    # 1. Ensure column exists.
    async with async_session_factory() as db:
        await db.execute(text(
            "ALTER TABLE activities ADD COLUMN IF NOT EXISTS additional_info JSONB"
        ))
        await db.commit()
        log.info("Column ensured: activities.additional_info JSONB")

    # 2. Pull the 103 activity IDs.
    async with async_session_factory() as db:
        ids = [r[0] for r in (await db.execute(text(
            "SELECT id FROM activities "
            "WHERE LOWER(city) = 'london' "
            "AND tour_variants IS NOT NULL "
            "AND jsonb_array_length(tour_variants::jsonb) > 0 "
            "ORDER BY name"
        ))).all()]

    log.info("Populating additional_info for %d activities", len(ids))
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
                ).order_by(ProductReview.rating.desc().nullslast()).limit(30)
            )).scalars().all()

            sample = _pick_review_sample(list(reviews))
            review_block = "\n".join(sample) if sample else "(no clean reviews available)"

            user_prompt = (
                f"ACTIVITY DATA:\n{_build_activity_context(act)}\n\n"
                f"SAMPLE REVIEWS:\n{review_block}\n\n"
                "Output the AdditionalInformation JSON now."
            )

            try:
                raw = await claude_client.generate(
                    prompt=user_prompt,
                    system=SYSTEM_PROMPT,
                    model="claude-sonnet-4-6",
                    max_tokens=512,
                    temperature=0.1,
                )
            except Exception as exc:
                log.error("[%d/%d] %s → CLAUDE ERROR: %s", i, len(ids), act.name[:50], str(exc)[:120])
                stats["error"] += 1
                continue

            flags = _parse_flags(raw)
            if flags is None:
                log.error("[%d/%d] %s → BAD JSON: %r", i, len(ids), act.name[:50], raw[:150])
                stats["no_parse"] += 1
                continue

            # Overlay hard truths from DB columns (these must not be overridden by Claude).
            flags["InstantConfirmation"] = bool(getattr(act, "instant_confirmation", False))
            flags["WheelchairOK"] = getattr(act, "wheelchair_access", None) not in (None, "", "No", "no")
            flags["PregnantGuestsOK"] = not bool(getattr(act, "pregnancy_restriction", False))
            # Deterministic overrides for MealIncluded and Transfer
            flags["MealIncluded"] = flags["MealIncluded"] or bool(getattr(act, "has_meals", False))
            flags["Transfer"] = flags["Transfer"] or bool(getattr(act, "has_transport", False)) \
                                or bool(getattr(act, "pickup_available", False))

            # Write it.
            await db.execute(
                text("UPDATE activities SET additional_info = CAST(:j AS jsonb) WHERE id = :aid"),
                {"j": json.dumps(flags), "aid": aid},
            )
            await db.commit()

            stats["ok"] += 1
            log.info("[%d/%d] %s → OK  TimeOfDay=%d BestSuited=%d",
                     i, len(ids), act.name[:50],
                     flags["TimeOfDay"], flags["BestSuited"])

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
