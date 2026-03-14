"""
reidin_debug.py — DOM Diagnostic for Reidin Insight
Run this WHILE the Reidin Sales Transactions page is open in Chrome on port 9222.
It will print what the page actually contains so we can fix the extractor selectors.

Usage:
    python reidin_debug.py
"""

import asyncio
import json
from playwright.async_api import async_playwright

CDP_URL = "http://127.0.0.1:9222"

DIAG_JS = """
() => {
    const results = {};

    // 1. Page URL and title
    results.url   = window.location.href;
    results.title = document.title;

    // 2. Iframe check
    const iframes = document.querySelectorAll('iframe');
    results.iframes = Array.from(iframes).map(f => ({
        src: f.src || f.getAttribute('src') || '(no src)',
        id:  f.id,
        cls: f.className,
    }));

    // 3. Native <table> elements
    const tables = document.querySelectorAll('table');
    results.native_tables = tables.length;
    if (tables.length > 0) {
        results.first_table_rows = tables[0].querySelectorAll('tr').length;
        results.first_table_html_preview = tables[0].outerHTML.slice(0, 500);
    }

    // 4. Div-based grid heuristics
    const gridCandidates = [
        '[class*="grid"]',
        '[class*="Grid"]',
        '[class*="table"]',
        '[class*="Table"]',
        '[class*="row"]',
        '[class*="Row"]',
        '[role="grid"]',
        '[role="table"]',
        '[role="row"]',
        '[role="rowgroup"]',
    ];
    results.div_grid_counts = {};
    for (const sel of gridCandidates) {
        const found = document.querySelectorAll(sel);
        if (found.length > 0) {
            results.div_grid_counts[sel] = found.length;
        }
    }

    // 5. Body outer HTML preview (first 1500 chars)
    results.body_preview = document.body ? document.body.outerHTML.slice(0, 1500) : 'no body';

    // 6. All unique top-level tag names in body
    const tags = new Set();
    if (document.body) {
        document.body.querySelectorAll('*').forEach(el => tags.add(el.tagName.toLowerCase()));
    }
    results.all_tags_in_body = Array.from(tags).sort();

    return results;
}
"""


async def main():
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as exc:
            print(f"[ERROR] Cannot connect to Chrome: {exc}")
            print("Make sure Chrome is running with --remote-debugging-port=9222")
            return

        # Find Reidin tab
        reidin_page = None
        for context in browser.contexts:
            for page in context.pages:
                if "reidin.com" in page.url:
                    reidin_page = page
                    break

        if reidin_page is None:
            print("[ERROR] No Reidin tab found.")
            print("Open tabs detected:")
            for context in browser.contexts:
                for page in context.pages:
                    print(f"  {page.url}")
            return

        print(f"[OK] Found Reidin tab: {reidin_page.url}\n")
        print("=" * 70)

        # Run diagnostic in the top-level frame
        result = await reidin_page.evaluate(DIAG_JS)
        print("=== TOP-LEVEL FRAME ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # Check iframes — run same diagnostic inside each iframe
        frames = reidin_page.frames
        print(f"\n=== ALL FRAMES ({len(frames)} total) ===")
        for i, frame in enumerate(frames):
            frame_url = frame.url
            print(f"\n--- Frame {i}: {frame_url} ---")
            try:
                fr = await frame.evaluate(DIAG_JS)
                if fr.get("native_tables", 0) > 0 or fr.get("div_grid_counts"):
                    print("[MATCH] This frame has table/grid content!")
                    print(json.dumps({
                        "url":              fr["url"],
                        "native_tables":    fr.get("native_tables", 0),
                        "first_table_rows": fr.get("first_table_rows", 0),
                        "div_grid_counts":  fr.get("div_grid_counts", {}),
                        "body_preview":     fr.get("body_preview", "")[:800],
                    }, indent=2, ensure_ascii=False))
                else:
                    print(f"  (no tables/grids — tags: {fr.get('all_tags_in_body', [])[:20]})")
            except Exception as exc:
                print(f"  [SKIP] Could not evaluate in frame: {exc}")

        print("\n" + "=" * 70)
        print("Diagnostic complete. Share the output above to identify the fix.")


if __name__ == "__main__":
    asyncio.run(main())
