"""Playwright-based scraper for day-wise availability and tour options.

Uses a real browser (non-headless) to interact with Viator/GYG pages,
select dates, and extract time slots + tour options for each day of the week.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta

from app.integrations.claude_client import claude_client

logger = logging.getLogger(__name__)

# Claude prompt for extracting structured data from page text after date selection
DAYWISE_EXTRACTION_PROMPT = """You are a tour availability extraction specialist. Given the text content of a booking page AFTER a specific date has been selected, extract the available time slots and tour options/variants.

Return a JSON object:
{
  "time_slots": ["08:00", "09:00", "10:00", "14:00"],
  "tour_options": [
    {
      "name": "Car + Tour Guide Only",
      "price": {"amount": 49.00, "currency": "USD"},
      "duration_minutes": 480,
      "description": "Private tour with car and guide",
      "includes": ["Guide", "Transport", "Water"],
      "excludes": ["Lunch", "Tips"],
      "time_slots": ["08:00", "09:00"]
    }
  ]
}

RULES:
- Extract ALL time slots shown (format HH:MM 24h). Convert "8:00 AM" → "08:00", "1:00 PM" → "13:00"
- Extract ALL tour options/variants if shown (e.g., "Car + Tour Guide Only", "Tour + Lunch", "Group Tour")
- Each option may have its own price, duration, includes/excludes, and time slots
- If no distinct tour options exist (just a single booking option), return empty tour_options: []
- If no time slots visible, return empty time_slots: []
- Prices: extract amount and currency. Use "USD" if $ symbol without other context
- Do NOT fabricate data — only extract what's visible
- Return ONLY valid JSON, no markdown fences"""


async def _extract_with_claude(page_text: str, date_str: str) -> dict | None:
    """Use Claude to extract structured availability from page text."""
    try:
        response = await claude_client.generate(
            prompt=f"Extract availability data for date {date_str} from this booking page content:\n\n{page_text[:12000]}",
            system=DAYWISE_EXTRACTION_PROMPT,
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            temperature=0.1,
        )
        text = response.strip()
        # Parse JSON robustly
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                return json.loads(text[start:end + 1])
    except Exception as exc:
        logger.warning("Claude extraction failed for %s: %s", date_str, exc)
    return None


async def _launch_browser(playwright):
    """Launch browser with anti-detection measures."""
    browser = await playwright.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
    )
    await context.add_init_script(
        'Object.defineProperty(navigator, "webdriver", { get: () => false });'
    )
    return browser, context


def _detect_platform(url: str) -> str:
    """Detect the booking platform from URL."""
    url_lower = url.lower()
    if "viator.com" in url_lower:
        return "viator"
    elif "getyourguide.com" in url_lower:
        return "gyg"
    elif "tripadvisor.com" in url_lower:
        return "tripadvisor"
    elif "klook.com" in url_lower:
        return "klook"
    return "unknown"


async def _open_viator_calendar(page) -> bool:
    """Open the Viator date calendar by clicking the Date dropdown.

    Viator layout (right sidebar):
      [Date: Wed, May 20  v]  [Traveler: 1  v]
      [       Check Availability             ]

    Clicking the "Date" dropdown opens a calendar popup.
    """
    # Scroll to the booking widget area (right sidebar)
    await page.mouse.wheel(0, 3000)
    await page.wait_for_timeout(2000)

    # Try clicking the Date dropdown — it contains "Date" text + a date value
    date_selectors = [
        # The date dropdown container
        'text="Date"',
        '[class*="DateSelector"]',
        '[class*="dateSelector"]',
        '[class*="date-selector"]',
        '[data-testid*="date"]',
    ]

    for sel in date_selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.scroll_into_view_if_needed()
                await page.wait_for_timeout(300)
                await el.click()
                await page.wait_for_timeout(3000)
                # Check if calendar appeared — look for month headers or gridcells
                cal = await page.query_selector('td[role="gridcell"], [class*="Calendar"], [class*="calendar"]')
                if cal:
                    logger.debug("Calendar opened via: %s", sel)
                    return True
        except Exception:
            continue

    # Fallback: click the area that shows the date text (e.g. "Wed, May 20")
    try:
        opened = await page.evaluate("""() => {
            // Find elements showing date patterns like "Mon, May 25" or "Wed, May 20"
            const els = [...document.querySelectorAll('*')].filter(e => {
                const t = e.textContent.trim();
                return /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d{1,2}$/.test(t)
                    && e.children.length <= 2;
            });
            if (els.length > 0) {
                // Click the parent (the dropdown container)
                const target = els[0].closest('button, [role="button"], [class*="select"], [class*="dropdown"]') || els[0];
                target.click();
                return true;
            }
            return false;
        }""")
        if opened:
            await page.wait_for_timeout(3000)
            cal = await page.query_selector('td[role="gridcell"], [class*="Calendar"]')
            if cal:
                logger.debug("Calendar opened via date text click")
                return True
    except Exception as exc:
        logger.debug("Date text click fallback failed: %s", exc)

    # Last resort: try "Check Availability" button
    try:
        check_btn = await page.query_selector(
            'button:has-text("Check Availability"), a:has-text("Check Availability")'
        )
        if check_btn and await check_btn.is_visible():
            await check_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            await check_btn.click()
            await page.wait_for_timeout(4000)
            return True
    except Exception as exc:
        logger.debug("Check Availability fallback failed: %s", exc)

    return False


async def _open_gyg_calendar(page) -> bool:
    """Open the GYG availability calendar."""
    await page.mouse.wheel(0, 4000)
    await page.wait_for_timeout(2000)

    # GYG has different selectors for date selection
    try:
        # Try clicking the date selector / availability section
        for sel in [
            'button:has-text("Check availability")',
            'button:has-text("Select date")',
            '[data-testid="activity-booking-widget"] button',
            '[class*="DatePicker"]',
            '[class*="availability"]',
        ]:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.scroll_into_view_if_needed()
                await page.wait_for_timeout(300)
                await btn.click()
                await page.wait_for_timeout(3000)
                return True
    except Exception as exc:
        logger.debug("GYG calendar open failed: %s", exc)

    return False


async def _click_date(page, target_date: datetime, platform: str) -> bool:
    """Click a specific date on the calendar."""
    # Try various aria-label formats
    formats_to_try = [
        target_date.strftime("%a %b %d %Y"),           # Mon May 25 2026
        target_date.strftime("%A, %B %d, %Y"),          # Monday, May 25, 2026
        target_date.strftime("%B %d, %Y"),              # May 25, 2026
        target_date.strftime("%d %B %Y"),               # 25 May 2026
        target_date.strftime("%Y-%m-%d"),               # 2026-05-25
    ]

    for fmt in formats_to_try:
        btn = await page.query_selector(f'button[aria-label="{fmt}"]')
        if btn:
            disabled = await btn.get_attribute("disabled")
            aria_disabled = await btn.get_attribute("aria-disabled")
            if disabled or aria_disabled == "true":
                return False
            try:
                await btn.click()
                await page.wait_for_timeout(3000)
                return True
            except Exception:
                continue

    # Fallback: try finding date by text content inside calendar grid
    try:
        day_num = str(target_date.day)
        grid_buttons = await page.query_selector_all('td[role="gridcell"] button')
        for btn in grid_buttons:
            text = await btn.inner_text()
            if text.strip() == day_num:
                await btn.click()
                await page.wait_for_timeout(3000)
                return True
    except Exception:
        pass

    return False


async def _reopen_calendar(page, platform: str):
    """Re-open the calendar after selecting a date (calendar often closes)."""
    if platform == "viator":
        # Try clicking the date input area to reopen
        for sel in [
            'button:has-text("Date")',
            '[class*="DateInput"]',
            '[data-testid*="date"]',
            'input[placeholder*="date"]',
        ]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(2000)
                    return
            except Exception:
                continue

        # Fallback: look for any calendar trigger
        try:
            cal = await page.query_selector('[class*="calendar"], [class*="Calendar"]')
            if not cal:
                # Calendar is closed, try scrolling back to it
                await page.mouse.wheel(0, -2000)
                await page.wait_for_timeout(1000)
        except Exception:
            pass

    elif platform == "gyg":
        for sel in [
            '[class*="DatePicker"]',
            'button:has-text("Change date")',
            '[data-testid*="date"]',
        ]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(2000)
                    return
            except Exception:
                continue


async def _extract_page_content(page) -> str:
    """Get the full text content of the page."""
    try:
        return await page.evaluate("() => document.body?.innerText || ''")
    except Exception:
        return ""


def _extract_time_slots_regex(text: str) -> list[str]:
    """Extract time slots from text using regex."""
    # Match patterns like "8:00 AM", "13:00", "8:00\u202fam"
    pattern = r'\b(\d{1,2}:\d{2})\s*([APap][Mm])?\b'
    matches = re.findall(pattern, text.replace('\u202f', ' '))

    time_slots = set()
    for time_str, ampm in matches:
        hour, minute = map(int, time_str.split(':'))
        if ampm:
            ampm = ampm.upper()
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            time_slots.add(f"{hour:02d}:{minute:02d}")

    return sorted(time_slots)


async def _set_travelers_viator(page):
    """Open Traveler dropdown and click Apply on Viator.

    After date selection, the Viator sidebar shows:
      [Date: Thu, May 21 v]  [Traveler: 1  v]

    Flow:
    1. Click the "Traveler" dropdown → opens traveler selector showing
       Adult (Age 12-99): 1, Child (Age 6-11): 0, Infant (0-5): 0
       with an "Apply" button at the bottom
    2. Click "Apply" → tour options load below
    """
    try:
        await page.wait_for_timeout(1000)

        # --- Step 1: Click the Traveler dropdown to open it ---
        traveler_selectors = [
            'text="Traveler"',
            '[class*="TravelerSelector"]',
            '[class*="travelerSelector"]',
            '[class*="traveler-selector"]',
            '[data-testid*="traveler"]',
            '[data-testid*="Traveler"]',
        ]

        dropdown_opened = False
        for sel in traveler_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.scroll_into_view_if_needed()
                    await page.wait_for_timeout(300)
                    await el.click()
                    await page.wait_for_timeout(2000)
                    # Check if traveler panel opened — look for "Adult" text
                    adult_el = await page.query_selector('text=/Adult.*Age/')
                    if adult_el:
                        dropdown_opened = True
                        logger.debug("Traveler dropdown opened via: %s", sel)
                        break
            except Exception:
                continue

        if not dropdown_opened:
            # Fallback: find the element showing traveler count (e.g., icon + "1")
            try:
                opened = await page.evaluate("""() => {
                    // Look for the Traveler dropdown area
                    const els = [...document.querySelectorAll('*')].filter(e => {
                        const t = e.textContent.trim();
                        return t === 'Traveler' && e.children.length <= 1;
                    });
                    if (els.length > 0) {
                        const target = els[0].closest('button, [role="button"], [class*="select"], [class*="dropdown"], div[class]') || els[0];
                        target.click();
                        return true;
                    }
                    return false;
                }""")
                if opened:
                    await page.wait_for_timeout(2000)
                    adult_el = await page.query_selector('text=/Adult.*Age/')
                    if adult_el:
                        dropdown_opened = True
                        logger.debug("Traveler dropdown opened via JS fallback")
            except Exception as exc:
                logger.debug("Traveler JS fallback failed: %s", exc)

        if not dropdown_opened:
            logger.warning("Could not open Traveler dropdown, trying Apply directly")

        # --- Step 2: Click Apply button ---
        await page.wait_for_timeout(500)

        # The Apply button is inside the traveler dropdown panel
        apply_btn = await page.query_selector('button:has-text("Apply")')
        if apply_btn:
            await apply_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(300)
            if await apply_btn.is_visible():
                await apply_btn.click()
                logger.info("Clicked Apply button in traveler dropdown")
                await page.wait_for_timeout(6000)  # Wait for tour options to load
                return True

        # Fallback: try other button texts
        for btn_text in ["Search", "Check Availability", "Update Search"]:
            try:
                btn = await page.query_selector(f'button:has-text("{btn_text}")')
                if btn:
                    await btn.scroll_into_view_if_needed()
                    await page.wait_for_timeout(300)
                    if await btn.is_visible():
                        await btn.click()
                        logger.info("Clicked fallback button: %s", btn_text)
                        await page.wait_for_timeout(6000)
                        return True
            except Exception:
                continue

        # JS fallback for Apply
        try:
            result = await page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const text = b.textContent.trim();
                    if (text === 'Apply') {
                        b.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        b.click();
                        return 'Apply';
                    }
                }
                return null;
            }""")
            if result:
                logger.info("Clicked Apply via JS evaluation")
                await page.wait_for_timeout(6000)
                return True
        except Exception:
            pass

        logger.debug("No Apply button found on Viator")
    except Exception as exc:
        logger.debug("Set travelers failed: %s", exc)
    return False


async def _set_travelers_gyg(page):
    """Set travelers on GYG."""
    try:
        apply_btn = await page.query_selector(
            'button:has-text("Apply"), button:has-text("Search"), '
            'button:has-text("Check availability")'
        )
        if apply_btn and await apply_btn.is_visible():
            await apply_btn.click()
            await page.wait_for_timeout(4000)
            return True
    except Exception as exc:
        logger.debug("GYG set travelers failed: %s", exc)
    return False


async def _navigate_calendar_month(page, target_date: datetime) -> bool:
    """Navigate the Viator calendar to the correct month if needed.

    The calendar shows 2 months side by side. If the target date is in a
    future month not yet visible, click the next arrow to advance.
    """
    target_month_name = target_date.strftime("%B %Y")  # e.g. "June 2026"
    try:
        # Check if target month is already visible
        for _ in range(6):  # max 6 forward clicks
            month_headers = await page.query_selector_all('[class*="CalendarMonth"] strong, [class*="calendar"] caption, th[colspan]')
            visible_months = []
            for h in month_headers:
                txt = (await h.inner_text()).strip()
                if txt:
                    visible_months.append(txt)

            # Also check via page text
            page_text = await page.evaluate("() => document.body?.innerText || ''")
            if target_month_name in page_text:
                return True

            for vm in visible_months:
                if target_month_name in vm:
                    return True

            # Click next arrow to advance month
            next_btn = await page.query_selector(
                'button[aria-label="Next"], button[aria-label="next month"], '
                '[class*="next"], [class*="Next"], [class*="forward"]'
            )
            if next_btn and await next_btn.is_visible():
                await next_btn.click()
                await page.wait_for_timeout(1000)
            else:
                break
    except Exception as exc:
        logger.debug("Navigate calendar month failed: %s", exc)
    return True  # Proceed anyway


async def _scrape_single_day(context, source_url: str, target_date: datetime, platform: str) -> dict:
    """Scrape availability for a single day by loading the page fresh.

    Viator flow (from user screenshots):
    1. Load page → scroll to booking sidebar
    2. Click Date dropdown → calendar opens
    3. Navigate to correct month if needed
    4. Click the target date → calendar closes
    5. Click Traveler dropdown → traveler selector opens (default: 1 adult)
    6. Click Apply → tour options load below
    7. Scroll down and extract all content
    """
    day_name = target_date.strftime("%A")
    date_str = target_date.strftime("%Y-%m-%d")

    page = await context.new_page()
    try:
        # Load the page fresh
        await page.goto(source_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(5000)

        # Open calendar (clicks Date dropdown)
        if platform == "viator":
            cal_opened = await _open_viator_calendar(page)
        elif platform == "gyg":
            cal_opened = await _open_gyg_calendar(page)
        else:
            cal_opened = await _open_viator_calendar(page) or await _open_gyg_calendar(page)

        if not cal_opened:
            logger.warning("  %s: could not open calendar", day_name)

        # Navigate to correct month if target date is in next month
        await _navigate_calendar_month(page, target_date)

        # Click the target date
        clicked = await _click_date(page, target_date, platform)
        if not clicked:
            return {
                "date": date_str,
                "available": False,
                "time_slots": [],
                "tour_options": [],
            }

        # After date selection, open Traveler dropdown and click Apply
        # This is REQUIRED on Viator to see tour options
        if platform == "viator":
            applied = await _set_travelers_viator(page)
            if not applied:
                logger.warning("  %s: Apply not clicked, options may not load", day_name)
        elif platform == "gyg":
            await _set_travelers_gyg(page)

        # Scroll down to see all tour options that loaded
        await page.mouse.wheel(0, 3000)
        await page.wait_for_timeout(2000)

        # Extract page content after date + travelers selection
        text = await _extract_page_content(page)

        # Quick regex extraction for time slots
        regex_times = _extract_time_slots_regex(text)

        # Use Claude for structured extraction
        claude_data = await _extract_with_claude(text, date_str)

        time_slots = []
        tour_options = []

        if claude_data:
            time_slots = claude_data.get("time_slots", [])
            tour_options = claude_data.get("tour_options", [])

        # Merge regex times if Claude missed some
        if regex_times and not time_slots:
            time_slots = regex_times
        elif regex_times:
            all_times = set(time_slots) | set(regex_times)
            time_slots = sorted(all_times)

        logger.info("  %s: %d time slots, %d options", day_name, len(time_slots), len(tour_options))

        return {
            "date": date_str,
            "available": True,
            "time_slots": time_slots,
            "tour_options": tour_options,
        }

    except Exception as exc:
        logger.warning("  %s: error - %s", day_name, exc)
        return {
            "date": date_str,
            "available": False,
            "time_slots": [],
            "tour_options": [],
            "error": str(exc),
        }
    finally:
        await page.close()


async def scrape_daily_availability(
    source_url: str,
    week_offset: int = 0,
    parallel_days: int = 3,
) -> dict:
    """Scrape day-wise availability from a source URL using Playwright.

    Opens the booking page in PARALLEL tabs for each day of the week,
    navigates the calendar, selects the date, and captures time slots + tour options.

    Args:
        source_url: The Viator/GYG/other booking page URL.
        week_offset: 0 = next week, 1 = week after, etc.
        parallel_days: How many days to scrape at once (default: all 7).

    Returns:
        Dict with daily availability data.
    """
    from playwright.async_api import async_playwright

    platform = _detect_platform(source_url)
    logger.info("Scraping daily availability from %s (platform=%s, parallel=%d)",
                source_url, platform, parallel_days)

    # Calculate target week (Mon-Sun)
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday + (week_offset * 7))

    result = {
        "source_url": source_url,
        "platform": platform,
        "scraped_at": datetime.utcnow().isoformat(),
        "week_start": next_monday.strftime("%Y-%m-%d"),
        "daily": {},
    }

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    import subprocess
    p = await async_playwright().start()
    browser = None
    try:
        browser, context = await _launch_browser(p)

        # Scrape all 7 days in parallel (or in batches)
        sem = asyncio.Semaphore(parallel_days)

        async def _scrape_day_with_sem(day_offset):
            async with sem:
                target_date = next_monday + timedelta(days=day_offset)
                day_name = day_names[day_offset]
                logger.info("  Scraping %s (%s)...", day_name, target_date.strftime("%Y-%m-%d"))
                return day_name, await _scrape_single_day(context, source_url, target_date, platform)

        tasks = [_scrape_day_with_sem(i) for i in range(7)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.warning("Day scrape error: %s", r)
                continue
            day_name, day_data = r
            result["daily"][day_name] = day_data

    except Exception as exc:
        logger.error("Playwright scraping failed for %s: %s", source_url, exc)
        result["error"] = str(exc)
    finally:
        # Kill browser via taskkill on Windows to avoid hanging
        if browser:
            try:
                pid = browser.process.pid
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, timeout=5)
            except Exception:
                pass
        # Stop playwright connection - don't await, just schedule and move on
        try:
            asyncio.get_event_loop().call_soon(lambda: asyncio.ensure_future(_safe_stop(p)))
        except Exception:
            pass

    return result


async def _safe_stop(p):
    """Stop playwright silently in background."""
    try:
        await asyncio.wait_for(p.stop(), timeout=3)
    except Exception:
        pass


async def bulk_scrape_parallel(
    concurrency: int = 3,
    city: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict:
    """Scrape daily availability for multiple activities in parallel.

    Runs `concurrency` browser instances simultaneously, each scraping
    all 7 days in parallel tabs. This is ~20x faster than sequential.

    Args:
        concurrency: Number of activities to scrape at once (default: 3).
        city: Optional city filter.
        limit: Max activities to process.
        offset: Skip first N activities.

    Returns:
        Summary dict with counts and per-activity results.
    """
    from app.db.base import async_session_factory
    from app.db.models.activities import Activity
    from sqlalchemy import text
    from uuid import UUID
    import time

    # Fetch activities to scrape
    async with async_session_factory() as db:
        params = {
            "viator": "%viator.com%",
            "gyg": "%getyourguide.com%",
            "limit": limit,
            "offset": offset,
        }
        city_filter = ""
        if city:
            city_filter = "AND LOWER(city) = LOWER(:city)"
            params["city"] = city

        r = await db.execute(text(f"""
            SELECT id, name, source_url, source_urls FROM activities
            WHERE daily_availability IS NULL
            AND (source_url LIKE :viator OR source_url LIKE :gyg)
            {city_filter}
            ORDER BY
                CASE WHEN source_url LIKE :viator THEN 0 ELSE 1 END,
                created_at
            LIMIT :limit OFFSET :offset
        """), params)
        activities = r.all()

    if not activities:
        return {"total": 0, "done": 0, "errors": 0, "message": "No activities to scrape"}

    logger.info("Bulk scraping %d activities with concurrency=%d", len(activities), concurrency)

    sem = asyncio.Semaphore(concurrency)
    total_done = 0
    total_errors = 0
    results_log = []

    async def _scrape_one(act):
        nonlocal total_done, total_errors
        async with sem:
            start = time.time()
            try:
                # Determine best URL
                source_urls = act.source_urls or []
                if not source_urls and act.source_url:
                    source_urls = [act.source_url]
                url = source_urls[0] if source_urls else None
                for u in source_urls:
                    if "viator.com" in u or "getyourguide.com" in u:
                        url = u
                        break

                if not url:
                    total_errors += 1
                    return

                # Scrape with parallel days
                data = await scrape_daily_availability(url)

                # Save to DB
                async with async_session_factory() as db:
                    activity = await db.get(Activity, act.id)
                    if not activity:
                        total_errors += 1
                        return

                    daily = data.get("daily", {})
                    all_times = set()
                    all_options = []
                    operating_days = []

                    for day_name, day_data in daily.items():
                        if day_data.get("available"):
                            operating_days.append(day_name)
                            for t in day_data.get("time_slots", []):
                                all_times.add(t)
                            for opt in day_data.get("tour_options", []):
                                if not any(o.get("name") == opt.get("name") for o in all_options):
                                    all_options.append(opt)

                    if all_times:
                        activity.start_times = sorted(all_times)
                    if operating_days:
                        activity.operating_days = operating_days
                    if all_options:
                        variants = []
                        for opt in all_options:
                            variants.append({
                                "name": opt.get("name", "Standard"),
                                "description": opt.get("description"),
                                "duration_minutes": opt.get("duration_minutes"),
                                "price": opt.get("price"),
                                "includes": opt.get("includes"),
                                "excludes": opt.get("excludes"),
                                "is_default": len(variants) == 0,
                            })
                        activity.tour_variants = variants
                    activity.daily_availability = data

                    await db.commit()
                    total_done += 1

                elapsed = time.time() - start
                days_ok = sum(1 for d in daily.values() if d.get("available"))
                total_slots = sum(len(d.get("time_slots", [])) for d in daily.values())
                total_opts = sum(len(d.get("tour_options", [])) for d in daily.values())
                logger.info("[%d] DONE: %s — %d/7 days, %d slots, %d opts (%.0fs)",
                            total_done, act.name[:50], days_ok, total_slots, total_opts, elapsed)
                results_log.append({
                    "name": act.name, "days": days_ok, "slots": total_slots,
                    "options": total_opts, "time": round(elapsed),
                })

            except Exception as exc:
                total_errors += 1
                elapsed = time.time() - start
                logger.error("[ERR] %s — %s (%.0fs)", act.name[:50], str(exc)[:100], elapsed)
                results_log.append({"name": act.name, "error": str(exc)[:100]})

    # Run all activities with concurrency limit
    tasks = [_scrape_one(act) for act in activities]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Bulk scrape complete: %d done, %d errors out of %d total",
                total_done, total_errors, len(activities))

    return {
        "total": len(activities),
        "done": total_done,
        "errors": total_errors,
        "results": results_log[:50],  # First 50 for summary
    }


async def scrape_daily_for_activity(db, activity_id) -> dict:
    """Scrape day-wise availability for a single activity and update the DB."""
    from uuid import UUID

    from app.core.exceptions import NotFoundError
    from app.db.models.activities import Activity

    activity = await db.get(Activity, UUID(str(activity_id)))
    if not activity:
        raise NotFoundError("Activity not found")

    # Get source URL
    source_urls = activity.source_urls or []
    if not source_urls and activity.source_url:
        source_urls = [activity.source_url]
    if not source_urls:
        return {"activity_id": str(activity_id), "error": "No source URLs", "updated": False}

    # Try each source URL (prefer Viator/GYG)
    url = source_urls[0]
    for u in source_urls:
        if "viator.com" in u or "getyourguide.com" in u:
            url = u
            break

    result = await scrape_daily_availability(url)

    # Update activity fields
    daily = result.get("daily", {})
    if not daily:
        return {"activity_id": str(activity_id), "error": "No daily data scraped", "updated": False}

    # Aggregate all unique time slots across all days
    all_times = set()
    all_options = []
    operating_days = []

    for day_name, day_data in daily.items():
        if day_data.get("available"):
            operating_days.append(day_name)
            for t in day_data.get("time_slots", []):
                all_times.add(t)
            for opt in day_data.get("tour_options", []):
                # Deduplicate by name
                if not any(o.get("name") == opt.get("name") for o in all_options):
                    all_options.append(opt)

    # Update activity
    updated_fields = []

    if all_times:
        new_times = sorted(all_times)
        if new_times != sorted(activity.start_times or []):
            activity.start_times = new_times
            updated_fields.append("start_times")

    if operating_days:
        if sorted(operating_days) != sorted(activity.operating_days or []):
            activity.operating_days = operating_days
            updated_fields.append("operating_days")

    if all_options:
        # Convert to tour_variants format
        variants = []
        for opt in all_options:
            variants.append({
                "name": opt.get("name", "Standard"),
                "description": opt.get("description"),
                "duration_minutes": opt.get("duration_minutes"),
                "price": opt.get("price"),
                "includes": opt.get("includes"),
                "excludes": opt.get("excludes"),
                "is_default": len(variants) == 0,
            })
        activity.tour_variants = variants
        updated_fields.append("tour_variants")

    # Store the full daily breakdown
    activity.daily_availability = result

    return {
        "activity_id": str(activity_id),
        "name": activity.name,
        "url": url,
        "updated": len(updated_fields) > 0,
        "updated_fields": updated_fields,
        "daily_summary": {
            day: {
                "available": d.get("available", False),
                "time_slots": len(d.get("time_slots", [])),
                "options": len(d.get("tour_options", [])),
            }
            for day, d in daily.items()
        },
    }
