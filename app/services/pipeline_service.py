import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.destinations import CatalogDestination
from app.db.models.scraping import ScrapeJob, ScrapeSource
from app.services.enrichment_service import enrich_activity
from app.services.scraping_service import (
    extract_activities,
    save_extracted_activities,
    scrape_source,
)

logger = logging.getLogger(__name__)


async def run_activity_pipeline(
    db: AsyncSession,
    source_id: uuid.UUID,
    triggered_by: uuid.UUID | None = None,
) -> ScrapeJob:
    """Master orchestrator: scrape → extract → save → enrich per source.

    Returns the completed ScrapeJob with all counts.
    """
    # Load source
    source = await db.get(ScrapeSource, source_id)
    if not source:
        raise NotFoundError("Scrape source not found")

    # Load destination for city/country names
    dest = await db.get(CatalogDestination, source.city_id)
    if not dest:
        raise NotFoundError("Destination not found")

    city_name = dest.city_name or dest.name
    country_name = dest.country_name or ""

    # Create scrape job
    job = ScrapeJob(
        discovery_run_id=source.discovery_run_id,
        city_id=source.city_id,
        category=source.category,
        status="scraping",
        source_id=source.id,
        source_url=source.source_url,
        scrape_type="apify",
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    errors = []

    try:
        # ── Step 1: Scrape the source ────────────────────────────────
        logger.info("Scraping source %s: %s", source.id, source.source_url)
        pages = await scrape_source(source)
        job.pages_scraped = len(pages)
        job.scrape_type = pages[0]["source_type"] if pages else "apify"
        job.status = "extracting"
        await db.flush()

        # ── Step 2: Extract activities from each page ────────────────
        all_extracted = []
        for page in pages:
            try:
                extracted = await extract_activities(
                    page["clean_markdown"], page["url"]
                )
                all_extracted.extend(extracted)
            except Exception as exc:
                errors.append(
                    {"page_url": page["url"], "error": str(exc), "step": "extraction"}
                )
                logger.warning(
                    "Extraction failed for page %s: %s", page["url"], exc
                )

        job.records_found = len(all_extracted)
        job.status = "saving"
        await db.flush()

        # ── Step 3: Deduplicate & save ───────────────────────────────
        if all_extracted:
            counts = await save_extracted_activities(
                db, all_extracted, source, job, city_name, country_name
            )
            job.records_saved = counts["saved"]
            job.records_skipped_dup = counts["skipped_dup"]
        else:
            job.records_saved = 0
            job.records_skipped_dup = 0

        job.status = "enriching"
        await db.flush()

        # ── Step 4: Enrich saved activities ──────────────────────────
        enriched_count = 0
        if job.records_saved > 0:
            from app.db.models.activities import Activity

            # Get recently saved activities from this pipeline run
            # Use a buffer because PostgreSQL now() returns transaction
            # start time which can be earlier than Python's datetime.now()
            enrichment_cutoff = job.started_at - timedelta(seconds=30)
            result = await db.execute(
                select(Activity)
                .where(
                    Activity.city_id == source.city_id,
                    Activity.quality_score < 60,
                    Activity.created_at >= enrichment_cutoff,
                )
                .order_by(Activity.created_at.desc())
                .limit(job.records_saved)
            )
            activities_to_enrich = list(result.scalars().all())

            for activity in activities_to_enrich:
                try:
                    await enrich_activity(db, activity)
                    enriched_count += 1
                except Exception as exc:
                    errors.append(
                        {
                            "activity_id": str(activity.id),
                            "error": str(exc),
                            "step": "enrichment",
                        }
                    )
                    logger.warning(
                        "Enrichment failed for activity %s: %s",
                        activity.id,
                        exc,
                    )

        job.records_enriched = enriched_count

        # ── Finalize ─────────────────────────────────────────────────
        job.status = "completed"
        job.errors_json = {"errors": errors} if errors else None
        job.completed_at = datetime.now(timezone.utc)

        # Update source last_scraped_at
        source.last_scraped_at = datetime.now(timezone.utc)

        await db.flush()
        await db.commit()

        logger.info(
            "Pipeline completed for source %s: %d found, %d saved, %d dup, %d enriched",
            source.id,
            job.records_found,
            job.records_saved,
            job.records_skipped_dup,
            job.records_enriched,
        )
        return job

    except Exception as exc:
        await db.rollback()
        # Re-fetch job in a fresh transaction to update its status
        job = await db.get(ScrapeJob, job.id)
        if job:
            job.status = "failed"
            job.errors_json = {"errors": errors, "fatal": str(exc)}
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        logger.error("Pipeline failed for source %s: %s", source.id, exc)
        raise


async def run_pipeline_for_discovery(
    db: AsyncSession,
    discovery_run_id: uuid.UUID,
    category: str,
    triggered_by: uuid.UUID | None = None,
) -> list[ScrapeJob]:
    """Run pipeline for all approved sources from a discovery run."""
    result = await db.execute(
        select(ScrapeSource).where(
            ScrapeSource.discovery_run_id == discovery_run_id,
            ScrapeSource.approved.is_(True),
            ScrapeSource.is_active.is_(True),
        )
    )
    sources = list(result.scalars().all())

    if not sources:
        raise NotFoundError("No approved sources found for this discovery run")

    jobs = []
    for source in sources:
        try:
            job = await run_activity_pipeline(db, source.id, triggered_by)
            jobs.append(job)
        except Exception as exc:
            logger.error(
                "Pipeline failed for source %s (%s): %s",
                source.id,
                source.source_url,
                exc,
            )
    return jobs
