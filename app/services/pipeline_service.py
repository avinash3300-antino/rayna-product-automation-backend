import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.activities import Activity
from app.db.models.destinations import CatalogDestination
from app.db.models.scraping import ScrapeJob, ScrapeSource
from app.services.enrichment_service import enrich_activity
from app.services.geocoding_service import geocode_activity
from app.services.image_service import fetch_and_upload_images
from app.services.review_service import scrape_reviews_for_activity
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

        # ── Step 4: Enrich ALL saved activities (mandatory rewrite) ──
        enriched_count = 0
        if job.records_saved > 0:
            # Get ALL recently saved activities — enrichment is mandatory
            # for copyright safety (every description must be rewritten)
            enrichment_cutoff = job.started_at - timedelta(seconds=30)
            result = await db.execute(
                select(Activity)
                .where(
                    Activity.city_id == source.city_id,
                    Activity.status == "draft",
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

        # ── Step 5-7: Gallery, geocoding, reviews for enriched activities ──
        if enriched_count > 0 or job.records_saved > 0:
            enrichment_cutoff = job.started_at - timedelta(seconds=30)
            result = await db.execute(
                select(Activity)
                .where(
                    Activity.city_id == source.city_id,
                    Activity.created_at >= enrichment_cutoff,
                )
                .order_by(Activity.created_at.desc())
                .limit(max(job.records_saved, enriched_count))
            )
            post_activities = list(result.scalars().all())

            for activity in post_activities:
                await _run_post_enrichment(db, activity, errors)

        await db.flush()

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


async def _run_post_enrichment(
    db: AsyncSession,
    activity: Activity,
    errors: list[dict],
) -> None:
    """Run Freepik images, geocoding, and review scraping for one activity."""
    # ── Step 5: Gallery images (Freepik → Cloudinary) ─────────────
    if not activity.gallery_json:
        try:
            gallery = await fetch_and_upload_images(
                activity.name, activity.city, str(activity.id), num_images=8
            )
            if gallery:
                activity.gallery_json = gallery
                # Use first Freepik image as cover too
                if not activity.cover_image_url:
                    activity.cover_image_url = gallery[0]["url"]
                logger.info(
                    "Gallery: %d Freepik images for '%s'",
                    len(gallery), activity.name,
                )
        except Exception as exc:
            errors.append({
                "activity_id": str(activity.id),
                "error": str(exc),
                "step": "gallery",
            })
            logger.warning("Gallery failed for %s: %s", activity.id, exc)

    # ── Step 6: Geocoding ───────────────────────────────────────────
    if activity.lat == 0 and activity.lng == 0:
        try:
            coords = await geocode_activity(
                activity.name, activity.city, activity.country, activity.address
            )
            if coords["lat"] != 0:
                activity.lat = coords["lat"]
                activity.lng = coords["lng"]
                logger.info(
                    "Geocoded '%s': %s, %s",
                    activity.name, coords["lat"], coords["lng"],
                )
        except Exception as exc:
            errors.append({
                "activity_id": str(activity.id),
                "error": str(exc),
                "step": "geocoding",
            })
            logger.warning("Geocoding failed for %s: %s", activity.id, exc)

    # ── Step 7: Reviews ─────────────────────────────────────────────
    if not activity.review_snippets:
        try:
            review_result = await scrape_reviews_for_activity(
                db, activity.id, platforms=["google", "tripadvisor"]
            )
            logger.info(
                "Reviews: %d scraped for '%s'",
                review_result.get("total_scraped", 0), activity.name,
            )
        except Exception as exc:
            errors.append({
                "activity_id": str(activity.id),
                "error": str(exc),
                "step": "reviews",
            })
            logger.warning("Review scrape failed for %s: %s", activity.id, exc)

    await db.flush()


async def run_post_enrichment_for_city(
    db: AsyncSession,
    city_id: uuid.UUID,
) -> dict:
    """Run gallery, geocoding, and reviews for all activities in a city.

    Use this to backfill data for activities that were scraped before
    these pipeline steps existed.
    """
    result = await db.execute(
        select(Activity).where(Activity.city_id == city_id)
    )
    activities = list(result.scalars().all())

    if not activities:
        raise NotFoundError("No activities found for this city")

    errors: list[dict] = []
    counts = {"gallery": 0, "geocoded": 0, "reviews": 0, "total": len(activities)}

    for i, activity in enumerate(activities, 1):
        logger.info(
            "[%d/%d] Processing '%s'...",
            i, len(activities), activity.name,
        )
        had_gallery = bool(activity.gallery_json)
        had_coords = activity.lat != 0
        had_reviews = bool(activity.review_snippets)

        await _run_post_enrichment(db, activity, errors)

        if not had_gallery and activity.gallery_json:
            counts["gallery"] += 1
        if not had_coords and activity.lat != 0:
            counts["geocoded"] += 1
        if not had_reviews and activity.review_snippets:
            counts["reviews"] += 1

        # Rate limit to avoid 429s from SearchAPI
        if i < len(activities):
            await asyncio.sleep(2)

    await db.commit()

    logger.info(
        "Post-enrichment for city %s: %d activities, %d gallery, %d geocoded, %d reviews",
        city_id, counts["total"], counts["gallery"],
        counts["geocoded"], counts["reviews"],
    )
    return {"counts": counts, "errors": errors}


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
