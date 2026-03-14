"""
reidin_extractor.py — Reidin Sales Transactions CDP Scraper
Attaches to an authenticated Chrome session on port 9222, locates the
Power BI iframe that Reidin embeds, and scrapes the Sales Transactions
table page-by-page, saving to data/reidin_raw.csv.

Usage (CLI):
    python reidin_extractor.py

Usage (programmatic):
    import asyncio
    from reidin_extractor import run_extraction
    result = asyncio.run(run_extraction(progress_cb=print))
    # result = {rows: int, output_path: str, error: str|None}
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CDP_URL       = "http://127.0.0.1:9222"
OUTPUT_PATH   = Path("data/reidin_raw.csv")
PROGRESS_PATH = Path("data/reidin_progress.json")
MAX_PAGES     = 50  # hard failsafe — never infinite-loop

# ---------------------------------------------------------------------------
# Output columns
# ---------------------------------------------------------------------------
OUTPUT_COLUMNS = [
    "date", "community", "property", "property_type",
    "unit", "bedrooms", "floor", "view", "size_sqf", "amount_aed",
]


# ---------------------------------------------------------------------------
# Tab + frame discovery
# ---------------------------------------------------------------------------

async def _find_reidin_page(browser):
    """Return the first page whose URL contains 'reidin.com', or None."""
    for context in browser.contexts:
        for page in context.pages:
            if "reidin.com" in page.url:
                return page
    return None


def _find_powerbi_frame(page):
    """Return the Power BI iframe frame object, or None."""
    for frame in page.frames:
        if "powerbi.com" in frame.url:
            return frame
    return None


# ---------------------------------------------------------------------------
# Power BI ARIA-based table extraction
# ---------------------------------------------------------------------------

# Reidin embeds its Sales Transactions table in a Power BI report.
# Power BI renders grids using ARIA roles (no native <table> elements):
#   [role="grid"]         — the grid container
#   [role="columnheader"] — header cells
#   [role="row"]          — each data row
#   [role="gridcell"]     — each cell within a row

_EXTRACT_JS = """
() => {
    // Find the grid — Power BI may have multiple, take the largest one
    const grids = Array.from(document.querySelectorAll('[role="grid"]'));
    if (grids.length === 0) return {headers: [], rows: []};

    // Pick the grid with the most rows (the data table, not a filter panel)
    const grid = grids.reduce((best, g) => {
        const rowCount = g.querySelectorAll('[role="row"]').length;
        return rowCount > (best ? best.querySelectorAll('[role="row"]').length : 0)
            ? g : best;
    }, null);

    if (!grid) return {headers: [], rows: []};

    // --- Headers ---
    const headerCells = Array.from(
        grid.querySelectorAll('[role="columnheader"]')
    );
    const headers = headerCells.map(c => c.textContent.trim());

    // --- Data rows (rows that contain gridcell children) ---
    const dataRows = Array.from(grid.querySelectorAll('[role="row"]'))
        .filter(r => r.querySelector('[role="gridcell"]'));

    const rows = dataRows.map(r =>
        Array.from(r.querySelectorAll('[role="gridcell"]'))
            .map(c => c.textContent.trim())
    ).filter(r => r.length > 0);

    return {headers, rows};
}
"""

_FIRST_ROW_JS = """
() => {
    const grid = document.querySelector('[role="grid"]');
    if (!grid) return '';
    const firstDataRow = Array.from(grid.querySelectorAll('[role="row"]'))
        .find(r => r.querySelector('[role="gridcell"]'));
    return firstDataRow ? firstDataRow.textContent.trim() : '';
}
"""

# Power BI table visuals expose pagination buttons with aria-labels or titles
# containing "Next page", "next", or navigation arrow icons.
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

        // Disabled checks
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
# Header → column index mapping
# ---------------------------------------------------------------------------

def _map_headers(headers: list[str]) -> dict[str, int]:
    """Map canonical field names to column indices."""
    canonical = {
        "date":          ["date", "contract date", "transaction date", "trans date"],
        "community":     ["community", "area", "location"],
        "property":      ["property", "building", "project", "development"],
        "property_type": ["property type", "type", "unit type", "subtype"],
        "unit":          ["unit", "unit no", "unit no.", "unit number"],
        "bedrooms":      ["bedrooms", "beds", "no. of bedrooms", "bedroom"],
        "floor":         ["floor", "floor no", "level"],
        "view":          ["view", "primary/secondary view", "primary view"],
        "size_sqf":      ["size (sqf)", "size (sq ft)", "size (sqft)", "size",
                          "area", "sq ft", "sqft"],
        "amount_aed":    ["amount (aed)", "amount", "price", "sale price",
                          "transaction amount", "value (aed)"],
    }
    lower_headers = [h.lower() for h in headers]
    mapping: dict[str, int] = {}
    for field, aliases in canonical.items():
        for alias in aliases:
            if alias in lower_headers:
                mapping[field] = lower_headers.index(alias)
                break
    return mapping


def _extract_row(cells: list[str], col_map: dict[str, int]) -> dict:
    row: dict = {}
    for field in OUTPUT_COLUMNS:
        idx = col_map.get(field)
        row[field] = cells[idx].strip() if idx is not None and idx < len(cells) else ""
    return row


# ---------------------------------------------------------------------------
# Main extraction coroutine
# ---------------------------------------------------------------------------

async def run_extraction(progress_cb=None, max_pages: int = MAX_PAGES) -> dict:
    """
    Connect to Chrome on 9222, find the Reidin tab, locate the Power BI
    iframe, and scrape the Sales Transactions table with pagination.

    Returns:
        {rows: int, output_path: str, error: str|None}
    """
    def _progress(page_num: int, row_count: int, msg: str = ""):
        PROGRESS_PATH.parent.mkdir(exist_ok=True)
        PROGRESS_PATH.write_text(
            json.dumps({"page": page_num, "rows": row_count,
                        "status": "running", "msg": msg}),
            encoding="utf-8",
        )
        if progress_cb:
            progress_cb(page_num, row_count, msg)
        else:
            print(f"  Page {page_num} | {row_count} rows{' — ' + msg if msg else ''}")

    def _error(msg: str) -> dict:
        PROGRESS_PATH.parent.mkdir(exist_ok=True)
        PROGRESS_PATH.write_text(
            json.dumps({"status": "error", "error": msg}), encoding="utf-8"
        )
        return {"rows": 0, "output_path": None, "error": msg}

    async with async_playwright() as pw:
        # -- Connect to Chrome ------------------------------------------------
        try:
            browser = await pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as exc:
            return _error(f"I cannot connect to Chrome on {CDP_URL}: {exc}")

        page = await _find_reidin_page(browser)
        if page is None:
            return _error(
                "I could not find a Reidin tab. "
                "Open reidin.com and go to Sales Transactions, then try again."
            )
        print(f"[OK] Found Reidin tab: {page.url}")

        # -- Locate Power BI iframe -------------------------------------------
        # Give the iframe a moment to initialise if the page just loaded
        pbi_frame = _find_powerbi_frame(page)
        if pbi_frame is None:
            print("  [INFO] Power BI frame not ready — waiting up to 15s…")
            for _ in range(15):
                await asyncio.sleep(1)
                pbi_frame = _find_powerbi_frame(page)
                if pbi_frame:
                    break

        if pbi_frame is None:
            return _error(
                "I could not find the Power BI iframe on the Reidin page. "
                "Make sure I am on the Sales Transactions page with the data table visible."
            )
        print(f"[OK] Found Power BI frame: {pbi_frame.url[:80]}…")

        # -- Scrape loop -------------------------------------------------------
        all_rows: list[dict] = []
        col_map: dict[str, int] | None = None
        page_num = 0

        while page_num < max_pages:
            page_num += 1
            _progress(page_num, len(all_rows))

            # Extract from the Power BI frame
            try:
                data = await pbi_frame.evaluate(_EXTRACT_JS)
            except Exception as exc:
                print(f"  [WARN] JS extraction failed on page {page_num}: {exc}")
                break

            headers = data.get("headers", [])
            rows    = data.get("rows", [])

            if not headers and not rows:
                print(f"  [WARN] No table data found on page {page_num} — stopping")
                break

            # Build column map once from the first non-empty header row
            if col_map is None and headers:
                col_map = _map_headers(headers)
                unmapped = [f for f in OUTPUT_COLUMNS if f not in col_map]
                print(f"  [OK] Headers found: {headers}")
                print(f"  [OK] Column map: {col_map}")
                if unmapped:
                    print(f"  [INFO] Unmapped fields (will be empty): {unmapped}")

            if col_map is None:
                print("  [WARN] I could not map any columns — stopping")
                break

            for cells in rows:
                all_rows.append(_extract_row(cells, col_map))

            _progress(page_num, len(all_rows))

            # -- Pagination (runs inside Power BI frame) ----------------------
            has_next = await pbi_frame.evaluate(_NEXT_PAGE_JS)
            if not has_next:
                print(f"  [OK] No more pages after page {page_num}")
                break

            # Capture first-row text BEFORE the transition
            try:
                first_row_before = await pbi_frame.evaluate(_FIRST_ROW_JS)
            except Exception:
                first_row_before = ""

            # Wait until first-row content changes — confirms new page loaded
            try:
                await pbi_frame.wait_for_function(
                    """(prev) => {
                        const grid = document.querySelector('[role="grid"]');
                        if (!grid) return false;
                        const firstRow = Array.from(
                            grid.querySelectorAll('[role="row"]')
                        ).find(r => r.querySelector('[role="gridcell"]'));
                        return firstRow && firstRow.textContent.trim() !== prev;
                    }""",
                    arg=first_row_before,
                    timeout=15_000,
                )
            except Exception:
                # Fallback: short network idle wait
                try:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass  # continue regardless — don't stall the loop

        # -- Save output -------------------------------------------------------
        OUTPUT_PATH.parent.mkdir(exist_ok=True)

        if all_rows:
            df = pd.DataFrame(all_rows, columns=OUTPUT_COLUMNS)
            df.to_csv(OUTPUT_PATH, index=False)
            print(f"\n[OK] Saved {len(df):,} rows to {OUTPUT_PATH}")
        else:
            pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(OUTPUT_PATH, index=False)
            print(f"\n[WARN] No rows extracted — empty CSV written to {OUTPUT_PATH}")

        PROGRESS_PATH.write_text(
            json.dumps({
                "status": "done",
                "page": page_num,
                "rows": len(all_rows),
                "output_path": str(OUTPUT_PATH),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }),
            encoding="utf-8",
        )

        return {
            "rows": len(all_rows),
            "output_path": str(OUTPUT_PATH),
            "error": None,
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = asyncio.run(run_extraction())
    if result["error"]:
        print(f"\n[ERROR] {result['error']}")
        sys.exit(1)
    print(f"\nDone. {result['rows']:,} rows saved to {result['output_path']}")
