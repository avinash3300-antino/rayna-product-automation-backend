import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ExternalServiceError, NotFoundError
from app.db.models.audit import AuditAuditLog
from app.db.models.destinations import CatalogDestination
from app.db.models.scraping import ScrapeSource, SourceDiscoveryRun
from app.integrations.claude_client import claude_client
from app.integrations.searchapi_client import searchapi_client

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a travel data source analyst.
Given a list of search results for a travel category in a city, identify the BEST
websites to scrape for structured product data.

Return a JSON array of sources, each with:
- source_name (string, e.g. "GetYourGuide Dubai")
- source_url (string, the best landing page URL for scraping)
- tier (1 = official aggregator / large OTA, 2 = niche/blog/local)
- authority_score (float 0-100, estimate based on domain authority)
- reasoning (1 sentence why this source is valuable)

Rules:
- Max 15 sources per request.
- Prefer aggregator sites (Viator, GetYourGuide, Klook, TripAdvisor) as tier 1.
- Include 2-3 local/niche sites as tier 2.
- Exclude social media, forums, or generic travel blogs.
- Return ONLY valid JSON array, no markdown fences."""

# Category-specific search query templates
SEARCH_QUERIES = {
    "activities": [
        "best {category} in {city} {country} book online",
        "{category} {city} tickets prices tours",
        "top {category} experiences {city} {country} 2025",
        "{category} {city} viator getyourguide klook",
    ],
    "cruises": [
        "best {category} cruises in {city} {country}",
        "{category} boat tours {city} book online",
        "top {category} cruise experiences {city} tickets prices",
        "{category} dinner cruise yacht {city}",
    ],
}

# Category-specific query overrides for more targeted searches
CATEGORY_QUERY_OVERRIDES: dict[str, list[str]] = {
    "Sightseeing Tours": [
        "hop on hop off bus tour {city} tickets book online",
        "best sightseeing tours {city} walking tour open top bus",
        "{city} city tour book online viator getyourguide",
        "top rated sightseeing experiences {city} {country}",
    ],
    "Landmark Tickets": [
        "best landmarks {city} tickets book online skip the line",
        "{city} attraction tickets prices entry",
        "top landmarks to visit {city} {country} book tickets",
        "{city} famous monuments entrance tickets viator",
    ],
    "Museum & Gallery": [
        "best museum tours {city} guided tour tickets",
        "{city} art gallery museum skip the line book online",
        "top museums {city} {country} guided experience",
        "{city} museum tickets viator getyourguide",
    ],
    "Thames River": [
        "Thames river cruise {city} tickets book online",
        "{city} river boat tour dinner cruise speedboat",
        "best Thames cruise experiences {city} afternoon tea",
        "Thames sightseeing cruise {city} viator tickets",
    ],
    "Day Trips": [
        "best day trips from {city} book online tours",
        "{city} day trip stonehenge bath windsor oxford",
        "top day tours from {city} {country} viator getyourguide",
        "day excursions from {city} prices book online",
    ],
    "Harry Potter & Film": [
        "Harry Potter studio tour {city} tickets book online",
        "{city} harry potter walking tour filming locations",
        "Warner Bros Studio Tour {city} tickets prices",
        "{city} film location tours book online viator",
    ],
    "Food & Drink": [
        "best food tours {city} walking tour book online",
        "{city} pub crawl food experience afternoon tea tasting",
        "top food and drink experiences {city} {country}",
        "{city} cooking class market tour viator getyourguide",
    ],
    "Shows & Entertainment": [
        "West End theatre tickets {city} book online",
        "{city} shows entertainment comedy cabaret tickets",
        "best theatre experiences {city} {country} tickets",
        "{city} dinner show entertainment viator tickets",
    ],
    "Passes & Combos": [
        "{city} Pass all inclusive attractions book online",
        "Go City Explorer Pass {city} prices attractions",
        "{city} multi attraction pass bundle tickets",
        "best sightseeing pass {city} {country} save money",
    ],
    "Transfers": [
        "{city} airport transfer book online private shared",
        "Heathrow Gatwick {city} transfer shuttle taxi prices",
        "{city} airport to city center transfer viator",
        "private transfer {city} airport book online",
    ],
    "Sports & Outdoor": [
        "best stadium tours {city} book online tickets",
        "{city} outdoor activities cycling kayaking climbing",
        "top sports experiences {city} {country} book online",
        "{city} stadium tour football viator getyourguide",
    ],
    "Night Tours": [
        "best night tours {city} ghost tour jack the ripper",
        "{city} evening tour haunted walks night bus",
        "top night experiences {city} {country} book online",
        "{city} ghost tour night sightseeing viator",
    ],
    "Family & Kids": [
        "best family activities {city} kids children book online",
        "{city} family attractions zoo aquarium kids experiences",
        "top family friendly tours {city} {country}",
        "{city} kids activities viator family tours",
    ],
    "Luxury & Private": [
        "luxury private tours {city} book online VIP",
        "{city} private car tour helicopter ride exclusive",
        "best luxury experiences {city} {country} premium",
        "{city} VIP tour private guide viator",
    ],
    "Seasonal & Events": [
        "{city} seasonal events experiences book online",
        "Christmas markets {city} seasonal tours activities",
        "{city} special events festivals tours tickets",
        "best seasonal experiences {city} {country}",
    ],
}


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    old_data: dict | None = None,
    new_data: dict | None = None,
) -> None:
    log = AuditAuditLog(
        actor_user_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_data=old_data,
        new_data=new_data,
    )
    db.add(log)
    await db.flush()


async def run_discovery(
    db: AsyncSession,
    city_id: uuid.UUID,
    category: str,
    product_type: str = "activities",
    triggered_by: uuid.UUID | None = None,
) -> SourceDiscoveryRun:
    """Run source discovery for a city + category.

    Steps:
    1. Create SourceDiscoveryRun record.
    2. Run SearchAPI queries to find relevant websites.
    3. Use Claude to synthesize and rank sources.
    4. Create ScrapeSource records for each discovered source.
    """
    # Validate city exists
    dest = await db.get(CatalogDestination, city_id)
    if not dest:
        raise NotFoundError("Destination not found")

    city_name = dest.city_name or dest.name
    country_name = dest.country_name or ""

    # Create discovery run
    run = SourceDiscoveryRun(
        city_id=city_id,
        category=category,
        product_type=product_type,
        status="running",
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    try:
        # ── Step 1: SearchAPI queries ────────────────────────────────
        # Use category-specific overrides if available, else generic
        if category in CATEGORY_QUERY_OVERRIDES:
            templates = CATEGORY_QUERY_OVERRIDES[category]
        else:
            templates = SEARCH_QUERIES.get(product_type, SEARCH_QUERIES["activities"])
        queries = [
            t.format(category=category, city=city_name, country=country_name)
            for t in templates
        ]

        all_search_results = []
        for query in queries:
            try:
                results = await searchapi_client.search(query, num_results=15)
                all_search_results.extend(results)
            except Exception as exc:
                logger.warning("SearchAPI query failed for '%s': %s", query, exc)

        run.searchapi_results = {
            "queries": queries,
            "total_results": len(all_search_results),
            "results": all_search_results[:50],  # Cap stored results
        }

        if not all_search_results:
            run.status = "completed"
            run.error_message = "No search results found"
            run.completed_at = datetime.now(timezone.utc)
            await db.flush()
            await db.commit()
            return run

        # ── Step 2: Claude synthesis ─────────────────────────────────
        search_summary = json.dumps(all_search_results[:30], indent=2)
        synthesis_prompt = f"""City: {city_name}, {country_name}
Category: {category}

Search results from Google:
{search_summary[:8000]}

Analyze these results and identify the best websites to scrape for
{category} activities/tours in {city_name}."""

        try:
            synthesis_text = await claude_client.generate(
                prompt=synthesis_prompt,
                system=SYNTHESIS_SYSTEM_PROMPT,
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0.2,
            )

            # Parse JSON
            text = synthesis_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
            sources_data = json.loads(text)

            run.claude_synthesis = {
                "sources": sources_data,
                "model": "claude-sonnet-4-20250514",
            }
        except json.JSONDecodeError:
            logger.error("Claude returned invalid JSON for discovery synthesis")
            sources_data = []
            run.claude_synthesis = {"error": "Invalid JSON from Claude"}
        except Exception as exc:
            logger.error("Claude synthesis failed: %s", exc)
            sources_data = []
            run.claude_synthesis = {"error": str(exc)}

        # ── Step 3: Create ScrapeSource records ──────────────────────
        sources_created = 0
        for src in sources_data:
            source_url = (src.get("source_url") or "").strip()
            source_name = (src.get("source_name") or "").strip()
            if not source_url or not source_name:
                continue

            # Check for existing source with same URL for this city
            existing = await db.execute(
                select(ScrapeSource).where(
                    ScrapeSource.city_id == city_id,
                    ScrapeSource.source_url == source_url,
                )
            )
            if existing.scalar_one_or_none():
                continue

            source = ScrapeSource(
                city_id=city_id,
                category=category,
                product_type=product_type,
                source_name=source_name,
                source_url=source_url,
                tier=src.get("tier", 2),
                authority_score=src.get("authority_score"),
                approved=False,
                added_by="discovery",
                discovery_run_id=run.id,
            )
            db.add(source)
            sources_created += 1

        run.sources_found = sources_created
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        await db.flush()

        if triggered_by:
            await _write_audit(
                db,
                triggered_by,
                "source_discovery_runs",
                run.id,
                "created",
                None,
                {"city_id": str(city_id), "category": category, "sources_found": sources_created},
            )

        await db.commit()
        return run

    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:500]
        run.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await db.commit()
        logger.error("Discovery failed for city=%s category=%s: %s", city_id, category, exc)
        raise ExternalServiceError(f"Discovery failed: {exc}")


async def approve_sources(
    db: AsyncSession,
    source_ids: list[uuid.UUID],
    approved: bool,
    actor_id: uuid.UUID,
) -> list[ScrapeSource]:
    """Approve or reject discovered sources."""
    sources = []
    for source_id in source_ids:
        source = await db.get(ScrapeSource, source_id)
        if not source:
            continue

        old_approved = source.approved
        source.approved = approved
        source.approved_by = actor_id
        source.approved_at = datetime.now(timezone.utc) if approved else None

        await _write_audit(
            db,
            actor_id,
            "scrape_sources",
            source_id,
            "approved" if approved else "rejected",
            {"approved": old_approved},
            {"approved": approved},
        )
        sources.append(source)

    # Update discovery run counts
    if sources:
        run_id = sources[0].discovery_run_id
        if run_id:
            run = await db.get(SourceDiscoveryRun, run_id)
            if run:
                result = await db.execute(
                    select(ScrapeSource).where(
                        ScrapeSource.discovery_run_id == run_id,
                        ScrapeSource.approved.is_(True),
                    )
                )
                run.sources_approved = len(result.scalars().all())

    await db.commit()
    return sources


async def add_manual_source(
    db: AsyncSession,
    city_id: uuid.UUID,
    category: str,
    source_url: str,
    source_name: str,
    tier: int,
    actor_id: uuid.UUID,
    product_type: str = "activities",
    discovery_run_id: uuid.UUID | None = None,
) -> ScrapeSource:
    """Manually add a scrape source."""
    dest = await db.get(CatalogDestination, city_id)
    if not dest:
        raise NotFoundError("Destination not found")

    source = ScrapeSource(
        city_id=city_id,
        category=category,
        product_type=product_type,
        source_name=source_name,
        source_url=source_url,
        tier=tier,
        approved=True,
        approved_by=actor_id,
        approved_at=datetime.now(timezone.utc),
        added_by="manual",
        discovery_run_id=discovery_run_id,
    )
    db.add(source)
    await db.flush()

    await _write_audit(
        db,
        actor_id,
        "scrape_sources",
        source.id,
        "created",
        None,
        {"source_url": source_url, "source_name": source_name},
    )
    await db.commit()
    return source


# ── Source URL backfill ─────────────────────────────────────────────────

TRUSTED_DOMAINS = [
    "viator.com", "getyourguide.com", "klook.com", "tripadvisor.com",
    "tiqets.com", "musement.com", "headout.com", "civitatis.com",
    "expedia.com", "booking.com", "tourscanner.com", "timeout.com",
    "visitlondon.com", "londonpass.com", "attractiontickets.com",
    "ticketmaster.co.uk", "seetickets.com", "lastminute.com",
    "goldentours.com", "bigbustours.com",
]


async def discover_additional_source_urls(
    activity_name: str,
    activity_city: str,
    existing_urls: list[str] | None = None,
    max_new: int = 2,
) -> list[str]:
    """Search for additional booking/travel URLs for an activity.

    Returns up to `max_new` new URLs not already in existing_urls.
    """
    existing = set(existing_urls or [])
    query = f'"{activity_name}" {activity_city} book online tickets'

    try:
        results = await searchapi_client.search(query, num_results=15)
    except Exception as exc:
        logger.warning("Source URL search failed for '%s': %s", activity_name, exc)
        return []

    new_urls: list[str] = []
    for r in results:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        # Must be from a trusted travel/booking domain
        if not any(domain in url.lower() for domain in TRUSTED_DOMAINS):
            continue
        # Not already known
        if url in existing:
            continue
        # Avoid search/category pages — prefer detail pages
        if any(skip in url.lower() for skip in ["/search?", "/s?", "/category/"]):
            continue
        new_urls.append(url)
        existing.add(url)
        if len(new_urls) >= max_new:
            break

    return new_urls
