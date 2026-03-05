"""
Property Monitor Scraper - Hybrid Mode Launcher
================================================
Launches Chrome with remote debugging, then connects to scrape data.
You handle login + Cloudflare. Script handles extraction.
"""

import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding FIRST before any prints
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass  # Already wrapped or not a real console

# Add property_research_agent to path
sys.path.insert(0, str(Path(__file__).parent / "property_research_agent"))

from unit_number_scraper import UnitNumberScraper, launch_chrome_with_debugging


async def main():
    print()
    print("=" * 70)
    print("  PROPERTY MONITOR UNIT NUMBER SCRAPER")
    print("  Hybrid Mode: You browse, script extracts")
    print("=" * 70)
    print()
    print("  HOW IT WORKS:")
    print("  1. Script opens Chrome with a special debug connection")
    print("  2. YOU log in to Property Monitor manually")
    print("  3. YOU pass the Cloudflare challenge")
    print("  4. YOU search for the building and apply filters")
    print("  5. When the results table is visible, press ENTER here")
    print("  6. Script automatically extracts ALL pages of data")
    print()
    print("=" * 70)
    print()
    print("  Options:")
    print("    1. Test run (scrape first 2 pages only)")
    print("    2. Full scrape (ALL pages)")
    print()

    try:
        choice = input("  Enter choice [1/2]: ").strip()
    except:
        choice = "1"

    test_mode = choice != "2"

    if test_mode:
        print("\n  [MODE] Test run - will scrape first 2 pages only")
    else:
        print("\n  [MODE] Full scrape - will scrape ALL pages")

    # Step 1: Launch Chrome with remote debugging
    print()
    print("-" * 70)
    print("  STEP 1: Launching Chrome...")
    print("-" * 70)

    chrome_process = launch_chrome_with_debugging()

    print()
    print("  Chrome should have opened and navigated to Property Monitor.")
    print("  If Chrome didn't open, you may already have Chrome running.")
    print("  Close ALL Chrome windows first, then try again.")
    print()
    print("-" * 70)
    print("  STEP 2: Do these steps in the Chrome window:")
    print("-" * 70)
    print()
    print("    a) Log in with your Property Monitor credentials")
    print("    b) Complete the Cloudflare challenge (tick the box)")
    print("    c) Navigate to the transactions/search page")
    print("    d) Set data points: Title Deed + Oqood only")
    print("    e) Search for your building")
    print("    f) Set date: All Historical Data")
    print("    g) Set per page: 250")
    print("    h) Wait for the results TABLE to appear")
    print()
    print("-" * 70)

    input("  >>> When the table is showing, press ENTER here to start scraping... ")

    # Step 2: Connect and scrape
    print()
    print("-" * 70)
    print("  STEP 3: Connecting to your browser and starting extraction...")
    print("-" * 70)
    print()

    scraper = UnitNumberScraper()
    await scraper.run(test_mode=test_mode)

    print()
    print("=" * 70)
    print("  ALL DONE!")
    print("=" * 70)
    print()
    print("  Next steps:")
    print("    1. Check scraped_data/ folder for your CSV files")
    print("    2. Run: python merge_unit_numbers.py")
    print("       (merges unit numbers with your title deed data)")
    print("    3. Restart the Streamlit app to use enriched data")
    print()
    input("  Press ENTER to exit...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Cancelled by user")
    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        input("\nPress ENTER to exit...")
