"""
Bayut Scraper - CLI Entry Point
Scrape Bayut.com for unit type classifications and view data.
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from bayut_scraper.scraper import BayutScraper, launch_chrome_with_debugging
from bayut_scraper.bayut_urls import get_all_buildings


async def main():
    parser = argparse.ArgumentParser(description='Bayut Unit Type Scraper')
    parser.add_argument('--mode', choices=['building_guides', 'floor_plans', 'listings', 'full', 'guides_only'],
                       default='guides_only',
                       help='Scraping mode: building_guides, floor_plans, listings, full, or guides_only (default)')
    parser.add_argument('--building', type=str, help='Scrape single building only')
    parser.add_argument('--limit', type=int, help='Limit number of buildings to scrape')
    parser.add_argument('--merge', action='store_true', help='Merge Bayut data into unit registry')
    parser.add_argument('--launch-chrome', action='store_true', help='Launch Chrome with debug mode')
    
    args = parser.parse_args()
    
    # Handle merge mode
    if args.merge:
        print("\n" + "=" * 70)
        print("  MERGING BAYUT DATA INTO UNIT REGISTRY")
        print("=" * 70 + "\n")
        await merge_bayut_data()
        return
    
    # Launch Chrome if requested
    if args.launch_chrome:
        print("\n" + "=" * 70)
        print("  BAYUT SCRAPER - Chrome Launch")
        print("=" * 70 + "\n")
        launch_chrome_with_debugging()
        print("\n[OK] Chrome launched!")
        print("\nNext steps:")
        print("  1. Navigate to Bayut.com in the Chrome window")
        print("  2. If prompted, dismiss any popups/cookies")
        print("  3. Run this script again WITHOUT --launch-chrome to start scraping")
        print("\nExample:")
        print("  python bayut_scraper/run_bayut_scrape.py --mode guides_only")
        return
    
    # Display scraping info
    print("\n" + "=" * 70)
    print("  BAYUT UNIT TYPE SCRAPER")
    print("=" * 70 + "\n")
    
    buildings = get_all_buildings()
    
    if args.building:
        buildings = [b for b in buildings if args.building.lower() in b.lower()]
        if not buildings:
            print(f"[ERROR] Building '{args.building}' not found in URL mappings")
            print("\nAvailable buildings:")
            for b in get_all_buildings()[:10]:
                print(f"  - {b}")
            print(f"  ... and {len(get_all_buildings()) - 10} more")
            return
    
    if args.limit:
        buildings = buildings[:args.limit]
    
    print(f"Mode: {args.mode}")
    print(f"Buildings to scrape: {len(buildings)}")
    if args.building:
        print(f"Selected building: {buildings[0]}")
    print()
    
    # Confirm before scraping
    if args.mode == 'full':
        print("[WARNING] Full mode includes listings - this will take a long time!")
        print("[WARNING] Recommended to start with 'guides_only' first.")
        print()
    
    print("Make sure:")
    print("  1. Chrome is running with remote debugging (port 9222)")
    print("  2. You've dismissed any Bayut popups/cookies")
    print()
    
    try:
        input("Press ENTER to start scraping (or Ctrl+C to cancel)... ")
    except KeyboardInterrupt:
        print("\n[CANCELLED]")
        return
    
    # Initialize scraper
    scraper = BayutScraper()
    
    # Connect to Chrome
    print("\n" + "-" * 70)
    print("  CONNECTING TO CHROME")
    print("-" * 70 + "\n")
    
    if not await scraper.connect_to_chrome():
        print("\n[ERROR] Could not connect to Chrome")
        print("\nTroubleshooting:")
        print("  1. Make sure Chrome is running")
        print("  2. Run with --launch-chrome first:")
        print("     python bayut_scraper/run_bayut_scrape.py --launch-chrome")
        print("  3. Then run again to start scraping")
        return
    
    # Run scraping
    print("\n" + "-" * 70)
    print("  STARTING SCRAPING")
    print("-" * 70 + "\n")
    
    try:
        if args.building:
            # Single building mode
            include_listings = args.mode in ['listings', 'full']
            await scraper.scrape_building(buildings[0], include_listings=include_listings)
        else:
            # All buildings mode
            scrape_mode = 'full' if args.mode == 'full' else 'guides_only'
            await scraper.scrape_all_buildings(mode=scrape_mode)
        
        # Save results
        scraper.save_results()
        
        print("\n" + "=" * 70)
        print("  SCRAPING COMPLETE!")
        print("=" * 70 + "\n")
        print(f"Total records extracted: {len(scraper.results)}")
        print(f"Output file: data/bayut_unit_types.csv")
        print(f"Raw HTML saved to: bayut_scraper/raw_html/")
        print()
        print("Next steps:")
        print("  1. Review the CSV file")
        print("  2. Run merge to integrate with unit registry:")
        print("     python bayut_scraper/run_bayut_scrape.py --merge")
    
    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Scraping interrupted by user")
        print("Saving partial results...")
        scraper.save_results()
    
    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        print("\nSaving partial results...")
        scraper.save_results()
    
    finally:
        await scraper.close()


async def merge_bayut_data():
    """Merge Bayut unit types into the unit registry."""
    import pandas as pd
    from pathlib import Path
    
    bayut_path = Path("data/bayut_unit_types.csv")
    registry_path = Path("data/unit_registry.csv")
    
    if not bayut_path.exists():
        print(f"[ERROR] Bayut data not found: {bayut_path}")
        print("Run scraping first:")
        print("  python bayut_scraper/run_bayut_scrape.py --mode guides_only")
        return
    
    if not registry_path.exists():
        print(f"[ERROR] Unit registry not found: {registry_path}")
        print("Run registry builder first:")
        print("  python build_unit_registry.py")
        return
    
    print(f"[LOADING] Bayut data from {bayut_path}")
    bayut_df = pd.read_csv(bayut_path)
    print(f"  {len(bayut_df)} records")
    
    print(f"[LOADING] Unit registry from {registry_path}")
    registry_df = pd.read_csv(registry_path)
    print(f"  {len(registry_df)} units")
    
    # Create type → specs lookup from Bayut data
    print("\n[BUILDING] Type lookup table...")
    type_specs = {}
    for _, row in bayut_df.iterrows():
        building = row['building']
        unit_type = row['unit_type']
        if pd.isna(unit_type):
            continue
        
        key = (building, unit_type)
        if key not in type_specs:
            type_specs[key] = {
                'bedrooms': row.get('bedrooms'),
                'bathrooms': row.get('bathrooms'),
                'size_sqft': row.get('size_sqft'),
                'view': row.get('view'),
            }
    
    print(f"  {len(type_specs)} unique (building, type) combinations")
    
    # Match registry units to types
    print("\n[MATCHING] Units to types...")
    matches = 0
    registry_df['unit_type_bayut'] = None
    registry_df['view_bayut'] = None
    
    for idx, unit in registry_df.iterrows():
        building = unit['building_name']
        bedrooms = str(unit['bedrooms']) if pd.notna(unit['bedrooms']) else None
        size = unit['size_sqft']
        
        if not bedrooms or pd.isna(size):
            continue
        
        # Find matching type in Bayut data for this building
        best_match = None
        best_score = float('inf')
        
        for (type_building, type_letter), specs in type_specs.items():
            if type_building != building:
                continue
            
            # Match by bedroom count
            if specs['bedrooms'] != bedrooms:
                continue
            
            # Match by size (closest)
            if pd.notna(specs['size_sqft']):
                size_diff = abs(size - specs['size_sqft'])
                if size_diff < best_score:
                    best_score = size_diff
                    best_match = (type_letter, specs)
        
        # If match found and size is close (within 200 sqft)
        if best_match and best_score < 200:
            type_letter, specs = best_match
            registry_df.at[idx, 'unit_type_bayut'] = type_letter
            if pd.notna(specs['view']):
                registry_df.at[idx, 'view_bayut'] = specs['view']
            matches += 1
    
    print(f"  Matched {matches} units to Bayut types")
    
    # Update view column with Bayut views where available
    view_updates = 0
    for idx, row in registry_df.iterrows():
        if pd.notna(row['view_bayut']) and pd.isna(row['view']):
            registry_df.at[idx, 'view'] = row['view_bayut']
            registry_df.at[idx, 'confidence'] = 'BAYUT_MATCHED'
            view_updates += 1
    
    print(f"  Updated {view_updates} units with Bayut views")
    
    # Save updated registry
    output_path = Path("data/unit_registry_with_bayut.csv")
    registry_df.to_csv(output_path, index=False)
    print(f"\n[SAVED] {output_path}")
    
    # Stats
    print("\n" + "=" * 70)
    print("  MERGE STATISTICS")
    print("=" * 70)
    print(f"Total units: {len(registry_df)}")
    print(f"Units matched to Bayut types: {matches} ({100*matches/len(registry_df):.1f}%)")
    print(f"Views added from Bayut: {view_updates}")
    print(f"Units with views (after merge): {registry_df['view'].notna().sum()}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
