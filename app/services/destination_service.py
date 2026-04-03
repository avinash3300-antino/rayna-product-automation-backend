import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models.audit import AuditAuditLog
from app.db.models.destinations import CatalogDestination, CatalogLocation
from app.db.models.ingestion import IngestionJob
from app.db.models.products import CatalogProduct
from app.db.models.transfers import CatalogTransferProduct

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
    """Returns (destinations, total, product_counts_map, last_ingestion_map)."""
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
    last_ingestion_map: dict = {}

    if dest_ids:
        # Batch fetch product counts per category
        pc_result = await db.execute(
            select(
                CatalogProduct.destination_id,
                CatalogProduct.category,
                func.count(CatalogProduct.id),
            )
            .where(CatalogProduct.destination_id.in_(dest_ids))
            .group_by(CatalogProduct.destination_id, CatalogProduct.category)
        )
        for dest_id, category, cnt in pc_result.all():
            product_counts_map.setdefault(dest_id, {})[category] = cnt

        # Batch fetch last ingestion run details per destination
        ranked = (
            select(
                IngestionJob.destination_id,
                IngestionJob.status,
                IngestionJob.created_at,
                IngestionJob.started_at,
                IngestionJob.completed_at,
                IngestionJob.total_records_fetched,
                func.row_number()
                .over(
                    partition_by=IngestionJob.destination_id,
                    order_by=IngestionJob.created_at.desc(),
                )
                .label("rn"),
            )
            .where(IngestionJob.destination_id.in_(dest_ids))
            .subquery()
        )
        li_result = await db.execute(
            select(
                ranked.c.destination_id,
                ranked.c.status,
                ranked.c.created_at,
                ranked.c.started_at,
                ranked.c.completed_at,
                ranked.c.total_records_fetched,
            ).where(ranked.c.rn == 1)
        )
        for row in li_result.all():
            dest_id, status_val, created_at, started_at, completed_at, records = row
            duration_ms = 0
            if started_at and completed_at:
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            last_ingestion_map[dest_id] = {
                "date": created_at,
                "status": status_val,
                "records_processed": records or 0,
                "duration_ms": duration_ms,
            }

    return destinations, total, product_counts_map, last_ingestion_map


async def get_recent_ingestion_jobs(
    db: AsyncSession,
    destination_id: uuid.UUID,
    limit: int = 3,
) -> list[IngestionJob]:
    result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.destination_id == destination_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_pipeline_status(
    db: AsyncSession,
    destination_id: uuid.UUID,
) -> list[dict]:
    result = await db.execute(
        select(
            CatalogProduct.category,
            CatalogProduct.status,
            func.count(CatalogProduct.id),
        )
        .where(CatalogProduct.destination_id == destination_id)
        .group_by(CatalogProduct.category, CatalogProduct.status)
    )

    category_map: dict = {}
    for category, status, cnt in result.all():
        category_map.setdefault(category, {})[status] = cnt

    pipeline = []
    for category, status_counts in category_map.items():
        total = sum(status_counts.values())
        pipeline.append(
            {
                "category": category,
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

    ref_count_result = await db.execute(
        select(func.count(CatalogTransferProduct.product_id)).where(
            (CatalogTransferProduct.origin_location_id == location_id)
            | (CatalogTransferProduct.destination_location_id == location_id)
        )
    )
    ref_count = ref_count_result.scalar_one()
    if ref_count > 0:
        raise ConflictError(
            f"Cannot delete location: referenced by {ref_count} transfer product(s)"
        )

    old_data = location_to_dict(loc)
    await db.delete(loc)

    await _write_audit(
        db, deleted_by, "catalog_locations", location_id, "deleted", old_data, None,
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

    # Products by category
    prod_result = await db.execute(
        select(CatalogProduct.category, func.count(CatalogProduct.id))
        .group_by(CatalogProduct.category)
    )
    products_by_cat: dict = {}
    total_products = 0
    for category, cnt in prod_result.all():
        products_by_cat[category] = cnt
        total_products += cnt

    # Published and in-pipeline counts
    pub_result = await db.execute(
        select(func.count(CatalogProduct.id)).where(CatalogProduct.publish_flag.is_(True))
    )
    products_published = pub_result.scalar_one()

    pipeline_result = await db.execute(
        select(func.count(CatalogProduct.id)).where(
            CatalogProduct.publish_flag.is_(False),
            CatalogProduct.status != "draft",
        )
    )
    products_in_pipeline = pipeline_result.scalar_one()

    return {
        "total_destinations": total_dest,
        "active_destinations": active_dest,
        "total_products": {
            "hotels": products_by_cat.get("hotels", 0),
            "attractions": products_by_cat.get("attractions", 0),
            "transfers": products_by_cat.get("transfers", 0),
            "restaurants": products_by_cat.get("restaurants", 0),
            "total": total_products,
        },
        "products_published": products_published,
        "products_in_pipeline": products_in_pipeline,
    }
