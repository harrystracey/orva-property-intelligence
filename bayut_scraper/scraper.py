"""
Bayut Scraper - Playwright Automation with Chrome Debug Mode
Uses same pattern as Property Monitor scraper (user logs in, script automates extraction).
"""

import asyncio
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import random
import json
import os
import subprocess
import sys
from typing import List, Dict, Optional

from .bayut_urls import get_building_guide_url, get_floor_plan_url, get_listings_url, get_all_buildings
from .building_guide_parser import parse_building_guide
from .floor_plan_parser import parse_floor_plan_page
from .listing_parser import parse_listings_page

# Chrome paths
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"

# Human-like delays
HUMAN_DELAY = (5.0, 10.0)  # 5-10 seconds between pages
PAGE_LOAD_TIMEOUT = 30000  # 30 seconds


class BayutScraper:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.results = []
        self.raw_html_dir = Path("bayut_scraper/raw_html")
        self.raw_html_dir.mkdir(parents=True, exist_ok=True)
    
    async def connect_to_chrome(self):
        """Connect to existing Chrome instance via CDP."""
        print("[CONNECTING] Connecting to Chrome debug port...")
        
        playwright = await async_playwright().start()
        
        try:
            self.browser = await playwright.chromium.connect_over_cdp(CDP_URL)
            print(f"[OK] Connected to Chrome (contexts: {len(self.browser.contexts)})")
            
            # Use existing context or create new
            if self.browser.contexts:
                self.context = self.browser.contexts[0]
                print(f"[OK] Using existing context (pages: {len(self.context.pages)})")
            else:
                self.context = await self.browser.new_context()
                print("[OK] Created new context")
            
            # Get active page or create new
            if self.context.pages:
                self.page = self.context.pages[0]
                print(f"[OK] Using existing page: {self.page.url}")
            else:
                self.page = await self.context.new_page()
                print("[OK] Created new page")
            
            return True
        
        except Exception as e:
            print(f"[ERROR] Failed to connect: {e}")
            print(f"[HINT] Make sure Chrome is running with --remote-debugging-port={CDP_PORT}")
            return False
    
    async def human_delay(self, min_sec: float = None, max_sec: float = None):
        """Random human-like delay."""
        if min_sec is None:
            min_sec, max_sec = HUMAN_DELAY
        delay = random.uniform(min_sec, max_sec)
        print(f"  [DELAY] Waiting {delay:.1f}s...")
        await asyncio.sleep(delay)
    
    async def save_html(self, content: str, filename: str):
        """Save raw HTML for debugging."""
        filepath = self.raw_html_dir / f"{filename}.html"
        filepath.write_text(content, encoding='utf-8')
        print(f"  [SAVED] {filepath}")
    
    async def scrape_building_guide(self, building_name: str) -> List[Dict]:
        """Scrape building guide page for unit type → view mappings."""
        url = get_building_guide_url(building_name)
        if not url:
            print(f"  [SKIP] No building guide URL for {building_name}")
            return []
        
        print(f"\n[BUILDING GUIDE] {building_name}")
        print(f"  URL: {url}")
        
        try:
            # Navigate to page
            await self.page.goto(url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
            await self.human_delay(3, 5)
            
            # Get page text
            content = await self.page.content()
            page_text = await self.page.evaluate('() => document.body.innerText')
            
            # Save raw HTML
            await self.save_html(content, f"{building_name.replace(' ', '_')}_guide")
            
            # Parse
            results = parse_building_guide(page_text, building_name)
            print(f"  [EXTRACTED] {len(results)} unit types")
            
            return results
        
        except Exception as e:
            print(f"  [ERROR] {e}")
            return []
    
    async def scrape_floor_plan(self, building_name: str) -> List[Dict]:
        """Scrape floor plan page for unit type → bedroom → bathroom mappings."""
        url = get_floor_plan_url(building_name)
        if not url:
            print(f"  [SKIP] No floor plan URL for {building_name}")
            return []
        
        print(f"\n[FLOOR PLAN] {building_name}")
        print(f"  URL: {url}")
        
        try:
            # Navigate to page
            await self.page.goto(url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
            await self.human_delay(3, 5)
            
            # Get HTML
            content = await self.page.content()
            
            # Save raw HTML
            await self.save_html(content, f"{building_name.replace(' ', '_')}_floorplan")
            
            # Parse
            results = parse_floor_plan_page(content, building_name)
            print(f"  [EXTRACTED] {len(results)} unit types")
            
            return results
        
        except Exception as e:
            print(f"  [ERROR] {e}")
            return []
    
    async def scrape_listings(self, building_name: str, listing_type: str = 'rent', max_pages: int = 3) -> List[Dict]:
        """Scrape listing pages for unit-level data."""
        url = get_listings_url(building_name, listing_type)
        if not url:
            print(f"  [SKIP] No listings URL for {building_name}")
            return []
        
        print(f"\n[LISTINGS] {building_name} ({listing_type})")
        print(f"  URL: {url}")
        
        all_results = []
        
        try:
            for page_num in range(1, max_pages + 1):
                page_url = f"{url}?page={page_num}" if page_num > 1 else url
                print(f"  [PAGE {page_num}] Loading...")
                
                # Navigate
                await self.page.goto(page_url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
                await self.human_delay(5, 8)  # Longer delay for listings
                
                # Get HTML
                content = await self.page.content()
                
                # Save raw HTML
                await self.save_html(content, f"{building_name.replace(' ', '_')}_listings_{listing_type}_p{page_num}")
                
                # Parse
                results = parse_listings_page(content, building_name)
                print(f"  [EXTRACTED] {len(results)} listings")
                
                all_results.extend(results)
                
                # Check if there's a next page button
                next_button = await self.page.query_selector('button[aria-label*="Next"], a[aria-label*="Next"]')
                if not next_button or page_num >= max_pages:
                    break
                
                await self.human_delay(7, 12)  # Extra delay between pages
            
            return all_results
        
        except Exception as e:
            print(f"  [ERROR] {e}")
            return all_results
    
    async def scrape_building(self, building_name: str, include_listings: bool = False):
        """Scrape all data for a single building."""
        print("=" * 70)
        print(f"BUILDING: {building_name}")
        print("=" * 70)
        
        # 1. Floor plan (fast, structured)
        floor_plan_data = await self.scrape_floor_plan(building_name)
        self.results.extend(floor_plan_data)
        
        await self.human_delay()
        
        # 2. Building guide (fast, text parsing)
        guide_data = await self.scrape_building_guide(building_name)
        self.results.extend(guide_data)
        
        # 3. Listings (slow, optional)
        if include_listings:
            await self.human_delay()
            listing_data_rent = await self.scrape_listings(building_name, 'rent', max_pages=2)
            self.results.extend(listing_data_rent)
            
            await self.human_delay()
            listing_data_sale = await self.scrape_listings(building_name, 'sale', max_pages=2)
            self.results.extend(listing_data_sale)
    
    async def scrape_all_buildings(self, mode: str = 'guides_only'):
        """Scrape all buildings in order."""
        buildings = get_all_buildings()
        print(f"\n[TOTAL BUILDINGS] {len(buildings)}\n")
        
        include_listings = mode == 'full'
        
        for idx, building in enumerate(buildings, 1):
            print(f"\n\n[PROGRESS] {idx}/{len(buildings)}")
            await self.scrape_building(building, include_listings=include_listings)
            
            # Save progress after each building
            self.save_results()
            
            # Delay between buildings
            if idx < len(buildings):
                await self.human_delay(8, 15)
    
    def save_results(self):
        """Save results to CSV."""
        if not self.results:
            print("[WARNING] No results to save")
            return
        
        df = pd.DataFrame(self.results)
        output_path = Path("data/bayut_unit_types.csv")
        output_path.parent.mkdir(exist_ok=True)
        
        df.to_csv(output_path, index=False, encoding='utf-8')
        print(f"\n[SAVED] {output_path} ({len(df)} records)")
    
    async def close(self):
        """Close browser connection."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()


def find_chrome() -> str:
    """Find Chrome executable."""
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
        sys.exit(1)
    
    print(f"[CHROME] Found at: {chrome_path}")
    print(f"[CHROME] Launching with remote debugging on port {CDP_PORT}...")
    
    # Create debug profile
    debug_profile = Path("bayut_scraper/chrome_debug_profile")
    debug_profile.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        chrome_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={debug_profile.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        "https://www.bayut.com/"
    ]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
    )
    
    print(f"[OK] Chrome launched (PID: {process.pid})")
    print("[WAIT] Giving Chrome 5 seconds to initialize...")
    time.sleep(5)
    
    return process
