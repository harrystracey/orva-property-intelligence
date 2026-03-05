"""
Bayut Palm Jumeirah Listings Scraper
=====================================
Scrapes ALL for-sale and for-rent apartment listings on Palm Jumeirah from Bayut.

Data extracted per listing (using aria-label attributes — stable across CSS changes):
  - building_name   (from Location field, first segment)
  - bedrooms        (confirmed integer)
  - bathrooms
  - size_sqft
  - price_aed
  - view            (parsed from listing title)
  - listing_type    (sale / rent)
  - listing_title   (full title text for reference)
  - listing_url
  - scraped_at

Output: data/bayut_palm_listings.csv
Progress: data/bayut_listings_progress.json  (resume-safe)

Usage:
    python bayut_scraper/run_palm_listings.py
    python bayut_scraper/run_palm_listings.py --type sale
    python bayut_scraper/run_palm_listings.py --type rent
    python bayut_scraper/run_palm_listings.py --max-pages 10   (for testing)
"""

import asyncio
import json
import re
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URLS = {
    "sale": "https://www.bayut.com/for-sale/apartments/dubai/palm-jumeirah/",
    "rent": "https://www.bayut.com/to-rent/apartments/dubai/palm-jumeirah/",
}

OUTPUT_PATH      = Path("data/bayut_palm_listings.csv")
PROGRESS_PATH    = Path("data/bayut_listings_progress.json")
CDP_URL          = "http://localhost:9222"
PAGE_DELAY       = (4.0, 8.0)   # seconds between pages
PAGE_LOAD_TIMEOUT = 30_000      # ms


# ---------------------------------------------------------------------------
# View extraction
# ---------------------------------------------------------------------------

VIEW_PATTERNS = [
    (r"full sea.{0,10}burj",          "Full Sea & Burj Al Arab View"),
    (r"sea.{0,10}burj",               "Sea & Burj Al Arab View"),
    (r"full atlantis",                 "Full Atlantis View"),
    (r"panoramic sea",                 "Panoramic Sea View"),
    (r"full sea",                      "Full Sea View"),
    (r"partial sea",                   "Partial Sea View"),
    (r"ocean view",                    "Ocean View"),
    (r"sea view",                      "Sea View"),
    (r"sea\b",                         "Sea View"),
    (r"atlantis",                      "Atlantis View"),
    (r"burj al arab",                  "Burj Al Arab View"),
    (r"burj view",                     "Burj Al Arab View"),
    (r"marina view",                   "Marina View"),
    (r"lagoon view",                   "Lagoon View"),
    (r"palm view",                     "Palm View"),
    (r"garden view",                   "Garden View"),
    (r"pool view",                     "Pool View"),
    (r"beach view",                    "Beach View"),
    (r"skyline",                       "Skyline View"),
    (r"park view",                     "Park View"),
    (r"community view",                "Community View"),
    (r"road view|road.facing|facing.road", "Road View"),
    (r"inland view",                   "Inland View"),
]

def extract_view(title: str) -> Optional[str]:
    t = title.lower()
    for pattern, label in VIEW_PATTERNS:
        if re.search(pattern, t):
            return label
    return None


# ---------------------------------------------------------------------------
# Unit type extraction from title
# ---------------------------------------------------------------------------

def extract_unit_type(title: str) -> Optional[str]:
    """Extract unit type letter if mentioned (e.g. 'D Type', 'Type F')."""
    m = re.search(r'\b(?:Type[\s\-]?([A-H]\d?)|([A-H])\s*[Tt]ype)\b', title)
    if m:
        return (m.group(1) or m.group(2)).upper()
    return None


# ---------------------------------------------------------------------------
# Parse a single article element
# ---------------------------------------------------------------------------

def parse_article(article, listing_type: str) -> Optional[Dict]:
    """Extract all data from a single Bayut listing article using aria-labels."""

    def get(label: str) -> str:
        el = article.find(attrs={"aria-label": label})
        return el.get_text(strip=True) if el else ""

    # Core fields
    beds_raw  = get("Beds")
    baths_raw = get("Baths")
    area_raw  = get("Area")
    price_raw = get("Price")
    title     = get("Title")
    location  = get("Location")
    prop_type = get("Type")

    # Skip if none of the key fields are present
    if not beds_raw and not area_raw and not title:
        return None

    # Building name — first segment of Location before comma
    building = location.split(",")[0].strip() if location else None
    if not building:
        return None

    # Skip if clearly not Palm Jumeirah
    if location and "palm jumeirah" not in location.lower() and "palm" not in location.lower():
        return None

    # Parse bedrooms
    bedrooms = None
    if beds_raw:
        try:
            bedrooms = int(beds_raw)
        except ValueError:
            m = re.search(r"(\d+)", beds_raw)
            if m:
                bedrooms = int(m.group(1))

    # Parse bathrooms
    bathrooms = None
    if baths_raw:
        try:
            bathrooms = int(baths_raw)
        except ValueError:
            pass

    # Parse size
    size_sqft = None
    if area_raw:
        m = re.search(r"([\d,]+)", area_raw)
        if m:
            try:
                size_sqft = float(m.group(1).replace(",", ""))
            except ValueError:
                pass

    # Parse price
    price_aed = None
    if price_raw:
        try:
            price_aed = float(price_raw.replace(",", ""))
        except ValueError:
            pass

    # Listing URL
    link_el = article.find(attrs={"aria-label": "Listing link"})
    listing_url = None
    if link_el and link_el.get("href"):
        href = link_el["href"]
        listing_url = "https://www.bayut.com" + href if href.startswith("/") else href

    # View and unit type from title
    view      = extract_view(title)
    unit_type = extract_unit_type(title)

    # Skip completely empty records
    if bedrooms is None and size_sqft is None:
        return None

    return {
        "building_name": building,
        "bedrooms":      bedrooms,
        "bathrooms":     bathrooms,
        "size_sqft":     size_sqft,
        "price_aed":     price_aed,
        "view":          view,
        "unit_type":     unit_type,
        "listing_type":  listing_type,
        "listing_title": title,
        "listing_url":   listing_url,
        "scraped_at":    datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Parse a full listings page
# ---------------------------------------------------------------------------

def parse_listings_page(html: str, listing_type: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.find_all("article")
    results = []
    for article in articles:
        record = parse_article(article, listing_type)
        if record:
            results.append(record)
    return results


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def load_progress() -> Dict:
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"sale": {"last_page": 0, "total_records": 0},
            "rent": {"last_page": 0, "total_records": 0}}


def save_progress(progress: Dict):
    PROGRESS_PATH.parent.mkdir(exist_ok=True)
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)


def append_records(records: List[Dict]) -> int:
    """Append new records to CSV, deduplicating by listing_url. Returns count of new records saved."""
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    df = pd.DataFrame(records)
    if OUTPUT_PATH.exists():
        existing = pd.read_csv(OUTPUT_PATH, encoding="utf-8", low_memory=False)
        if "listing_url" in existing.columns and "listing_url" in df.columns:
            known_urls = set(existing["listing_url"].dropna())
            df = df[~df["listing_url"].isin(known_urls)]
        if df.empty:
            return 0
        df.to_csv(OUTPUT_PATH, mode="a", header=False, index=False, encoding="utf-8")
    else:
        df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    return len(df)


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------

class PalmListingsScraper:

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def connect(self) -> bool:
        playwright = await async_playwright().start()
        try:
            self.browser = await playwright.chromium.connect_over_cdp(CDP_URL)
            if self.browser.contexts:
                self.context = self.browser.contexts[0]
            else:
                self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            print(f"[OK] Connected to Chrome")
            return True
        except Exception as e:
            print(f"[ERROR] Cannot connect to Chrome: {e}")
            print("Make sure Chrome is running with --remote-debugging-port=9222")
            return False

    async def scrape_type(
        self,
        listing_type: str,
        start_page: int = 1,
        max_pages: Optional[int] = None,
    ) -> int:
        """Scrape all pages of a listing type (sale or rent). Returns total records scraped."""

        base_url = BASE_URLS[listing_type]
        progress = load_progress()
        total_new = 0
        consecutive_empty = 0
        consecutive_no_new = 0
        page_num = start_page

        print(f"\n{'='*70}")
        print(f"  Scraping: {listing_type.upper()} listings")
        print(f"  Start page: {page_num}")
        print(f"{'='*70}\n")

        while True:
            if max_pages and (page_num - start_page) >= max_pages:
                print(f"[STOP] Reached max_pages limit ({max_pages})")
                break

            url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
            print(f"[Page {page_num}] {url}")

            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                # Wait for first article to appear (confirms listings loaded)
                try:
                    await self.page.wait_for_selector("article", timeout=10_000)
                except Exception:
                    pass  # No articles — will be caught as empty page below
                delay = random.uniform(*PAGE_DELAY)
                print(f"  Waiting {delay:.1f}s...")
                await asyncio.sleep(delay)

                html = await self.page.content()
                records = parse_listings_page(html, listing_type)

                if not records:
                    consecutive_empty += 1
                    consecutive_no_new += 1
                    print(f"  [EMPTY] No records (consecutive empty: {consecutive_empty})")
                    if consecutive_empty >= 2:
                        print("[STOP] Two consecutive empty pages — end of results")
                        break
                else:
                    consecutive_empty = 0
                    new_count = append_records(records)
                    total_new += new_count
                    if new_count == 0:
                        consecutive_no_new += 1
                        print(f"  [DUPE] {len(records)} found but all duplicates (consecutive no-new: {consecutive_no_new})")
                        if consecutive_no_new >= 3:
                            print("[STOP] 3 consecutive pages with no new listings — end of real results")
                            break
                    else:
                        consecutive_no_new = 0
                        print(f"  [OK] {new_count} new listings saved (total so far: {total_new})")

                # Update progress
                progress[listing_type]["last_page"] = page_num
                progress[listing_type]["total_records"] += len(records)
                save_progress(progress)

                page_num += 1

            except KeyboardInterrupt:
                print("\n[INTERRUPTED] Saving progress and stopping...")
                break
            except Exception as e:
                print(f"  [ERROR] Page {page_num}: {e}")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    print("[STOP] Too many errors, stopping this listing type")
                    break
                await asyncio.sleep(5)
                page_num += 1

        return total_new

    async def close(self):
        if self.page:
            await self.page.close()


# ---------------------------------------------------------------------------
# Convenience function for running from run_palm_listings.py
# ---------------------------------------------------------------------------

async def run_scrape(listing_types: List[str] = None, max_pages: int = None, resume: bool = True):
    if listing_types is None:
        listing_types = ["sale", "rent"]

    scraper = PalmListingsScraper()
    if not await scraper.connect():
        return

    progress = load_progress() if resume else {"sale": {"last_page": 0}, "rent": {"last_page": 0}}
    grand_total = 0

    for ltype in listing_types:
        start_page = (progress[ltype].get("last_page", 0) + 1) if resume else 1
        total = await scraper.scrape_type(ltype, start_page=start_page, max_pages=max_pages)
        grand_total += total
        print(f"\n[{ltype.upper()} DONE] {total} new records scraped")

    await scraper.close()

    print(f"\n{'='*70}")
    print(f"  SCRAPING COMPLETE")
    print(f"  Total new records: {grand_total}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"{'='*70}")

    # Print summary of what was collected
    if OUTPUT_PATH.exists():
        df = pd.read_csv(OUTPUT_PATH)
        print(f"\nDatabase summary:")
        print(f"  Total listings: {len(df):,}")
        print(f"  Unique buildings: {df['building_name'].nunique():,}")
        print(f"  With bedrooms: {df['bedrooms'].notna().sum():,}")
        print(f"\nTop buildings by listing count:")
        print(df['building_name'].value_counts().head(15).to_string())
