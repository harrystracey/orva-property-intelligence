"""
CLI runner for PropSpace leads scraper.

SETUP:
  1. Launch Chrome: python bayut_scraper/run_bayut_scrape.py --launch-chrome
  2. Log into crm.propspace.com/leads/
  3. Apply filters in Chrome (location, pool, etc.) — the scraper reads the current page
  4. Do NOT touch Chrome while running

Usage:
  python propspace_scraper/run_propspace_scrape.py                # Reads current Chrome page (all pages)
  python propspace_scraper/run_propspace_scrape.py --max-pages 5  # Stop after 5 pages (testing)
  python propspace_scraper/run_propspace_scrape.py --append       # Append to existing CSV

The --location and --all flags are informational only (logged in header).
Filters must be applied manually in the Chrome window.
"""

import asyncio
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from propspace_scraper.propspace_scraper import scrape_leads, save_to_csv, OUTPUT_PATH


def main():
    parser = argparse.ArgumentParser(description="PropSpace Leads Scraper")
    parser.add_argument("--location", default="Palm Jumeirah",
                        help="Location filter (default: 'Palm Jumeirah', use '' for all locations)")
    parser.add_argument("--all", action="store_true",
                        help="Scrape all leads, not just lead pool (claimed + unclaimed)")
    parser.add_argument("--detail", action="store_true",
                        help="Click each lead to extract beds/price requirements (slower)")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Stop after N pages (default: all pages)")
    parser.add_argument("--append", action="store_true",
                        help="Append to existing CSV instead of overwriting")
    args = parser.parse_args()

    pool_only = not args.all

    print(f"\nPropSpace Scraper")
    print(f"  Location : {args.location or 'All'}")
    print(f"  Pool only: {pool_only}")
    print(f"  Detail   : {args.detail}")
    print(f"  Output   : {OUTPUT_PATH}")
    print()

    try:
        input("Press ENTER to start (make sure Chrome is open and logged into PropSpace)... ")
    except KeyboardInterrupt:
        print("\n[CANCELLED]")
        return

    leads = asyncio.run(scrape_leads(
        location=args.location,
        pool_only=pool_only,
        max_pages=args.max_pages,
        detail=args.detail,
    ))

    if leads:
        saved = save_to_csv(leads, append=args.append)
        print(f"\nDone! {len(leads)} leads scraped, {saved} saved to CSV.")
        print(f"File: {OUTPUT_PATH}")
        print()
        # Quick summary
        from collections import Counter
        types = Counter(l["lead_type"] for l in leads)
        statuses = Counter(l["sub_status"] for l in leads)
        locations = Counter(l["sub_location"] for l in leads if l["sub_location"])
        print("Lead types   :", dict(types))
        print("Sub-statuses :", dict(statuses))
        print("Top locations:", dict(locations.most_common(10)))
    else:
        print("\nNo leads scraped. Check Chrome is open and logged into PropSpace.")


if __name__ == "__main__":
    main()
