"""Supervised Viator scraper — you solve CAPTCHAs, automation handles the rest.

Opens a VISIBLE Chrome window. For each Viator activity:
  1. Navigates to its source_url
  2. If DataDome CAPTCHA shows → script waits, you solve it manually
  3. Once page loads → script auto-clicks Date dropdown, picks day +7,
     opens Travelers, decrements Adult to 1, clicks Apply
  4. Captures the rendered options panel + sends to Claude
  5. Saves variants in AED, moves to next activity

Session cookies persist across activities so DataDome usually only challenges
once per browser session.

Usage:
    python viator_supervised_scrape.py            # all 88 Viator activities
    python viator_supervised_scrape.py --limit 5  # test on 5 first
    python viator_supervised_scrape.py --city London
"""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("viator-sup")

STORAGE_STATE_FILE = Path(__file__).parent / ".viator_session.json"


async def _wait_for_real_page(page, max_wait_sec: int = 180) -> bool:
    """Block until the page has real Viator content (not the DataDome wall).

    Returns True if real content appears, False if max_wait exceeded.
    Detects DataDome by tiny HTML + 'captcha' / 'datadome' keywords.
    """
    for sec in range(max_wait_sec):
        html = await page.content()
        size = len(html)
        is_block = (
            size < 5000
            and ("captcha" in html.lower() or "datadome" in html.lower()
                 or "pardon our interruption" in html.lower())
        )
        # Real Viator pages are 100KB+ with reviews / activity title visible
        if size > 50000 and not is_block:
            return True
        if sec == 0 and is_block:
            print("\n" + "=" * 70)
            print(">>> DataDome CAPTCHA detected — PLEASE SOLVE IT IN THE BROWSER <<<")
            print("    Script will continue automatically once page loads.")
            print("=" * 70 + "\n")
        await asyncio.sleep(1)
    return False


async def _scrape_one(page, url: str) -> dict | None:
    """Run the date + travelers + Apply + extract flow on a single Viator URL."""
    target = datetime.now() + timedelta(days=7)
    target_day = target.day
    target_iso = target.strftime("%Y-%m-%d")

    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)

    ok = await _wait_for_real_page(page)
    if not ok:
        logger.warning("  timed out waiting for real page")
        return None

    # Step 1: Open Date dropdown
    opened_date = await page.evaluate("""() => {
        const els = [...document.querySelectorAll('button, [role="button"], div')];
        for (const e of els) {
            const t = (e.textContent || '').trim();
            if ((t === 'Date' || /^Date\\s/.test(t) ||
                 /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/.test(t))
                && e.offsetParent !== null) {
                const btn = e.closest('button, [role="button"]') || e;
                if (btn.offsetWidth > 50 && btn.offsetWidth < 400) {
                    btn.click(); return true;
                }
            }
        }
        return false;
    }""")
    if not opened_date:
        logger.warning("  could not open Date dropdown")
        return None
    await page.wait_for_timeout(2000)

    # Step 2: Click the target day
    clicked = await page.evaluate("""({day, iso}) => {
        const all = [...document.querySelectorAll('button, [role="gridcell"], [role="button"], td')];
        for (const el of all) {
            for (const attr of ['aria-label', 'data-date', 'data-day']) {
                const v = (el.getAttribute(attr) || '').toLowerCase();
                if (v.includes(iso) || v.includes(iso.replaceAll('-', '/'))) {
                    if (el.offsetParent !== null) { el.click(); return 'aria'; }
                }
            }
        }
        for (const el of all) {
            const t = (el.textContent || '').trim();
            if (t === String(day) && el.offsetParent !== null
                && !el.disabled && el.getAttribute('aria-disabled') !== 'true') {
                el.click(); return 'text';
            }
        }
        return null;
    }""", {"day": target_day, "iso": target_iso})
    if not clicked:
        logger.warning("  could not click day %s", target_day)
        return None
    await page.wait_for_timeout(2500)

    # Step 3: Open Travelers dropdown
    await page.evaluate("""() => {
        const els = [...document.querySelectorAll('button, [role="button"], div')];
        for (const e of els) {
            const t = (e.textContent || '').trim();
            if ((t === 'Travelers' || /^Travelers/.test(t) || /^Traveler/.test(t)
                 || /^\\d+\\s+(Adult|Traveler)/i.test(t)) && e.offsetParent !== null) {
                const btn = e.closest('button, [role="button"]') || e;
                if (btn.offsetWidth > 40 && btn.offsetWidth < 400) {
                    btn.click(); return true;
                }
            }
        }
        return false;
    }""")
    await page.wait_for_timeout(1500)

    # Step 4: Decrement Adult to 1
    await page.evaluate("""() => {
        const sections = [...document.querySelectorAll('div')].filter(d =>
            /Adult/.test(d.textContent || '') && d.offsetParent !== null
        );
        for (const sec of sections) {
            const minusBtns = [...sec.querySelectorAll('button')].filter(b => {
                const t = (b.textContent || '').trim();
                const al = (b.getAttribute('aria-label') || '').toLowerCase();
                return t === '-' || t === '−' || al.includes('decrease') || al.includes('minus') || al.includes('remove');
            });
            if (minusBtns.length > 0) {
                for (let i = 0; i < 5; i++) {
                    const btn = minusBtns[0];
                    if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') break;
                    btn.click();
                }
                return true;
            }
        }
        return false;
    }""")
    await page.wait_for_timeout(1000)

    # Step 5: Click Apply
    await page.evaluate("""() => {
        const els = [...document.querySelectorAll('button, [role="button"]')];
        for (const e of els) {
            const t = (e.textContent || '').trim();
            if (t === 'Apply' && e.offsetParent !== null
                && !e.disabled && e.getAttribute('aria-disabled') !== 'true') {
                e.click(); return true;
            }
        }
        return false;
    }""")
    await page.wait_for_timeout(7000)

    # Step 6: Expand any collapsed option cards
    expanded = await page.evaluate("""() => {
        let clicked = 0;
        const buttons = [...document.querySelectorAll('button[aria-expanded="false"]')];
        for (const btn of buttons) {
            if (btn.offsetParent === null) continue;
            const card = btn.closest('[class*="option"], [class*="Option"], [class*="product"], [class*="tour-grade"]');
            if (!card) continue;
            try { btn.click(); clicked++; } catch (e) {}
        }
        return clicked;
    }""")
    if expanded > 0:
        await page.wait_for_timeout(3000)

    html = await page.content()
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Lazy import services to avoid circular deps when used as a script
    from app.services.tour_variants_service import _extract_from_markdown
    data = await _extract_from_markdown(text[:30000])
    return data


async def main(city: str | None, limit: int | None) -> None:
    from playwright.async_api import async_playwright

    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from app.services.tour_variants_service import _convert_variants_to_aed, _has_variants as has_variants
    from sqlalchemy import select

    async with async_session_factory() as db:
        q = select(Activity).where(
            Activity.source_url.ilike("%viator.com%"),
        ).order_by(Activity.name)
        if city:
            q = q.where(Activity.city.ilike(city))
        result = await db.execute(q)
        all_acts = list(result.scalars().all())

    targets = [a for a in all_acts
               if not (isinstance(a.tour_variants, list) and len(a.tour_variants) > 0)]

    logger.info("=" * 70)
    logger.info("Viator supervised scrape: %d total Viator, %d need variants",
                len(all_acts), len(targets))
    logger.info("=" * 70)

    if limit:
        targets = targets[:limit]
        logger.info("Limited to first %d", limit)

    wins = 0
    no_options = 0
    errors = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # VISIBLE browser so user can solve CAPTCHAs
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx_kwargs = {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "viewport": {"width": 1440, "height": 900},
            "locale": "en-US",
        }
        # Reuse saved session cookies if available
        if STORAGE_STATE_FILE.exists():
            ctx_kwargs["storage_state"] = str(STORAGE_STATE_FILE)
            logger.info("Loaded saved session from %s", STORAGE_STATE_FILE.name)

        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        try:
            for i, act in enumerate(targets, 1):
                logger.info("[%d/%d] %s — %s", i, len(targets), act.city, act.name[:60])
                logger.info("       url: %s", act.source_url[:100])
                try:
                    data = await _scrape_one(page, act.source_url)
                    if not data or not has_variants(data):
                        no_options += 1
                        logger.info("  No options found")
                    else:
                        new_variants = _convert_variants_to_aed(data.get("tour_variants", []))
                        async with async_session_factory() as db:
                            a = await db.get(Activity, act.id)
                            a.tour_variants = new_variants
                            await db.commit()
                        wins += 1
                        logger.info("  OK: %d options scraped", len(new_variants))

                    # Save updated session cookies after each successful navigation
                    await context.storage_state(path=str(STORAGE_STATE_FILE))
                except Exception as exc:
                    errors += 1
                    logger.warning("  FAILED: %s", str(exc)[:140])

                if i % 3 == 0:
                    await asyncio.sleep(2)
        finally:
            await context.close()
            await browser.close()

    logger.info("=" * 70)
    logger.info("DONE VIATOR-SUPERVISED — Wins: %d  No options: %d  Errors: %d",
                wins, no_options, errors)
    logger.info("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", help="Filter by city (London / Cairo)")
    parser.add_argument("--limit", type=int, help="Cap activities processed")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.city, args.limit))
    except KeyboardInterrupt:
        print("\nInterrupted — completed activities are saved.")
        sys.exit(130)
