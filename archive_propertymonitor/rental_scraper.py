"""
Property Monitor Rental Scraper - HYBRID MODE
==============================================
Scrapes rental transaction data (Ejari contracts) from Property Monitor.

YOU log in manually and set up the search.
The script connects to YOUR browser and scrapes all pages automatically.

How it works:
1. Script launches Chrome with remote debugging enabled (port 9222)
2. YOU log in, pass Cloudflare, navigate to Rentals page
3. YOU select: Palm Jumeirah, Last 3 years, Rentals mode, per page = 250
4. Press Enter in the terminal when ready
5. Script connects to your browser and extracts ALL pages automatically

Shoreline tower resolution (optional):
  Run with --shoreline-only to capture Sub Community tower names (Al Das, Al Masalli, etc.):
  In Property Monitor set Community/Building = "Shoreline Apartments", then run:
    python property_research_agent/rental_scraper.py --shoreline-only
  Output: scraped_data/palm_jumeirah_rentals_shoreline.csv
  Then run merge_shoreline_rentals.py to merge into the main rental CSV.
"""

import asyncio
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
import re

# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

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

# Shoreline tower mapping (for building name normalization)
SHORELINE_ARABIC = {
    'al ramth': 'Shoreline 1', 'al nabat': 'Shoreline 2', 'al sultana': 'Shoreline 3',
    'al tamr': 'Shoreline 4', 'al jeer': 'Shoreline 5', 'al shahla': 'Shoreline 6',
    'al khudrawi': 'Shoreline 7', 'al sarrood': 'Shoreline 8',
    'al msalli': 'Shoreline 9', 'al masalli': 'Shoreline 9',
    'al dabas': 'Shoreline 10', 'al habool': 'Shoreline 11', 'al haseer': 'Shoreline 12',
    'al ameera': 'Shoreline 13', 'al hallawi': 'Shoreline 14', 'al das': 'Shoreline 15',
    'al khushkar': 'Shoreline 16', 'al hamri': 'Shoreline 17', 'al safeena': 'Shoreline 18',
    'al basri': 'Shoreline 19', 'al ghozlan': 'Shoreline 20',
}


def find_chrome() -> str:
    """Find Chrome executable on this machine."""
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None


def launch_chrome_with_debugging():
    """Launch Chrome with remote debugging enabled."""
    chrome_path = find_chrome()
    if not chrome_path:
        print("[ERROR] Chrome not found! Looked in:")
        for p in CHROME_PATHS:
            print(f"  - {p}")
        print("\nPlease install Chrome or provide the path.")
        sys.exit(1)

    print(f"[CHROME] Found at: {chrome_path}")
    print(f"[CHROME] Launching with remote debugging on port {CDP_PORT}...")

    # Use temp directory to avoid permission issues
    import tempfile
    temp_dir = tempfile.gettempdir()
    debug_profile = Path(temp_dir) / "chrome_debug_rental"
    
    # Clean up old profile if it exists and is locked
    if debug_profile.exists():
        try:
            import shutil
            shutil.rmtree(debug_profile, ignore_errors=True)
        except:
            pass
    
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

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
    )

    print(f"[OK] Chrome launched (PID: {process.pid})")
    return process


def normalize_building_name(community: str, sub_community: str) -> str:
    """
    Normalize building name from Property Monitor columns.
    
    Combines Community + Sub Community and applies Shoreline mapping.
    Examples:
        "Shoreline Apartments", "Al Das" -> "Shoreline 15"
        "Tiara Residences", "Sapphire" -> "Tiara Residences Sapphire"
        "Marina Residences", "Marina Residences 1" -> "Marina Residences 1"
    """
    community_clean = str(community or '').strip()
    sub_clean = str(sub_community or '').strip()
    
    # Check if sub_community is a Shoreline Arabic name
    sub_lower = sub_clean.lower()
    if sub_lower in SHORELINE_ARABIC:
        return SHORELINE_ARABIC[sub_lower]
    
    # Check if community contains "shoreline" and sub has Arabic name
    if 'shoreline' in community_clean.lower():
        if sub_lower in SHORELINE_ARABIC:
            return SHORELINE_ARABIC[sub_lower]
    
    # Tiara sub-buildings
    if 'tiara' in community_clean.lower():
        if sub_clean and sub_clean != community_clean:
            return f"Tiara Residences {sub_clean}"
        return "Tiara Residences"
    
    # Oceana sub-buildings
    if 'oceana' in community_clean.lower():
        oceana_subs = ['Adriatic', 'Aegean', 'Atlantic', 'Caribbean', 'Pacific', 
                       'Baltic', 'Southern', 'Ruby', 'Luce', 'Emerald', 'Diamond', 
                       'Tanzanite', 'Aquamarine']
        for sub in oceana_subs:
            if sub.lower() in sub_lower:
                return f"Oceana {sub}"
        return "Oceana"
    
    # Marina buildings
    if 'marina' in community_clean.lower() and sub_clean:
        return sub_clean
    
    # Default: use sub_community if more specific, else community
    if sub_clean and sub_clean != community_clean and sub_clean.lower() != 'nan':
        return sub_clean
    return community_clean if community_clean else sub_clean


def parse_date_from_pm(date_str: str) -> Optional[str]:
    """
    Parse Property Monitor date format to YYYY-MM-DD.
    Input: "03 Feb 2025" or "! 10 Feb 2026" (with ! prefix)
    Output: "2025-02-03" or "2026-02-10"
    """
    if not date_str or pd.isna(date_str):
        return None
    
    # Strip the ! prefix that appears on some rental dates
    date_str = str(date_str).replace('!', '').strip()
    
    if not date_str or date_str == 'nan':
        return None
    
    try:
        dt = datetime.strptime(date_str.strip(), '%d %b %Y')
        return dt.strftime('%Y-%m-%d')
    except:
        # Try alternative format
        try:
            dt = datetime.strptime(date_str.strip(), '%d/%m/%Y')
            return dt.strftime('%Y-%m-%d')
        except:
            return None


def clean_price(price_str: str) -> Optional[float]:
    """Remove commas and convert to float."""
    if not price_str or pd.isna(price_str):
        return None
    try:
        cleaned = str(price_str).replace(',', '').replace('AED', '').strip()
        return float(cleaned) if cleaned else None
    except:
        return None


class RentalScraper:
    """
    Hybrid rental scraper: connects to user's already-open Chrome via CDP.
    User handles login + Cloudflare manually, script handles data extraction.
    """

    def __init__(self, shoreline_only: bool = False):
        self.browser = None
        self.page: Optional[Page] = None
        self.scraped_data: List[Dict] = []
        self.progress_file = Path("scraped_data/rental_scraping_progress.json")
        self.shoreline_only = shoreline_only
        if shoreline_only:
            self.output_file = Path("scraped_data/palm_jumeirah_rentals_shoreline.csv")
        else:
            self.output_file = Path("scraped_data/palm_jumeirah_rentals.csv")

        Path("scraped_data").mkdir(exist_ok=True)

    async def connect_to_browser(self):
        """Connect to already-running Chrome via CDP."""
        print(f"[CONNECT] Connecting to Chrome on port {CDP_PORT}...")

        playwright = await async_playwright().start()

        try:
            self.browser = await playwright.chromium.connect_over_cdp(CDP_URL)
            print("[OK] Connected to Chrome")

            contexts = self.browser.contexts
            if contexts:
                pages = contexts[0].pages
                if pages:
                    self.page = pages[-1]
                    print(f"[OK] Attached to tab: {self.page.url}")
                    return

            print("[WARN] No existing tab found, creating new one...")
            context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
            self.page = await context.new_page()

        except Exception as e:
            print(f"[ERROR] Could not connect to Chrome: {e}")
            print(f"  Make sure Chrome is running with --remote-debugging-port={CDP_PORT}")
            raise

    async def wait_for_user_ready(self):
        """Wait for user to set up the rental search manually."""
        print()
        print("=" * 70)
        print("  YOUR TURN - DO THESE STEPS IN CHROME:")
        print("=" * 70)
        print()
        print("  1. Log in to Property Monitor")
        print("  2. Pass the Cloudflare challenge")
        print("  3. Navigate to the RENTALS page")
        print("  4. Select: Palm Jumeirah")
        if self.shoreline_only:
            print("  5. Set Community/Building filter to: SHORELINE APARTMENTS (required for tower names)")
            print("  6. Set date range: Last 3 years (or 'All Historical Data')")
            print("  7. Set 'Select Data Points' to 'Rental Contract' (or leave as 'All')")
            print("  8. Set per page to 250")
            print("  9. Click Search and ensure the Shoreline results TABLE is visible")
        else:
            print("  5. Set date range: Last 3 years (or 'All Historical Data')")
            print("  6. Set 'Select Data Points' to 'Rental Contract' (or leave as 'All')")
            print("  7. Set per page to 250")
            print("  8. Make sure the rental results TABLE is visible on screen")
        print()
        print("=" * 70)
        input("  >>> Press ENTER here when the rental table is showing... ")
        print()

        # Re-attach to the current tab
        if self.browser and self.browser.contexts:
            pages = self.browser.contexts[0].pages
            if pages:
                self.page = pages[-1]
                print(f"[OK] Attached to: {self.page.url}")

    async def extract_rental_table_data(self) -> List[Dict]:
        """
        Extract rental transaction data from the current page.
        Rental tables have different columns than sales tables.
        """
        print("[TABLE] Extracting rental data from current page...")

        try:
            await asyncio.sleep(2)

            # Extract using JavaScript
            table_data = await self.page.evaluate("""
                () => {
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

            if isinstance(table_data, dict) and 'error' in table_data:
                print(f"  [WARN] {table_data['error']}")
                return []

            if isinstance(table_data, dict) and table_data.get('success'):
                rows = table_data['rows']
                headers = table_data['headers']

                print(f"  [OK] Found {table_data['row_count']} rows")
                print(f"  [OK] Columns: {', '.join(headers[:8])}{'...' if len(headers) > 8 else ''}")

                # Add metadata
                for row in rows:
                    row['_scraped_at'] = datetime.now().isoformat()
                    row['_source'] = 'Property Monitor Rentals'
                    row['_page_url'] = self.page.url

                return rows

            return []

        except Exception as e:
            print(f"  [ERROR] Extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def check_pagination(self) -> bool:
        """Check if there's a Next page button that's clickable."""
        try:
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
                    await asyncio.sleep(random.uniform(*HUMAN_ACTION_DELAY))

                    try:
                        await self.page.wait_for_load_state('networkidle', timeout=15000)
                    except:
                        await asyncio.sleep(3)

                    print("  [NEXT] Moved to next page")
                    return True
            except:
                continue

        print("  [WARN] Could not find Next button")
        return False

    def save_progress(self):
        """Save progress checkpoint."""
        progress = {
            'total_records': len(self.scraped_data),
            'last_updated': datetime.now().isoformat(),
        }

        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)

        if self.scraped_data:
            df = pd.DataFrame(self.scraped_data)
            df.to_csv(self.output_file, index=False, encoding='utf-8')

    def save_final_csv(self):
        """Save and normalize the rental data."""
        print("\n[SAVE] Processing and saving rental data...")

        if not self.scraped_data:
            print("  [WARN] No data collected!")
            return

        df = pd.DataFrame(self.scraped_data)
        print(f"  [OK] {len(df)} raw records collected")
        print(f"  [OK] Raw columns: {list(df.columns)[:15]}")

        # Save raw data BEFORE normalization (so we can debug/fix normalization issues)
        raw_file = Path(str(self.output_file).replace('.csv', '_raw.csv'))
        df.to_csv(raw_file, index=False, encoding='utf-8')
        print(f"  [OK] Raw data saved to {raw_file}")

        # Normalize columns to standard names
        normalized = self._normalize_rental_data(df)

        # Save normalized CSV
        normalized.to_csv(self.output_file, index=False, encoding='utf-8')
        print(f"  [OK] Normalized data saved to {self.output_file}")

        # Timestamped backup
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        prefix = "palm_rentals_shoreline_backup" if self.shoreline_only else "palm_rentals_backup"
        backup = Path(f"scraped_data/{prefix}_{ts}.csv")
        normalized.to_csv(backup, index=False, encoding='utf-8')
        print(f"  [OK] Backup: {backup}")

        # Summary
        print()
        print("=" * 70)
        print("  RENTAL SCRAPE SUMMARY")
        print("=" * 70)
        print(f"  Total records:       {len(normalized)}")
        print(f"  Unique buildings:    {normalized['building_name'].nunique()}")
        print(f"  Unique units:        {normalized['unit_number'].nunique()}")
        print(f"  With contract dates: {normalized['contract_start'].notna().sum()}")
        print(f"  With prices:         {normalized['annualized_rent'].notna().sum()}")
        print(f"  With sizes:          {normalized['size_sqft'].notna().sum()}")
        print(f"  With bedrooms:       {normalized['bedrooms'].notna().sum()}")
        if 'rent_recurrence' in normalized.columns:
            renewals = (normalized['rent_recurrence'].fillna('').str.lower() == 'renewal').sum()
            new_contracts = (normalized['rent_recurrence'].fillna('').str.lower() == 'new contract').sum()
            print(f"  Renewals:            {renewals} ({renewals/len(normalized)*100:.1f}%)")
            print(f"  New contracts:       {new_contracts} ({new_contracts/len(normalized)*100:.1f}%)")
        print("=" * 70)

    def _normalize_rental_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize raw scraped rental data to standard schema.
        
        Handles:
        - Column name mapping (flexible matching)
        - Date parsing (existence date has TWO dates: start / end)
        - Price cleaning
        - Building name normalization (Shoreline Arabic mapping)
        - Filtering garbage rows (alternating empty rows from table structure)
        """
        # Filter out garbage rows where both building and unit are null
        # This handles alternating empty rows from PM table structure
        col_map = self._detect_rental_columns(df)
        
        # Get building and unit columns (if detected) to filter garbage rows
        building_col = col_map.get('community') or col_map.get('sub_community')
        unit_col = col_map.get('unit_number')
        
        if building_col and unit_col:
            # Filter: keep rows where at least building OR unit has data
            building_has_data = df[building_col].notna() & (df[building_col].astype(str).str.strip() != '')
            unit_has_data = df[unit_col].notna() & (df[unit_col].astype(str).str.strip() != '')
            valid_rows = building_has_data | unit_has_data
            initial_count = len(df)
            df = df[valid_rows].copy()
            df = df.reset_index(drop=True)  # Reset index to avoid misalignment
            removed = initial_count - len(df)
            if removed > 0:
                print(f"  [FILTER] Removed {removed} garbage rows (empty building+unit)")
        
        result = pd.DataFrame()
        
        # Column mapping already done above, reuse it
        
        # Parse existence date (contains start / end)
        if col_map.get('existence_date'):
            existence = df[col_map['existence_date']].astype(str)
            
            def parse_existence(val):
                """Extract start and end dates from 'DD Mon YYYY / DD Mon YYYY'.
                
                Property Monitor uses non-breaking spaces (\xa0) around the slash:
                '10 Feb 2026\xa0/\xa009 Feb 2027'
                Must normalize these to regular spaces before splitting.
                """
                if not val or val == 'nan':
                    return None, None
                # Replace non-breaking spaces with regular spaces
                val = val.replace('\xa0', ' ')
                # Strip ! prefix (red warning marker on some rows)
                val = val.replace('!', '').strip()
                # Split on " / " 
                parts = val.split(' / ')
                start = parse_date_from_pm(parts[0].strip()) if parts else None
                end = parse_date_from_pm(parts[1].strip()) if len(parts) > 1 else None
                return start, end
            
            dates = existence.apply(parse_existence)
            result['contract_start'] = dates.apply(lambda x: x[0] if x else None)
            result['contract_end'] = dates.apply(lambda x: x[1] if x else None)
        else:
            result['contract_start'] = None
            result['contract_end'] = None
        
        # Contract type
        if col_map.get('contract_type'):
            result['contract_type'] = df[col_map['contract_type']]
        else:
            result['contract_type'] = 'Rental Contract'
        
        # Building names (community + sub_community)
        # Handle missing columns gracefully
        if col_map.get('community'):
            community = df[col_map['community']].astype(str).fillna('')
        else:
            community = pd.Series([''] * len(df))
        
        if col_map.get('sub_community'):
            sub_community = df[col_map['sub_community']].astype(str).fillna('')
        else:
            sub_community = pd.Series([''] * len(df))
        
        # Clean up 'nan' strings
        community = community.replace('nan', '')
        sub_community = sub_community.replace('nan', '')
        
        result['building_raw'] = [
            f"{s} ({c})" if s and c else (s if s else c) 
            for s, c in zip(sub_community, community)
        ]
        result['building_name'] = [
            normalize_building_name(c, s) 
            for c, s in zip(community, sub_community)
        ]
        
        # Unit number
        if col_map.get('unit_number'):
            result['unit_number'] = df[col_map['unit_number']].astype(str).str.strip()
        else:
            result['unit_number'] = ''
        
        # Prices
        if col_map.get('annualized_rent'):
            result['annualized_rent'] = df[col_map['annualized_rent']].apply(clean_price)
        else:
            result['annualized_rent'] = None
        
        if col_map.get('contract_rent'):
            result['contract_rent'] = df[col_map['contract_rent']].apply(clean_price)
        else:
            result['contract_rent'] = result['annualized_rent']
        
        # Frequency
        if col_map.get('frequency'):
            result['frequency'] = df[col_map['frequency']]
        else:
            result['frequency'] = 'Yearly'
        
        # Size
        if col_map.get('size_sqft'):
            result['size_sqft'] = df[col_map['size_sqft']].apply(clean_price)  # Same cleaning (remove commas)
        else:
            result['size_sqft'] = None
        
        # Unit type - Property Monitor includes PM ID numbers like "Apartment 3812731"
        if col_map.get('unit_type'):
            def clean_unit_type(val):
                """Strip PM numeric ID from unit type."""
                if pd.isna(val):
                    return 'Apartment'
                s = str(val).strip()
                # Extract just the type text, remove trailing numbers
                import re
                match = re.match(r'^([A-Za-z\s]+)', s)
                return match.group(1).strip() if match else s
            
            result['unit_type'] = df[col_map['unit_type']].apply(clean_unit_type)
        else:
            result['unit_type'] = 'Apartment'
        
        # Floor level - can be "B1", "P1", "G+1" (keep as string)
        if col_map.get('floor_level'):
            result['floor_level'] = df[col_map['floor_level']].astype(str).str.strip()
        else:
            result['floor_level'] = None
        
        # Bedrooms
        if col_map.get('bedrooms'):
            result['bedrooms'] = df[col_map['bedrooms']].astype(str).str.strip()
        else:
            result['bedrooms'] = None
        
        # View
        if col_map.get('view'):
            result['view'] = df[col_map['view']]
        else:
            result['view'] = ''
        
        # Furnished
        if col_map.get('furnished'):
            result['furnished'] = df[col_map['furnished']]
        else:
            result['furnished'] = ''
        
        # Broker/source
        if col_map.get('source'):
            result['broker'] = df[col_map['source']]
        else:
            result['broker'] = ''
        
        # Description
        if col_map.get('description'):
            result['description'] = df[col_map['description']]
        else:
            result['description'] = ''
        
        # Next contract date
        if col_map.get('next_existence'):
            result['next_contract_date'] = df[col_map['next_existence']].apply(parse_date_from_pm)
        else:
            result['next_contract_date'] = None
        
        # Rent Recurrence - CRITICAL for renewal analysis
        if col_map.get('rent_recurrence'):
            result['rent_recurrence'] = df[col_map['rent_recurrence']].astype(str).str.strip()
        else:
            result['rent_recurrence'] = ''
        
        # Rent PSF
        if col_map.get('rent_psf'):
            result['rent_psf'] = df[col_map['rent_psf']].apply(clean_price)
        else:
            result['rent_psf'] = None
        
        # Plot size (for villas)
        if col_map.get('plot_sqft'):
            result['plot_sqft'] = df[col_map['plot_sqft']].apply(clean_price)
        else:
            result['plot_sqft'] = None
        
        # Balcony
        if col_map.get('balcony'):
            result['balcony'] = df[col_map['balcony']].astype(str).str.strip()
        else:
            result['balcony'] = ''
        
        return result

    def _detect_rental_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """
        Detect rental table columns by fuzzy matching header text.
        
        Returns dict mapping standard names to actual column names.
        """
        col_lower = {str(c).lower().strip(): c for c in df.columns}
        mapping = {}
        
        # Existence Date (contract start/end) - Property Monitor uses "Evidence Date"
        for pattern in ['evidence date', 'existence date', 'contract date', 'date']:
            for col_l, col in col_lower.items():
                if pattern in col_l and 'next' not in col_l:
                    mapping['existence_date'] = col
                    break
            if mapping.get('existence_date'):
                break
        
        # Contract type
        for pattern in ['contract type', 'select date', 'type']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['contract_type'] = col
                    break
            if mapping.get('contract_type'):
                break
        
        # Community/Building
        for pattern in ['community', 'all developments']:
            for col_l, col in col_lower.items():
                if pattern in col_l and 'sub' not in col_l:
                    mapping['community'] = col
                    break
            if mapping.get('community'):
                break
        
        # Sub Community/Building - PM has TWO columns with this name, take the one with most data
        sub_community_candidates = []
        for pattern in ['sub community', 'sub-community', 'sub building']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    # Check if this column has actual data (not all null/empty)
                    if col in df.columns:
                        non_null_count = df[col].notna().sum()
                        non_empty_count = (df[col].astype(str).str.strip() != '').sum()
                        if non_null_count > 0 or non_empty_count > 0:
                            sub_community_candidates.append((col, non_empty_count))
        
        # Use the column with the most non-empty values
        if sub_community_candidates:
            sub_community_candidates.sort(key=lambda x: x[1], reverse=True)
            mapping['sub_community'] = sub_community_candidates[0][0]
        
        # Unit number
        for pattern in ['unit #', 'unit no', 'unit_no', 'unit number']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['unit_number'] = col
                    break
            if mapping.get('unit_number'):
                break
        
        # Annualized rent - Property Monitor uses British spelling "Annualised"
        for pattern in ['annualised rental', 'annualized rental', 'annual rent', 'annualised', 'annualized']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['annualized_rent'] = col
                    break
            if mapping.get('annualized_rent'):
                break
        
        # Contract rent
        for pattern in ['contract rental', 'contract price']:
            for col_l, col in col_lower.items():
                if pattern in col_l and 'annualized' not in col_l:
                    mapping['contract_rent'] = col
                    break
            if mapping.get('contract_rent'):
                break
        
        # Frequency
        for pattern in ['frequency']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['frequency'] = col
                    break
            if mapping.get('frequency'):
                break
        
        # Size
        for pattern in ['unit size', 'sq. ft', 'sqft', 'size']:
            for col_l, col in col_lower.items():
                if pattern in col_l and 'plot' not in col_l:
                    mapping['size_sqft'] = col
                    break
            if mapping.get('size_sqft'):
                break
        
        # Unit type
        for pattern in ['unit type', 'property type']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['unit_type'] = col
                    break
            if mapping.get('unit_type'):
                break
        
        # Floor level
        for pattern in ['floor level', 'floor']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['floor_level'] = col
                    break
            if mapping.get('floor_level'):
                break
        
        # Bedrooms
        for pattern in ['beds', 'bedroom']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['bedrooms'] = col
                    break
            if mapping.get('bedrooms'):
                break
        
        # View
        for pattern in ['view']:
            for col_l, col in col_lower.items():
                if col_l == 'view':
                    mapping['view'] = col
                    break
        
        # Furnished
        for pattern in ['furnished']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['furnished'] = col
                    break
            if mapping.get('furnished'):
                break
        
        # Source/broker
        for pattern in ['source', 'broker']:
            for col_l, col in col_lower.items():
                if pattern in col_l and 'data' not in col_l:
                    mapping['source'] = col
                    break
            if mapping.get('source'):
                break
        
        # Description
        for pattern in ['concession', 'description', 'notes']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['description'] = col
                    break
            if mapping.get('description'):
                break
        
        # Next existence
        for pattern in ['next existence', 'next contract']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['next_existence'] = col
                    break
            if mapping.get('next_existence'):
                break
        
        # Rent Recurrence - CRITICAL for renewal analysis
        for pattern in ['rent recurrence', 'recurrence']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['rent_recurrence'] = col
                    break
            if mapping.get('rent_recurrence'):
                break
        
        # Rent PSF
        for pattern in ['rent (aed/sq ft)', 'rent psf', 'aed/sq ft']:
            for col_l, col in col_lower.items():
                if 'rent' in col_l and ('sq ft' in col_l or 'psf' in col_l):
                    mapping['rent_psf'] = col
                    break
            if mapping.get('rent_psf'):
                break
        
        # Plot size (for villas)
        for pattern in ['plot size']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['plot_sqft'] = col
                    break
            if mapping.get('plot_sqft'):
                break
        
        # Balcony
        for pattern in ['balcony']:
            for col_l, col in col_lower.items():
                if pattern in col_l:
                    mapping['balcony'] = col
                    break
            if mapping.get('balcony'):
                break
        
        return mapping

    async def scrape_all_pages(self, max_pages: int = None):
        """Automatically scrape all rental pages."""
        page_num = 1
        empty_pages = 0

        while True:
            print(f"\n[PAGE {page_num}]")

            # Extract data
            page_data = await self.extract_rental_table_data()

            if page_data:
                self.scraped_data.extend(page_data)
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

            # Progress update every 10 pages
            if page_num % 10 == 0:
                elapsed = time.time() - self.start_time
                rate = len(self.scraped_data) / elapsed if elapsed > 0 else 0
                print(f"  [PROGRESS] {page_num} pages | {len(self.scraped_data):,} records | {rate:.1f} rec/sec")

            # Polite delay
            delay = random.uniform(2.0, 4.0)
            await asyncio.sleep(delay)

        return page_num

    async def run(self, test_mode: bool = False):
        """Main hybrid workflow."""
        self.start_time = time.time()

        try:
            print()
            print("=" * 70)
            print("  PROPERTY MONITOR RENTAL SCRAPER")
            print("  Mode: HYBRID (you browse, script extracts)")
            print("=" * 70)

            # Connect to Chrome
            await self.connect_to_browser()

            # Wait for user to set up search
            await self.wait_for_user_ready()

            # Take screenshot (non-blocking - skip if it times out)
            print("[CHECK] Taking screenshot...")
            screenshot_path = Path("scraped_data/rental_scrape_screenshot.png")
            try:
                await self.page.screenshot(path=str(screenshot_path), timeout=5000)
                print(f"  [OK] Screenshot: {screenshot_path}")
            except Exception as e:
                print(f"  [SKIP] Screenshot failed (non-critical): {str(e)[:50]}")

            # Test extraction
            print("\n[TEST] Running test extraction on current page...")
            test_data = await self.extract_rental_table_data()

            if not test_data:
                print("[WARN] No data extracted!")
                retry = input("  Try again? (y/n): ").strip().lower()
                if retry == 'y':
                    test_data = await self.extract_rental_table_data()

            if test_data:
                print(f"\n[OK] Test extraction successful: {len(test_data)} rows")
                print(f"[OK] Sample row keys: {list(test_data[0].keys())[:10]}")
                print()
                print("  First row preview:")
                first = test_data[0]
                for key, val in list(first.items())[:10]:
                    if not key.startswith('_'):
                        print(f"    {key}: {val}")

                print()
                proceed = input("  Start scraping all pages? (y/n): ").strip().lower()

                if proceed != 'y':
                    print("[CANCELLED] Scraping cancelled")
                    return
            else:
                print("[ERROR] Could not extract any data. Check the page and try again.")
                return

            # Scrape all pages
            max_pages = 2 if test_mode else None
            print(f"\n[SCRAPE] Starting {'test (2 pages)' if test_mode else 'full'} scrape...")
            print(f"[SCRAPE] Press Ctrl+C at any time to stop (data will be saved)")
            print()

            self.scraped_data = []
            total_pages = await self.scrape_all_pages(max_pages=max_pages)

            # Save results
            self.save_final_csv()

            # Duration
            duration = time.time() - self.start_time
            mins = int(duration // 60)
            secs = int(duration % 60)

            print()
            print(f"[COMPLETE] Done in {mins}m {secs}s")
            print(f"[COMPLETE] {len(self.scraped_data)} records across {total_pages} pages")

        except KeyboardInterrupt:
            print("\n\n[INTERRUPTED] Saving collected data before exit...")
            self.save_final_csv()
            print("[OK] Data saved despite interruption")

        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()

            if self.scraped_data:
                print("\n[SAVE] Saving partial data...")
                self.save_final_csv()


if __name__ == "__main__":
    import time
    import argparse

    parser = argparse.ArgumentParser(description="Property Monitor Rental Scraper")
    parser.add_argument(
        "--shoreline-only",
        action="store_true",
        help="Shoreline Apartments only: set filter to Shoreline Apartments to capture Sub Community tower names (Al Das, Al Masalli, etc.). Output: palm_jumeirah_rentals_shoreline.csv",
    )
    parser.add_argument("--test", action="store_true", help="Run only 2 pages (for testing)")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  STEP 1: LAUNCHING CHROME")
    print("=" * 70)

    if args.shoreline_only:
        print("\n[MODE] Shoreline-only scrape (output: palm_jumeirah_rentals_shoreline.csv)")

    # Launch Chrome with debugging enabled
    try:
        chrome_process = launch_chrome_with_debugging()
        print("\n[OK] Chrome launched successfully")
        print("[WAIT] Waiting 3 seconds for Chrome to start...")
        time.sleep(3)
    except Exception as e:
        print(f"\n[ERROR] Failed to launch Chrome: {e}")
        print("\nTROUBLESHOOTING:")
        print("1. Close any existing Chrome windows")
        print("2. Try running the scraper again")
        print("3. Or manually launch Chrome with:")
        print("   chrome.exe --remote-debugging-port=9222 --user-data-dir=scraped_data/chrome_debug_profile")
        exit(1)

    print("\n" + "=" * 70)
    print("  STEP 2: RUNNING SCRAPER")
    print("=" * 70)

    scraper = RentalScraper(shoreline_only=args.shoreline_only)
    asyncio.run(scraper.run(test_mode=args.test))
