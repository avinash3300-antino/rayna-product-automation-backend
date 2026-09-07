"""Top up reviews to 40/platform (google + tripadvisor + trustpilot) for
the 103 London activities that have tour_variants.

Append-only — never deletes existing rows. Dedups by (platform, reviewer_name, first 100 chars).
Walks up to 5 paginated pages for TA/TP. Skips reviews containing OTA brand names
(handled by the updated REVIEW_EXTRACTION_PROMPT in review_service.py).
"""
import asyncio
import json
import logging
import os
import re
import sys
from uuid import UUID

LOCK_FILE = "/tmp/bulk_scrape_london_120.pid"

import httpx
from sqlalchemy import func, select, text

from app.core.config import settings
from app.db.base import async_session_factory
from app.db.models.activities import Activity
from app.db.models.reviews import ProductReview
from app.integrations.claude_client import claude_client
from app.integrations.jina_client import jina_client
from app.services.review_service import (
    REVIEW_EXTRACTION_PROMPT,
    SEARCHAPI_BASE,
    _find_google_place,
    _find_review_page,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bulk_120")

TARGET_PER_PLATFORM = 40
MAX_PAGES = 5
SLEEP_BETWEEN_ACTIVITIES = 2.0
SLEEP_BETWEEN_PAGES = 1.0

# OTA brands we must NOT publish (defense in depth; Claude prompt also filters).
OTA_BRANDS = re.compile(
    r"\b(viator|getyourguide|gyg|tripadvisor|trustpilot|booking\.com|booking|klook|"
    r"tiqets|civitatis|expedia|tours4fun|headout|musement|airbnb experiences)\b",
    re.IGNORECASE,
)


def has_brand_mention(text: str) -> bool:
    return bool(OTA_BRANDS.search(text or ""))


def dedup_key(reviewer_name: str | None, review_text: str | None) -> str:
    name = (reviewer_name or "").strip().lower()
    text = (review_text or "").strip().lower()[:100]
    return f"{name}|{text}"


async def existing_dedup_keys(db, product_id: UUID, platform: str) -> set[str]:
    stmt = select(ProductReview.reviewer_name, ProductReview.review_text).where(
        ProductReview.product_type == "activities",
        ProductReview.product_id == product_id,
        ProductReview.source_platform == platform,
    )
    rows = (await db.execute(stmt)).all()
    return {dedup_key(r[0], r[1]) for r in rows}


async def existing_count(db, product_id: UUID, platform: str) -> int:
    stmt = select(func.count(ProductReview.id)).where(
        ProductReview.product_type == "activities",
        ProductReview.product_id == product_id,
        ProductReview.source_platform == platform,
    )
    return (await db.execute(stmt)).scalar_one()


# ── Google: SearchAPI google_maps_reviews with next_page_token pagination ──


async def fetch_google_reviews(name: str, city: str, country: str, want: int) -> list[dict]:
    """Paginate Google Maps reviews via next_page_token until we have `want` or no more."""
    query = f"{name} {city} {country}"
    data_id = await _find_google_place(query)
    if not data_id:
        log.info("    google: no place found for '%s'", query)
        return []

    out: list[dict] = []
    next_token: str | None = None
    for page in range(1, MAX_PAGES + 1):
        if len(out) >= want:
            break
        params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": settings.SEARCHAPI_KEY,
        }
        if next_token:
            params["next_page_token"] = next_token
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.get(SEARCHAPI_BASE, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            log.warning("    google: SearchAPI failed page %d: %s", page, exc)
            break

        page_revs = data.get("reviews", []) or []
        log.info("    google: page %d returned %d reviews", page, len(page_revs))
        for r in page_revs:
            text = r.get("snippet") or r.get("text") or ""
            if len(text) < 20:
                continue
            if has_brand_mention(text):
                continue
            out.append({
                "reviewer_name": (r.get("user") or {}).get("name") or "Google User",
                "rating": r.get("rating"),
                "review_title": None,
                "review_text": text,
                "review_date": r.get("date"),
                "verified": r.get("is_local_guide", False),
                "language": "en",
                "source_url": r.get("link"),
                "source_platform": "google",
            })
            if len(out) >= want:
                break

        next_token = (data.get("pagination") or {}).get("next_page_token") or data.get("next_page_token")
        if not next_token:
            log.info("    google: no next_page_token at page %d — stopping", page)
            break
        await asyncio.sleep(SLEEP_BETWEEN_PAGES)
    return out


# ── Pagination URL builders ──────────────────────────────────────────────


def tripadvisor_page_url(base_url: str, page: int) -> str:
    """TripAdvisor paginates by inserting -or<N> before the review slug.
    Page 1 = base URL. Page N (N>1) = inject -or<(N-1)*10>.
    """
    if page <= 1:
        return base_url
    offset = (page - 1) * 10
    # Replace first '-Reviews-' (or '-Reviews-or<num>-') with '-Reviews-or<offset>-'
    new_url = re.sub(
        r"-Reviews(-or\d+)?-",
        f"-Reviews-or{offset}-",
        base_url,
        count=1,
    )
    return new_url


def trustpilot_page_url(base_url: str, page: int) -> str:
    """Strip any existing ?page= or &page= from base, then append our own."""
    cleaned = re.sub(r"[?&]page=\d+", "", base_url)
    cleaned = cleaned.rstrip("?&")
    if page <= 1:
        return cleaned
    sep = "&" if "?" in cleaned else "?"
    return f"{cleaned}{sep}page={page}"


# ── Claude extraction from a Jina-rendered page ──────────────────────────


async def extract_from_page(url: str, platform: str, max_reviews: int) -> list[dict]:
    try:
        raw = await jina_client.clean_page(url)
        content = jina_client.clean_markdown(raw)
    except Exception as exc:
        log.warning("    %s: Jina failed for %s: %s", platform, url, exc)
        return []
    if not content or len(content) < 100:
        return []
    content = content[:15000]

    prompt = (
        f"Extract reviews from this {platform} page.\n\n"
        f"Page URL: {url}\n\nPage Content:\n{content}\n\n"
        f"Extract up to {max_reviews} real reviews."
    )
    try:
        response_text = await claude_client.generate(
            prompt=prompt,
            system=REVIEW_EXTRACTION_PROMPT.format(max_reviews=max_reviews),
            model="claude-sonnet-4-6",
            max_tokens=4096,
            temperature=0.1,
        )
    except Exception as exc:
        log.warning("    %s: Claude extraction failed: %s", platform, exc)
        return []

    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        log.warning("    %s: bad JSON from Claude (%d chars)", platform, len(text))
        return []
    if not isinstance(items, list):
        return []

    out = []
    for r in items:
        rt = (r.get("review_text") or "").strip()
        if len(rt) < 20:
            continue
        if has_brand_mention(rt):
            continue  # defense in depth — also covered by prompt
        r["source_url"] = url
        r["source_platform"] = platform
        out.append(r)
    return out


# ── Paginated scrape for TA / TP ─────────────────────────────────────────


async def paginated_scrape(platform: str, base_url: str, want: int) -> list[dict]:
    if platform == "tripadvisor":
        page_url = tripadvisor_page_url
    elif platform == "trustpilot":
        page_url = trustpilot_page_url
    else:
        raise ValueError(platform)

    collected: list[dict] = []
    seen: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        if len(collected) >= want:
            break
        url = page_url(base_url, page)
        remaining = want - len(collected)
        log.info("    %s: page %d (%s) — need %d more", platform, page, url, remaining)
        page_reviews = await extract_from_page(url, platform, max_reviews=min(remaining + 5, 20))
        if not page_reviews:
            log.info("    %s: page %d returned 0; stopping pagination", platform, page)
            break
        new = 0
        for r in page_reviews:
            k = dedup_key(r.get("reviewer_name"), r.get("review_text"))
            if k in seen:
                continue
            seen.add(k)
            collected.append(r)
            new += 1
        log.info("    %s: page %d added %d new (total %d)", platform, page, new, len(collected))
        if new == 0:
            break
        if len(collected) < want:
            await asyncio.sleep(SLEEP_BETWEEN_PAGES)
    return collected[:want]


_TA_PLACE_ID_RE = re.compile(r"-d(\d+)-")


async def scrape_tripadvisor(name: str, city: str, want: int) -> list[dict]:
    """Use SearchAPI tripadvisor_reviews engine (structured, no Jina/Claude/CAPTCHA).
    Find page URL via Google search, extract d<digits> as place_id, paginate by ?page=N.
    """
    base_url = await _find_review_page(
        f"site:tripadvisor.com {name} {city}", "tripadvisor.com"
    )
    if not base_url:
        log.info("    tripadvisor: no page found for '%s' in %s", name, city)
        return []
    m = _TA_PLACE_ID_RE.search(base_url)
    if not m:
        log.info("    tripadvisor: could not extract place_id from %s", base_url)
        return []
    place_id = m.group(1)
    log.info("    tripadvisor: place_id=%s", place_id)

    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        if len(out) >= want:
            break
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.get(SEARCHAPI_BASE, params={
                    "engine": "tripadvisor_reviews",
                    "place_id": place_id,
                    "api_key": settings.SEARCHAPI_KEY,
                    "page": page,
                })
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            log.warning("    tripadvisor: SearchAPI failed page %d: %s", page, exc)
            break

        page_revs = data.get("reviews", []) or []
        log.info("    tripadvisor: page %d returned %d reviews", page, len(page_revs))
        if not page_revs:
            break
        for r in page_revs:
            text = (r.get("text") or "").strip()
            if len(text) < 20:
                continue
            if has_brand_mention(text):
                continue
            author = r.get("author") or {}
            if isinstance(author, dict):
                reviewer = author.get("name") or author.get("display_name") or "TripAdvisor User"
            else:
                reviewer = str(author) or "TripAdvisor User"
            out.append({
                "reviewer_name": reviewer,
                "rating": r.get("rating"),
                "review_title": r.get("title"),
                "review_text": text,
                "review_date": r.get("date"),
                "verified": False,
                "language": r.get("language") or "en",
                "source_url": r.get("link") or base_url,
                "source_platform": "tripadvisor",
            })
            if len(out) >= want:
                break

        pag = data.get("pagination") or {}
        if not pag.get("next_page"):
            log.info("    tripadvisor: no next_page at page %d — stopping", page)
            break
        await asyncio.sleep(SLEEP_BETWEEN_PAGES)
    return out


async def scrape_trustpilot(operator_or_name: str, city: str, want: int) -> list[dict]:
    base_url = await _find_review_page(
        f"site:trustpilot.com {operator_or_name} {city}", "trustpilot.com"
    )
    if not base_url:
        log.info("    trustpilot: no page found for '%s'", operator_or_name)
        return []
    return await paginated_scrape("trustpilot", base_url, want)


# ── Persistence ──────────────────────────────────────────────────────────


async def insert_reviews(db, product_id: UUID, reviews: list[dict], existing_keys: set[str]) -> int:
    inserted = 0
    for r in reviews:
        text = (r.get("review_text") or "")[:5000]
        if not text or has_brand_mention(text):
            continue
        k = dedup_key(r.get("reviewer_name"), text)
        if k in existing_keys:
            continue
        existing_keys.add(k)
        db.add(ProductReview(
            product_type="activities",
            product_id=product_id,
            reviewer_name=r.get("reviewer_name") or "Anonymous",
            rating=r.get("rating"),
            review_title=r.get("review_title"),
            review_text=text,
            review_date=r.get("review_date"),
            source_platform=r.get("source_platform", "unknown"),
            source_url=r.get("source_url"),
            verified=bool(r.get("verified", False)),
            language=r.get("language") or "en",
        ))
        inserted += 1
    if inserted:
        await db.flush()
    return inserted


# ── Main per-activity workflow ───────────────────────────────────────────


async def process_activity(act: Activity) -> dict:
    result = {"name": act.name, "google": 0, "tripadvisor": 0, "trustpilot": 0,
              "google_total": 0, "tripadvisor_total": 0, "trustpilot_total": 0}

    for platform, scrape_fn in [
        ("google", lambda need: fetch_google_reviews(act.name, act.city, act.country, need)),
        ("tripadvisor", lambda need: scrape_tripadvisor(act.name, act.city, need)),
        ("trustpilot", lambda need: scrape_trustpilot(
            getattr(act, "operator_name", None) or act.name, act.city, need
        )),
    ]:
        async with async_session_factory() as db:
            cur = await existing_count(db, act.id, platform)
            need = TARGET_PER_PLATFORM - cur
            if need <= 0:
                log.info("  %s: already at %d (target %d) — skip",
                         platform, cur, TARGET_PER_PLATFORM)
                result[f"{platform}_total"] = cur
                continue
            log.info("  %s: have %d, need %d more (fetching up to %d to allow for dedup)",
                     platform, cur, need, need + 10)
            existing_keys = await existing_dedup_keys(db, act.id, platform)

        try:
            reviews = await scrape_fn(need + 10)  # over-fetch a bit for dedup margin
        except Exception as exc:
            log.warning("  %s: scrape error: %s", platform, exc)
            continue

        if not reviews:
            log.info("  %s: nothing returned", platform)
            result[f"{platform}_total"] = cur
            continue

        async with async_session_factory() as db:
            ins = await insert_reviews(db, act.id, reviews[:need], existing_keys)
            await db.commit()
        result[platform] = ins
        result[f"{platform}_total"] = cur + ins
        log.info("  %s: inserted %d (now total %d)", platform, ins, cur + ins)

    return result


# ── Entry point ──────────────────────────────────────────────────────────


async def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = all
    only_id = sys.argv[2] if len(sys.argv) > 2 else None  # specific activity id

    # Query IDs via raw SQL (Activity model in this container may not declare
    # tour_variants — but the DB column exists).
    async with async_session_factory() as db:
        if only_id:
            id_rows = [(UUID(only_id),)]
        else:
            id_result = await db.execute(text(
                "SELECT id FROM activities "
                "WHERE LOWER(city) = 'london' "
                "AND tour_variants IS NOT NULL "
                "AND jsonb_array_length(tour_variants::jsonb) > 0 "
                "ORDER BY name"
            ))
            id_rows = id_result.all()
        ids = [r[0] for r in id_rows]
        if limit > 0:
            ids = ids[:limit]
        # Load Activity ORM objects by primary key
        activities: list[Activity] = []
        for aid in ids:
            a = await db.get(Activity, aid)
            if a is not None:
                activities.append(a)

    log.info("Processing %d London activities (target %d/platform)",
             len(activities), TARGET_PER_PLATFORM)

    totals = {"google": 0, "tripadvisor": 0, "trustpilot": 0}
    for i, act in enumerate(activities, 1):
        log.info("─" * 70)
        log.info("[%d/%d] %s", i, len(activities), act.name)
        try:
            r = await process_activity(act)
            for k in totals:
                totals[k] += r[k]
        except Exception as exc:
            log.exception("  FAILED: %s", exc)
        await asyncio.sleep(SLEEP_BETWEEN_ACTIVITIES)

    log.info("=" * 70)
    log.info("DONE — inserted: %s", totals)


def acquire_lock():
    """Refuse to start if another instance is already running."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                other_pid = int(f.read().strip())
            # check if pid is alive (/proc check works in linux containers)
            if os.path.exists(f"/proc/{other_pid}"):
                log.error("Another instance is running (PID %d). Refusing to start.", other_pid)
                log.error("If you're sure no other instance is alive, delete %s and retry.", LOCK_FILE)
                sys.exit(2)
            else:
                log.warning("Stale lock file (PID %d not alive) — removing", other_pid)
        except (OSError, ValueError):
            log.warning("Stale/unreadable lock file — removing")
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
