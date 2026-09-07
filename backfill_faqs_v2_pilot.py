"""Pilot: generate v2 FAQs for 3 diverse tier-0 activities and print result summary.

Picks:
  1. A Headout-sourced variant activity from Amsterdam/Rome/London.
  2. A fuzzy-matched variant activity.
  3. A playwright/JSON-LD variant activity.

Saves FAQs to the DB so they show up on the UI immediately.
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("faq_pilot")


async def main():
    from app.db.base import async_session_factory
    from app.services.faq_service_v2 import generate_faqs_for_activity_v2
    from sqlalchemy import text

    # Pick 3 tier-0 activities with variety of variant source provenance
    async with async_session_factory() as db:
        # 1) Headout-sourced (source=='headout')
        r = await db.execute(text("""
          SELECT id, name, city
          FROM activities
          WHERE deleted_at IS NULL AND merged_into_id IS NULL
            AND tour_variants IS NOT NULL AND tour_variants::text NOT IN ('null','[]')
            AND gallery_json IS NOT NULL AND gallery_json::text NOT IN ('null','[]')
            AND tour_variants::text LIKE '%"source": "headout"%'
            AND length(description_long) > 200
          ORDER BY random()
          LIMIT 1
        """))
        row1 = r.fetchone()

        # 2) Fuzzy-matched
        r = await db.execute(text("""
          SELECT id, name, city
          FROM activities
          WHERE deleted_at IS NULL AND merged_into_id IS NULL
            AND tour_variants IS NOT NULL AND tour_variants::text NOT IN ('null','[]')
            AND gallery_json IS NOT NULL AND gallery_json::text NOT IN ('null','[]')
            AND tour_variants::text LIKE '%fuzzy_matched%'
            AND length(description_long) > 200
          ORDER BY random()
          LIMIT 1
        """))
        row2 = r.fetchone()

        # 3) Playwright / other source
        r = await db.execute(text("""
          SELECT id, name, city
          FROM activities
          WHERE deleted_at IS NULL AND merged_into_id IS NULL
            AND tour_variants IS NOT NULL AND tour_variants::text NOT IN ('null','[]')
            AND gallery_json IS NOT NULL AND gallery_json::text NOT IN ('null','[]')
            AND tour_variants::text LIKE '%playwright%'
            AND length(description_long) > 200
          ORDER BY random()
          LIMIT 1
        """))
        row3 = r.fetchone()

        picks = [x for x in [row1, row2, row3] if x is not None]
        need = 3 - len(picks)
        # De-duplicate by id in case any query overlapped
        seen_ids = {str(p.id) for p in picks}

        # Fill any empty slot with random tier-0 rows (pull extra, filter dupes)
        while need > 0:
            r = await db.execute(text("""
              SELECT id, name, city
              FROM activities
              WHERE deleted_at IS NULL AND merged_into_id IS NULL
                AND tour_variants IS NOT NULL AND tour_variants::text NOT IN ('null','[]')
                AND gallery_json IS NOT NULL AND gallery_json::text NOT IN ('null','[]')
                AND length(description_long) > 200
              ORDER BY random()
              LIMIT 10
            """))
            for row in r.fetchall():
                if str(row.id) in seen_ids:
                    continue
                picks.append(row)
                seen_ids.add(str(row.id))
                need -= 1
                if need == 0:
                    break
            if need > 0 and len(picks) == 0:
                break  # safety

    logger.info("Picked %d activities for FAQ v2 pilot:", len(picks))
    for i, p in enumerate(picks, 1):
        logger.info("  %d) %s / %s [id=%s]", i, p.name[:80], p.city, p.id)

    results = []
    for i, p in enumerate(picks, 1):
        logger.info("[%d/%d] Generating FAQs for %s ...", i, len(picks), p.name[:60])
        async with async_session_factory() as db:
            try:
                out = await generate_faqs_for_activity_v2(db, p.id)
                await db.commit()
            except Exception as exc:
                logger.exception("Failed to generate FAQs for %s: %s", p.id, exc)
                results.append({"id": p.id, "name": p.name, "city": p.city, "error": str(exc)})
                continue

        logger.info(
            "  -> %d FAQs, ok=%s, attempts=%d%s",
            len(out["faqs"]), out["ok"], out["attempts"],
            "" if out["ok"] else f", errors={out['errors'][:3]}",
        )
        # Print full first 2 FAQs for eyeball QA
        for j, f in enumerate(out["faqs"][:3], 1):
            logger.info("     [%d] Q: %s", j, f["question"])
            logger.info("         A: %s", f["answer"][:200])
            logger.info("         source: %s", f["source"])
        results.append({
            "id": str(p.id),
            "name": p.name,
            "city": p.city,
            "faq_count": len(out["faqs"]),
            "ok": out["ok"],
            "attempts": out["attempts"],
            "errors": out["errors"][:5] if not out["ok"] else [],
        })

    logger.info("=" * 60)
    logger.info("FAQ v2 pilot complete. View on UI to review:")
    for r in results:
        if "error" in r:
            logger.info("  FAIL  %-40s / %-15s  err=%s", r["name"][:40], r.get("city",""), r["error"])
        else:
            status = "OK   " if r["ok"] else "PART "
            logger.info("  %s %-40s / %-15s  count=%d  attempts=%d",
                        status, r["name"][:40], r["city"], r["faq_count"], r["attempts"])
            logger.info("        id: %s", r["id"])


if __name__ == "__main__":
    asyncio.run(main())
