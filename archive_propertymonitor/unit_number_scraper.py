"""
Property Monitor Unit Number Scraper - HYBRID MODE
===================================================
You log in manually and pass Cloudflare.
The script connects to YOUR browser and scrapes all pages automatically.

How it works:
1. Script launches Chrome with remote debugging enabled (port 9222)
2. YOU log in, pass Cloudflare, navigate to search results
3. YOU apply filters (building, date range, per page = 250)
4. Press Enter in the terminal when ready
5. Script connects to your browser and extracts ALL pages automatically
"""

import asyncio
import hashlib
from playwright.async_api import async_playwright, Page, Browser
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import random
from typing import List, Dict, Optional
import json
import os
import subprocess
import sys
import io


# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass  # Already wrapped or not a real console


# Chrome paths to try on Windows
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"

# Human-like delays between automated actions (seconds)
HUMAN_ACTION_DELAY = (2.0, 4.0)


def find_chrome() -> str:
    """Find Chrome executable on this machine."""
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None


def launch_chrome_with_debugging():
    """
    Launch Chrome with remote debugging enabled.
    This lets Playwright connect to the user's real browser session.
    """
    chrome_path = find_chrome()
    if not chrome_path:
        print("[ERROR] Chrome not found! Looked in:")
        for p in CHROME_PATHS:
            print(f"  - {p}")
        print("\nPlease install Chrome or provide the path.")
        sys.exit(1)

    print(f"[CHROME] Found at: {chrome_path}")
    print(f"[CHROME] Launching with remote debugging on port {CDP_PORT}...")

    # Create a separate user data dir so it doesn't conflict with existing Chrome
    debug_profile = Path("scraped_data/chrome_debug_profile")
    debug_profile.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={debug_profile.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        "https://www.propertymonitor.ae/"
    ]

    # Launch Chrome as a detached subprocess (won't block our script)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
    )

    print(f"[OK] Chrome launched (PID: {process.pid})")
    return process


class UnitNumberScraper:
    """
    Hybrid scraper: connects to user's already-open Chrome via CDP.
    User handles login + Cloudflare manually, script handles data extraction.
    """

    def __init__(self):
        self.browser = None
        self.page: Optional[Page] = None
        self.scraped_data: List[Dict] = []
        self.already_scraped_keys: set = set()
        self.progress_file = Path("scraped_data/scraping_progress.json")
        self.output_file = Path("scraped_data/unit_numbers_palm_jumeirah.csv")

        Path("scraped_data").mkdir(exist_ok=True)
        self._load_existing_csv()

    @staticmethod
    def _row_to_key(row: Dict) -> str:
        """
        Stable key for dedup: prefer Unit + Building/Property + Date columns (case-insensitive),
        else hash of all non-metadata values.
        """
        data = {k: (v or "").strip() for k, v in row.items() if not k.startswith("_")}
        if not data:
            data = dict(row)

        def find_col(*candidates: str) -> Optional[str]:
            keys_lower = {k.lower(): k for k in data}
            for c in candidates:
                for k in keys_lower:
                    if c in k or (c.replace(" ", "") in k.replace(" ", "")):
                        return data.get(keys_lower[k], "")
            return None

        unit = find_col("unit", "unit number")
        building = find_col("building", "property", "project", "tower")
        date = find_col("date", "registration", "completion", "transfer")
        if unit is not None and building is not None:
            parts = [str(building), str(unit)]
            if date is not None:
                parts.append(str(date))
            return "|".join(parts)

        # Fallback: hash of sorted key=value pairs (stable)
        h = hashlib.sha256()
        for k in sorted(data):
            h.update(f"{k}={data[k]}".encode("utf-8", errors="replace"))
        return h.hexdigest()

    def _load_existing_csv(self):
        """Load existing output CSV into already_scraped_keys and scraped_data (resume behaviour)."""
        if not self.output_file.exists():
            return
        try:
            df = pd.read_csv(self.output_file, encoding="utf-8")
            if df.empty:
                return
            records = df.to_dict("records")
            for row in records:
                key = self._row_to_key(row)
                self.already_scraped_keys.add(key)
                self.scraped_data.append(row)
            print(f"[DEDUP] Loaded {len(self.scraped_data)} existing records — will skip already-scraped rows")
        except Exception as e:
            print(f"[WARN] Could not load existing CSV: {e}")

    async def connect_to_browser(self):
        """Connect to already-running Chrome via CDP."""
        print(f"[CONNECT] Connecting to Chrome on port {CDP_PORT}...")

        playwright = await async_playwright().start()

        try:
            self.browser = await playwright.chromium.connect_over_cdp(CDP_URL)
            print("[OK] Connected to Chrome")

            # Get existing pages/tabs
            contexts = self.browser.contexts
            if contexts:
                pages = contexts[0].pages
                if pages:
                    # Use the last active tab (most likely the Property Monitor one)
                    self.page = pages[-1]
                    print(f"[OK] Attached to tab: {self.page.url}")
                    return

            # Fallback: no existing tab found
            print("[WARN] No existing tab found, creating new one...")
            context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
            self.page = await context.new_page()

        except Exception as e:
            print(f"[ERROR] Could not connect to Chrome: {e}")
            print(f"  Make sure Chrome is running with --remote-debugging-port={CDP_PORT}")
            raise

    async def wait_for_user_ready(self):
        """
        Wait for the user to confirm they've done the manual steps:
        - Logged in
        - Passed Cloudflare
        - Applied filters
        - Results are showing on screen
        """
        print()
        print("=" * 70)
        print("  YOUR TURN - DO THESE STEPS IN CHROME:")
        print("=" * 70)
        print()
        print("  1. Log in to Property Monitor")
        print("  2. Pass the Cloudflare challenge")
        print("  3. Navigate to the search/transactions page")
        print("  4. Search for your building (e.g. 'The Fairmont Palm Residences')")
        print("  5. Set data points to 'Title Deed' and 'Oqood' only")
        print("  6. Set date range to 'All Historical Data'")
        print("  7. Set per page to 250")
        print("  8. Make sure the results TABLE is visible on screen")
        print()
        print("=" * 70)
        input("  >>> Press ENTER here when the table is showing... ")
        print()

        # Re-attach to the current tab (user may have navigated)
        if self.browser and self.browser.contexts:
            pages = self.browser.contexts[0].pages
            if pages:
                self.page = pages[-1]
                print(f"[OK] Attached to: {self.page.url}")

    async def extract_table_data(self) -> List[Dict]:
        """
        Extract ALL transaction data from the currently visible table.
        Uses JavaScript to read every row and column, including unit numbers.
        """
        print("[TABLE] Extracting data from current page...")

        try:
            # Give page a moment to fully render
            await asyncio.sleep(2)

            # Extract using JavaScript - handles any table structure
            table_data = await self.page.evaluate("""
                () => {
                    // Try multiple table selectors
                    const table = document.querySelector('table')
                        || document.querySelector('div[role="table"]')
                        || document.querySelector('.data-table')
                        || document.querySelector('.dataTable');
                    
                    if (!table) return { error: 'No table found on page', tables: document.querySelectorAll('table').length };
                    
                    const rows = [];
                    
                    // Get ALL header cells
                    const headers = [];
                    const headerRow = table.querySelector('thead tr') || table.querySelector('tr:first-child');
                    if (headerRow) {
                        headerRow.querySelectorAll('th, td').forEach(cell => {
                            headers.push(cell.innerText.trim().replace(/\\n/g, ' '));
                        });
                    }
                    
                    // Get ALL data rows
                    const allRows = table.querySelectorAll('tbody tr');
                    const dataRows = allRows.length > 0 ? allRows : table.querySelectorAll('tr:not(:first-child)');
                    
                    dataRows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length === 0) return;
                        
                        const rowData = {};
                        cells.forEach((cell, index) => {
                            const header = headers[index] || `column_${index}`;
                            rowData[header] = cell.innerText.trim();
                        });
                        
                        // Only add rows that have actual data
                        if (Object.values(rowData).some(v => v && v.length > 0)) {
                            rows.push(rowData);
                        }
                    });
                    
                    return { 
                        success: true,
                        headers: headers,
                        row_count: rows.length,
                        rows: rows
                    };
                }
            """)

            # Handle errors
            if isinstance(table_data, dict) and 'error' in table_data:
                print(f"  [WARN] {table_data['error']}")
                print(f"  Tables on page: {table_data.get('tables', 'unknown')}")

                # Try alternative: maybe data is in divs, not a table
                print("  [RETRY] Trying alternative extraction...")
                table_data = await self._extract_alternative()
                if not table_data:
                    return []

            # Process successful extraction
            if isinstance(table_data, dict) and table_data.get('success'):
                rows = table_data['rows']
                headers = table_data['headers']

                print(f"  [OK] Found {table_data['row_count']} rows")
                print(f"  [OK] Columns: {', '.join(headers[:8])}{'...' if len(headers) > 8 else ''}")

                # Add metadata to each row
                for row in rows:
                    row['_scraped_at'] = datetime.now().isoformat()
                    row['_source'] = 'Property Monitor'
                    row['_page_url'] = self.page.url

                return rows

            return []

        except Exception as e:
            print(f"  [ERROR] Extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _extract_alternative(self) -> List[Dict]:
        """Fallback extraction for non-standard table layouts."""
        try:
            data = await self.page.evaluate("""
                () => {
                    // Sometimes Property Monitor uses DataTables or custom grids
                    // Try to find any structured data container
                    
                    // Method 1: DataTables
                    if (typeof $ !== 'undefined' && $.fn.DataTable) {
                        const dt = $('table').DataTable();
                        const data = dt.rows().data().toArray();
                        const headers = dt.columns().header().toArray().map(h => h.innerText.trim());
                        return {
                            success: true,
                            headers: headers,
                            row_count: data.length,
                            rows: data.map(row => {
                                const obj = {};
                                headers.forEach((h, i) => obj[h] = String(row[i] || ''));
                                return obj;
                            })
                        };
                    }
                    
                    // Method 2: Look for repeated row-like elements
                    const containers = document.querySelectorAll('[class*="row"], [class*="record"], [class*="item"]');
                    if (containers.length > 5) {
                        return { 
                            success: false, 
                            message: 'Found row-like elements but cannot determine structure',
                            count: containers.length 
                        };
                    }
                    
                    return { success: false, message: 'No structured data found' };
                }
            """)
            return data if isinstance(data, list) else None
        except:
            return None

    async def check_pagination(self) -> bool:
        """Check if there's a Next page button that's clickable."""
        try:
            # Try multiple "next" button patterns
            next_selectors = [
                'a:has-text("Next")',
                'button:has-text("Next")',
                'a.next',
                '.paginate_button.next:not(.disabled)',
                'li.next:not(.disabled) a',
                'a[aria-label*="next" i]',
                'button[aria-label*="next" i]',
                '.pagination .next:not(.disabled)',
            ]

            for selector in next_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        # Check it's not disabled
                        classes = await btn.get_attribute('class') or ''
                        disabled = await btn.get_attribute('disabled')
                        if 'disabled' not in classes and not disabled:
                            return True
                except:
                    continue

            return False

        except Exception:
            return False

    async def go_to_next_page(self):
        """Click the Next button and wait for new data to load."""
        next_selectors = [
            'a:has-text("Next")',
            'button:has-text("Next")',
            'a.next',
            '.paginate_button.next:not(.disabled)',
            'li.next:not(.disabled) a',
            'a[aria-label*="next" i]',
        ]

        for selector in next_selectors:
            try:
                btn = self.page.locator(selector).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()

                    # Wait for page content to update
                    await asyncio.sleep(random.uniform(*HUMAN_ACTION_DELAY))

                    # Wait for network to settle (new data loading)
                    try:
                        await self.page.wait_for_load_state('networkidle', timeout=15000)
                    except:
                        # networkidle might not trigger on AJAX-loaded tables
                        await asyncio.sleep(3)

                    print("  [NEXT] Moved to next page")
                    return True
            except:
                continue

        print("  [WARN] Could not find Next button")
        return False

    def save_progress(self):
        """Save progress checkpoint (in case of crash, data is preserved)."""
        progress = {
            'total_records': len(self.scraped_data),
            'last_updated': datetime.now().isoformat(),
        }

        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)

        # Also save incremental CSV so data is never lost
        if self.scraped_data:
            df = pd.DataFrame(self.scraped_data)
            df.to_csv(self.output_file, index=False, encoding='utf-8')

    def save_final_csv(self):
        """Save the complete dataset."""
        print("\n[SAVE] Saving final data...")

        if not self.scraped_data:
            print("  [WARN] No data collected!")
            return

        df = pd.DataFrame(self.scraped_data)

        # Remove internal metadata columns from display
        display_cols = [c for c in df.columns if not c.startswith('_')]
        meta_cols = [c for c in df.columns if c.startswith('_')]

        # Save full dataset (with metadata)
        df.to_csv(self.output_file, index=False, encoding='utf-8')
        print(f"  [OK] Saved {len(df)} records to {self.output_file}")

        # Save clean version (without metadata)
        clean_file = Path("scraped_data/unit_numbers_clean.csv")
        df[display_cols].to_csv(clean_file, index=False, encoding='utf-8')
        print(f"  [OK] Clean version: {clean_file}")

        # Timestamped backup
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = Path(f"scraped_data/unit_numbers_backup_{ts}.csv")
        df.to_csv(backup, index=False, encoding='utf-8')
        print(f"  [OK] Backup: {backup}")

        # Summary
        print()
        print("=" * 70)
        print("  SCRAPE SUMMARY")
        print("=" * 70)
        print(f"  Total records:  {len(df)}")
        print(f"  Columns found:  {len(display_cols)}")
        print(f"  Column names:   {', '.join(display_cols)}")

        # Check for unit number column
        unit_cols = [c for c in df.columns if 'unit' in c.lower()]
        if unit_cols:
            for uc in unit_cols:
                filled = df[uc].notna().sum()
                print(f"  '{uc}' filled: {filled}/{len(df)} ({filled/len(df)*100:.1f}%)")
        else:
            print("  [WARN] No column with 'unit' in the name found")
            print(f"  All columns: {list(df.columns)}")

        print("=" * 70)

    async def scrape_all_pages(self, max_pages: int = None):
        """
        Automatically scrape the current page and all subsequent pages.
        Handles pagination, progress saving, and error recovery.
        """
        page_num = 1
        empty_pages = 0  # Track consecutive empty pages to detect end

        while True:
            print(f"\n[PAGE {page_num}]")

            # Extract data
            page_data = await self.extract_table_data()

            if page_data:
                new_rows = []
                skipped = 0
                for row in page_data:
                    key = self._row_to_key(row)
                    if key in self.already_scraped_keys:
                        skipped += 1
                        continue
                    self.already_scraped_keys.add(key)
                    new_rows.append(row)
                self.scraped_data.extend(new_rows)
                if skipped:
                    print(f"  [SKIP] {skipped} already scraped (this page)")
                self.save_progress()
                empty_pages = 0
                print(f"  [TOTAL] {len(self.scraped_data)} records collected so far")
            else:
                empty_pages += 1
                print(f"  [WARN] No data (empty pages in a row: {empty_pages})")
                if empty_pages >= 3:
                    print("  [STOP] 3 consecutive empty pages - stopping")
                    break

            # Check max pages limit
            if max_pages and page_num >= max_pages:
                print(f"\n[LIMIT] Reached {max_pages} page limit")
                break

            # Check for next page
            has_next = await self.check_pagination()
            if not has_next:
                print("\n[DONE] No more pages - reached the end")
                break

            # Go to next page
            success = await self.go_to_next_page()
            if not success:
                print("[STOP] Failed to navigate to next page")
                break

            page_num += 1

            # Small delay between pages (polite scraping)
            delay = random.uniform(2.0, 4.0)
            print(f"  [WAIT] {delay:.1f}s delay...")
            await asyncio.sleep(delay)

        return page_num

    async def run(self, test_mode: bool = False):
        """
        Main hybrid workflow:
        1. Connect to user's Chrome
        2. Wait for user to do manual steps
        3. Scrape all pages automatically
        """
        start_time = time.time()

        try:
            print()
            print("=" * 70)
            print("  PROPERTY MONITOR UNIT NUMBER SCRAPER")
            print("  Mode: HYBRID (you browse, script extracts)")
            print("=" * 70)

            # Step 1: Connect to Chrome
            await self.connect_to_browser()

            # Step 2: Wait for user to do manual steps
            await self.wait_for_user_ready()

            # Step 3: Take a screenshot to confirm what we see
            print("[CHECK] Taking screenshot of current page...")
            screenshot_path = Path("scraped_data/pre_scrape_screenshot.png")
            await self.page.screenshot(path=str(screenshot_path))
            print(f"  [OK] Screenshot saved: {screenshot_path}")
            print(f"  [OK] Current URL: {self.page.url}")

            # Step 4: Do a test extraction first
            print("\n[TEST] Running test extraction on current page...")
            test_data = await self.extract_table_data()

            if not test_data:
                print("[WARN] No data extracted from current page!")
                print("[WARN] Possible reasons:")
                print("  - The table hasn't loaded yet")
                print("  - The page structure is different than expected")
                print("  - No results matching your filters")
                print()
                retry = input("  Try again? (y/n): ").strip().lower()
                if retry == 'y':
                    test_data = await self.extract_table_data()

            if test_data:
                print(f"\n[OK] Test extraction successful: {len(test_data)} rows")
                print(f"[OK] Sample row keys: {list(test_data[0].keys())[:8]}")
                print()

                # Show first row as preview
                first = test_data[0]
                print("  First row preview:")
                for key, val in list(first.items())[:8]:
                    if not key.startswith('_'):
                        print(f"    {key}: {val}")

                print()
                proceed = input("  Looks correct? Start scraping all pages? (y/n): ").strip().lower()

                if proceed != 'y':
                    print("[CANCELLED] Scraping cancelled by user")
                    return
            else:
                print("[ERROR] Could not extract any data. Check the page and try again.")
                return

            # Step 5: Scrape all pages
            max_pages = 2 if test_mode else None
            print(f"\n[SCRAPE] Starting {'test (2 pages)' if test_mode else 'full'} scrape...")
            print(f"[SCRAPE] Press Ctrl+C at any time to stop (data will be saved)")
            print()

            # We already have the first page data
            # Reset and start fresh extraction
            self.scraped_data = []
            total_pages = await self.scrape_all_pages(max_pages=max_pages)

            # Step 6: Save results
            self.save_final_csv()

            # Duration
            duration = time.time() - start_time
            mins = int(duration // 60)
            secs = int(duration % 60)

            print()
            print(f"[COMPLETE] Done in {mins}m {secs}s")
            print(f"[COMPLETE] {len(self.scraped_data)} records across {total_pages} pages")
            print(f"[COMPLETE] Saved to: {self.output_file}")

        except KeyboardInterrupt:
            print("\n\n[INTERRUPTED] Saving collected data before exit...")
            self.save_final_csv()
            print("[OK] Data saved despite interruption")

        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()

            # Try to save whatever we have
            if self.scraped_data:
                print("\n[SAVE] Saving partial data...")
                self.save_final_csv()


if __name__ == "__main__":
    scraper = UnitNumberScraper()
    asyncio.run(scraper.run(test_mode=True))
