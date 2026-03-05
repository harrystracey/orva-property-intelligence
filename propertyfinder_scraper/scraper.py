"""
PropertyFinder + Replit Permit Scraper (HYBRID MODE)
=====================================================
Collects DLD permit numbers from PropertyFinder rental listings, looks them up
on the Replit property-scraper app, and saves landlord/owner details to a CSV.

1. Run start_pf_chrome.ps1 to launch Chrome (PropertyFinder + Replit tabs).
2. Log in to the Replit app; search Palm Jumeirah / Rent on PropertyFinder.
3. Run this script; press Enter when ready.
4. Script collects listing URLs, visits each, extracts permit, submits to Replit, saves leads.

Usage:
  python propertyfinder_scraper/scraper.py --max-pages 5 --max-listings 50
  python propertyfinder_scraper/scraper.py --resume
"""

import asyncio
import argparse
import csv
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from playwright.async_api import async_playwright

# #region agent log
_SCRIPTER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTER_DIR.parent
_DBG = _PROJECT_ROOT / ".cursor" / "debug.log"
_DBG2 = _PROJECT_ROOT / "scraped_data" / "debug_pf_run.log"
_DBG3 = _SCRIPTER_DIR / "last_run.log"  # next to scraper.py so we always have a writable path
def _dlog(loc, msg, data=None, hyp=""):
    import json as _j
    line = _j.dumps({"timestamp": int(time.time()*1000), "location": loc, "message": msg, "data": data or {}, "hypothesisId": hyp}) + "\n"
    for p in (_DBG3, _DBG, _DBG2):  # DBG3 first: script dir is always writable when this file runs
        try:
            with open(p, "a", encoding="utf-8") as _f:
                _f.write(line)
                _f.flush()
        except Exception:
            pass
# Log once at import to confirm this file is the one running
_dlog("scraper.py:import", "module_loaded", {"cwd": str(Path.cwd()), "file": str(Path(__file__).resolve())}, "H0")
# Visible in console so we know this build is running when started from Streamlit
print("[PF] Scraper build 2026-02-debug loaded", flush=True)
print(f"[PF] Logs: {_DBG3} | {_DBG}", flush=True)
# #endregion

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"
HUMAN_DELAY = (3.0, 6.0)
REPLIT_RESULT_WAIT_TIMEOUT_MS = 30000
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRAPED_DATA = PROJECT_ROOT / "scraped_data"
OUTPUT_CSV = SCRAPED_DATA / "propertyfinder_scraped_leads.csv"
PROGRESS_FILE = SCRAPED_DATA / "pf_scraping_progress.json"
PERMITS_FILE = SCRAPED_DATA / "pf_seen_permits.json"

CSV_HEADERS = [
    "unit_number", "building_name", "zone", "size_sqm", "land_no",
    "owner_name", "phone", "property_value", "room_type", "permit_type",
    "listing_url", "listing_price", "listing_type", "furnished", "scraped_at",
]

# PropertyFinder: listing detail URLs contain this
PF_LISTING_PATH = "/plp/rent/"
# Replit app base URL to identify the tab
REPLIT_BASE = "property-scraper-towersdubai.replit.app"


def ensure_scraped_data_dir():
    SCRAPED_DATA.mkdir(parents=True, exist_ok=True)
    if not OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
            f.write(",".join(CSV_HEADERS) + "\n")


def load_already_scraped_urls() -> set:
    """Load listing_url values from CSV so we never re-scrape (avoids paid Replit lookups)."""
    urls = set()
    if not OUTPUT_CSV.exists():
        return urls
    try:
        with open(OUTPUT_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return urls
            try:
                idx = header.index("listing_url")
            except ValueError:
                return urls
            for row in reader:
                if len(row) > idx and row[idx].strip():
                    urls.add(row[idx].strip())
    except Exception:
        pass
    return urls


def load_already_scraped_properties() -> set:
    """Load (unit_number, building_name, owner_name) from CSV to prevent property duplicates."""
    properties = set()
    if not OUTPUT_CSV.exists():
        return properties
    try:
        with open(OUTPUT_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return properties
            try:
                unit_idx = header.index("unit_number")
                building_idx = header.index("building_name")
                owner_idx = header.index("owner_name")
            except ValueError:
                return properties
            for row in reader:
                if len(row) > max(unit_idx, building_idx, owner_idx):
                    unit = row[unit_idx].strip()
                    building = row[building_idx].strip()
                    owner = row[owner_idx].strip()
                    if unit and building and owner:
                        properties.add((unit, building, owner))
    except Exception:
        pass
    return properties


def load_seen_permits() -> set:
    """Load permit numbers we've already submitted to Replit (any previous run)."""
    if not PERMITS_FILE.exists():
        return set()
    try:
        with open(PERMITS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(str(p) for p in data if p)
    except Exception:
        return set()


def save_seen_permits(permits: set):
    SCRAPED_DATA.mkdir(parents=True, exist_ok=True)
    with open(PERMITS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(permits), f, indent=2)


class PropertyFinderScraper:
    def __init__(self, max_pages: int = 5, max_listings: int = 50, resume: bool = False, debug: bool = False):
        self.max_pages = max_pages
        self.max_listings = max_listings
        self.resume = resume
        self.debug = debug
        self.browser = None
        self.pf_page = None  # PropertyFinder tab
        self.replit_page = None  # Replit app tab
        self.processed_urls: set = set()
        self.already_scraped_urls: set = set()  # persistent: URLs already in CSV (skip to avoid paid lookups)
        self.already_scraped_properties: set = set()  # (unit, building, owner) tuples to prevent property duplicates
        self.seen_permits: set = set()  # permit numbers already submitted to Replit (skip costly re-lookups)
        self.saved_count = 0
        self.start_time = None
        self.listing_type = "sell"  # "rent" or "sell", set from PF tab URL at run start
        ensure_scraped_data_dir()

    async def connect_to_browser(self):
        """Connect to Chrome via CDP and identify PF vs Replit tabs."""
        print(f"[CONNECT] Connecting to Chrome on port {CDP_PORT}...")
        playwright = await async_playwright().start()
        self._playwright = playwright
        try:
            self.browser = await playwright.chromium.connect_over_cdp(CDP_URL)
            print("[OK] Connected to Chrome")
        except Exception as e:
            print(f"[ERROR] Could not connect: {e}")
            print(f"  Run: powershell -File propertyfinder_scraper/start_pf_chrome.ps1")
            raise

        contexts = self.browser.contexts
        if not contexts:
            print("[ERROR] No browser context found")
            raise RuntimeError("No context")
        pages = contexts[0].pages
        if not pages:
            print("[WARN] No tabs; open PropertyFinder and Replit app in Chrome")
            raise RuntimeError("No pages")

        for p in pages:
            url = p.url or ""
            if REPLIT_BASE in url:
                self.replit_page = p
            elif "propertyfinder" in url.lower():
                self.pf_page = p

        if not self.pf_page:
            self.pf_page = pages[0]
            print("[WARN] PropertyFinder tab not detected; using first tab")
        if not self.replit_page:
            self.replit_page = next((p for p in pages if p != self.pf_page), None)
            if not self.replit_page:
                self.replit_page = pages[0]
            print("[WARN] Replit tab not detected; ensure Replit app is open in another tab")
        print(f"  [OK] PF tab: {self.pf_page.url[:60]}...")
        print(f"  [OK] Replit tab: {self.replit_page.url[:60]}...")

    async def wait_for_user_ready(self):
        """Prompt user to confirm search and Replit login."""
        print()
        print("=" * 70)
        print("  YOUR TURN")
        print("=" * 70)
        print("  1. In the PropertyFinder tab: set location (e.g. Palm Jumeirah), Rent, filters.")
        print("  2. In the Replit tab: log in to property-scraper-towersdubai.replit.app")
        print("  3. Return to the PropertyFinder tab so search results are visible.")
        print("=" * 70)
        input("  >>> Press ENTER when ready to start scraping... ")
        print()
        if self.browser and self.browser.contexts:
            pages = self.browser.contexts[0].pages
            for p in pages:
                if REPLIT_BASE in (p.url or ""):
                    self.replit_page = p
                elif "propertyfinder" in (p.url or "").lower():
                    self.pf_page = p
        print(f"[OK] Starting from: {self.pf_page.url[:70]}...")
        # Derive listing type from PF tab URL: rent vs buy/sale
        pf_url = (self.pf_page.url or "").lower()
        if "/plp/rent/" in pf_url or "c=2" in pf_url or "&c=2" in pf_url:
            self.listing_type = "rent"
        else:
            self.listing_type = "sell"
        print(f"  [OK] Listing type: {self.listing_type} (from search)")

    def load_progress(self) -> Dict:
        """Load processed URLs and state from progress file."""
        if not self.resume or not PROGRESS_FILE.exists():
            return {"processed_urls": [], "total_saved": 0}
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception:
            return {"processed_urls": [], "total_saved": 0}

    def save_progress(self, processed_urls: List[str], total_saved: int):
        state = {
            "processed_urls": list(processed_urls),
            "total_saved": total_saved,
            "last_updated": datetime.now().isoformat(),
        }
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    async def collect_listing_urls(self) -> List[str]:
        """From current PropertyFinder search results page, collect all listing detail URLs."""
        page = self.pf_page
        await asyncio.sleep(random.uniform(1.5, 3.0))
        try:
            urls = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const out = [];
                    const seen = new Set();
                    for (const a of links) {
                        const href = (a.href || '').trim();
                        // Match any PLP page (rent OR buy/sale) with .html extension
                        if (href.indexOf('/plp/') !== -1 && href.indexOf('.html') !== -1 && !seen.has(href)) {
                            seen.add(href);
                            out.push(href);
                        }
                    }
                    return out;
                }
            """)
            return list(urls) if isinstance(urls, list) else []
        except Exception as e:
            print(f"  [WARN] collect_listing_urls failed: {e}")
            return []

    async def extract_permit_number(self) -> Optional[str]:
        """Extract DLD permit number from __NEXT_DATA__ JSON (primary) or visible DOM (fallback)."""
        page = self.pf_page

        def valid(s):
            return s and str(s).strip().isdigit() and len(str(s).strip()) >= 7

        # ── Strategy 1 (PRIMARY): Parse __NEXT_DATA__ JSON ──
        # PropertyFinder is a Next.js app. The DLD permit lives at:
        #   regulatory_details[] -> {id:"regulatory_validation_url", label.en:"DLD Permit Number",
        #     values.primary.value.localized_value.en: "THE_NUMBER"}
        # Also: rera.permit_validation_url contains a URL with the number embedded.
        # The permit is displayed as a QR code (display_format:"qr"), NOT as text in the DOM.
        permit_from_json = await page.evaluate("""
            () => {
                try {
                    const nd = document.getElementById('__NEXT_DATA__');
                    if (!nd) return {found: false, reason: 'no __NEXT_DATA__'};
                    const data = JSON.parse(nd.textContent);
                    const prop = data?.props?.pageProps?.propertyResult?.property;
                    if (!prop) return {found: false, reason: 'no property object'};

                    const out = {found: false};

                    // Strategy 1: prop.rera.number — the actual DLD/RERA permit number
                    const reraNum = prop?.rera?.number;
                    out.rera_number = reraNum || null;
                    if (reraNum && /^[0-9]{7,}$/.test(String(reraNum).trim())) {
                        out.found = true;
                        out.permit = String(reraNum).trim();
                        out.method = 'rera_number';
                    }

                    // Strategy 2: regulatory_details → DLD Permit entry → direct number value
                    if (!out.found) {
                        const regDetails = prop.regulatory_details || [];
                        for (const rd of regDetails) {
                            const labelEn = rd?.label?.en || rd?.label || '';
                            if (typeof labelEn === 'string' && labelEn.includes('DLD Permit')) {
                                const val = rd?.values?.primary?.value?.localized_value?.en
                                         || rd?.values?.primary?.value?.localized_value?.ar;
                                if (val && /^[0-9]{7,}$/.test(String(val).trim())) {
                                    out.found = true;
                                    out.permit = String(val).trim();
                                    out.method = 'regulatory_details';
                                }
                                break;
                            }
                        }
                    }

                    return out;
                } catch(e) {
                    return {found: false, reason: e.message};
                }
            }
        """)
        if permit_from_json and permit_from_json.get("found"):
            permit_val = permit_from_json.get("permit", "")
            method = permit_from_json.get("method", "")
            if valid(permit_val):
                print(f"  [OK] Permit extracted ({method}): {permit_val}")
                return str(permit_val).strip()

        # ── Strategy 2 (FALLBACK): DOM search excluding <script> tags ──
        # Use querySelectorAll to find visible elements only, skipping <script>
        permit_from_dom = await page.evaluate("""
            () => {
                // Find all visible elements containing 'DLD Permit Number' text
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT, {
                        acceptNode: (node) => {
                            // Skip script/style tags
                            const p = node.parentElement;
                            if (!p || p.tagName === 'SCRIPT' || p.tagName === 'STYLE' || p.tagName === 'NOSCRIPT') 
                                return NodeFilter.FILTER_REJECT;
                            if (node.textContent.includes('DLD Permit Number'))
                                return NodeFilter.FILTER_ACCEPT;
                            return NodeFilter.FILTER_SKIP;
                        }
                    }
                );
                const labelNode = walker.nextNode();
                if (!labelNode) return {found: false, reason: 'no visible DLD Permit Number text'};

                const labelEl = labelNode.parentElement;
                const out = {found: false, label_tag: labelEl.tagName, label_text: labelEl.textContent.substring(0, 100)};

                // Check immediate next sibling of label element
                if (labelEl.nextElementSibling) {
                    const t = labelEl.nextElementSibling.textContent.trim();
                    out.next_sib = t.substring(0, 50);
                    if (/^[0-9]{7,}$/.test(t)) { out.found = true; out.value = t; return out; }
                }
                // Check parent's next sibling
                const parent = labelEl.parentElement;
                if (parent && parent.nextElementSibling) {
                    const t = parent.nextElementSibling.textContent.trim();
                    out.parent_next_sib = t.substring(0, 50);
                    if (/^[0-9]{7,}$/.test(t)) { out.found = true; out.value = t; return out; }
                }
                // Check closest div's next sibling
                const div = labelEl.closest('div');
                if (div && div.nextElementSibling) {
                    const t = div.nextElementSibling.textContent.trim();
                    out.div_next_sib = t.substring(0, 50);
                    if (/^[0-9]{7,}$/.test(t)) { out.found = true; out.value = t; return out; }
                }
                // Walk up to grandparent and search for any number
                const gp = parent ? parent.parentElement : null;
                if (gp) {
                    const text = gp.innerText || '';
                    out.gp_text_snippet = text.substring(0, 200);
                    const idx = text.indexOf('DLD Permit');
                    if (idx !== -1) {
                        const slice = text.slice(idx, idx + 200);
                        const nums = slice.match(/[0-9]{7,}/g);
                        if (nums) {
                            for (const n of nums) {
                                if (n.length >= 10 && n.length <= 12 && n.startsWith('7')) {
                                    out.found = true; out.value = n; return out;
                                }
                            }
                            out.found = true; out.value = nums[0]; return out;
                        }
                    }
                }
                return out;
            }
        """)
        if permit_from_dom and permit_from_dom.get("found") and valid(permit_from_dom.get("value")):
            val = str(permit_from_dom["value"]).strip()
            print(f"  [OK] Permit extracted (DOM): {val}")
            return val

        return None

    async def extract_listing_price(self) -> Optional[str]:
        """Get main listing price from current PF detail page (e.g. AED 7,499,999 or 105,000 AED/year)."""
        try:
            # Strategy 1: __NEXT_DATA__ (PropertyFinder is Next.js; price is in JSON)
            result = await self.pf_page.evaluate("""
                () => {
                    try {
                        const nd = document.getElementById('__NEXT_DATA__');
                        if (!nd) return null;
                        const data = JSON.parse(nd.textContent);
                        const prop = data?.props?.pageProps?.propertyResult?.property;
                        if (!prop) return null;
                        const price = prop?.price;
                        if (price == null) return null;
                        const amount = price?.amount ?? price?.value ?? price;
                        const period = price?.period || (price?.frequency ? ' /' + price.frequency : '');
                        if (amount != null) {
                            const num = typeof amount === 'number' ? String(amount).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ',') : String(amount);
                            const s = (num + ' AED' + (period || '')).trim();
                            return s.length <= 60 ? s : s.slice(0, 60);
                        }
                        const raw = price?.raw || price?.formatted;
                        if (raw && typeof raw === 'string') return raw.length <= 60 ? raw : raw.slice(0, 60);
                        return null;
                    } catch (e) { return null; }
                }
            """)
            if result and isinstance(result, str) and result.strip():
                return result.strip()
            # Strategy 2: body text regex (fallback) - allow comma or semicolon as thousands sep (Property Monitor / PF)
            result = await self.pf_page.evaluate("""
                () => {
                    const body = document.body.innerText || '';
                    const re = /AED\\s*([0-9,;]+)(\\s*\\/\\s*(year|month))?/gi;
                    let m;
                    while ((m = re.exec(body)) !== null) {
                        const before = body.slice(Math.max(0, m.index - 40), m.index).toLowerCase();
                        if (before.includes('from just') || before.includes('just ') || before.includes('from ')) continue;
                        let num = (m[1] || '').replace(/;/g, ',').replace(/,/g, '');
                        if (num.length > 0) num = parseInt(num, 10).toLocaleString('en-US');
                        const period = m[3] ? ' /' + m[3] : '';
                        const s = (num + ' AED' + period).trim();
                        return s.length <= 60 ? s : s.slice(0, 60);
                    }
                    return null;
                }
            """)
            if result and isinstance(result, str) and result.strip():
                return result.strip()
            # Strategy 3: any element with price-like text (rentals: "350,000 AED /year" or "350;000 AED/year")
            result = await self.pf_page.evaluate("""
                () => {
                    const walk = (el) => {
                        if (!el || el.children.length > 4) return null;
                        const t = (el.innerText || '').trim();
                        const match = t.match(/\\b([0-9][0-9,;]*)\\s*AED\\s*(\\/\\s*(?:year|month))?/i);
                        if (match && match[1]) {
                            let n = match[1].replace(/[;,]/g, '');
                            if (n.length >= 3 && parseInt(n, 10) > 0) {
                                n = parseInt(n, 10).toLocaleString('en-US');
                                return n + ' AED' + (match[2] ? ' ' + match[2].trim() : '');
                            }
                        }
                        for (const c of el.children) { const r = walk(c); if (r) return r; }
                        return null;
                    };
                    return walk(document.body);
                }
            """)
            if result and isinstance(result, str) and result.strip():
                return result.strip()
        except Exception:
            pass
        return None

    async def extract_bedrooms_from_pf_page(self) -> str:
        """Extract bedroom/room spec from PF detail page (e.g. '6 Bedrooms + Maid', '2 Bedrooms'). Non-negotiable: PF shows this in the specs."""
        try:
            result = await self.pf_page.evaluate("""
                () => {
                    try {
                        const nd = document.getElementById('__NEXT_DATA__');
                        if (nd) {
                            const data = JSON.parse(nd.textContent);
                            const prop = data?.props?.pageProps?.propertyResult?.property;
                            if (prop) {
                                const beds = prop.bedrooms ?? prop.rooms ?? prop.room_count;
                                if (beds != null) {
                                    const b = typeof beds === 'number' ? beds : parseInt(beds, 10);
                                    if (!isNaN(b)) return b + ' Bedrooms';
                                }
                                const rt = prop.room_type || prop.roomType || prop.property_type;
                                if (rt && typeof rt === 'string' && /\\d+\\s*bed/i.test(rt)) return rt.trim().slice(0, 80);
                            }
                        }
                    } catch (e) {}
                    const body = document.body.innerText || '';
                    const m = body.match(/\\b(\\d+)\\s*Bedrooms?(?:\\s*\\+\\s*Maid)?\\b/i);
                    if (m && m[1]) return m[0].trim();
                    const m2 = body.match(/\\b(Studio|\\d+)\\s*(?:Beds?|BR|Bedrooms?)\\b/i);
                    if (m2) return m2[0].trim();
                    return '';
                }
            """)
            if result and isinstance(result, str) and result.strip():
                return result.strip()
        except Exception:
            pass
        return ""

    async def extract_furnished(self) -> str:
        """Detect Furnished/Unfurnished from current PropertyFinder listing detail page. Returns 'Furnished', 'Unfurnished', or ''."""
        try:
            result = await self.pf_page.evaluate("""
                () => {
                    const body = (document.body && document.body.innerText) ? document.body.innerText : '';
                    const lower = body.toLowerCase();
                    // Prefer explicit "Furnished" / "Unfurnished" in features or description (word-boundary style)
                    if (/\\bunfurnished\\b/i.test(body)) return 'Unfurnished';
                    if (/\\bfurnished\\b/i.test(body)) return 'Furnished';
                    return '';
                }
            """)
            if result and isinstance(result, str) and result.strip():
                return result.strip()
        except Exception:
            pass
        return ""

    async def submit_permit_to_replit(self, permit_number: str) -> bool:
        """Switch to Replit tab, enter permit number, click Extract Data, wait for result box."""
        page = self.replit_page
        await page.bring_to_front()
        await asyncio.sleep(random.uniform(0.5, 1.0))

        try:
            # Input: placeholder or name often contains "Permit" or "permit"
            input_el = page.locator('input[placeholder*="ermit"], input[placeholder*="Permit"], input[type="text"]').first
            await input_el.fill("")
            await asyncio.sleep(0.2)
            await input_el.fill(permit_number)
            await asyncio.sleep(1.0)

            # Button "Extract Data"
            btn = page.locator('button:has-text("Extract Data")').first
            await btn.click()
            # Wait for green result box (Permit Lookup Result)
            await page.locator('text=Permit Lookup Result').wait_for(state="visible", timeout=REPLIT_RESULT_WAIT_TIMEOUT_MS)
            await asyncio.sleep(1.0)
            return True
        except Exception as e:
            print(f"  [WARN] Replit submit failed: {e}")
            return False

    async def extract_owner_data(self) -> Optional[Dict]:
        """Read Permit Lookup Result box on Replit page. Returns dict with keys matching CSV_HEADERS (partial)."""
        page = self.replit_page
        try:
            data = await page.evaluate("""
                () => {
                    const box = document.querySelector('[class*="border-green"], .alert-success, [class*="success"]')
                        || Array.from(document.querySelectorAll('div')).find(d => d.innerText.includes('Permit Lookup Result'));
                    if (!box) return null;
                    const text = box.innerText || '';
                    const obj = {};
                    const pairs = [
                        ['Permit', 'permit_number'], ['Unit', 'unit_number'], ['Building', 'building_name'],
                        ['Zone', 'zone'], ['Size', 'size_sqm'], ['Land No', 'land_no'],
                        ['Name', 'owner_name'], ['Phone', 'phone'],
                        ['Property Value', 'property_value'], ['Room Type', 'room_type'], ['Permit Type', 'permit_type']
                    ];
                    for (const [label, key] of pairs) {
                        const re = new RegExp(label + '[\\\\s:]*([^\\\\n]+)', 'i');
                        const m = text.match(re);
                        obj[key] = m ? m[1].trim() : '';
                    }
                    return obj;
                }
            """)
            if data and isinstance(data, dict):
                return data
        except Exception as e:
            print(f"  [WARN] extract_owner_data: {e}")
        return None

    def save_to_csv(self, row: Dict):
        """Append one row to propertyfinder_scraped_leads.csv. Flush so app can see new rows without restart."""
        ensure_scraped_data_dir()
        values = [str(row.get(h, "")).replace(",", ";") for h in CSV_HEADERS]
        line = ",".join(values) + "\n"
        with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
        self.saved_count += 1

    async def check_pagination(self) -> bool:
        """Check if PropertyFinder has a Next page button."""
        await self.pf_page.bring_to_front()
        next_selectors = [
            'a:has-text("Next")',
            'button:has-text("Next")',
            'a[aria-label*="next" i]',
            '[class*="pagination"] a:not([disabled])',
        ]
        for sel in next_selectors:
            try:
                el = self.pf_page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    return True
            except Exception:
                continue
        return False

    async def go_to_next_page(self) -> bool:
        """Click Next on PropertyFinder search results."""
        next_selectors = [
            'a:has-text("Next")',
            'button:has-text("Next")',
            'a[aria-label*="next" i]',
        ]
        for sel in next_selectors:
            try:
                btn = self.pf_page.locator(sel).first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
                    await asyncio.sleep(random.uniform(*HUMAN_DELAY))
                    try:
                        await self.pf_page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        await asyncio.sleep(3)
                    return True
            except Exception:
                continue
        return False

    async def run(self):
        self.start_time = time.time()
        # #region agent log
        _dlog("scraper.py:run", "run_started", {"max_pages": self.max_pages, "max_listings": self.max_listings}, "H0")
        # #endregion
        print()
        print("=" * 70)
        print("  PROPERTYFINDER + REPLIT PERMIT SCRAPER")
        print("=" * 70)

        await self.connect_to_browser()
        # #region agent log
        _dlog("scraper.py:run", "after connect", {"pf_url": (self.pf_page.url if self.pf_page else None)[:80]}, "H1")
        # #endregion
        await self.wait_for_user_ready()
        # #region agent log
        _dlog("scraper.py:run", "user_ready", {}, "H3")
        # #endregion

        # Load URLs already in CSV from any previous run — never re-scrape (saves paid Replit lookups)
        self.already_scraped_urls = load_already_scraped_urls()
        if self.already_scraped_urls:
            print(f"[DEDUP] {len(self.already_scraped_urls)} listing URLs already in CSV — will skip (no cost)")
        # Load properties already in CSV to prevent duplicates (same unit+building+owner)
        self.already_scraped_properties = load_already_scraped_properties()
        if self.already_scraped_properties:
            print(f"[DEDUP] {len(self.already_scraped_properties)} unique properties already in CSV")
        # Load permit numbers already submitted to Replit (avoids repeat paid lookups)
        self.seen_permits = load_seen_permits()
        if self.seen_permits:
            print(f"[DEDUP] {len(self.seen_permits)} permit numbers already looked up — will skip Replit")

        if self.resume:
            prog = self.load_progress()
            self.processed_urls = set(prog.get("processed_urls", []))
            self.saved_count = prog.get("total_saved", 0)
            print(f"[RESUME] Skipping {len(self.processed_urls)} already-processed URLs")

        total_processed = 0
        page_num = 1

        while page_num <= self.max_pages:
            await self.pf_page.bring_to_front()
            # Remember search results URL so we can return here after processing listings (pagination is on this page)
            search_results_url = self.pf_page.url
            urls = await self.collect_listing_urls()
            # If on search page with 0 URLs, wait for results to load and retry once
            if not urls and "search" in (self.pf_page.url or ""):
                print("  [WAIT] No listing links yet (search page?). Waiting 5s for results to load...")
                await asyncio.sleep(5.0)
                urls = await self.collect_listing_urls()
            if not urls and "search" in (self.pf_page.url or ""):
                print("  [TIP] Still no listings. In the PropertyFinder tab, run your search (e.g. Palm Jumeirah, Rent)")
                print("        so the list of properties is visible, then start the scraper again.")
            # Exclude URLs already in CSV (any run) and this run's processed — avoids paid Replit lookups
            to_process = [
                u for u in urls
                if u not in self.processed_urls and u not in self.already_scraped_urls
            ][: self.max_listings - total_processed]
            # #region agent log
            _dlog("scraper.py:run", "urls_collected", {"page": page_num, "urls_count": len(urls), "to_process": len(to_process)}, "H2")
            # #endregion
            skipped = len([u for u in urls if u in self.already_scraped_urls])
            if skipped:
                print(f"  [PAGE {page_num}] Skipping {skipped} already scraped (in CSV)")
            if not to_process and urls:
                print(f"  [PAGE {page_num}] All {len(urls)} listings already processed or in CSV")
            elif not to_process:
                print(f"  [PAGE {page_num}] No listing URLs found (have search results open in the PropertyFinder tab?)")
            else:
                print(f"  [PAGE {page_num}] Processing {len(to_process)} listings (of {len(urls)} on page)")

            for url in to_process:
                if total_processed >= self.max_listings:
                    print(f"[LIMIT] Reached max_listings={self.max_listings}")
                    break
                try:
                    await self.pf_page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(random.uniform(*HUMAN_DELAY))
                    listing_price = await self.extract_listing_price()
                    furnished = await self.extract_furnished()
                    bedrooms_pf = await self.extract_bedrooms_from_pf_page()
                    permit = await self.extract_permit_number()
                    # #region agent log
                    _dlog("scraper.py:run", "permit_result", {"permit": permit, "url_tail": url[-40:]}, "H4,H5")
                    # #endregion
                    if not permit:
                        print(f"  [SKIP] No permit: {url[-50:]}")
                        self.processed_urls.add(url)
                        self.save_progress(list(self.processed_urls), self.saved_count)
                        total_processed += 1
                        continue
                    if permit in self.seen_permits:
                        print(f"  [SKIP] Permit {permit} already looked up — skipping Replit")
                        self.processed_urls.add(url)
                        self.save_progress(list(self.processed_urls), self.saved_count)
                        total_processed += 1
                        continue
                    ok = await self.submit_permit_to_replit(permit)
                    self.seen_permits.add(permit)
                    save_seen_permits(self.seen_permits)
                    # #region agent log
                    _dlog("scraper.py:run", "replit_result", {"ok": ok, "permit": permit}, "H4,H5")
                    # #endregion
                    if not ok:
                        print(f"  [SKIP] Replit lookup failed for permit {permit}")
                        self.processed_urls.add(url)
                        self.save_progress(list(self.processed_urls), self.saved_count)
                        total_processed += 1
                        continue
                    row = await self.extract_owner_data()
                    if not row:
                        print(f"  [SKIP] No owner data for permit {permit}")
                    else:
                        # VALIDATION: Check phone number
                        phone = (row.get("phone") or "").strip()
                        if not phone:
                            print(f"  [SKIP] No phone number: {row.get('building_name', '')} {row.get('unit_number', '')}")
                            self.processed_urls.add(url)
                            self.save_progress(list(self.processed_urls), self.saved_count)
                            total_processed += 1
                            continue
                        # VALIDATION: Check for duplicate property
                        unit = row.get("unit_number", "").strip()
                        building = row.get("building_name", "").strip()
                        owner = row.get("owner_name", "").strip()
                        property_key = (unit, building, owner)
                        if property_key in self.already_scraped_properties:
                            print(f"  [SKIP] Duplicate property: {building} {unit} ({owner})")
                            self.processed_urls.add(url)
                            self.save_progress(list(self.processed_urls), self.saved_count)
                            total_processed += 1
                            continue
                        # All validations passed - save (bedrooms from PF page is non-negotiable when present)
                        if bedrooms_pf:
                            row["room_type"] = bedrooms_pf
                        row["listing_url"] = url
                        row["listing_price"] = listing_price or ""
                        row["listing_type"] = self.listing_type
                        row["furnished"] = furnished or ""
                        row["scraped_at"] = datetime.now().isoformat()
                        for h in CSV_HEADERS:
                            if h not in row:
                                row[h] = ""
                        self.save_to_csv(row)
                        self.already_scraped_properties.add(property_key)
                        self.already_scraped_urls.add(url)
                        # #region agent log
                        _dlog("scraper.py:run", "saved", {"owner": row.get("owner_name", "")[:30]}, "H5")
                        # #endregion
                        print(f"  [SAVED] {owner} | {building} | {unit}")
                    self.processed_urls.add(url)
                    self.save_progress(list(self.processed_urls), self.saved_count)
                    total_processed += 1
                except Exception as e:
                    # #region agent log
                    _dlog("scraper.py:run", "listing_error", {"url_tail": url[-40:], "err": str(e)[:100]}, "H4")
                    # #endregion
                    print(f"  [ERROR] {url[-40:]}: {e}")
                    continue

            if total_processed >= self.max_listings:
                break
            if page_num >= self.max_pages:
                print(f"[LIMIT] Reached max_pages={self.max_pages}")
                break
            # Return to search results page so Next button is visible (we were on last listing detail page)
            try:
                await self.pf_page.goto(search_results_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2.0)
            except Exception as e:
                print(f"[WARN] Could not return to search page for pagination: {e}")
                break
            has_next = await self.check_pagination()
            if not has_next:
                print("[DONE] No more pages")
                break
            success = await self.go_to_next_page()
            if not success:
                break
            page_num += 1

        elapsed = time.time() - self.start_time
        print()
        print("=" * 70)
        print("  SCRAPE SUMMARY")
        print("=" * 70)
        print(f"  Listings processed: {total_processed}")
        print(f"  Leads saved:        {self.saved_count}")
        print(f"  Output:             {OUTPUT_CSV}")
        print(f"  Time:               {elapsed:.1f}s")
        print("=" * 70)
        # #region agent log
        _dlog("scraper.py:run", "run_end", {"total_processed": total_processed, "saved_count": self.saved_count, "elapsed": round(elapsed, 1)}, "H1,H2,H4,H5")
        # #endregion


def main():
    parser = argparse.ArgumentParser(description="PropertyFinder + Replit permit scraper")
    parser.add_argument("--max-pages", type=int, default=5, help="Max search result pages (default 5)")
    parser.add_argument("--max-listings", type=int, default=50, help="Max listings to process (default 50)")
    parser.add_argument("--resume", action="store_true", help="Resume from progress file")
    parser.add_argument("--debug", action="store_true", help="Screenshot + HTML dump when extracting permit")
    args = parser.parse_args()

    scraper = PropertyFinderScraper(
        max_pages=args.max_pages,
        max_listings=args.max_listings,
        resume=args.resume,
        debug=args.debug,
    )
    asyncio.run(scraper.run())


if __name__ == "__main__":
    main()
