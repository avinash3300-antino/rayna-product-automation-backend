"""Derive AdditionalInformation block (TimeOfDay, BestSuited, capability flags)
from an Activity row. Used by API responses and payload builders alike.

TimeOfDay & BestSuited are bitmasks (sum of period/audience bits).
Bits are exposed alongside the int via the helper expanders below so the
frontend can chip-render them.
"""
from __future__ import annotations

from typing import Any

# ── Bitmask tables ──────────────────────────────────────────────────────────

TIME_OF_DAY_BITS: dict[str, int] = {
    "Sunrise": 1,
    "Morning": 2,
    "Afternoon": 4,
    "Sunset": 8,
    "Evening": 16,
    "Night": 32,
    "FullDay": 64,
    "Overnight": 128,
}

BEST_SUITED_BITS: dict[str, int] = {
    "Adults": 1,
    "AdventureSeekers": 2,
    "AllTravelers": 4,
    "Couples": 8,
    "CultureLovers": 16,
    "Families": 32,
    "FirstTimeVisitors": 64,
    "Groups": 128,
    "Kids": 256,
    "NatureLovers": 512,
    "Romantics": 1024,
    "ThrillSeekers": 2048,
}


def _contains_any(text: str, keywords: list[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in keywords)


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


# ── Derivations ─────────────────────────────────────────────────────────────


def _derive_time_of_day(start_times: list | None, duration_minutes: int | None) -> int:
    labels: set[str] = set()
    if duration_minutes and duration_minutes >= 480:
        labels.add("FullDay")

    if start_times:
        def bucket(h: int) -> str:
            if h < 6: return "Night"
            if h < 12: return "Morning"
            if h < 17: return "Afternoon"
            if h < 20: return "Sunset"
            if h < 23: return "Evening"
            return "Night"

        for t in start_times:
            try:
                h = int(str(t).split(":")[0])
                labels.add(bucket(h))
            except (ValueError, AttributeError):
                pass

    return sum(TIME_OF_DAY_BITS[l] for l in labels if l in TIME_OF_DAY_BITS)


def _derive_best_suited(activity: Any) -> int:
    name = (_safe_str(getattr(activity, "name", "")) or "").lower()
    desc = (_safe_str(getattr(activity, "description_long", "")) or "").lower()
    cat = _safe_str(getattr(activity, "category", "")) or ""
    text = name + " " + desc
    min_age = getattr(activity, "min_age", None)
    min_p = getattr(activity, "min_participants", None)

    audiences: set[str] = set()

    if getattr(activity, "price_adult", None) is not None:
        audiences.add("Adults")

    adventure_activities = ["safari", "quad bike", "zipline", "skydiv", "jetcar",
                            "atv ", "off-road", "bungee", "rafting", "kayak",
                            "rock climb", "paragliding", "dune bash"]
    if cat == "Adventure" or _contains_any(name, adventure_activities):
        audiences.add("AdventureSeekers")
    if _contains_any(name, ["thrill", "extreme adventure", "skydiv", "jetcar"]):
        audiences.add("ThrillSeekers")

    if cat in ("Landmark Tickets", "Sightseeing Tours", "Museums & Heritage") or \
       _contains_any(text, ["museum", "heritage", "historic", "cathedral", "abbey", "palace"]):
        audiences.add("CultureLovers")

    if cat in ("Landmark Tickets", "Passes & Combos", "Thames River", "Sightseeing Tours") or \
       "must-see" in desc or "iconic" in desc:
        audiences.add("FirstTimeVisitors")

    if cat == "Family & Kids" or "family" in name or "kid" in name:
        audiences.add("Families")
        audiences.add("Kids")
    if cat in ("Landmark Tickets", "Passes & Combos", "Sightseeing Tours", "Thames River") and \
       not _contains_any(text, ["bar crawl", "club crawl", "pub crawl", "adults only", "alcohol", "wine tasting"]):
        audiences.add("Families")
    if min_age is not None and min_age <= 5:
        audiences.add("Kids")

    if _contains_any(text, ["romantic", "sunset", "champagne", "dinner cruise", "afternoon tea"]):
        audiences.add("Couples")
        audiences.add("Romantics")

    if min_p is not None and min_p >= 4:
        audiences.add("Groups")
    if _contains_any(text, ["group tour", "small group", "private group", "club crawl"]):
        audiences.add("Groups")

    if _contains_any(text, ["nature", "wildlife", "garden", "park tour", "safari", "desert"]):
        audiences.add("NatureLovers")

    if not audiences or audiences == {"Adults"}:
        audiences.add("AllTravelers")

    return sum(BEST_SUITED_BITS[a] for a in audiences if a in BEST_SUITED_BITS)


def derive_additional_information(activity: Any) -> dict:
    """Return AdditionalInformation block for an Activity ORM row."""
    name = _safe_str(getattr(activity, "name", "")).lower()
    desc = _safe_str(getattr(activity, "description_long", "")).lower()
    cat = _safe_str(getattr(activity, "category", ""))
    text = name + " " + desc + " " + cat.lower()
    important_notes = getattr(activity, "important_notes", None)
    notes_text = " ".join(important_notes).lower() if isinstance(important_notes, list) else ""

    min_age = getattr(activity, "min_age", None)
    min_p = getattr(activity, "min_participants", None)
    fitness = getattr(activity, "fitness_level", None)
    difficulty = getattr(activity, "difficulty", None)
    wa = (_safe_str(getattr(activity, "wheelchair_access", None)) or "").lower()
    variants = getattr(activity, "tour_variants", None) or []
    op_days = getattr(activity, "operating_days", None) or []

    is_ticket = cat in ("Landmark Tickets", "Passes & Combos") or \
        _contains_any(name, ["ticket", "entry", "pass ", "admission"])
    self_guided = _contains_any(text, ["self-guided", "audio guide"]) and \
        not _contains_any(text, ["guided tour by"])
    kids_friendly = (min_age is None or min_age <= 5) or cat == "Family & Kids"
    adult_signals = ["bar crawl", "club crawl", "pub crawl", "wine tasting",
                     "adults only", "18+", "21+", "minimum age 18", "minimum age 21",
                     "alcohol focused", "speakeasy", "cocktail tour", "beer tour"]
    if _contains_any(name + " " + desc, adult_signals):
        kids_friendly = False
    if min_age is not None and min_age >= 12:
        kids_friendly = False

    senior_friendly = (fitness == "Easy") and (difficulty in ("Beginner", None))
    wheelchair_ok = wa in ("yes", "accessible", "full") or "accessible" in wa
    swimming = _contains_any(text, ["snorkel", "diving", "swim", "water park", "beach swim", "pool swimming"])
    passport = _contains_any(notes_text + " " + desc, ["passport"])
    seasonal = (0 < len(op_days) < 5) or _contains_any(text, ["seasonal", "summer only", "winter only"])

    solo = (min_p is None or min_p <= 1)
    if _contains_any(name + " " + desc, [
        "couples only", "minimum 2 people", "minimum 2 guests", "min 2 pax",
        "for two", "romantic for two", "couples retreat",
    ]):
        solo = False
    if "private" in name and _contains_any(name + " " + desc, ["romantic", "couples", "for two"]):
        solo = False

    private_opts = any(
        "private" in (v.get("name", "") + v.get("title", "")).lower()
        for v in variants if isinstance(v, dict)
    )

    return {
        "TimeOfDay": _derive_time_of_day(getattr(activity, "start_times", None), getattr(activity, "duration_minutes", None)),
        "Transfer": bool(getattr(activity, "has_transport", False)),
        "TicketType": is_ticket,
        "MealIncluded": bool(getattr(activity, "has_meals", False)),
        "SelfGuided": self_guided,
        "BestSuited": _derive_best_suited(activity),
        "KidsFriendly": kids_friendly,
        "SeniorFriendly": senior_friendly,
        "WheelchairOK": wheelchair_ok,
        "PregnantGuestsOK": not bool(getattr(activity, "pregnancy_restriction", False)),
        "SwimmingRequired": swimming,
        "InstantConfirmation": bool(getattr(activity, "instant_confirmation", False)),
        "PassportRequired": passport,
        "SeasonalOnly": seasonal,
        "SoloFriendly": solo,
        "PrivateOptions": private_opts,
    }


def expand_time_of_day(value: int) -> list[str]:
    """Convert bitmask int → list of labels (for UI chip rendering)."""
    return [k for k, bit in TIME_OF_DAY_BITS.items() if value & bit]


def expand_best_suited(value: int) -> list[str]:
    """Convert bitmask int → list of audience labels (for UI chip rendering)."""
    return [k for k, bit in BEST_SUITED_BITS.items() if value & bit]
