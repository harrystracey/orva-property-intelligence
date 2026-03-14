"""
PropSpace Leads Scraper
Uses CDP via websockets (no Playwright) — connects to Chrome on port 9222.
Requires Chrome already running and logged into crm.propspace.com.

Reads buyer/tenant leads from the CURRENT PAGE STATE in Chrome.
Apply your filters in Chrome (location, lead pool, etc.) BEFORE running.
The scraper reads the table and paginates automatically via the Next button.

Output: scraped_data/propspace_leads.csv
Columns: ref, lead_type, status, sub_status, first_name, last_name,
         phone, country_code, category, emirate, location, sub_location,
         source, agent, enquiry_date, contact_ref

Usage:
  1. Open Chrome: python bayut_scraper/run_bayut_scrape.py --launch-chrome
  2. Log in to crm.propspace.com/leads/
  3. Apply filters in Chrome (location, lead pool, etc.)
  4. Run: python propspace_scraper/run_propspace_scrape.py
  5. Do NOT touch the Chrome window while scraping
"""

import asyncio
import csv
import json
import re
import sys
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[ERROR] websockets not installed. Run: pip install websockets")
    sys.exit(1)

CDP_HTTP = "http://localhost:9222"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "scraped_data" / "propspace_leads.csv"


# ---------------------------------------------------------------------------
# CDP helpers
# ---------------------------------------------------------------------------

async def _get_propspace_tab():
    """Find the PropSpace tab ID from Chrome's CDP /json endpoint."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{CDP_HTTP}/json", timeout=5) as resp:
            tabs = json.loads(resp.read())
        for tab in tabs:
            if "propspace" in tab.get("url", ""):
                return tab["id"]
        # No propspace tab — use first navigable tab
        for tab in tabs:
            if tab.get("type") == "page":
                return tab["id"]
    except Exception as e:
        print(f"[ERROR] Cannot reach Chrome on port 9222: {e}")
    return None


async def _cdp_send(ws, method, params=None, msg_id=1):
    """Send a CDP command and return the result."""
    await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("id") == msg_id:
            return msg


async def _navigate(ws, url, timeout=10):
    """Navigate page to url and wait for load."""
    await _cdp_send(ws, "Page.navigate", {"url": url})
    await asyncio.sleep(timeout)


async def _eval(ws, js, msg_id=99):
    """Evaluate JavaScript and return the string value."""
    result = await _cdp_send(ws, "Runtime.evaluate", {
        "expression": js,
        "returnByValue": True,
    }, msg_id=msg_id)
    return result.get("result", {}).get("result", {}).get("value")


async def _click_js(ws, selector, msg_id=100):
    """Click an element via JavaScript."""
    js = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (el) {{ el.click(); return true; }}
        return false;
    }})()
    """
    return await _eval(ws, js, msg_id=msg_id)


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

async def scrape_leads(location="Palm Jumeirah", pool_only=True, max_pages=None, detail=False):
    """
    Scrape PropSpace leads from the CURRENT page state in Chrome.
    Filters must be applied manually in the Chrome window before running.
    The scraper reads the table as-is and paginates via the Next button.

    location / pool_only: informational only (logged in header, not applied here)
    detail: reserved for future per-lead detail scraping (not implemented)
    """
    print(f"\n{'='*60}")
    print(f"  PROPSPACE LEADS SCRAPER")
    print(f"{'='*60}")
    print(f"  Location  : {location or 'All'} (apply filter in Chrome first)")
    print(f"  Pool only : {pool_only} (apply filter in Chrome first)")
    print(f"{'='*60}")
    print(f"  NOTE: Reads from current Chrome page — do NOT change the")
    print(f"        Chrome window while scraping is running.")
    print(f"{'='*60}\n")

    tab_id = await _get_propspace_tab()
    if not tab_id:
        print("[ERROR] No PropSpace tab found. Open Chrome and log in first.")
        return []

    ws_url = f"ws://localhost:9222/devtools/page/{tab_id}"
    results = []
    seen_refs = set()

    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        # Verify we're on PropSpace leads page
        current_url = await _eval(ws, "window.location.href", msg_id=10)
        if not current_url or "propspace" not in current_url.lower():
            print(f"[ERROR] Chrome is not on PropSpace. Current URL: {current_url}")
            print("        Please navigate to crm.propspace.com/leads/ and apply your filters.")
            return []
        if "login" in current_url.lower() or "sign" in current_url.lower():
            print("[ERROR] Not logged in to PropSpace. Please log in first.")
            return []

        print(f"[INFO] Reading from: {current_url}")
        if detail:
            print(f"[INFO] Detail mode ON - will open each lead panel for beds/budget (slower)")

        # Close any open panel before starting (Escape key)
        await _eval(ws, "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}))", msg_id=11)
        await asyncio.sleep(0.5)

        page_num = 0
        consecutive_empty = 0

        while True:
            page_num += 1
            await asyncio.sleep(1.5)  # Let table render after pagination click

            rows = await _extract_rows(ws)
            # Deduplicate across pages
            new_rows = [r for r in rows if r["ref"] not in seen_refs]
            for r in new_rows:
                seen_refs.add(r["ref"])

            print(f"[PAGE {page_num}] {len(rows)} rows found, {len(new_rows)} new leads")

            if not new_rows:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    print("[INFO] No new leads on consecutive pages — stopping.")
                    break
            else:
                consecutive_empty = 0
                # Detail mode: click each row's panel while still on this page
                if detail:
                    for j, lead in enumerate(new_rows):
                        print(f"  [detail {j+1}/{len(new_rows)}] {lead['ref']}", end=" ")
                        try:
                            req = await _get_lead_requirements(ws, lead["ref"], msg_id_base=200 + j * 3)
                            lead.update(req)
                            beds = req.get("beds_min", "?")
                            budget = req.get("budget_max", "?")
                            print(f"-> beds={beds}, budget={budget:,}" if isinstance(budget, int) else "-> no data")
                        except Exception as e:
                            print(f"-> warn: {e}")
                results.extend(new_rows)

            if max_pages and page_num >= max_pages:
                print(f"[INFO] Reached max_pages={max_pages}")
                break

            # Try next page
            has_next = await _go_next_page(ws)
            if not has_next:
                print("[INFO] Last page reached.")
                break

        print(f"\n[DONE] {len(results)} leads total.")
    return results


async def _extract_rows(ws):
    """Extract lead rows from the current page."""
    js = r"""
(function() {
    var rows = Array.from(document.querySelectorAll('tr'));
    var leadRows = rows.filter(function(r) { return r.innerHTML.indexOf('EDT-L-') >= 0; });
    return JSON.stringify(leadRows.map(function(r) {
        return Array.from(r.querySelectorAll('td')).map(function(c) {
            return c.innerText.trim().replace(/\s+/g, ' ');
        });
    }));
})()
"""
    raw = await _eval(ws, js, msg_id=50)
    if not raw:
        return []

    try:
        all_rows = json.loads(raw)
    except Exception:
        return []

    results = []
    for cells in all_rows:
        if len(cells) < 10:
            continue

        def get(i, default=""):
            return cells[i].strip() if i < len(cells) else default

        # [0]=chk [1]=act [2]=ref [3]=type [4]=status [5]=sub_status
        # [8]=first [9]=last [10]=phone [11]=cat [12]=emirate [13]=location
        # [14]=sub_loc [15]=source [16]=agent [17]=enq_date [23]=country_code [30]=contact_ref
        ref = get(2)
        if not ref.startswith("EDT-L-"):
            continue

        results.append({
            "ref": ref,
            "lead_type": get(3),
            "status": get(4),
            "sub_status": get(5),
            "first_name": get(8),
            "last_name": get(9),
            "phone": _normalise_phone(get(10)),
            "country_code": get(23),
            "category": get(11),
            "emirate": get(12),
            "location": get(13),
            "sub_location": get(14),
            "source": get(15),
            "agent": get(16),
            "enquiry_date": get(17),
            "contact_ref": get(30) if len(cells) > 30 else "",
        })

    return results


async def _get_lead_requirements(ws, ref, msg_id_base=200):
    """
    Click a lead row's detail panel (opens in-page, no navigation).
    Extracts Property Requirements: beds, budget, size from Property 1.
    Returns dict with beds_min, beds_max, budget_min, budget_max, size_min, size_max.
    """
    # Click the w=1700 detail link in the row for this ref
    open_js = f"""
(function() {{
    var rows = Array.from(document.querySelectorAll('tr'));
    var target = rows.find(function(r) {{ return r.innerHTML.indexOf({json.dumps(ref)}) >= 0; }});
    if (!target) return 'NOT_FOUND';
    var link = target.querySelector('a[href="#?w=1700"]');
    if (!link) {{
        var links = target.querySelectorAll('a[href]');
        link = links[3] || links[0];
    }}
    if (!link) return 'NO_LINK';
    link.click();
    return 'CLICKED';
}})()
"""
    result = await _eval(ws, open_js, msg_id=msg_id_base)
    if result != "CLICKED":
        return {}

    await asyncio.sleep(0.8)  # Wait for panel to render

    # Extract by parsing body text around the Property Requirements block
    extract_js = r"""
(function() {
    var bodyText = document.body.innerText;
    var start = bodyText.indexOf('Property Requirements');
    if (start < 0) return '{}';
    var block = bodyText.substring(start, start + 800);
    var lines = block.split('\n').map(function(l) { return l.trim(); }).filter(Boolean);
    var result = {};
    var keys = ['Price', 'Beds', 'BUA'];
    for (var i = 0; i < lines.length - 1; i++) {
        if (keys.indexOf(lines[i]) >= 0) {
            result[lines[i]] = lines[i + 1];
        }
    }
    return JSON.stringify(result);
})()
"""
    raw = await _eval(ws, extract_js, msg_id=msg_id_base + 1)

    # Close the panel
    close_js = r"""
(function() {
    var btns = Array.from(document.querySelectorAll('button, a')).filter(function(el) {
        var t = (el.innerText || '').trim();
        return t === '×' || t === 'Close' || t === 'close';
    });
    if (btns.length) { btns[btns.length - 1].click(); return 'btn'; }
    document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', keyCode:27, bubbles:true}));
    return 'esc';
})()
"""
    await _eval(ws, close_js, msg_id=msg_id_base + 2)
    await asyncio.sleep(0.3)

    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}

    out = {}

    # "2 Beds - 2 Beds" | "Studio - Studio"
    beds_raw = data.get("Beds", "")
    if beds_raw:
        nums = re.findall(r"\d+", beds_raw)
        if nums:
            out["beds_min"] = int(nums[0])
            out["beds_max"] = int(nums[-1])
        elif "studio" in beds_raw.lower():
            out["beds_min"] = 0
            out["beds_max"] = 0

    # "Price: 365,000 - 365,000"
    price_raw = data.get("Price", "")
    if price_raw:
        nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", price_raw)
                if len(n.replace(",", "")) >= 4]
        if len(nums) >= 2:
            out["budget_min"] = nums[0]
            out["budget_max"] = nums[1]
        elif len(nums) == 1:
            out["budget_min"] = nums[0]
            out["budget_max"] = nums[0]

    # "Size: 2652 - 2652"
    bua_raw = data.get("BUA", "")
    if bua_raw:
        nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", bua_raw)
                if int(n.replace(",", "")) > 0]
        if len(nums) >= 2:
            out["size_min"] = nums[0]
            out["size_max"] = nums[1]
        elif len(nums) == 1:
            out["size_min"] = nums[0]
            out["size_max"] = nums[0]

    return out


async def _go_next_page(ws):
    """Click the Next pagination button. Returns True if clicked."""
    js = r"""
(function() {
    var links = Array.from(document.querySelectorAll('a'));
    for (var i = 0; i < links.length; i++) {
        var t = links[i].innerText.trim().toLowerCase();
        if (t === 'next' || t === '>' || t === 'next »') {
            var cls = (links[i].className || '').toLowerCase();
            if (cls.indexOf('disabled') < 0) {
                links[i].click();
                return true;
            }
            return false;  // disabled = last page
        }
    }
    return false;
})()
"""
    return await _eval(ws, js, msg_id=60)


def _normalise_phone(phone):
    """Strip spaces/dashes, keep + prefix."""
    if not phone:
        return ""
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", phone)
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned.lstrip("+")
    return cleaned if len(cleaned) > 3 else ""


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "ref", "lead_type", "status", "sub_status",
    "first_name", "last_name", "phone", "country_code",
    "category", "emirate", "location", "sub_location",
    "source", "agent", "enquiry_date", "contact_ref",
    "beds_min", "beds_max", "budget_min", "budget_max", "size_min", "size_max",
]


def save_to_csv(leads, output_path=None, append=False):
    """Save leads list to CSV. Returns count of new rows written."""
    if not leads:
        print("[WARN] No leads to save.")
        return 0

    path = Path(output_path or OUTPUT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_refs = set()
    if append and path.exists():
        with open(path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                existing_refs.add(row.get("ref", ""))

    mode = "a" if append and path.exists() else "w"
    new_count = 0
    with open(path, mode, encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if mode == "w":
            writer.writeheader()
        for lead in leads:
            if lead["ref"] not in existing_refs:
                writer.writerow(lead)
                new_count += 1

    print(f"[SAVED] {new_count} new leads → {path}")
    return new_count
