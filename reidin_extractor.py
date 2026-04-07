"""
reidin_extractor.py — Reidin Rent Transactions Playwright Scraper
Launches its own Chromium browser (NO --remote-debugging-port needed),
logs in to Reidin with credentials from .env, sets filters, and scrapes
the Power BI ARIA grid page-by-page.

Usage (CLI):
    python reidin_extractor.py                  # rentals (default)
    python reidin_extractor.py --type sales     # sales transactions

Usage (programmatic):
    import asyncio
    from reidin_extractor import run_extraction
    result = asyncio.run(run_extraction(data_type="rentals", progress_cb=print))
    # result = {rows: int, output_path: str, error: str|None}

.env keys required:
    REIDIN_EMAIL=your@email.com
    REIDIN_PASSWORD=yourpassword
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REIDIN_EMAIL    = os.getenv("REIDIN_EMAIL", "")
REIDIN_PASSWORD = os.getenv("REIDIN_PASSWORD", "")

CDP_PORT = 9222
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_PROFILE = "Profile 9"
CHROME_USER_DATA = r"C:\Users\thema\AppData\Local\Google\Chrome\User Data"

REIDIN_LOGIN_URL = "https://insight.reidin.com/account/login"

# Reidin dashboard page paths
REIDIN_PAGES = {
    "sales":   "https://insight.reidin.com/home/dashboard/750",
    "rentals": "https://insight.reidin.com/home/dashboard/1147",
}

# Output paths per type
OUTPUT_PATHS = {
    "sales":   Path("data/reidin_raw_sales.csv"),
    "rentals": Path("data/reidin_raw_rentals.csv"),
}
PROGRESS_PATH = Path("data/reidin_progress.json")

MAX_PAGES = 500   # hard failsafe
AREA_FILTER = "Palm Jumeirah"

# ---------------------------------------------------------------------------
# Output columns
# ---------------------------------------------------------------------------
SALES_COLUMNS = [
    "transaction_type", "subtype", "sales_sequence", "times_sold",
    "date", "community", "property", "property_type",
    "unit", "bedrooms", "floor", "view", "size_sqf", "land_size", "amount_aed",
]

RENTAL_COLUMNS = [
    "rent_type", "date", "contract_start", "contract_end",
    "community", "property", "property_type",
    "unit", "bedrooms", "floor", "view",
    "parking", "balcony_area", "size_sqf", "land_size", "annual_rent_aed",
]

# ---------------------------------------------------------------------------
# Power BI ARIA grid JS (same as before — works inside Playwright-owned frame)
# ---------------------------------------------------------------------------
_EXTRACT_JS = """
() => {
    const grids = Array.from(document.querySelectorAll('[role="grid"]'));
    if (grids.length === 0) return {headers: [], rows: [], gridCount: 0};
    const grid = grids.reduce((best, g) => {
        const rowCount = g.querySelectorAll('[role="row"]').length;
        return rowCount > (best ? best.querySelectorAll('[role="row"]').length : 0) ? g : best;
    }, null);
    if (!grid) return {headers: [], rows: [], gridCount: grids.length};
    const headerCells = Array.from(grid.querySelectorAll('[role="columnheader"]'));
    const headers = headerCells.map(c => c.textContent.trim());
    const dataRows = Array.from(grid.querySelectorAll('[role="row"]'))
        .filter(r => r.querySelector('[role="gridcell"]'));
    const rows = dataRows.map(r =>
        Array.from(r.querySelectorAll('[role="gridcell"]')).map(c => c.textContent.trim())
    ).filter(r => r.length > 0);
    return {headers, rows, gridCount: grids.length};
}
"""

_GRID_EXISTS_JS = """
() => {
    const grids = document.querySelectorAll('[role="grid"]');
    for (const g of grids) {
        if (g.querySelectorAll('[role="row"]').length > 1) return true;
    }
    return false;
}
"""

_FIRST_ROW_JS = """
() => {
    const grids = Array.from(document.querySelectorAll('[role="grid"]'));
    const grid = grids.reduce((best, g) => {
        const rowCount = g.querySelectorAll('[role="row"]').length;
        return rowCount > (best ? best.querySelectorAll('[role="row"]').length : 0) ? g : best;
    }, null);
    if (!grid) return '';
    const firstDataRow = Array.from(grid.querySelectorAll('[role="row"]'))
        .find(r => r.querySelector('[role="gridcell"]'));
    return firstDataRow ? firstDataRow.textContent.trim() : '';
}
"""

_NEXT_PAGE_JS = """
() => {
    const allBtns = Array.from(
        document.querySelectorAll('button, [role="button"], [role="menuitem"]')
    );
    const nextBtn = allBtns.find(el => {
        const lbl   = (el.getAttribute('aria-label') || '').toLowerCase();
        const title = (el.getAttribute('title') || '').toLowerCase();
        const txt   = (el.textContent || '').trim();
        const isNext = lbl.includes('next') || title.includes('next')
                    || txt === '>' || txt === '›' || txt === '»' || txt === 'Next';
        if (!isNext) return false;
        if (el.disabled) return false;
        if (el.getAttribute('aria-disabled') === 'true') return false;
        const cls = (el.className || '').toLowerCase();
        if (cls.includes('disabled') || cls.includes('inactive')) return false;
        const style = window.getComputedStyle(el);
        if (style.pointerEvents === 'none') return false;
        if (parseFloat(style.opacity) < 0.4) return false;
        return true;
    });
    if (!nextBtn) return false;
    nextBtn.click();
    return true;
}
"""


# ---------------------------------------------------------------------------
# Header → column mapping
# ---------------------------------------------------------------------------
def _map_headers(headers: list[str], data_type: str) -> dict[str, int]:
    canonical = {
        "date":          ["date", "contract date", "transaction date", "trans date"],
        "community":     ["community", "area", "location"],
        "property":      ["property", "building", "project", "development"],
        "property_type": ["property type", "type", "unit type"],
        "unit":          ["unit", "unit no", "unit no.", "unit number"],
        "bedrooms":      ["bedrooms", "beds", "no. of bedrooms", "bedroom"],
        "floor":         ["floor", "floor no", "level"],
        "view":          ["view", "primary/secondary view", "primary view"],
        "size_sqf":      ["size (sqf)", "size (sq ft)", "size (sqft)", "size", "sq ft", "sqft"],
    }
    if data_type == "sales":
        canonical.update({
            "transaction_type": ["transaction type", "trans type"],
            "subtype":          ["subtype", "sub type"],
            "sales_sequence":   ["sales sequence", "sequence"],
            "times_sold":       ["times sold"],
            "land_size":        ["land size", "land area", "plot size"],
            "amount_aed":       ["amount (aed)", "amount", "price", "sale price",
                                 "transaction amount", "value (aed)"],
        })
    else:
        canonical.update({
            "rent_type":      ["rent type", "type"],
            "parking":        ["parking"],
            "balcony_area":   ["balcony area", "balcony"],
            "land_size":      ["land size", "land area", "plot size"],
            "annual_rent_aed": ["annual (aed) amount", "annual rent", "rent",
                                "annual amount", "rental amount", "amount (aed)",
                                "amount", "annual rent (aed)"],
            "contract_start": ["start date", "contract start", "from", "contract start date"],
            "contract_end":   ["end date", "contract end", "to", "expiry",
                               "contract end date", "expiry date"],
        })
    lower_headers = [h.lower() for h in headers]
    mapping: dict[str, int] = {}
    for field, aliases in canonical.items():
        for alias in aliases:
            if alias in lower_headers:
                mapping[field] = lower_headers.index(alias)
                break
    return mapping


def _extract_row(cells: list[str], col_map: dict[str, int], columns: list[str]) -> dict:
    row: dict = {}
    for field in columns:
        idx = col_map.get(field)
        row[field] = cells[idx].strip() if idx is not None and idx < len(cells) else ""
    return row


# ---------------------------------------------------------------------------
# Login helper
# ---------------------------------------------------------------------------
async def _login(page, email: str, password: str) -> bool:
    """Navigate to login page and sign in. Returns True on success."""
    print(f"  [INFO] Logging in as {email}…")
    await page.goto(REIDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(2)

    # Fill email
    email_sel = 'input[type="email"], input[name="email"], input[placeholder*="email" i], #email'
    try:
        await page.wait_for_selector(email_sel, timeout=10_000)
        await page.fill(email_sel, email)
    except Exception:
        # Try username field
        await page.fill('input[type="text"]:first-of-type', email)

    # Fill password
    pw_sel = 'input[type="password"]'
    await page.fill(pw_sel, password)

    # Submit
    submit_sel = 'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Sign In")'
    await page.click(submit_sel)

    # Wait for redirect away from login
    try:
        await page.wait_for_url(lambda url: "login" not in url, timeout=15_000)
        print("  [OK] Logged in successfully")
        return True
    except Exception:
        print("  [WARN] Login may have failed — check credentials in .env")
        return False


# ---------------------------------------------------------------------------
# CDP helpers — connect to existing Chrome session (avoids OTP)
# ---------------------------------------------------------------------------
async def _check_cdp(port: int, timeout: float = 3.0) -> bool:
    """Return True if Chrome already has CDP exposed on given port."""
    url = f"http://127.0.0.1:{port}/json/version"
    loop = asyncio.get_event_loop()
    try:
        def _fetch():
            req = urllib.request.urlopen(url, timeout=timeout)
            return req.read()
        await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=timeout + 1)
        return True
    except Exception:
        return False


def _kill_chrome():
    """Kill all Chrome processes."""
    subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)


def _launch_chrome_cdp(port: int):
    """Launch Chrome with CDP port via PowerShell Start-Process (independent process)."""
    args = " ".join([
        f'"{CHROME_EXE}"',
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f'--user-data-dir="{CHROME_USER_DATA}"',
        f'--profile-directory="{CHROME_PROFILE}"',
        "--no-first-run",
        "--no-default-browser-check",
        f'"https://insight.reidin.com/home/dashboard/1147"',
    ])
    subprocess.Popen(
        ["powershell", "-Command", f"Start-Process {args}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def _wait_for_cdp(port: int, timeout: int = 45) -> bool:
    """Poll until CDP responds or timeout. Returns True if ready."""
    for _ in range(timeout):
        if await _check_cdp(port, timeout=2.0):
            return True
        await asyncio.sleep(1)
    return False


# ---------------------------------------------------------------------------
# Filter helpers (clicking inside the Power BI iframe)
# ---------------------------------------------------------------------------
async def _set_area_filter(frame, area: str) -> bool:
    """Click the Area & Community dropdown and select the given area."""
    # Find the dropdown — it's a Power BI slicer
    # Try several selector strategies
    dropdown_selectors = [
        'div[title="Area & Community"]',
        'div.slicer-dropdown-menu',
        '[aria-label*="Area"]',
        'div.slicerCheckbox',
    ]

    # First look for the current value (e.g. "Dubai Marina" or "All")
    # and click the parent dropdown
    try:
        # PBI slicers: click the expand button
        await frame.wait_for_selector('.slicer-dropdown-toggle, [aria-haspopup="listbox"]',
                                      timeout=10_000)
        toggles = await frame.query_selector_all('.slicer-dropdown-toggle, [aria-haspopup="listbox"]')
        # Find the one that looks like Area & Community
        for toggle in toggles:
            text = (await toggle.text_content() or "").strip()
            parent_text = ""
            try:
                container = await toggle.query_selector('..')
                if container:
                    parent_text = (await container.text_content() or "").strip()
            except Exception:
                pass
            if "area" in parent_text.lower() or "community" in parent_text.lower():
                await toggle.click()
                await asyncio.sleep(1)
                break
        else:
            # Try clicking any dropdown-like element with Area text
            await frame.click('text="Dubai Marina"')
            await asyncio.sleep(1)
    except Exception as e:
        print(f"  [WARN] Could not click Area dropdown: {e}")
        return False

    # Search for Palm Jumeirah
    try:
        search_input = await frame.query_selector('input[type="text"][aria-label*="Search"], .searchInput input, input.search')
        if search_input:
            await search_input.fill(area)
            await asyncio.sleep(1)
    except Exception:
        pass

    # Click the option
    try:
        await frame.click(f'text="{area}"')
        await asyncio.sleep(2)
        print(f"  [OK] Area filter set to '{area}'")
        return True
    except Exception as e:
        print(f"  [WARN] Could not select '{area}': {e}")
        return False


# ---------------------------------------------------------------------------
# Main extraction coroutine
# ---------------------------------------------------------------------------
async def run_extraction(
    data_type: str = "rentals",
    progress_cb=None,
    max_pages: int = MAX_PAGES,
    area_filter: str = AREA_FILTER,
    headless: bool = False,
) -> dict:
    """
    Launch a fresh Chromium browser, log in to Reidin, navigate to the
    rent/sales transactions dashboard, set the area filter to Palm Jumeirah,
    and scrape the Power BI ARIA grid page by page.

    Args:
        data_type: "rentals" or "sales"
        progress_cb: optional callback(page_num, row_count, msg)
        max_pages: failsafe page limit
        area_filter: the community to filter to (default: "Palm Jumeirah")
        headless: run browser without UI (default False so you can watch)

    Returns:
        {rows: int, output_path: str, error: str|None}
    """
    output_path    = OUTPUT_PATHS.get(data_type, OUTPUT_PATHS["rentals"])
    output_columns = RENTAL_COLUMNS if data_type == "rentals" else SALES_COLUMNS
    target_url     = REIDIN_PAGES.get(data_type, REIDIN_PAGES["rentals"])

    def _progress(page_num: int, row_count: int, msg: str = ""):
        PROGRESS_PATH.parent.mkdir(exist_ok=True)
        PROGRESS_PATH.write_text(
            json.dumps({"page": page_num, "rows": row_count,
                        "status": "running", "type": data_type, "msg": msg}),
            encoding="utf-8",
        )
        if progress_cb:
            progress_cb(page_num, row_count, msg)
        else:
            print(f"  Page {page_num} | {row_count} rows{' — ' + msg if msg else ''}")

    def _error(msg: str) -> dict:
        PROGRESS_PATH.parent.mkdir(exist_ok=True)
        PROGRESS_PATH.write_text(
            json.dumps({"status": "error", "error": msg, "type": data_type}),
            encoding="utf-8",
        )
        return {"rows": 0, "output_path": None, "error": msg}

    # Validate credentials
    if not REIDIN_EMAIL or not REIDIN_PASSWORD:
        return _error(
            "REIDIN_EMAIL and REIDIN_PASSWORD must be set in .env\n"
            "Add these lines to your .env file:\n"
            "  REIDIN_EMAIL=your@email.com\n"
            "  REIDIN_PASSWORD=yourpassword"
        )

    async with async_playwright() as pw:
        # ----------------------------------------------------------------
        # TIER 1: Connect to existing Chrome session via CDP (no OTP risk)
        # ----------------------------------------------------------------
        cdp_alive = await _check_cdp(CDP_PORT)
        browser = None
        using_cdp = False

        if cdp_alive:
            print(f"  [OK] Found existing Chrome CDP session on port {CDP_PORT} — connecting")
            try:
                browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
                using_cdp = True
            except Exception as e:
                print(f"  [WARN] CDP connect failed ({e}) — falling back to fresh browser")
                browser = None
        else:
            print()
            print("  ╔══════════════════════════════════════════════════════════╗")
            print("  ║  Chrome is not running with remote debugging enabled.    ║")
            print("  ║                                                          ║")
            print("  ║  Please do the following:                                ║")
            print("  ║    1. Double-click start_reidin_chrome.bat               ║")
            print("  ║    2. Enter the OTP if Reidin asks for one               ║")
            print("  ║    3. Leave Chrome open                                  ║")
            print("  ║    4. Re-run: python reidin_extractor.py --type rentals  ║")
            print("  ╚══════════════════════════════════════════════════════════╝")
            print()
            return _error("Chrome not running with CDP. Run start_reidin_chrome.bat first.")

        if browser is not None:
            # Using CDP — get or create page, avoid reloading if already on dashboard
            contexts = browser.contexts
            if contexts:
                pages = contexts[0].pages
                page = pages[0] if pages else await contexts[0].new_page()
            else:
                ctx = await browser.new_context()
                page = await ctx.new_page()

            current_url = page.url
            print(f"  [INFO] Current page URL: {current_url[:80]}")

            if "dashboard/1147" in current_url or "dashboard/750" in current_url:
                print("  [OK] Already on Reidin dashboard — not reloading (avoids OTP)")
                await asyncio.sleep(2)
            elif "login" in current_url.lower() or "auth" in current_url.lower() or "otp" in current_url.lower():
                await browser.close()
                return _error(
                    "Reidin is showing a login/OTP page. "
                    "Please open Chrome manually, complete the OTP, then re-run."
                )
            else:
                print(f"  [INFO] Navigating to {data_type} dashboard: {target_url}")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(5)

        # --- Find Power BI iframe --------------------------------------------
        print("  [INFO] Locating Power BI iframe…")
        pbi_frame = None
        for _ in range(30):
            for frame in page.frames:
                if "powerbi.com" in frame.url:
                    pbi_frame = frame
                    break
            if pbi_frame:
                break
            await asyncio.sleep(1)

        if pbi_frame is None:
            await browser.close()
            return _error("Power BI iframe not found — page may not have loaded correctly")
        print(f"  [OK] Power BI frame: {pbi_frame.url[:80]}…")

        # --- Wait for the grid to appear -------------------------------------
        print("  [INFO] Waiting for data grid to render…")
        grid_ready = False
        for attempt in range(60):
            try:
                has_grid = await pbi_frame.evaluate(_GRID_EXISTS_JS)
                if has_grid:
                    grid_ready = True
                    print(f"  [OK] Grid ready after {attempt + 1}s")
                    break
            except Exception:
                pass
            await asyncio.sleep(1)

        if not grid_ready:
            await browser.close()
            return _error("Grid did not render within 60s. Try running with headless=False to debug.")

        await asyncio.sleep(2)

        # --- Set Area & Community filter to Palm Jumeirah -------------------
        print(f"  [INFO] Applying '{area_filter}' filter…")
        filter_ok = await _set_area_filter(pbi_frame, area_filter)
        if not filter_ok:
            print(f"  [WARN] Could not set filter automatically — proceeding with current filter")
            print(f"         TIP: Run with headless=False and set the filter manually, then press Enter")
            if not headless:
                input("  Set the Palm Jumeirah filter manually, then press Enter to start scraping…")

        # Re-wait for grid after filter change
        await asyncio.sleep(3)
        for attempt in range(30):
            try:
                has_grid = await pbi_frame.evaluate(_GRID_EXISTS_JS)
                if has_grid:
                    break
            except Exception:
                pass
            await asyncio.sleep(1)
        await asyncio.sleep(2)

        # --- Scrape loop -----------------------------------------------------
        all_rows: list[dict] = []
        col_map: dict[str, int] | None = None
        page_num = 0

        while page_num < max_pages:
            page_num += 1
            _progress(page_num, len(all_rows))

            try:
                data = await pbi_frame.evaluate(_EXTRACT_JS)
            except Exception as exc:
                print(f"  [WARN] JS extraction failed on page {page_num}: {exc}")
                break

            headers   = data.get("headers", [])
            rows      = data.get("rows", [])
            grid_count = data.get("gridCount", 0)

            if page_num == 1:
                print(f"  [INFO] {grid_count} grid(s), {len(headers)} headers, {len(rows)} rows on first page")

            if not headers and not rows:
                if page_num == 1:
                    print("  [WARN] No data on first page — waiting 5s and retrying…")
                    await asyncio.sleep(5)
                    try:
                        data   = await pbi_frame.evaluate(_EXTRACT_JS)
                        headers = data.get("headers", [])
                        rows   = data.get("rows", [])
                    except Exception:
                        pass
                if not headers and not rows:
                    print(f"  [WARN] No table data on page {page_num} — stopping")
                    break

            if col_map is None and headers:
                col_map = _map_headers(headers, data_type)
                unmapped = [f for f in output_columns if f not in col_map]
                print(f"  [OK] Headers: {headers}")
                print(f"  [OK] Column map: {col_map}")
                if unmapped:
                    print(f"  [INFO] Unmapped fields (will be blank): {unmapped}")

            if col_map is None:
                print("  [WARN] No column map — stopping")
                break

            for cells in rows:
                all_rows.append(_extract_row(cells, col_map, output_columns))

            _progress(page_num, len(all_rows))

            # Pagination
            try:
                first_row_before = await pbi_frame.evaluate(_FIRST_ROW_JS)
            except Exception:
                first_row_before = ""

            has_next = await pbi_frame.evaluate(_NEXT_PAGE_JS)
            if not has_next:
                print(f"  [OK] No more pages after page {page_num}")
                break

            try:
                await pbi_frame.wait_for_function(
                    """(prev) => {
                        const grids = Array.from(document.querySelectorAll('[role="grid"]'));
                        const grid = grids.reduce((best, g) => {
                            const rc = g.querySelectorAll('[role="row"]').length;
                            return rc > (best ? best.querySelectorAll('[role="row"]').length : 0) ? g : best;
                        }, null);
                        if (!grid) return false;
                        const fr = Array.from(grid.querySelectorAll('[role="row"]'))
                            .find(r => r.querySelector('[role="gridcell"]'));
                        return fr && fr.textContent.trim() !== prev;
                    }""",
                    arg=first_row_before,
                    timeout=15_000,
                )
            except Exception:
                await asyncio.sleep(3)

        await browser.close()

        # --- Save ------------------------------------------------------------
        output_path.parent.mkdir(exist_ok=True)
        if all_rows:
            df = pd.DataFrame(all_rows, columns=output_columns)
            df.to_csv(output_path, index=False)
            print(f"\n[OK] Saved {len(df):,} rows → {output_path}")
        else:
            pd.DataFrame(columns=output_columns).to_csv(output_path, index=False)
            print(f"\n[WARN] No rows extracted — empty CSV written to {output_path}")

        PROGRESS_PATH.write_text(
            json.dumps({
                "status": "done", "type": data_type,
                "page": page_num, "rows": len(all_rows),
                "output_path": str(output_path),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }),
            encoding="utf-8",
        )

        return {"rows": len(all_rows), "output_path": str(output_path), "error": None}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reidin Rent/Sales transaction scraper (Playwright)")
    parser.add_argument("--type", dest="data_type", default="rentals",
                        choices=["sales", "rentals"])
    parser.add_argument("--area", default=AREA_FILTER,
                        help=f"Area filter (default: {AREA_FILTER})")
    parser.add_argument("--headless", action="store_true",
                        help="Run browser headlessly (default: visible)")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = parser.parse_args()

    if not REIDIN_EMAIL:
        print("[ERROR] REIDIN_EMAIL not set in .env")
        print("Add to .env:  REIDIN_EMAIL=your@email.com")
        print("              REIDIN_PASSWORD=yourpassword")
        sys.exit(1)

    print(f"Reidin Extractor — {args.data_type.upper()} | Area: {args.area}")
    print("=" * 50)
    result = asyncio.run(run_extraction(
        data_type=args.data_type,
        max_pages=args.max_pages,
        area_filter=args.area,
        headless=args.headless,
    ))
    if result["error"]:
        print(f"\n[ERROR] {result['error']}")
        sys.exit(1)
    print(f"\nDone. {result['rows']:,} rows → {result['output_path']}")
