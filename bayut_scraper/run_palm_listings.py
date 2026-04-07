"""
Run the Bayut Palm Jumeirah Listings Scraper.

Usage:
    python bayut_scraper/run_palm_listings.py                  # scrape both sale + rent
    python bayut_scraper/run_palm_listings.py --type sale      # sale only
    python bayut_scraper/run_palm_listings.py --type rent      # rent only
    python bayut_scraper/run_palm_listings.py --test           # 3 pages only (quick test)
    python bayut_scraper/run_palm_listings.py --resume         # continue from last saved page

Requires:
    Chrome running with --remote-debugging-port=9222
    Run: python bayut_scraper/run_bayut_scrape.py --launch-chrome
"""

import asyncio
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bayut_scraper.palm_listings_scraper import run_scrape, OUTPUT_PATH, PROGRESS_PATH


def main():
    parser = argparse.ArgumentParser(description="Bayut Palm Jumeirah Listings Scraper")
    parser.add_argument("--type", choices=["sale", "rent", "both"], default="both",
                        help="Which listing type to scrape (default: both)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: scrape only 3 pages per type")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Maximum pages to scrape per listing type")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Resume from last saved page (default: True)")
    parser.add_argument("--fresh", action="store_true",
                        help="Start fresh (ignore previous progress, overwrite output)")
    parser.add_argument("--headless", action="store_true",
                        help="Launch headless Chromium instead of connecting to Chrome CDP (for server use)")
    args = parser.parse_args()

    # Determine types to scrape
    if args.type == "both":
        listing_types = ["sale", "rent"]
    else:
        listing_types = [args.type]

    # Max pages
    max_pages = 3 if args.test else args.max_pages

    # Fresh start — only reset the types being re-scraped, never touch other types
    if args.fresh:
        import json, pandas as pd
        # Remove only the rows matching the types being reset from the CSV
        if OUTPUT_PATH.exists():
            try:
                existing = pd.read_csv(OUTPUT_PATH, encoding="utf-8", low_memory=False)
                kept = existing[~existing["listing_type"].isin(listing_types)]
                if kept.empty:
                    OUTPUT_PATH.unlink()
                    print(f"[RESET] Cleared {OUTPUT_PATH}")
                else:
                    kept.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
                    removed = len(existing) - len(kept)
                    print(f"[RESET] Removed {removed} {'/'.join(listing_types)} records from CSV ({len(kept)} other records kept)")
            except Exception as e:
                print(f"[WARN] Could not filter CSV: {e} — leaving it untouched")
        # Reset only the relevant type(s) in the progress file
        if PROGRESS_PATH.exists():
            try:
                progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
                for ltype in listing_types:
                    progress[ltype] = {"last_page": 0, "total_records": 0}
                PROGRESS_PATH.write_text(json.dumps(progress, indent=2), encoding="utf-8")
                print(f"[RESET] Progress reset for: {', '.join(listing_types)}")
            except Exception as e:
                print(f"[WARN] Could not update progress file: {e}")

    print("\n" + "=" * 70)
    print("  BAYUT PALM JUMEIRAH LISTINGS SCRAPER")
    print("=" * 70)
    print(f"  Types:     {', '.join(listing_types)}")
    print(f"  Max pages: {max_pages or 'unlimited'}")
    print(f"  Resume:    {not args.fresh}")
    print(f"  Output:    data/bayut_palm_listings.csv")
    print("=" * 70)
    print()

    if not args.test and not args.headless:
        print("Make sure Chrome is running with remote debugging on port 9222.")
        print("If not, run first:")
        print("  python bayut_scraper/run_bayut_scrape.py --launch-chrome")
        print()
        try:
            input("Press ENTER to start scraping (Ctrl+C to cancel)... ")
        except KeyboardInterrupt:
            print("\n[CANCELLED]")
            return

    asyncio.run(run_scrape(
        listing_types=listing_types,
        max_pages=max_pages,
        resume=not args.fresh,
        headless=args.headless,
    ))


if __name__ == "__main__":
    main()
