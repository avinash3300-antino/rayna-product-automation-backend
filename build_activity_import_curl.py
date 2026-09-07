"""Build a ready-to-paste curl body for the Rayna master 'create-activity-process/save' endpoint.

Maps one internal activity into the expected JSON schema and prints the full
curl command to stdout.
"""
import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta

# Silence SQLAlchemy / httpx chatter so stdout is pure curl output
logging.basicConfig(level=logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


AUTH = "pk_Activity_Supplier_Connect_3f2504e0-4f89-11d3-9a0c-0305e82c3301"
ENDPOINT = "https://api-access-alb-external-dev-1976965964.ap-southeast-1.elb.amazonaws.com/api/rayna-master/create-activity-process/save"

# ─── Rayna master lookup tables (from Country/City list endpoints) ───────────
# CountryId → country name. Values are the master IDs the create-activity API expects.
COUNTRY_ID_MAP = {
    "United Arab Emirates": 13063,
    "Albania": 13065,
    "Armenia": 13066,
    "Austria": 13069,
    "Australia": 13070,
    "Azerbaijan": 13072,
    "Belgium": 13076,
    "Bahrain": 13078,
    "Brazil": 13083,
    "Canada": 13088,
    "Switzerland": 13091,
    "China": 13096,
    "Cyprus": 13100,
    "Germany": 13102,
    "Estonia": 13107,
    "Egypt": 13108,
    "Spain": 13109,
    "France": 15377,
    "United Kingdom": 15379,
    "Georgia": 15381,
    "Ghana": 15382,
    "Greece": 15388,
    "Hong Kong": 15391,
    "Croatia": 15393,
    "Hungary": 15395,
    "Indonesia": 15396,
    "Ireland": 15397,
    "India": 15399,
    "Italy": 15403,
    "Jordan": 15405,
    "Japan": 15406,
    "Kenya": 15407,
    "South Korea": 15412,
    "Kazakhstan": 15415,
    "Sri Lanka": 15420,
    "Macau": 15434,
    "Mauritius": 15438,
    "Maldives": 15439,
    "Malaysia": 15442,
    "Netherlands": 15449,
    "Oman": 15453,
    "Philippines": 15458,
    "Pakistan": 15459,
    "Portugal": 15462,
    "Qatar": 15465,
    "Russia": 15469,
    "Saudi Arabia": 15471,
    "Singapore": 15474,
    "Slovenia": 15476,
    "Thailand": 15486,
    "Turkey": 15491,
    "Taiwan": 15493,
    "United States": 15497,
    "Uzbekistan": 15499,
    "Vietnam": 15504,
    "South Africa": 15508,
}

# CityId lookup — internal city name → {CityId, CountryId} for the master API.
# Populated batch-by-batch as we get responses from GET /master/city endpoints.
CITY_ID_MAP = {
    # Thailand
    "Bangkok": {"CityId": 16424, "CountryId": 15486},
    "Chiang Rai": {"CityId": 17036, "CountryId": 15486},
    "Chiang Mai": {"CityId": 17346, "CountryId": 15486},
    "Phuket": {"CityId": 19240, "CountryId": 15486},
    "Hua Hin": {"CityId": 19399, "CountryId": 15486},
    "Krabi": {"CityId": 19786, "CountryId": 15486},
    "Koh Samui": {"CityId": 20033, "CountryId": 15486},
    "Pattaya": {"CityId": 28213, "CountryId": 15486},

    # Singapore (internal DB stores it as "Singapore")
    "Singapore": {"CityId": 23726, "CountryId": 15474},

    # Saudi Arabia
    "Jeddah": {"CityId": 19683, "CountryId": 15471},
    "Makkah": {"CityId": 20776, "CountryId": 15471},
    "Madina": {"CityId": 20789, "CountryId": 15471},
    "Dammam": {"CityId": 22883, "CountryId": 15471},
    "Riyadh": {"CityId": 23288, "CountryId": 15471},
    "Al Ula": {"CityId": 70349, "CountryId": 15471},

    # Oman
    "Khasab": {"CityId": 19901, "CountryId": 15453},
    "Muscat": {"CityId": 20950, "CountryId": 15453},
    "Salalah": {"CityId": 23392, "CountryId": 15453},
    "Mirbat": {"CityId": 59521, "CountryId": 15453},
    "Taqa": {"CityId": 176849, "CountryId": 15453},

    # United States
    "Chicago": {"CityId": 17130, "CountryId": 15497},
    "Las Vegas": {"CityId": 20219, "CountryId": 15497},
    "Miami": {"CityId": 21083, "CountryId": 15497},
    "New York": {"CityId": 21921, "CountryId": 15497},
    "Orlando": {"CityId": 22106, "CountryId": 15497},
    "San Francisco": {"CityId": 23610, "CountryId": 15497},
    "Washington DC": {"CityId": 25202, "CountryId": 15497},

    # Italy
    "Naples": {"CityId": 21629, "CountryId": 15403},
    "Rome": {"CityId": 23214, "CountryId": 15403},
    "Venice": {"CityId": 24930, "CountryId": 15403},

    # Turkey
    "Antalya": {"CityId": 15865, "CountryId": 15491},
    "Cappadocia": {"CityId": 16918, "CountryId": 15491},
    "Istanbul": {"CityId": 19609, "CountryId": 15491},
    "Pamukkale": {"CityId": 22249, "CountryId": 15491},

    # United Kingdom
    "London": {"CityId": 20569, "CountryId": 15379},
}


_SELECT = """
  SELECT
    a.id, a.name, a.slug, a.city, a.country, a.lat, a.lng, a.address,
    a.description_short, a.description_long, a.highlights, a.included, a.excluded,
    a.what_to_bring, a.dress_code_note, a.meeting_point_desc,
    a.redemption_instructions, a.important_notes,
    a.tour_variants, a.gallery_json, a.cover_image_url,
    a.faqs, a.languages, a.duration_minutes,
    a.free_cancellation, a.cancellation_hours, a.instant_confirmation,
    a.start_times, a.operating_days,
    a.wheelchair_access, a.pregnancy_restriction,
    a.hotel_pickup_included, a.pickup_available,
    a.has_meals, a.has_transport,
    (SELECT jsonb_agg(row_to_json(pr.*) ORDER BY pr.rating DESC NULLS LAST)
     FROM (
        SELECT reviewer_name, rating, review_title, review_text, enriched_text, review_date
        FROM product_reviews
        WHERE product_id=a.id AND product_type='activities'
          AND enriched_text IS NOT NULL AND enriched_text != '__SKIP__'
     ) pr) AS sample_reviews
  FROM activities a
"""


async def _fetch_timeline(db, activity_id):
    """Return list of (order, time_label, title, description) for the activity."""
    from sqlalchemy import text
    r = await db.execute(text("""
      SELECT "order", time_label, title, description
      FROM catalog_activity_timeline
      WHERE activity_id = :aid
      ORDER BY "order"
    """), {"aid": str(activity_id)})
    return [dict(row._mapping) for row in r.fetchall()]


async def fetch_activity(activity_id: str):
    from app.db.base import async_session_factory, engine
    from sqlalchemy import text
    from types import SimpleNamespace
    engine.echo = False
    async with async_session_factory() as db:
        r = await db.execute(text(_SELECT + " WHERE a.id = :aid"), {"aid": activity_id})
        row = r.fetchone()
        if row is None:
            return None
        timeline = await _fetch_timeline(db, row.id)
        ns = SimpleNamespace(**dict(row._mapping))
        ns._timeline = timeline
        return ns


async def fetch_best_activity_for_city(city: str):
    """Pick the richest tier-0 activity for a city — long desc, many FAQs & variants."""
    from app.db.base import async_session_factory, engine
    from sqlalchemy import text
    engine.echo = False
    async with async_session_factory() as db:
        r = await db.execute(text(_SELECT + """
          WHERE a.city = :city
            AND a.deleted_at IS NULL AND a.merged_into_id IS NULL
            AND a.tour_variants IS NOT NULL AND a.tour_variants::text NOT IN ('null','[]')
            AND a.gallery_json IS NOT NULL AND a.gallery_json::text NOT IN ('null','[]')
            AND a.faqs IS NOT NULL AND a.faqs::text NOT IN ('null','[]')
            AND length(a.description_long) > 500
          ORDER BY
            jsonb_array_length(a.faqs::jsonb) DESC,
            jsonb_array_length(a.gallery_json::jsonb) DESC,
            jsonb_array_length(a.tour_variants::jsonb) DESC,
            length(a.description_long) DESC
          LIMIT 1
        """), {"city": city})
        row = r.fetchone()
        if row is None:
            return None
        timeline = await _fetch_timeline(db, row.id)
        from types import SimpleNamespace
        ns = SimpleNamespace(**dict(row._mapping))
        ns._timeline = timeline
        return ns


def _list_or_empty(v):
    return v if isinstance(v, list) else []


def _join_lines(items) -> str:
    """Turn list of bullets into a single \\n-joined string for text fields."""
    return "\n".join(f"- {x}" for x in _list_or_empty(items) if x)


def _first_or_default(items, default=""):
    return items[0] if _list_or_empty(items) else default


def _operating_days_map(days) -> list[str]:
    """Map arbitrary day-name inputs to the API's canonical 3-char codes.

    Rayna master API accepts strictly 3-character codes: Sun, Mon, Tue, Wed,
    Thu, Fri, Sat. Older 4-char forms (Tues, Thur) are NOT accepted.
    """
    canon = {
        "monday": "Mon", "mon": "Mon",
        "tuesday": "Tue", "tue": "Tue", "tues": "Tue",
        "wednesday": "Wed", "wed": "Wed",
        "thursday": "Thu", "thu": "Thu", "thur": "Thu", "thurs": "Thu",
        "friday": "Fri", "fri": "Fri",
        "saturday": "Sat", "sat": "Sat",
        "sunday": "Sun", "sun": "Sun",
    }
    result = []
    for d in _list_or_empty(days):
        key = str(d).strip().lower()
        code = canon.get(key)
        if code and code not in result:
            result.append(code)
    if not result:
        result = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return result


def _additional_field_names(a) -> list[str]:
    """Populate AdditionalInfo.SelectedFieldNames from real DB attributes only.

    Groups covered (matches Rayna extranet Additional Info taxonomy):
      * Voucher Mode
      * Booking Preferences
      * Best Suited For (derived from category)
      * Time of Day (derived from start_times / duration)
      * Guest Suitability (derived from min_age / pregnancy_restriction)
      * Physical Intensity (derived from difficulty / fitness_level)
      * Special Requirements (dress code, waiver, age/weight/swim gates)

    Only add a label when a DB attribute genuinely supports it. No dummy tags.
    """
    fields: list[str] = []

    # ── Voucher Mode ────────────────────────────────────────────────────
    if getattr(a, "wheelchair_access", None):
        fields.append("Wheelchair Access")
    if getattr(a, "hotel_pickup_included", False):
        fields.append("Hotel Pickup")
    if getattr(a, "has_meals", False):
        fields.append("Meal")
    if getattr(a, "has_transport", False):
        fields.append("Transfer")
    # Guide inferred from having languages defined (all guided tours do)
    if _list_or_empty(getattr(a, "languages", None)):
        fields.append("Guide")
    # Entry Ticket inferred from has_inventory on any variant
    variants = _list_or_empty(getattr(a, "tour_variants", None))
    if any(isinstance(v, dict) and v.get("has_inventory") for v in variants):
        fields.append("Entry Ticket")

    # ── Booking Preferences ────────────────────────────────────────────
    if getattr(a, "instant_confirmation", False):
        fields.append("Instant Confirmation")
    else:
        fields.append("On Request")
    # Voucher Required — always true for e-tickets
    fields.append("Voucher Required")

    # ── Best Suited For (from category) ────────────────────────────────
    cat = (getattr(a, "category", "") or "").lower()
    if any(k in cat for k in ("family", "kids", "children", "theme park")):
        fields.append("Family with Kids")
    if any(k in cat for k in ("romantic", "couple", "dinner cruise")):
        fields.append("Couples")
    if any(k in cat for k in ("adventure", "hiking", "trekking", "kayak", "safari")):
        fields.extend(["Group", "Solo travelling"])
    if any(k in cat for k in ("sightseeing", "guided tour", "walking")):
        fields.extend(["Couples", "Group"])

    # ── Time of Day (from start_times & duration) ──────────────────────
    starts = _list_or_empty(getattr(a, "start_times", None))
    dur = getattr(a, "duration_minutes", None) or 0
    try:
        dur = int(dur)
    except (TypeError, ValueError):
        dur = 0
    if dur >= 480 and dur < 1440:
        fields.append("Full Day")
    if dur >= 1440:
        fields.append("Overnight")
    for st in starts:
        try:
            hh = int(str(st)[:2])
        except (ValueError, TypeError):
            continue
        if 5 <= hh < 12: fields.append("Morning")
        elif 12 <= hh < 17: fields.append("Afternoon")
        elif 17 <= hh < 21: fields.append("Evening")
        elif hh >= 21 or hh < 5: fields.append("Night")

    # ── Guest Suitability ──────────────────────────────────────────────
    min_age = getattr(a, "min_age", None)
    if min_age is None or (isinstance(min_age, int) and min_age <= 3):
        fields.append("All Ages")
    elif isinstance(min_age, int):
        if min_age >= 18:
            fields.append("Adults Only")
        if min_age == 18:
            fields.append("18 Only")
    if getattr(a, "fitness_level", None) in ("high", "challenging", "extreme"):
        fields.append("Physically Fit Required")
    if not getattr(a, "pregnancy_restriction", False):
        fields.append("Pregnant Women OK")

    # ── Physical Intensity ─────────────────────────────────────────────
    diff = (getattr(a, "difficulty", "") or getattr(a, "fitness_level", "") or "").lower()
    if diff in ("easy", "low", "gentle"):
        fields.append("Easy")
    elif diff in ("moderate", "medium"):
        fields.append("Moderate")
    elif diff in ("challenging", "hard"):
        fields.append("Challenging")
    elif diff in ("extreme", "expert"):
        fields.append("Extreme")

    # ── Special Requirements ───────────────────────────────────────────
    if getattr(a, "dress_code_note", None):
        fields.append("Dress Code")
    if min_age is not None and isinstance(min_age, int) and min_age > 0:
        fields.append("Min Age Restriction")

    # Dedup while preserving order
    seen = set()
    out = []
    for f in fields:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _language_string(langs) -> str:
    lang_map = {"en": "English", "fr": "French", "es": "Spanish", "de": "German",
                "it": "Italian", "pt": "Portuguese", "ja": "Japanese", "zh": "Chinese",
                "ko": "Korean", "ar": "Arabic", "ru": "Russian", "hi": "Hindi",
                "tr": "Turkish", "nl": "Dutch"}
    items = _list_or_empty(langs) or ["en"]
    named = [lang_map.get(str(l).lower(), str(l).title()) for l in items]
    return ", ".join(named)


def build_payload(activity) -> dict:
    a = activity
    city = a.city or ""
    ids = CITY_ID_MAP.get(city, {"CityId": 0, "CountryId": 0})

    lat, lng = float(a.lat or 0), float(a.lng or 0)
    # Only construct a maps URL when real lat/lng exists (not 0,0).
    if lat != 0 and lng != 0:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    else:
        maps_url = ""
    # Real address only. Fall back to city name (which is real). Empty if truly missing.
    map_address = (
        (a.address or "").strip()
        or (a.meeting_point_desc or "").strip()
        or (city or "")
    )[:300]

    # Important-info
    # ImportantInfo* — real data only. Empty string if DB has nothing.
    if a.free_cancellation:
        imp_web = "Free cancellation up to 24 hours before departure"
    elif a.cancellation_hours:
        imp_web = f"Cancellation policy: {a.cancellation_hours} hours notice"
    else:
        imp_web = ""
    imp_voucher = _first_or_default(_list_or_empty(a.important_notes)) or ""

    variants = _list_or_empty(a.tour_variants)

    # SelectedOptions — pick a reasonable default set based on data present.
    # Only tags that match a real DB signal; no blanket defaults.
    selected_options = []
    if _list_or_empty(a.start_times):
        selected_options.append("multiple_time_slot")
    if any((v.get("has_inventory") for v in variants if isinstance(v, dict))):
        selected_options.append("ticket_required")
    selected_options_str = ",".join(selected_options)

    # Itinerary steps — prefer the real timeline from catalog_activity_timeline
    # (matches what the internal UI displays); fall back to a synthetic 2-step
    # template only when no timeline rows exist for the activity.
    steps = []
    timeline = getattr(a, "_timeline", None) or []

    def _time_from_label(label: str) -> str:
        """Convert '0:00 - 0:15' style label to 'HH:MM' start (API expects HH:MM)."""
        if not label:
            return "00:00"
        # Take portion before the dash if present
        first = str(label).split("-")[0].strip()
        # Ensure zero-padded HH:MM
        parts = first.split(":")
        if len(parts) < 2:
            return "00:00"
        try:
            hh = int(parts[0])
            mm = int(parts[1][:2])
        except (ValueError, IndexError):
            return "00:00"
        return f"{hh:02d}:{mm:02d}"

    if timeline:
        # Resolve base tour clock — use first start_time, else 10:00.
        base_starts = _list_or_empty(getattr(a, "start_times", None))
        first_start = str(base_starts[0])[:5] if base_starts else "10:00"
        try:
            _base_hh, _base_mm = int(first_start[:2]), int(first_start[3:5])
        except (ValueError, TypeError):
            _base_hh, _base_mm = 10, 0
        try:
            _total_dur = int(getattr(a, "duration_minutes", None) or 180)
        except (TypeError, ValueError):
            _total_dur = 180
        if _total_dur < 60:
            _total_dur = 60
        # If a tour is longer than a workday, cap the shown timeline span.
        _total_dur = min(_total_dur, 720)  # 12h max on the itinerary
        n_steps = max(1, len(timeline))
        for i, step in enumerate(timeline, 1):
            step_title = (step.get("title") or "").strip()
            step_desc = (step.get("description") or "").strip()
            # Prefer a real HH:MM from the DB label, else compute clock offset.
            label = step.get("time_label") or ""
            step_time = _time_from_label(label)
            if step_time == "00:00" and label:
                # Descriptive label — compute from position instead.
                offset = int(round(_total_dur * (i - 1) / n_steps))
                mins = _base_hh * 60 + _base_mm + offset
                step_time = f"{(mins // 60) % 24:02d}:{mins % 60:02d}"
            steps.append({
                "StepOrder": int(step.get("order") or i),
                "Time": step_time,
                "Action": step_title[:200],
                "Title": step_title[:200],
                "Description": (step_desc or step_title)[:1000],
            })
    # No timeline in DB — leave Steps empty. The internal UI shows
    # "No Timeline Available" for these activities, so we don't fabricate
    # from highlights. Rayna API accepts an empty Steps array.

    # Transfer-type computation happens below (per-option); we build the
    # top-level SelectedTypes AFTER the per-option loop from the actual
    # union of used types. Initialise here so tour_options_out loop can populate.
    transfer_types_set: set[str] = set()

    # Description block — real DB values only. Empty string when field missing.
    description = {
        "AboutExperience": (a.description_long or a.description_short or "")[:4000],
        "Highlights": _join_lines(a.highlights),
        "GeneralInclusion": _join_lines(a.included),
        "GeneralExclusion": _join_lines(a.excluded),
        "WhatToBring": (a.what_to_bring or "")[:500],
        "DressCode": (a.dress_code_note or "")[:200],
        "MeetingPoint": (a.meeting_point_desc or "")[:500],
        "HowToRedeem": _join_lines(a.redemption_instructions),
    }

    # Tour Options — map each internal variant to the API's TourOptions shape
    tour_options_out = []
    today = datetime.utcnow().date()
    start_date = (today + timedelta(days=30)).isoformat()
    end_date = (today + timedelta(days=365)).isoformat()

    for idx, v in enumerate(variants, 1):
        if not isinstance(v, dict):
            continue
        v_name = str(v.get("name") or f"Option {idx}")[:200]
        v_start = _first_or_default(_list_or_empty(a.start_times), "10:00")[:5] if _list_or_empty(a.start_times) else "10:00"
        # End = start + duration. Enforce a minimum 60-min gap — Rayna API
        # rejects tour options where StartTime == EndTime (variants with 0/None
        # duration would otherwise collapse to same start/end and cause
        # "Tour Option failed / Days Of Operation failed / Time Slot failed" errors).
        MIN_DURATION_MIN = 60
        try:
            hh, mm = int(v_start[:2]), int(v_start[3:5])
            _raw_dur = v.get("duration_minutes") or a.duration_minutes or MIN_DURATION_MIN
            try:
                dur = int(_raw_dur)
            except (TypeError, ValueError):
                dur = MIN_DURATION_MIN
            if dur < MIN_DURATION_MIN:
                dur = MIN_DURATION_MIN
            end_mins = hh * 60 + mm + dur
            v_end = f"{(end_mins // 60) % 24:02d}:{end_mins % 60:02d}"
            # Extra guard: if somehow end == start, bump by 1 hour
            if v_end == v_start:
                bumped = (hh + 1) % 24
                v_end = f"{bumped:02d}:{mm:02d}"
        except Exception:
            v_end = "17:00"

        # Rayna master API recognized transfer enums (as of 2026-09-01):
        #   without_transfer   — no transfer, meet at location
        #   sharing_transfer   — shared / group hotel pickup
        #   private_transfer   — private / dedicated transfer
        # `with_transfer` is NOT recognized. Map hotel/pickup variants to
        # sharing_transfer by default (safest — group tours are more common);
        # bump to private_transfer only when the variant name flags "private".
        low_name = v_name.lower()
        wants_transfer = (
            ("transfer" in low_name and "no transfer" not in low_name and "without" not in low_name)
            or "pickup" in low_name
            or "with hotel" in low_name
        )
        if wants_transfer:
            this_transfer = "private_transfer" if "private" in low_name else "sharing_transfer"
        else:
            this_transfer = "without_transfer"
        transfer_types_set.add(this_transfer)

        tour_options_out.append({
            "TourOption": {
                "OptionName": v_name,
                "ShortDescription": (v.get("description") or v_name)[:300],
                "ExclPax": {"Adult": False, "Child": False, "Infant": False},
                "TicketFlags": {
                    "Ticket": bool(v.get("has_inventory", False)),
                    "CheckIn": False,
                    "Waiver": False,
                },
                "DisplayOrder": idx,
                "OptionInclusion": _join_lines(v.get("includes")) or _join_lines(a.included),
                "OptionExclusion": _join_lines(v.get("excludes")) or _join_lines(a.excluded),
                "StartTime": v_start,
                "EndTime": v_end,
                "VoucherType": "Mobile",
                "BookingType": "Instant" if a.instant_confirmation else "OnRequest",
                "TransferTimingConfigs": [{
                    "Type": this_transfer,
                    "OnRequestWithinCutoff": False,
                    "CutOffHours": int(a.cancellation_hours or 24),
                    "Timings": [{"Pickup": v_start, "DropOff": v_end}],
                    "Note": "",
                }],
                "TransferTypes": [this_transfer],
            },
            "DaysOfOperation": {
                "OperatingDays": _operating_days_map(a.operating_days),
                "IncludeDateRanges": [{"StartDate": start_date, "EndDate": end_date}],
                "ExcludeDateRanges": [],
            },
            "TimeSlots": {
                "Slots": [{
                    "Time": f"{v_start}:00",
                    "OperatingDays": _operating_days_map(a.operating_days),
                    "ExcludeTransferTypes": [],
                    # New schema fields (spec update). Mirror the option-level
                    # date range unless the API team says otherwise.
                    "IncludeRanges": [{"StartDate": start_date, "EndDate": end_date}],
                    "ExcludeRanges": [],
                }],
            },
        })

    # Build top-level SelectedTypes from the union of per-option transfer types
    if not transfer_types_set:
        transfer_types_set.add("without_transfer")
    transfer_selected = [
        {"Type": t, "MinPax": 1, "IsDefault": (i == 0)}
        for i, t in enumerate(sorted(transfer_types_set))
    ]

    # FAQs (from our v2 FAQ format)
    faqs_list = _list_or_empty(a.faqs)
    faqs_out = [
        {"Question": f.get("question") or "", "Answer": f.get("answer") or ""}
        for f in faqs_list if isinstance(f, dict) and f.get("question") and f.get("answer")
    ]

    # Media (up to 5 total per Rayna master API).
    # Only Cloudinary-hosted URLs are allowed by the endpoint's SourceUrl host
    # whitelist — cover_image_url from OTA CDNs (e.g. triseptsolutions,
    # getyourguide, tacdn) is rejected. Filter to Cloudinary only.
    def _is_allowed_media_host(url: str) -> bool:
        return isinstance(url, str) and "res.cloudinary.com" in url

    MAX_MEDIA = 5
    gallery = _list_or_empty(a.gallery_json)
    media_out = []
    seen_urls = set()
    if _is_allowed_media_host(a.cover_image_url) and a.cover_image_url not in seen_urls:
        media_out.append({
            "CdnUrl": a.cover_image_url,
            "Type": "image",
            "IsCover": True,
            "Caption": (a.name or "Cover")[:200],
        })
        seen_urls.add(a.cover_image_url)
    for i, g in enumerate(gallery):
        if len(media_out) >= MAX_MEDIA:
            break
        if not isinstance(g, dict):
            continue
        url = g.get("url")
        if not url or url in seen_urls or not _is_allowed_media_host(url):
            continue
        seen_urls.add(url)
        media_out.append({
            "CdnUrl": url,
            "Type": "image",
            "IsCover": (len(media_out) == 0),
            "Caption": (g.get("alt_text") or f"{a.name} image {i+1}")[:200],
        })

    # Reviews — use enriched_text (professional rewrite, brand-scrubbed).
    # Replace placeholder names (Unknown/Anonymous/empty) with 'Traveller' so the
    # published page reads cleanly. These placeholders come from Trustpilot pages
    # where the reviewer name wasn't extractable.
    _PLACEHOLDER_NAMES = {"unknown", "anonymous", "anon", "google user", ""}

    reviews_out = []
    for r in (activity.sample_reviews or []):
        text_body = (r.get("enriched_text") or r.get("review_text") or "").strip()
        # Skip reviews with no real text — don't send placeholders
        if not text_body:
            continue
        # Only use a real title from DB; leave empty if none
        title = (r.get("review_title") or "").strip()
        review_date_iso = datetime.utcnow().replace(microsecond=0).isoformat()
        raw_name = (r.get("reviewer_name") or "").strip()
        guest_name = raw_name if raw_name.lower() not in _PLACEHOLDER_NAMES else "Traveller"
        raw_rating = r.get("rating")
        try:
            rating_val = int(float(raw_rating)) if raw_rating is not None else 5
        except (TypeError, ValueError):
            rating_val = 5
        reviews_out.append({
            "ReviewTitle": title[:200],
            "ReviewContent": text_body[:2000],
            "ReviewDate": review_date_iso,
            "TravelDate": review_date_iso,
            "Rating": rating_val,
            "GuestName": guest_name[:120],
            "GuestEmail": "",
            "BookingRefNo": "",
            "ImagePath": "",
            "ServiceName": "tour",
        })

    payload = {
        "BasicInfo": {
            "TourGroupName": a.name[:250],
            "CountryId": ids["CountryId"],
            "CityId": ids["CityId"],
            "ImportantInfoWeb": imp_web[:500],
            "ImportantInfoVoucher": imp_voucher[:500],
            "GoogleMapAddress": map_address,
            "GoogleMapUrl": maps_url,
            "SelectedOptions": selected_options_str,
        },
        "ItinerarySteps": {"Steps": steps},
        "TransferType": {"SelectedTypes": transfer_selected},
        "Description": description,
        "TourOptionVenueConfig": {
            "OperatingHoursStart": "09:00",
            "OperatingHoursEnd": "18:00",
            "TourLanguage": _language_string(a.languages),
        },
        "TourOptions": tour_options_out,
        "Faqs": {"Faqs": faqs_out},
        # AdditionalInfo — new schema section (spec update).
        # Populate from real DB fields only. Empty array if nothing applies.
        "AdditionalInfo": {
            "SelectedFieldNames": _additional_field_names(a),
        },
        "Indexing": {
            "IndexRows": [
                {
                    "FieldName": "Booking Reference",
                    "ControlType": "TextBox",
                    "IsRequired": True,
                    "ShowInGoogleSuggest": True,
                    "Order": 0,
                }
            ]
        },
        "Media": {"Media": media_out},
        "Reviews": {"Reviews": reviews_out},
    }
    return payload


def format_curl(activity) -> str:
    payload = build_payload(activity)
    body_json = json.dumps(payload, indent=4, ensure_ascii=False, default=str)
    return (
        f"curl --location '{ENDPOINT}' \\\n"
        f"--header 'Authorization: {AUTH}' \\\n"
        f"--header 'Content-Type: application/json' \\\n"
        f"--data '{body_json}'"
    )


async def main(activity_id: str | None, city: str | None):
    if city:
        a = await fetch_best_activity_for_city(city)
        if not a:
            print(f"No tier-0 activity found for city={city!r}")
            return
    else:
        a = await fetch_activity(activity_id)
        if not a:
            print(f"Activity {activity_id} not found")
            return
    print("=" * 80)
    print(f"Ready-to-paste curl for: {a.name}  ({a.city})")
    print("=" * 80)
    print(format_curl(a))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, default=None)
    parser.add_argument("--city", type=str, default=None)
    args = parser.parse_args()
    if not args.id and not args.city:
        args.id = "2353c4d2-95ab-43c3-b69a-58dd7f399b7a"  # default sample
    asyncio.run(main(args.id, args.city))
