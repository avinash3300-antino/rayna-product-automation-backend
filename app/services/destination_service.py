import logging
import uuid

from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models.activities import Activity
from app.db.models.audit import AuditAuditLog
from app.db.models.cruises import CruiseProduct
from app.db.models.destinations import CatalogDestination, CatalogLocation
from app.db.models.scraping import ScrapeJob

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Audit helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


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


def destination_to_dict(dest: CatalogDestination) -> dict:
    return {
        "id": str(dest.id),
        "code": dest.code,
        "name": dest.name,
        "country_code": dest.country_code,
        "country_name": dest.country_name,
        "country_flag": dest.country_flag,
        "region_name": dest.region_name,
        "city_name": dest.city_name,
        "timezone": dest.timezone,
        "latitude": float(dest.latitude) if dest.latitude is not None else None,
        "longitude": float(dest.longitude) if dest.longitude is not None else None,
        "enabled_categories": dest.enabled_categories,
        "status": dest.status,
    }


def location_to_dict(loc: CatalogLocation) -> dict:
    return {
        "id": str(loc.id),
        "destination_id": str(loc.destination_id),
        "name": loc.name,
        "type": loc.type,
        "address_text": loc.address_text,
        "latitude": float(loc.latitude) if loc.latitude is not None else None,
        "longitude": float(loc.longitude) if loc.longitude is not None else None,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Destination queries
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def get_destination_by_id(
    db: AsyncSession,
    destination_id: uuid.UUID,
) -> CatalogDestination | None:
    result = await db.execute(
        select(CatalogDestination)
        .options(selectinload(CatalogDestination.locations))
        .where(CatalogDestination.id == destination_id)
    )
    return result.scalar_one_or_none()


async def list_destinations(
    db: AsyncSession,
    search: str | None = None,
    status: str | None = None,
    country_code: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[CatalogDestination], int, dict, dict]:
    """Returns (destinations, total, product_counts_map, last_scrape_map)."""
    query = select(CatalogDestination).options(
        selectinload(CatalogDestination.locations)
    )
    count_query = select(func.count(CatalogDestination.id))

    if search:
        pattern = f"%{search}%"
        search_filter = (
            CatalogDestination.name.ilike(pattern)
            | CatalogDestination.code.ilike(pattern)
            | CatalogDestination.city_name.ilike(pattern)
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if status:
        query = query.where(CatalogDestination.status == status)
        count_query = count_query.where(CatalogDestination.status == status)

    if country_code:
        query = query.where(CatalogDestination.country_code == country_code)
        count_query = count_query.where(CatalogDestination.country_code == country_code)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(CatalogDestination.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    destinations = list(result.scalars().unique().all())

    dest_ids = [d.id for d in destinations]
    product_counts_map: dict = {}
    last_scrape_map: dict = {}

    if dest_ids:
        # Count activities per city
        act_result = await db.execute(
            select(Activity.city_id, func.count(Activity.id))
            .where(Activity.city_id.in_(dest_ids))
            .group_by(Activity.city_id)
        )
        for dest_id, cnt in act_result.all():
            product_counts_map.setdefault(dest_id, {})["activities"] = cnt

        # Count cruises per city
        cr_result = await db.execute(
            select(CruiseProduct.city_id, func.count(CruiseProduct.id))
            .where(CruiseProduct.city_id.in_(dest_ids))
            .group_by(CruiseProduct.city_id)
        )
        for dest_id, cnt in cr_result.all():
            product_counts_map.setdefault(dest_id, {})["cruises"] = cnt

        # Last scrape job per destination (via ScrapeJob → ScrapeSource → city)
        from app.db.models.scraping import ScrapeSource

        ranked = (
            select(
                ScrapeSource.city_id,
                ScrapeJob.status,
                ScrapeJob.created_at,
                ScrapeJob.started_at,
                ScrapeJob.completed_at,
                ScrapeJob.records_found,
                func.row_number()
                .over(
                    partition_by=ScrapeSource.city_id,
                    order_by=ScrapeJob.created_at.desc(),
                )
                .label("rn"),
            )
            .join(ScrapeSource, ScrapeJob.source_id == ScrapeSource.id)
            .where(ScrapeSource.city_id.in_(dest_ids))
            .subquery()
        )
        sj_result = await db.execute(
            select(
                ranked.c.city_id,
                ranked.c.status,
                ranked.c.created_at,
                ranked.c.started_at,
                ranked.c.completed_at,
                ranked.c.records_found,
            ).where(ranked.c.rn == 1)
        )
        for row in sj_result.all():
            dest_id, status_val, created_at, started_at, completed_at, records = row
            duration_ms = 0
            if started_at and completed_at:
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            last_scrape_map[dest_id] = {
                "date": created_at,
                "status": status_val,
                "records_found": records or 0,
                "duration_ms": duration_ms,
            }

    return destinations, total, product_counts_map, last_scrape_map


async def get_recent_scrape_jobs(
    db: AsyncSession,
    destination_id: uuid.UUID,
    limit: int = 5,
) -> list[ScrapeJob]:
    from app.db.models.scraping import ScrapeSource

    result = await db.execute(
        select(ScrapeJob)
        .join(ScrapeSource, ScrapeJob.source_id == ScrapeSource.id)
        .where(ScrapeSource.city_id == destination_id)
        .order_by(ScrapeJob.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_pipeline_status(
    db: AsyncSession,
    destination_id: uuid.UUID,
) -> list[dict]:
    # Activities by status
    act_result = await db.execute(
        select(Activity.status, func.count(Activity.id))
        .where(Activity.city_id == destination_id)
        .group_by(Activity.status)
    )
    act_status_map: dict[str, int] = {}
    for status_val, cnt in act_result.all():
        act_status_map[status_val] = cnt

    # Cruises by status
    cr_result = await db.execute(
        select(CruiseProduct.status, func.count(CruiseProduct.id))
        .where(CruiseProduct.city_id == destination_id)
        .group_by(CruiseProduct.status)
    )
    cr_status_map: dict[str, int] = {}
    for status_val, cnt in cr_result.all():
        cr_status_map[status_val] = cnt

    pipeline = []
    for product_type, status_counts in [("activities", act_status_map), ("cruises", cr_status_map)]:
        total = sum(status_counts.values())
        if total > 0:
            pipeline.append(
                {
                    "product_type": product_type,
                    "total": total,
                    "draft": status_counts.get("draft", 0),
                    "enriched": status_counts.get("enriched", 0),
                    "review_ready": status_counts.get("review_ready", 0),
                    "approved": status_counts.get("approved", 0),
                    "published": status_counts.get("published", 0),
                }
            )
    return pipeline


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Destination CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def create_destination(
    db: AsyncSession,
    data: dict,
    created_by: uuid.UUID,
) -> CatalogDestination:
    if data.get("code"):
        existing = await db.execute(
            select(CatalogDestination).where(CatalogDestination.code == data["code"])
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Destination with code '{data['code']}' already exists")

    dest = CatalogDestination(**data)
    db.add(dest)
    await db.flush()

    await _write_audit(db, created_by, "catalog_destinations", dest.id, "created", None, data)
    await db.commit()

    return await get_destination_by_id(db, dest.id)


async def update_destination(
    db: AsyncSession,
    destination_id: uuid.UUID,
    data: dict,
    updated_by: uuid.UUID,
) -> CatalogDestination:
    dest = await get_destination_by_id(db, destination_id)
    if not dest:
        raise NotFoundError("Destination not found")

    old_data = destination_to_dict(dest)

    if "code" in data and data["code"] is not None and data["code"] != dest.code:
        existing = await db.execute(
            select(CatalogDestination).where(CatalogDestination.code == data["code"])
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Destination with code '{data['code']}' already exists")

    for field, value in data.items():
        if hasattr(dest, field):
            setattr(dest, field, value)

    await _write_audit(
        db, updated_by, "catalog_destinations", destination_id, "updated", old_data, data,
    )
    await db.commit()

    return await get_destination_by_id(db, destination_id)


async def update_destination_status(
    db: AsyncSession,
    destination_id: uuid.UUID,
    new_status: str,
    updated_by: uuid.UUID,
) -> CatalogDestination:
    dest = await get_destination_by_id(db, destination_id)
    if not dest:
        raise NotFoundError("Destination not found")

    old_data = {"status": dest.status}
    dest.status = new_status

    await _write_audit(
        db, updated_by, "catalog_destinations", destination_id,
        "status_changed", old_data, {"status": new_status},
    )
    await db.commit()

    return await get_destination_by_id(db, destination_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Location queries & CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _get_location(
    db: AsyncSession,
    destination_id: uuid.UUID,
    location_id: uuid.UUID,
) -> CatalogLocation:
    result = await db.execute(
        select(CatalogLocation).where(
            CatalogLocation.id == location_id,
            CatalogLocation.destination_id == destination_id,
        )
    )
    loc = result.scalar_one_or_none()
    if not loc:
        raise NotFoundError("Location not found")
    return loc


async def list_locations(
    db: AsyncSession,
    destination_id: uuid.UUID,
) -> list[CatalogLocation]:
    dest = await get_destination_by_id(db, destination_id)
    if not dest:
        raise NotFoundError("Destination not found")

    result = await db.execute(
        select(CatalogLocation)
        .where(CatalogLocation.destination_id == destination_id)
        .order_by(CatalogLocation.created_at.desc())
    )
    return list(result.scalars().all())


async def create_location(
    db: AsyncSession,
    destination_id: uuid.UUID,
    data: dict,
    created_by: uuid.UUID,
) -> CatalogLocation:
    dest = await get_destination_by_id(db, destination_id)
    if not dest:
        raise NotFoundError("Destination not found")

    loc = CatalogLocation(destination_id=destination_id, **data)
    db.add(loc)
    await db.flush()

    await _write_audit(
        db, created_by, "catalog_locations", loc.id, "created",
        None, {"destination_id": str(destination_id), **data},
    )
    await db.commit()

    return loc


async def update_location(
    db: AsyncSession,
    destination_id: uuid.UUID,
    location_id: uuid.UUID,
    data: dict,
    updated_by: uuid.UUID,
) -> CatalogLocation:
    loc = await _get_location(db, destination_id, location_id)

    old_data = location_to_dict(loc)
    for field, value in data.items():
        if hasattr(loc, field):
            setattr(loc, field, value)

    await _write_audit(
        db, updated_by, "catalog_locations", location_id, "updated", old_data, data,
    )
    await db.commit()

    result = await db.execute(
        select(CatalogLocation).where(CatalogLocation.id == location_id)
    )
    return result.scalar_one()


async def delete_location(
    db: AsyncSession,
    destination_id: uuid.UUID,
    location_id: uuid.UUID,
    deleted_by: uuid.UUID,
) -> None:
    loc = await _get_location(db, destination_id, location_id)

    old_data = location_to_dict(loc)
    await db.delete(loc)

    await _write_audit(
        db, deleted_by, "catalog_locations", location_id, "deleted", old_data, None,
    )
    await db.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Destination delete
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def delete_destination(
    db: AsyncSession,
    destination_id: uuid.UUID,
    deleted_by: uuid.UUID,
) -> None:
    dest = await get_destination_by_id(db, destination_id)
    if not dest:
        raise NotFoundError("Destination not found")

    # Block deletion if products are linked
    act_count_result = await db.execute(
        select(func.count(Activity.id)).where(Activity.city_id == destination_id)
    )
    cr_count_result = await db.execute(
        select(func.count(CruiseProduct.id)).where(CruiseProduct.city_id == destination_id)
    )
    product_count = act_count_result.scalar_one() + cr_count_result.scalar_one()
    if product_count > 0:
        raise ConflictError(
            f"Cannot delete destination: {product_count} product(s) are linked to it"
        )

    old_data = destination_to_dict(dest)

    # Delete child locations first
    for loc in dest.locations:
        await db.delete(loc)

    await db.delete(dest)

    await _write_audit(
        db, deleted_by, "catalog_destinations", destination_id, "deleted", old_data, None,
    )
    await db.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Stats overview
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def get_stats_overview(db: AsyncSession) -> dict:
    # Destination counts
    dest_result = await db.execute(
        select(
            func.count(CatalogDestination.id),
            func.count(CatalogDestination.id).filter(CatalogDestination.status == "active"),
        )
    )
    total_dest, active_dest = dest_result.one()

    # Product counts
    act_result = await db.execute(select(func.count(Activity.id)))
    activities_count = act_result.scalar_one()

    cr_result = await db.execute(select(func.count(CruiseProduct.id)))
    cruises_count = cr_result.scalar_one()

    total_products = activities_count + cruises_count

    # Published counts
    pub_act = await db.execute(
        select(func.count(Activity.id)).where(Activity.status == "published")
    )
    pub_cr = await db.execute(
        select(func.count(CruiseProduct.id)).where(CruiseProduct.status == "published")
    )
    products_published = pub_act.scalar_one() + pub_cr.scalar_one()

    # In-pipeline counts (not draft, not published)
    pipe_act = await db.execute(
        select(func.count(Activity.id)).where(
            Activity.status.notin_(["draft", "published"])
        )
    )
    pipe_cr = await db.execute(
        select(func.count(CruiseProduct.id)).where(
            CruiseProduct.status.notin_(["draft", "published"])
        )
    )
    products_in_pipeline = pipe_act.scalar_one() + pipe_cr.scalar_one()

    return {
        "total_destinations": total_dest,
        "active_destinations": active_dest,
        "total_products": {
            "activities": activities_count,
            "cruises": cruises_count,
            "total": total_products,
        },
        "products_published": products_published,
        "products_in_pipeline": products_in_pipeline,
    }
