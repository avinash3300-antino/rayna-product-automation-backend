"""FAQ generation v2 — grounded, source-tagged, validated per FAQ-Generation-Logic.md.

Key differences from v1:
- 15-30 FAQs (target 15-20), 30-90 words each.
- Every FAQ carries a `source` tag (content_overview / content_highlights /
  content_inclusions / content_exclusions / content_know_before /
  content_how_to_redeem / amenity_field / options / location / derived /
  brand_usp / verified_fact).
- Doubt rule enforced: no transfer-type words, no exact hours, no prices.
- Style scan: no em/en dashes, no "AI-tell" marketing words, no "!".
- Post-generation validation gate with one regeneration attempt.
- Feeds real tour_variants (names + person_types + inventory) so the LLM
  can produce options-derived FAQs grounded in real data.
"""
import json
import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activities import Activity
from app.integrations.claude_client import claude_client
from app.integrations.gemini_client import gemini_client

logger = logging.getLogger(__name__)

# Provider switch: "gemini" (default, cheap) or "claude" (higher quality)
FAQ_PROVIDER = "gemini"

FAQ_MODEL_CLAUDE = "claude-haiku-4-5-20251001"
FAQ_ESCALATION_MODEL_CLAUDE = "claude-sonnet-4-6"

FAQ_MODEL_GEMINI = "gemini-flash-latest"
FAQ_ESCALATION_MODEL_GEMINI = "gemini-pro-latest"

VALID_SOURCE_TAGS = {
    "content_overview", "content_highlights", "content_inclusions",
    "content_exclusions", "content_know_before", "content_how_to_redeem",
    "amenity_field", "options", "location", "derived", "brand_usp",
    "verified_fact",
}

BANNED_WORDS = [
    "delve", "delving", "immerse", "immersing", "immersive",
    "vibrant", "bustling", "nestled", "breathtaking",
    "must-visit", "must visit", "hidden gem",
    "unforgettable", "embark", "unleash",
    "whether you're a", "whether you are a",
]

TRANSFER_TYPE_WORDS = ["private transfer", "shared transfer", "sharing transfer",
                       "private pickup", "shared pickup", "sharing pickup"]

FAQ_SYSTEM_PROMPT_V2 = """You generate factual FAQs for RaynaTours activity pages.

## FIRST PRINCIPLE (overrides everything)
No information is better than wrong information. If a fact is unavailable, ambiguous, or doubtful, DO NOT write that question at all. A smaller set of correct FAQs always beats a larger set with one wrong answer.

## OUTPUT
Return ONLY a JSON array. No markdown, no prose. Each item:
{"question": "...", "answer": "...", "source": "<tag>"}

Valid source tags (must use one from this list):
- content_overview       (from the description)
- content_highlights     (from highlights list)
- content_inclusions     (from what's included)
- content_exclusions     (from what's excluded)
- content_know_before    (from important notes / know-before-you-go)
- content_how_to_redeem  (from redemption instructions)
- amenity_field          (structured field: duration, language, cancellation, instant confirmation)
- options                (from tour_variants — the bookable options)
- location               (from address, meeting point, area, city)
- derived                (a logical inference certain from the content, e.g. "outdoors" for a desert tour)
- brand_usp              (RaynaTours operator/support standing policy)
- verified_fact          (a globally famous, easily checkable fact about a named landmark)

## COUNT
15-20 FAQs per activity. Up to 25 if content genuinely supports it. Never fewer than 15.

## ANSWER STYLE
- 30-90 words each. Hard band 20-110.
- Answer-first: first sentence directly answers the question. No preamble.
- Plain text only. No HTML. No markdown inside answers.
- Include a concrete detail (a number, name, distance) whenever the source supports it.
- Tone: knowledgeable phone-support agent. Direct, warm, plain.
- No two FAQs may answer the same thing.

## HARD BANS (do not output)
- Prices, currency figures, "cheapest", "from $X". Never.
- Transfer-type words: "private", "shared", "sharing" describing a transfer or pickup. Use type-neutral wording like "a roundtrip hotel transfer is included" instead.
- Exact opening hours, start times, Ramadan/seasonal timings — unless a structured amenity_field explicitly provides them.
- Child age thresholds, weight/height limits, pregnancy or medical suitability — unless the source states them.
- Em-dashes (—) and en-dashes (–). Use commas or periods.
- Exclamation marks.
- AI-tell marketing words: delve, immerse, vibrant, bustling, nestled, breathtaking, must-visit, hidden gem, unforgettable, embark, "whether you're a X or a Y".

## COVERAGE MENU (include every question the data can truthfully answer)
- Booking & logistics: instant confirmation, voucher format, ID needed, how to redeem, hotel pickup/transfer (type-neutral).
- Suitability: solo/couple/family/group/seniors; kids OK, physical fitness needed, wheelchair — only if content supports.
- The experience: what you do, how long, indoor/outdoor, guided/self-guided, guide language, what to wear/bring, meals (veg/halal only if stated).
- Location & discovery: where it is, how to get there, what's nearby, can it be combined.
- Options / variants: "What options can I choose?" (list real variant names, max 5, no prices), "Are child tickets available?" (from person types), "Are infant entries free?" (only if source data supports it — never guess).
- Operator/trust (brand_usp): "Who operates this activity?", "Who do I contact if plans change?" — RaynaTours arranges the booking and provides local on-ground support.
- Verified facts (verified_fact, MAX 2-3, use sparingly): only for genuinely globally famous landmarks tied to this activity (e.g. Eiffel Tower height, Colosseum age). If unsure, omit.

## SOURCE MAY BE WRONG — DROP DOUBTFUL CLAIMS
If two source sections contradict each other, or a claim looks like it belongs to a different activity/city, omit it. Never repeat obvious scraped garbage.

## RULE OF THUMB
Large majority of FAQs must be content-grounded tags (content_*, amenity_field, options, location). At most 2-3 verified_fact FAQs. At most 2 brand_usp FAQs. derived is for safe logical inference only.
"""

BRAND_USP_HINT = """Brand context (use for `brand_usp` FAQs — max 2):
RaynaTours coordinates the booking and provides local on-ground support in the destination city. Confirmed vouchers arrive by email. Customer support responds by email and phone for booking changes or on-day issues."""

# ── Sanitization ──────────────────────────────────────────────────────

_MARKUP_RE = re.compile(r"<[^>]+>|\\u00a0|\s+")


def _clean(s: str | None, max_len: int = 600) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len]


def _clean_list(items, max_items: int = 12, max_item_len: int = 150) -> list[str]:
    if not items or not isinstance(items, list):
        return []
    out = []
    for x in items[:max_items]:
        s = _clean(str(x), max_item_len)
        if s and len(s) > 2:
            out.append(s)
    return out


def _summarize_variants(variants) -> list[dict]:
    """Return top-5 variants with just what the LLM needs (no prices)."""
    if not variants or not isinstance(variants, list):
        return []
    seen_names = set()
    out = []
    for v in variants:
        if not isinstance(v, dict):
            continue
        name = _clean(v.get("name"), 200)
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        out.append({
            "name": name,
            "person_types": v.get("person_types") or [],
            "has_inventory": bool(v.get("has_inventory")),
        })
        if len(out) >= 5:
            break
    return out


def _summarize_reviews(snippets) -> list[str]:
    if not snippets or not isinstance(snippets, list):
        return []
    out = []
    for s in snippets[:3]:
        if isinstance(s, dict):
            text = s.get("text") or s.get("review") or s.get("body")
        else:
            text = s
        text = _clean(text, 200)
        if text:
            out.append(text)
    return out


def _build_activity_context_v2(a: Activity) -> str:
    parts = [
        f"Activity name: {a.name}",
        f"Category: {a.category}",
        f"City: {a.city}",
        f"Country: {a.country}",
    ]
    if a.duration_minutes:
        parts.append(f"Duration (minutes): {a.duration_minutes}")
    if a.languages:
        langs = _clean_list(a.languages, 8, 30)
        if langs:
            parts.append(f"Languages: {', '.join(langs)}")
    if a.instant_confirmation:
        parts.append("Instant confirmation: yes")
    if a.free_cancellation:
        parts.append("Free cancellation: yes")
    if a.cancellation_hours:
        parts.append(f"Free cancellation up to hours before: {a.cancellation_hours}")
    if a.hotel_pickup_included:
        parts.append("Hotel pickup included (do NOT specify private or shared)")
    elif a.pickup_available:
        parts.append("Pickup available at select points (do NOT specify private or shared)")

    desc = _clean(a.description_long, 1500) or _clean(a.description_short, 800)
    if desc:
        parts.append(f"Description: {desc}")

    hl = _clean_list(a.highlights)
    if hl:
        parts.append("Highlights:\n- " + "\n- ".join(hl))
    inc = _clean_list(a.included)
    if inc:
        parts.append("Included:\n- " + "\n- ".join(inc))
    exc = _clean_list(a.excluded)
    if exc:
        parts.append("Excluded:\n- " + "\n- ".join(exc))
    notes = _clean_list(a.important_notes)
    if notes:
        parts.append("Know before you go:\n- " + "\n- ".join(notes))
    redeem = _clean_list(a.redemption_instructions)
    if redeem:
        parts.append("Redemption:\n- " + "\n- ".join(redeem))

    if a.meeting_point_name or a.meeting_point_desc:
        mp = _clean(a.meeting_point_desc, 400) or _clean(a.meeting_point_name, 200)
        parts.append(f"Meeting point: {mp}")
    if a.address:
        parts.append(f"Address: {_clean(a.address, 300)}")
    if a.nearby_landmark:
        parts.append(f"Nearby landmark: {_clean(a.nearby_landmark, 200)}")
    if a.what_to_bring:
        parts.append(f"What to bring: {_clean(a.what_to_bring, 300)}")
    if a.dress_code_note:
        parts.append(f"Dress code: {_clean(a.dress_code_note, 200)}")
    if a.cancellation_policy:
        parts.append(f"Cancellation policy: {_clean(a.cancellation_policy, 400)}")

    variants = _summarize_variants(a.tour_variants)
    if variants:
        v_lines = []
        for v in variants:
            pts = ", ".join(v["person_types"]) if v["person_types"] else "ADULT"
            inv = "in stock" if v["has_inventory"] else "check availability"
            v_lines.append(f'- "{v["name"]}" (person types: {pts}; {inv})')
        parts.append("Bookable options (real, from supplier data):\n" + "\n".join(v_lines))

    reviews = _summarize_reviews(a.review_snippets)
    if reviews:
        parts.append("Traveller review snippets:\n- " + "\n- ".join(reviews))

    return "\n\n".join(parts)


# ── Validation gate (§8 of the doc) ───────────────────────────────────

def _word_count(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


def _normalize_question(q: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (q or "").lower())


def _has_em_or_en_dash(s: str) -> bool:
    return "—" in s or "–" in s


def _has_price_figure(s: str) -> bool:
    if re.search(r"[$€£¥₹]\s*\d", s):
        return True
    if re.search(r"\b(?:usd|eur|gbp|aed|inr|jpy|sgd|myr)\s*\d", s.lower()):
        return True
    if re.search(r"\bfrom\s+(?:usd|eur|gbp|\$|€|£)\b", s.lower()):
        return True
    return False


def _has_banned_word(s: str) -> bool:
    low = s.lower()
    return any(w in low for w in BANNED_WORDS)


def _has_transfer_type_word(s: str) -> bool:
    low = s.lower()
    return any(w in low for w in TRANSFER_TYPE_WORDS)


def _validate_faqs(faqs) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(faqs, list):
        return False, ["output is not a JSON array"]

    if len(faqs) < 15:
        errors.append(f"too few FAQs: {len(faqs)} (need >=15)")
    if len(faqs) > 30:
        errors.append(f"too many FAQs: {len(faqs)} (max 30)")

    seen = set()
    source_tags_used: set[str] = set()
    verified_fact_count = 0
    brand_usp_count = 0

    for i, item in enumerate(faqs):
        if not isinstance(item, dict):
            errors.append(f"item {i}: not an object")
            continue
        q = item.get("question")
        a = item.get("answer")
        tag = item.get("source")
        if not isinstance(q, str) or not q.strip():
            errors.append(f"item {i}: missing question")
            continue
        if not isinstance(a, str) or not a.strip():
            errors.append(f"item {i}: missing answer")
            continue
        if tag not in VALID_SOURCE_TAGS:
            errors.append(f"item {i}: invalid source tag '{tag}'")

        norm = _normalize_question(q)
        if norm in seen:
            errors.append(f"item {i}: duplicate question")
        seen.add(norm)

        wc = _word_count(a)
        if wc < 15 or wc > 120:
            errors.append(f"item {i}: answer word count {wc} out of band [15,120]")

        if _has_em_or_en_dash(a) or _has_em_or_en_dash(q):
            errors.append(f"item {i}: contains em/en dash")
        if a.count("!") > 0:
            errors.append(f"item {i}: contains exclamation mark")
        if _has_price_figure(a):
            errors.append(f"item {i}: contains a price/currency figure")
        if _has_banned_word(a):
            errors.append(f"item {i}: contains banned marketing word")
        if _has_transfer_type_word(a):
            errors.append(f"item {i}: contains transfer-type word (private/shared)")

        if tag == "verified_fact":
            verified_fact_count += 1
        if tag == "brand_usp":
            brand_usp_count += 1
        if tag in VALID_SOURCE_TAGS:
            source_tags_used.add(tag)

    if verified_fact_count > 3:
        errors.append(f"too many verified_fact FAQs: {verified_fact_count} (max 3)")
    if brand_usp_count > 2:
        errors.append(f"too many brand_usp FAQs: {brand_usp_count} (max 2)")

    return (len(errors) == 0), errors


def _parse_json(raw: str):
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    # Strip leading "json" tag left from fences
    if s.lower().startswith("json\n"):
        s = s[5:]
    return json.loads(s)


async def _one_generation(
    activity_context: str,
    model: str,
    extra_instructions: str = "",
    provider: str = FAQ_PROVIDER,
) -> tuple[list | None, str]:
    """Return (parsed_faqs, raw_text). parsed_faqs is None if JSON parse failed."""
    user_prompt = f"""{BRAND_USP_HINT}

Activity data:
---
{activity_context}
---

{extra_instructions}

Generate the FAQs now. Return ONLY the JSON array."""

    client = gemini_client if provider == "gemini" else claude_client
    raw = await client.generate(
        prompt=user_prompt,
        system=FAQ_SYSTEM_PROMPT_V2,
        model=model,
        max_tokens=6000,
        temperature=0.4,
    )
    try:
        parsed = _parse_json(raw)
    except (json.JSONDecodeError, IndexError, ValueError):
        return None, raw
    return parsed, raw


async def generate_faqs_for_activity_v2(
    db: AsyncSession, activity_id: UUID
) -> dict:
    """Generate v2 FAQs. Returns {'faqs': [...], 'ok': bool, 'errors': [...], 'attempts': N}."""
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()
    if not activity:
        raise ValueError(f"Activity {activity_id} not found")

    context = _build_activity_context_v2(activity)

    # Select model tier by provider
    if FAQ_PROVIDER == "gemini":
        primary_model = FAQ_MODEL_GEMINI
        escalation_model = FAQ_ESCALATION_MODEL_GEMINI
    else:
        primary_model = FAQ_MODEL_CLAUDE
        escalation_model = FAQ_ESCALATION_MODEL_CLAUDE

    # First attempt
    faqs, raw = await _one_generation(context, primary_model)
    attempts = 1
    if faqs is None:
        # bad JSON — retry with a nudge
        faqs, raw = await _one_generation(
            context, primary_model,
            extra_instructions="Previous attempt was not valid JSON. Return ONLY the JSON array, nothing else.",
        )
        attempts += 1

    if faqs is None:
        return {"faqs": [], "ok": False, "errors": ["invalid JSON after 2 attempts"], "attempts": attempts}

    ok, errors = _validate_faqs(faqs)

    # One regeneration attempt on primary model with error feedback
    if not ok:
        feedback = "Previous output failed validation. Fix these issues:\n- " + "\n- ".join(errors[:8])
        faqs2, _ = await _one_generation(context, primary_model, extra_instructions=feedback)
        attempts += 1
        if faqs2 is not None:
            ok2, errors2 = _validate_faqs(faqs2)
            if ok2:
                faqs, ok, errors = faqs2, True, []
            elif len(errors2) < len(errors):
                faqs, errors = faqs2, errors2

    # Escalate if still failing
    if not ok:
        feedback = "Previous output failed validation. Fix these issues:\n- " + "\n- ".join(errors[:8])
        faqs3, _ = await _one_generation(context, escalation_model, extra_instructions=feedback)
        attempts += 1
        if faqs3 is not None:
            ok3, errors3 = _validate_faqs(faqs3)
            if ok3:
                faqs, ok, errors = faqs3, True, []
            elif len(errors3) < len(errors):
                faqs, errors = faqs3, errors3

    # Persist only valid-shape items (question/answer required; source may be repaired)
    cleaned = []
    for item in faqs:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question") or "").strip()
        a = str(item.get("answer") or "").strip()
        tag = item.get("source") or "content_overview"
        if not q or not a:
            continue
        if tag not in VALID_SOURCE_TAGS:
            tag = "content_overview"
        cleaned.append({"question": q, "answer": a, "source": tag})

    activity.faqs = cleaned
    await db.flush()

    return {"faqs": cleaned, "ok": ok, "errors": errors, "attempts": attempts}
