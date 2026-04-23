"""Master pipeline orchestrator — product-type aware.

Dispatches to the correct pipeline (activity, cruise, etc.) via the router.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.activities import Activity
from app.db.models.cruises import CruiseProduct
from app.db.models.destinations import CatalogDestination
from app.db.models.scraping import ScrapeJob, ScrapeSource
from app.services.pipelines import get_pipeline
from app.services.scraping_service import extract_products, scrape_source

logger = logging.getLogger(__name__)


async def run_product_pipeline(
    db: AsyncSession,
    source_id: uuid.UUID,
    product_type: str = "activities",
    triggered_by: uuid.UUID | None = None,
    existing_job_id: uuid.UUID | None = None,
) -> ScrapeJob:
    """Master orchestrator: scrape → extract → save → enrich per source.

    Dispatches to the appropriate pipeline based on product_type.
    """
    pipeline = get_pipeline(product_type)

    # Load source
    source = await db.get(ScrapeSource, source_id)
    if not source:
        raise NotFoundError("Scrape source not found")

    _source_id = source.id
    _source_url = source.source_url

    # Load destination
    dest = await db.get(CatalogDestination, source.city_id)
    if not dest:
        raise NotFoundError("Destination not found")

    city_name = dest.city_name or dest.name
    country_name = dest.country_name or ""

    # Create or reuse scrape job
    if existing_job_id:
        job = await db.get(ScrapeJob, existing_job_id)
        if not job:
            raise NotFoundError("Scrape job not found")
        job.status = "scraping"
        job.started_at = datetime.now(timezone.utc)
        await db.flush()
    else:
        job = ScrapeJob(
            discovery_run_id=source.discovery_run_id,
            city_id=source.city_id,
            category=source.category,
            product_type=product_type,
            status="scraping",
            source_id=source.id,
            source_url=source.source_url,
            scrape_type="apify",
            triggered_by=triggered_by,
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()

    _job_id = job.id
    errors = []

    try:
        # ── Step 1: Scrape the source ────────────────────────────────
        logger.info("Scraping source %s: %s", _source_id, _source_url)
        pages = await scrape_source(source)
        job.pages_scraped = len(pages)
        job.scrape_type = pages[0]["source_type"] if pages else "apify"
        job.status = "extracting"
        await db.flush()

        # ── Step 2: Extract products from each page ──────────────────
        extraction_prompt = pipeline.get_extraction_prompt()
        all_extracted = []
        for page in pages:
            try:
                extracted = await extract_products(
                    page["clean_markdown"],
                    page["url"],
                    extraction_prompt,
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
            counts = await pipeline.save_extracted_products(
                db, all_extracted, source, job, city_name, country_name
            )
            job.records_saved = counts["saved"]
            job.records_skipped_dup = counts["skipped_dup"]
        else:
            job.records_saved = 0
            job.records_skipped_dup = 0

        job.status = "enriching"
        await db.flush()

        # ── Step 4: Enrich all saved products (mandatory rewrite) ────
        enriched_count = 0
        if job.records_saved > 0:
            products_to_enrich = await pipeline.get_recently_saved_products(
                db, source.city_id, job.started_at, job.records_saved,
            )
            for product in products_to_enrich:
                try:
                    await pipeline.enrich_product(db, product)
                    enriched_count += 1
                except Exception as exc:
                    errors.append({
                        "product_id": str(product.id),
                        "error": str(exc),
                        "step": "enrichment",
                    })
                    logger.warning(
                        "Enrichment failed for %s %s: %s",
                        product_type, product.id, exc,
                    )

        job.records_enriched = enriched_count

        # ── Step 5-7: Gallery, geocoding, reviews ────────────────────
        if enriched_count > 0 or job.records_saved > 0:
            post_products = await pipeline.get_recently_saved_products(
                db, source.city_id, job.started_at,
                max(job.records_saved, enriched_count),
            )
            for product in post_products:
                await pipeline.run_post_enrichment(db, product, errors)

        await db.flush()

        # ── Finalize ─────────────────────────────────────────────────
        job.status = "completed"
        job.errors_json = {"errors": errors} if errors else None
        job.completed_at = datetime.now(timezone.utc)

        source.last_scraped_at = datetime.now(timezone.utc)

        await db.flush()
        await db.commit()

        logger.info(
            "Pipeline completed for %s source %s: %d found, %d saved, %d dup, %d enriched",
            product_type, source.id,
            job.records_found, job.records_saved,
            job.records_skipped_dup, job.records_enriched,
        )
        return job

    except Exception as exc:
        await db.rollback()
        job = await db.get(ScrapeJob, _job_id)
        if job:
            job.status = "failed"
            job.errors_json = {"errors": errors, "fatal": str(exc)}
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        logger.error("Pipeline failed for source %s: %s", _source_id, exc)
        raise


# ── Backward compatibility alias ────────────────────────────────────────

async def run_activity_pipeline(
    db: AsyncSession,
    source_id: uuid.UUID,
    triggered_by: uuid.UUID | None = None,
    existing_job_id: uuid.UUID | None = None,
) -> ScrapeJob:
    """Legacy wrapper — runs the activities pipeline."""
    return await run_product_pipeline(
        db, source_id,
        product_type="activities",
        triggered_by=triggered_by,
        existing_job_id=existing_job_id,
    )


async def run_post_enrichment_for_city(
    db: AsyncSession,
    city_id: uuid.UUID,
    product_type: str = "activities",
) -> dict:
    """Run gallery, geocoding, and reviews for all products in a city."""
    pipeline = get_pipeline(product_type)

    if product_type == "cruises":
        model = CruiseProduct
    else:
        model = Activity

    result = await db.execute(
        select(model).where(model.city_id == city_id)
    )
    products = list(result.scalars().all())

    if not products:
        raise NotFoundError(f"No {product_type} found for this city")

    errors: list[dict] = []
    counts = {"gallery": 0, "geocoded": 0, "reviews": 0, "total": len(products)}

    for i, product in enumerate(products, 1):
        logger.info(
            "[%d/%d] Processing '%s'...",
            i, len(products), product.name,
        )
        had_gallery = bool(product.gallery_json)
        had_coords = product.lat != 0
        had_reviews = bool(product.review_snippets)

        await pipeline.run_post_enrichment(db, product, errors)

        if not had_gallery and product.gallery_json:
            counts["gallery"] += 1
        if not had_coords and product.lat != 0:
            counts["geocoded"] += 1
        if not had_reviews and product.review_snippets:
            counts["reviews"] += 1

        if i < len(products):
            await asyncio.sleep(2)

    await db.commit()

    logger.info(
        "Post-enrichment for %s city %s: %d products, %d gallery, %d geocoded, %d reviews",
        product_type, city_id, counts["total"], counts["gallery"],
        counts["geocoded"], counts["reviews"],
    )
    return {"counts": counts, "errors": errors}


async def run_pipeline_for_discovery(
    db: AsyncSession,
    discovery_run_id: uuid.UUID,
    category: str,
    product_type: str = "activities",
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

    source_info = [(s.id, s.source_url) for s in sources]

    jobs = []
    for sid, surl in source_info:
        try:
            job = await run_product_pipeline(
                db, sid, product_type=product_type, triggered_by=triggered_by,
            )
            jobs.append(job)
        except Exception as exc:
            logger.error(
                "Pipeline failed for source %s (%s): %s",
                sid, surl, exc,
            )
    return jobs


async def create_pending_jobs(
    db: AsyncSession,
    discovery_run_id: uuid.UUID,
    category: str,
    product_type: str = "activities",
    triggered_by: uuid.UUID | None = None,
) -> list[ScrapeJob]:
    """Create pending ScrapeJob records for all approved sources."""
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
        job = ScrapeJob(
            discovery_run_id=source.discovery_run_id,
            city_id=source.city_id,
            category=source.category,
            product_type=product_type,
            status="pending",
            source_id=source.id,
            source_url=source.source_url,
            scrape_type="apify",
            triggered_by=triggered_by,
        )
        db.add(job)
        jobs.append(job)

    await db.flush()
    await db.commit()
    return jobs


async def process_pending_jobs(
    job_source_pairs: list[tuple[uuid.UUID, uuid.UUID]],
    product_type: str = "activities",
    triggered_by: uuid.UUID | None = None,
) -> None:
    """Background processor: run pipeline for each pending job sequentially."""
    from app.db.base import async_session_factory

    for job_id, source_id in job_source_pairs:
        async with async_session_factory() as db:
            try:
                await run_product_pipeline(
                    db, source_id,
                    product_type=product_type,
                    triggered_by=triggered_by,
                    existing_job_id=job_id,
                )
            except Exception as exc:
                logger.error(
                    "Background pipeline failed for job %s / source %s: %s",
                    job_id, source_id, exc,
                )
