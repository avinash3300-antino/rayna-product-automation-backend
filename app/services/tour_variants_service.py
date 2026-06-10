"""Tour variants service — scrape tour options/variants from source URLs."""

import asyncio
import json
import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.activities import Activity
from app.integrations.claude_client import claude_client
from app.integrations.jina_client import jina_client
from app.integrations.apify_client import apify_client
from app.integrations.playwright_scraper import PlaywrightScraper
from app.services.pricing_service import EXCHANGE_RATES, _convert_to_aed

logger = logging.getLogger(__name__)

TOUR_VARIANTS_EXTRACTION_PROMPT = """You are a tour variant extraction specialist. Given web page content from a travel/booking site, \
extract all tour options, variants, or package types available for this activity.

Return a JSON object with:
{
  "tour_variants": [
    {
      "name": "Tour + Lunch",
      "description": "Full guided tour including traditional lunch",
      "duration_minutes": 480,
      "price": {"amount": 85.00, "currency": "USD"},
      "includes": ["Lunch", "Guide", "Transport"],
      "excludes": ["Tips", "Personal expenses"],
      "is_default": false
    }
  ]
}

RULES FOR VARIANT EXTRACTION:
- Look for sections like "Options", "Select an option", "Tour options", "Choose your experience", "Package types", "What's included"
- Look for radio buttons, tabs, cards, or lists showing different tour configurations
- Each variant typically has a different name, price, and set of inclusions
- Common variant patterns:
  * With/without meals: "Tour + Lunch" vs "Tour Without Lunch"
  * Transport options: "Car + Guide" vs "Car + Audio Guide" vs "Group Bus"
  * Duration tiers: "Half Day" vs "Full Day"
  * Group size: "Private Tour" vs "Group Tour" vs "Small Group"
  * Access levels: "Standard" vs "VIP" vs "Skip-the-line"
  * Combo packages: "Tour Only" vs "Tour + Dinner Cruise" vs "Tour + Show"
  * Ticket types: "Adult" vs "Child" vs "Family" (only if these are separate tour options, NOT just pricing tiers)
- Extract the variant name EXACTLY as shown on the page
- Extract description if available (often a short summary under the variant name)
- Extract the per-1-adult price (price for a single adult). If tiered prices are shown (adult / child / infant / family), use ONLY the adult price. If the variant is itself a "Private" or "Group" package priced per-vehicle/group, use that total as-is. Use the currency shown on the page. If no price visible, set price to null
- Extract duration_minutes if it differs per variant. If same as main activity or not shown, set to null
- Extract what's included per variant in the "includes" array
- Extract what's excluded per variant in the "excludes" array
- Mark is_default: true for the pre-selected or first/primary option
- If only ONE option exists with no alternatives, return an empty array
- If the page shows "Select a date to see options" but lists option NAMES, still extract those names
- Do NOT fabricate variants — only extract what's visible on the page
- Return ONLY valid JSON, no markdown fences or extra text
- If no variants/options are found at all, return {"tour_variants": []}"""


def _extract_json(text: str) -> dict | None:
    """Robustly extract JSON object from text that may contain extra content."""
    text = text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _identify_source(url: str) -> str:
    """Identify the booking platform from URL."""
    url_lower = url.lower()
    if "viator.com" in url_lower:
        return "Viator"
    elif "getyourguide.com" in url_lower:
        return "GetYourGuide"
    elif "tripadvisor.com" in url_lower:
        return "TripAdvisor"
    elif "klook.com" in url_lower:
        return "Klook"
    return "Unknown"


async def _extract_from_markdown(markdown: str) -> dict | None:
    """Use Claude to extract tour variants from markdown content."""
    try:
        source_hint = ""
        if "viator" in markdown.lower()[:500]:
            source_hint = "\nThis is a Viator page. Look for 'Choose an option' or 'Select option' sections with different tour packages."
        elif "getyourguide" in markdown.lower()[:500]:
            source_hint = "\nThis is a GetYourGuide page. Look for 'Options' or 'Select your option' sections."

        response_text = await claude_client.generate(
            prompt=f"Extract tour variants/options from this booking page:{source_hint}\n\n{markdown}",
            system=TOUR_VARIANTS_EXTRACTION_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            temperature=0.1,
        )

        data = _extract_json(response_text)
        if data is None:
            logger.warning("Claude returned unparseable response for tour variants")
        return data

    except Exception as exc:
        logger.warning("Tour variants extraction from markdown failed: %s", exc)
        return None


def _convert_variants_to_aed(variants: list[dict]) -> list[dict]:
    """Convert each variant's `price` from its source currency to AED.

    Returns a NEW list of NEW dicts so SQLAlchemy detects the JSON change.
    The original local price is preserved under `price_local`.
    """
    if not variants:
        return []
    out: list[dict] = []
    for v in variants:
        if not isinstance(v, dict):
            out.append(v)
            continue
        new_v = dict(v)
        price = new_v.get("price")
        if isinstance(price, dict):
            amount = price.get("amount")
            currency = price.get("currency")
            if amount is not None and currency:
                currency_upper = str(currency).upper()
                if currency_upper == "AED":
                    pass
                elif currency_upper in EXCHANGE_RATES:
                    aed_amount = _convert_to_aed(float(amount), currency_upper)
                    new_v["price_local"] = {"amount": float(amount), "currency": currency_upper}
                    new_v["price"] = {"amount": aed_amount, "currency": "AED"}
                else:
                    logger.warning("Unknown currency %s in tour variant — leaving as-is", currency_upper)
        out.append(new_v)
    return out


async def _scrape_gyg_with_date_click(url: str) -> dict | None:
    """GYG-specific: open page → click "Check Availability"/"Select date" →
    click date 7 days out → options panel renders below gallery → extract.

    Based on the actual current GYG UI: a right-sidebar booking widget with
    "Check Availability" button opens a 2-month calendar. Clicking a day
    populates the "Choose from N available options" section.
    """
    from datetime import datetime, timedelta

    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    if "getyourguide.com" not in url.lower():
        return None

    # Skip GYG landing/category pages (URL contains /lXXX-something-tcXXX/ or
    # ends with /lXXX/) — only tour pages have /tNNNN/
    if "-t" not in url or not any(seg.startswith("t") and seg[1:].rstrip("/").isdigit()
                                  for seg in url.split("/")[-2:]):
        # Allow if URL has -tNNN suffix on penultimate segment
        if not any("-t" in seg and seg.split("-t")[-1].rstrip("/").isdigit()
                   for seg in url.split("/")):
            logger.info("GYG: URL %s looks like a category page, skipping", url[:80])
            return None

    target = datetime.now() + timedelta(days=7)
    target_day = target.day
    target_iso = target.strftime("%Y-%m-%d")  # e.g. "2026-06-09"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await Stealth().apply_stealth_async(context)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)

            # Try opening the date picker. Prefer "Check Availability" button
            # (per current GYG UI), fall back to "Select date" dropdown.
            opened = await page.evaluate("""() => {
                const triggers = ['Check Availability', 'Check availability', 'Select date'];
                const els = [...document.querySelectorAll('button, [role="button"], a')];
                for (const trigger of triggers) {
                    for (const e of els) {
                        const t = (e.textContent || '').trim();
                        if (t === trigger || t.startsWith(trigger)) {
                            const btn = e.closest('button, [role="button"]') || e;
                            if (btn.offsetParent !== null) {
                                btn.click();
                                return trigger;
                            }
                        }
                    }
                }
                return null;
            }""")
            if not opened:
                logger.warning("GYG: could not find availability trigger on %s", url[:80])
                return None
            logger.info("GYG: opened picker via '%s'", opened)

            await page.wait_for_timeout(3000)

            # Click the day. Prefer aria-label or data-attribute matching the
            # ISO date, fall back to text match (first visible occurrence).
            clicked = await page.evaluate("""({day, iso}) => {
                // Strategy 1: aria-label or data-date matching ISO
                const dateAttrs = ['aria-label', 'data-date', 'data-day', 'data-testid'];
                const all = [...document.querySelectorAll('button, [role="gridcell"], [role="button"]')];
                for (const el of all) {
                    for (const attr of dateAttrs) {
                        const v = (el.getAttribute(attr) || '').toLowerCase();
                        if (v.includes(iso) || v.includes(iso.replaceAll('-', '/'))) {
                            if (el.offsetParent !== null) {
                                el.click();
                                return 'aria:' + attr;
                            }
                        }
                    }
                }
                // Strategy 2: text exactly equals day, in a clickable button/gridcell
                for (const el of all) {
                    const t = (el.textContent || '').trim();
                    if (t === String(day) && el.offsetParent !== null
                        && !el.disabled && el.getAttribute('aria-disabled') !== 'true') {
                        el.click();
                        return 'text';
                    }
                }
                return null;
            }""", {"day": target_day, "iso": target_iso})

            if not clicked:
                logger.warning("GYG: could not click day %s (%s) on %s", target_day, target_iso, url[:80])
                return None
            logger.info("GYG: clicked day %s via strategy=%s", target_day, clicked)

            # Wait for "Choose from N available options" panel to render
            await page.wait_for_timeout(6000)
            try:
                await page.wait_for_selector('text=/Choose from \\d+ available/', timeout=10000)
                logger.info("GYG: options panel rendered")
            except Exception:
                logger.info("GYG: options panel did not appear in time, trying anyway")

            # GYG renders ONLY the first option expanded; secondary options need
            # to be clicked to reveal their price/duration/includes/excludes.
            # Click every collapsed option header so the full data is in HTML
            # before we extract.
            expanded = await page.evaluate("""() => {
                let clicked = 0;
                // Find all collapsed expanders inside option-like containers
                const buttons = [...document.querySelectorAll('button[aria-expanded="false"]')];
                for (const btn of buttons) {
                    if (btn.offsetParent === null) continue;
                    const card = btn.closest('[class*="option"], [class*="Option"], [data-testid*="option"]');
                    if (!card) continue;
                    try { btn.click(); clicked++; } catch (e) {}
                }
                return clicked;
            }""")
            if expanded > 0:
                logger.info("GYG: expanded %d collapsed options", expanded)
                await page.wait_for_timeout(4000)  # let each expansion render

            html = await page.content()
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            # Narrow to the options region for higher Claude precision
            idx = text.lower().find("choose from")
            if idx > 0:
                text = text[idx:idx + 25000]

            data = await _extract_from_markdown(text[:25000])
            return data
        finally:
            await context.close()
            await browser.close()


async def _scrape_viator_with_date_click(url: str) -> dict | None:
    """Viator-specific flow: open page → click Date → pick day +7 → click
    Travelers → set Adult=1 → click Apply → options panel renders → extract.

    Per the actual Viator UI: a right-sidebar widget has "Date" + "Travelers"
    dropdowns and a green "Apply" button. Default travelers is often 2 — must
    be set to 1 (per-1-adult pricing requirement). The "Apply" click triggers
    the options panel rendering below the main gallery.
    """
    from datetime import datetime, timedelta

    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    if "viator.com" not in url.lower():
        return None

    target = datetime.now() + timedelta(days=7)
    target_day = target.day
    target_iso = target.strftime("%Y-%m-%d")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await Stealth().apply_stealth_async(context)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)

            # Quick DataDome check
            html_check = await page.content()
            if "captcha" in html_check.lower() and len(html_check) < 5000:
                logger.warning("Viator: DataDome blocked, %d bytes only", len(html_check))
                return None

            # Step 1: Click the Date dropdown in the right sidebar
            opened_date = await page.evaluate("""() => {
                // Date dropdown shows text like "Tue, Jun 9" or has 'Date' label
                const els = [...document.querySelectorAll('button, [role="button"], div')];
                for (const e of els) {
                    const t = (e.textContent || '').trim();
                    // Match elements that say "Date" alone or contain date pattern
                    if ((t === 'Date' || /^Date\\s/.test(t) ||
                         /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/.test(t))
                        && e.offsetParent !== null) {
                        const btn = e.closest('button, [role="button"]') || e;
                        if (btn.offsetWidth > 50 && btn.offsetWidth < 400) {
                            btn.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if not opened_date:
                logger.warning("Viator: could not open Date dropdown on %s", url[:80])
                return None
            logger.info("Viator: opened Date dropdown")
            await page.wait_for_timeout(2500)

            # Step 2: Click the target day in the calendar
            clicked_day = await page.evaluate("""({day, iso}) => {
                const all = [...document.querySelectorAll('button, [role="gridcell"], [role="button"], td')];
                // Try aria-label / data-date match first
                for (const el of all) {
                    for (const attr of ['aria-label', 'data-date', 'data-day']) {
                        const v = (el.getAttribute(attr) || '').toLowerCase();
                        if (v.includes(iso) || v.includes(iso.replaceAll('-', '/'))) {
                            if (el.offsetParent !== null) { el.click(); return 'aria'; }
                        }
                    }
                }
                // Fallback: text equals day
                for (const el of all) {
                    const t = (el.textContent || '').trim();
                    if (t === String(day) && el.offsetParent !== null
                        && !el.disabled && el.getAttribute('aria-disabled') !== 'true') {
                        el.click();
                        return 'text';
                    }
                }
                return null;
            }""", {"day": target_day, "iso": target_iso})
            if not clicked_day:
                logger.warning("Viator: could not click day %s", target_day)
                return None
            logger.info("Viator: clicked day %s via %s", target_day, clicked_day)
            await page.wait_for_timeout(2500)

            # Step 3: Open Travelers dropdown
            opened_travelers = await page.evaluate("""() => {
                const els = [...document.querySelectorAll('button, [role="button"], div')];
                for (const e of els) {
                    const t = (e.textContent || '').trim();
                    if ((t === 'Travelers' || /^Travelers/.test(t) ||
                         /^Traveler/.test(t) || /^\\d+\\s+(Adult|Traveler)/i.test(t))
                        && e.offsetParent !== null) {
                        const btn = e.closest('button, [role="button"]') || e;
                        if (btn.offsetWidth > 40 && btn.offsetWidth < 400) {
                            btn.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if opened_travelers:
                logger.info("Viator: opened Travelers dropdown")
                await page.wait_for_timeout(2000)

            # Step 4: Decrement Adult count to 1 (click minus until Adult = 1)
            await page.evaluate("""() => {
                // Find the Adult section's decrement button
                const sections = [...document.querySelectorAll('div')].filter(d =>
                    /Adult/.test(d.textContent || '') && d.offsetParent !== null
                );
                for (const sec of sections) {
                    // Look for buttons within with "-" or aria-label="decrement" / "minus"
                    const minusBtns = [...sec.querySelectorAll('button')].filter(b => {
                        const t = (b.textContent || '').trim();
                        const al = (b.getAttribute('aria-label') || '').toLowerCase();
                        return t === '-' || t === '−' || al.includes('decrease') || al.includes('minus') || al.includes('remove');
                    });
                    if (minusBtns.length > 0) {
                        // Click 2 times to go from 2 → 1 (or 3 → 1). Stop if disabled.
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

            # Step 5: Click Apply button
            applied = await page.evaluate("""() => {
                const els = [...document.querySelectorAll('button, [role="button"]')];
                for (const e of els) {
                    const t = (e.textContent || '').trim();
                    if (t === 'Apply' && e.offsetParent !== null
                        && !e.disabled && e.getAttribute('aria-disabled') !== 'true') {
                        e.click();
                        return true;
                    }
                }
                return false;
            }""")
            if applied:
                logger.info("Viator: clicked Apply")
            await page.wait_for_timeout(6000)

            # Step 6: Expand any collapsed option cards (similar to GYG)
            expanded = await page.evaluate("""() => {
                let clicked = 0;
                const buttons = [...document.querySelectorAll('button[aria-expanded="false"]')];
                for (const btn of buttons) {
                    if (btn.offsetParent === null) continue;
                    const card = btn.closest('[class*="option"], [class*="Option"], [class*="product"]');
                    if (!card) continue;
                    try { btn.click(); clicked++; } catch (e) {}
                }
                return clicked;
            }""")
            if expanded > 0:
                logger.info("Viator: expanded %d options", expanded)
                await page.wait_for_timeout(3000)

            html = await page.content()
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            data = await _extract_from_markdown(text[:30000])
            return data
        finally:
            await context.close()
            await browser.close()


async def _extract_via_date_click(url: str) -> dict | None:
    """Backward-compatible wrapper — routes URLs to the right platform clicker."""
    if "getyourguide.com" in url.lower():
        return await _scrape_gyg_with_date_click(url)
    if "viator.com" in url.lower():
        return await _scrape_viator_with_date_click(url)
    return None


def _has_variants(data: dict | None) -> bool:
    """Check if extracted data contains meaningful variant info."""
    if not data:
        return False
    variants = data.get("tour_variants", [])
    return isinstance(variants, list) and len(variants) > 0


async def _extract_variants_from_url(url: str) -> dict | None:
    """Scrape a URL and extract tour variants.

    For GYG URLs: go straight to date-click (Jina returns partial data with
    null prices on secondary options). For everything else: Jina → Apify →
    Playwright stealth.
    """

    is_gyg = "getyourguide.com" in url.lower()
    is_viator = "viator.com" in url.lower()

    # --- For GYG: skip Jina entirely (it returns null prices on Option 2+) ---
    if is_gyg:
        try:
            data = await _extract_via_date_click(url)
            if _has_variants(data):
                logger.info("DateClick+Claude extracted variants from %s", url)
                return data
        except Exception as exc:
            logger.warning("Date-click scrape failed for GYG %s: %s", url, exc)
        # If date-click fails for GYG, fall through to Jina as a partial fallback
        # (better to have first-option-only data than nothing)

    # --- Attempt 1: Jina Reader ---
    try:
        markdown = await jina_client.clean_page(url)
        if markdown and len(markdown) >= 100:
            data = await _extract_from_markdown(markdown[:15000])
            if _has_variants(data):
                logger.info("Jina+Claude extracted variants from %s", url)
                return data
    except Exception as exc:
        logger.warning("Jina failed for variants %s: %s", url, exc)

    # --- Attempt 2: Apify ---
    try:
        result = await apify_client.scrape_url(url)
        if result.get("success") and result.get("markdown"):
            markdown = result["markdown"]
            if len(markdown) >= 100:
                data = await _extract_from_markdown(markdown[:15000])
                if _has_variants(data):
                    logger.info("Apify+Claude extracted variants from %s", url)
                    return data
    except Exception as exc:
        logger.warning("Apify failed for variants %s: %s", url, exc)

    # --- Date-click for Viator (DataDome usually blocks but worth trying) ---
    if is_viator:
        try:
            data = await _extract_via_date_click(url)
            if _has_variants(data):
                logger.info("DateClick+Claude extracted variants from %s", url)
                return data
        except Exception as exc:
            logger.warning("Date-click scrape failed for Viator %s: %s", url, exc)

    # --- Attempt 3: Playwright with stealth (bypasses GYG anti-bot detection;
    # does NOT bypass Viator's DataDome). Heavy SPAs need >30s timeout. ---
    try:
        html = await PlaywrightScraper().scrape_url(
            url,
            wait_ms=8000,
            timeout=90000,
            wait_until="domcontentloaded",
            stealth=True,
        )
        if html and len(html) >= 500:
            # GYG pages are ~700KB with options panel deep in markup; strip
            # script/style + tags so the first ~30K chars sent to Claude are
            # actual text content rather than CSS/JS bytes.
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            data = await _extract_from_markdown(text[:30000])
            if _has_variants(data):
                logger.info("Playwright+Stealth+Claude extracted variants from %s", url)
                return data
    except Exception as exc:
        logger.warning("Playwright failed for variants %s: %s", url, exc)

    return None


async def scrape_variants_for_activity(
    db: AsyncSession,
    activity_id: UUID,
) -> dict:
    """Scrape tour variants from source URLs for an activity."""
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise NotFoundError("Activity not found")

    source_urls = activity.source_urls or []
    if not source_urls:
        if activity.source_url:
            source_urls = [activity.source_url]
        else:
            return {"activity_id": str(activity_id), "message": "No source URLs", "updated": False}

    # Use only the primary source_url (first one). Per-activity scraping is
    # expensive — secondary URLs are usually category pages anyway.
    variants_data = None
    used_url = None
    for url in source_urls[:1]:
        variants_data = await _extract_variants_from_url(url)
        if _has_variants(variants_data):
            used_url = url
            break

    if not variants_data or not _has_variants(variants_data):
        return {
            "activity_id": str(activity_id),
            "message": "No tour variants found in any source URL",
            "urls_tried": source_urls[:3],
            "updated": False,
        }

    new_variants = _convert_variants_to_aed(variants_data.get("tour_variants", []))
    old_variants = activity.tour_variants or []

    # Update if different
    old_names = sorted([v.get("name", "") for v in old_variants]) if old_variants else []
    new_names = sorted([v.get("name", "") for v in new_variants])

    if new_names != old_names:
        activity.tour_variants = new_variants
        return {
            "activity_id": str(activity_id),
            "url": used_url,
            "updated": True,
            "old_count": len(old_variants),
            "new_count": len(new_variants),
            "variants": [v.get("name") for v in new_variants],
        }

    return {
        "activity_id": str(activity_id),
        "url": used_url,
        "updated": False,
        "message": "Variants unchanged",
        "count": len(new_variants),
    }


async def bulk_scrape_variants(
    db: AsyncSession,
    city: str | None = None,
    source: str | None = None,
    missing_only: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Scrape tour variants for multiple activities.

    Filters:
      - city: 'London' / 'Cairo' (case-insensitive) — defaults to all
      - source: 'gyg' / 'viator' / 'other' — defaults to all
      - missing_only: when True (default), only activities without variants
      - limit / offset: pagination
    """
    from sqlalchemy import func as sa_func, or_, text as sa_text

    query = select(Activity).where(Activity.source_urls.isnot(None))
    if city:
        query = query.where(Activity.city.ilike(city))
    if source == "gyg":
        query = query.where(Activity.source_url.ilike("%getyourguide.com%"))
    elif source == "viator":
        query = query.where(Activity.source_url.ilike("%viator.com%"))
    elif source == "other":
        query = query.where(
            ~Activity.source_url.ilike("%getyourguide.com%"),
            ~Activity.source_url.ilike("%viator.com%"),
        )
    if missing_only:
        query = query.where(
            or_(
                Activity.tour_variants.is_(None),
                sa_func.jsonb_array_length(sa_text("tour_variants::jsonb")) == 0,
            )
        )
    query = query.order_by(Activity.name).offset(offset).limit(limit)

    result = await db.execute(query)
    activities = list(result.scalars().all())

    results = []
    updated_count = 0
    failed_count = 0

    for activity in activities:
        source_urls = activity.source_urls or []
        if not source_urls:
            continue

        try:
            variants_data = None
            for url in source_urls[:3]:
                variants_data = await _extract_variants_from_url(url)
                if _has_variants(variants_data):
                    break

            if not variants_data or not _has_variants(variants_data):
                failed_count += 1
                results.append({
                    "activity_id": str(activity.id),
                    "name": activity.name,
                    "status": "no_variants",
                })
                continue

            new_variants = _convert_variants_to_aed(variants_data.get("tour_variants", []))
            activity.tour_variants = new_variants
            updated_count += 1

            results.append({
                "activity_id": str(activity.id),
                "name": activity.name,
                "status": "updated",
                "count": len(new_variants),
                "variants": [v.get("name") for v in new_variants],
            })

        except Exception as exc:
            failed_count += 1
            results.append({
                "activity_id": str(activity.id),
                "name": activity.name,
                "status": "error",
                "message": str(exc),
            })

        await asyncio.sleep(0.5)

    return {
        "processed": len(activities),
        "updated": updated_count,
        "failed": failed_count,
        "offset": offset,
        "limit": limit,
        "results": results,
    }
