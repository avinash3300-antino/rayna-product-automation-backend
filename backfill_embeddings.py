"""Backfill embeddings for existing products that don't have one yet."""
import asyncio
import logging

from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models.activities import Activity
from app.db.models.cruises import CruiseProduct
from app.db.models.reviews import ProductEmbedding
from app.services.dedup_service import get_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PRODUCT_MODELS = {
    "activities": Activity,
    "cruises": CruiseProduct,
}


async def backfill_product_type(product_type: str):
    model = PRODUCT_MODELS[product_type]
    async with async_session_factory() as db:
        # Find products without embeddings
        result = await db.execute(
            select(model.id, model.name, model.description_short)
            .outerjoin(
                ProductEmbedding,
                (model.id == ProductEmbedding.product_id)
                & (ProductEmbedding.product_type == product_type),
            )
            .where(ProductEmbedding.id.is_(None))
        )
        rows = result.all()
        total = len(rows)
        logger.info("Found %d %s without embeddings", total, product_type)

        if total == 0:
            logger.info("Nothing to do for %s!", product_type)
            return

        success = 0
        failed = 0

        for i, (product_id, name, desc_short) in enumerate(rows, 1):
            text_for_embed = f"{name or ''}. {desc_short or ''}"
            try:
                embedding = await get_embedding(text_for_embed)
                emb = ProductEmbedding(
                    product_type=product_type,
                    product_id=product_id,
                    embedding=embedding,
                )
                db.add(emb)
                await db.flush()
                success += 1
                logger.info("[%d/%d] Embedded %s: %s", i, total, product_type, name)
            except Exception as exc:
                logger.error("[%d/%d] FAILED %s: %s — %s", i, total, product_type, name, exc)
                failed += 1

        await db.commit()
        logger.info(
            "%s done! %d embedded, %d failed out of %d total",
            product_type, success, failed, total,
        )


async def main():
    for pt in PRODUCT_MODELS:
        await backfill_product_type(pt)


if __name__ == "__main__":
    asyncio.run(main())
