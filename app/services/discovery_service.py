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
websites to scrape for structured activity/tour data.

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
        status="running",
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    try:
        # ── Step 1: SearchAPI queries ────────────────────────────────
        queries = [
            f"best {category} tours in {city_name} {country_name}",
            f"{category} activities {city_name} book online",
            f"top {category} experiences {city_name} tickets",
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
    discovery_run_id: uuid.UUID | None = None,
) -> ScrapeSource:
    """Manually add a scrape source."""
    dest = await db.get(CatalogDestination, city_id)
    if not dest:
        raise NotFoundError("Destination not found")

    source = ScrapeSource(
        city_id=city_id,
        category=category,
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
