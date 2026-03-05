"""
Clean up existing PropertyFinder scraped leads CSV:
1. Remove entries without phone numbers
2. Remove entries without listing price
3. Remove duplicate properties (keep first occurrence, or --keep-lowest-price to keep lowest listing price)
4. Optionally remove permit_number column
"""

import csv
import re
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRAPED_DATA = PROJECT_ROOT / "scraped_data"
INPUT_CSV = SCRAPED_DATA / "propertyfinder_scraped_leads.csv"
BACKUP_CSV = SCRAPED_DATA / f"propertyfinder_scraped_leads.csv.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _parse_price_value(listing_price_str):
    """Extract numeric value from listing_price (e.g. '105;000 AED/year' -> 105000). Returns float or None."""
    if not listing_price_str or not isinstance(listing_price_str, str):
        return None
    digits = re.sub(r"[^0-9]", "", listing_price_str)
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def cleanup_csv(remove_permit_column=True, keep_lowest_price=False):
    """Clean up CSV file."""
    if not INPUT_CSV.exists():
        print(f"[ERROR] CSV not found: {INPUT_CSV}")
        return

    # Backup original
    shutil.copy(INPUT_CSV, BACKUP_CSV)
    print(f"[BACKUP] Created: {BACKUP_CSV}")

    # Read all rows
    with open(INPUT_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    print(f"[LOADED] {len(rows)} rows")

    # Filter: Remove rows without phone
    rows_with_phone = []
    for row in rows:
        phone = (row.get("phone") or "").strip()
        if phone:
            rows_with_phone.append(row)
        else:
            print(f"  [REMOVED] No phone: {row.get('building_name', '')} {row.get('unit_number', '')}")

    print(f"[FILTER] {len(rows_with_phone)} rows with phone numbers")

    # Filter: Remove rows without listing price
    rows_with_price = []
    for row in rows_with_phone:
        price_str = (row.get("listing_price") or "").strip()
        if price_str:
            rows_with_price.append(row)
        else:
            print(f"  [REMOVED] No listing price: {row.get('building_name', '')} {row.get('unit_number', '')}")

    print(f"[FILTER] {len(rows_with_price)} rows with listing price")

    # Deduplicate: by (unit, building, owner). Keep first occurrence, or keep lowest price if --keep-lowest-price
    if keep_lowest_price:
        from collections import defaultdict
        groups = defaultdict(list)
        for row in rows_with_price:
            unit = row.get("unit_number", "").strip()
            building = row.get("building_name", "").strip()
            owner = row.get("owner_name", "").strip()
            key = (unit, building, owner)
            groups[key].append(row)
        unique_rows = []
        for key, group in groups.items():
            unit, building, owner = key
            if len(group) == 1:
                unique_rows.append(group[0])
            else:
                best = min(group, key=lambda r: _parse_price_value(r.get("listing_price")) or float("inf"))
                unique_rows.append(best)
                for r in group:
                    if r is not best:
                        print(f"  [REMOVED] Duplicate (kept lowest price): {building} {unit} ({owner})")
        print(f"[DEDUP] {len(unique_rows)} unique properties (kept lowest price per property)")
    else:
        seen = set()
        unique_rows = []
        for row in rows_with_price:
            unit = row.get("unit_number", "").strip()
            building = row.get("building_name", "").strip()
            owner = row.get("owner_name", "").strip()
            key = (unit, building, owner)

            if key not in seen:
                seen.add(key)
                unique_rows.append(row)
            else:
                print(f"  [REMOVED] Duplicate: {building} {unit} ({owner})")

        print(f"[DEDUP] {len(unique_rows)} unique properties")

    # Optionally remove permit_number column
    if remove_permit_column and "permit_number" in headers:
        headers = [h for h in headers if h != "permit_number"]
        for row in unique_rows:
            row.pop("permit_number", None)
        print("[REMOVED] permit_number column")

    # Write cleaned CSV
    with open(INPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(unique_rows)

    print(f"\n[DONE] Cleaned CSV: {INPUT_CSV}")
    print(f"  Original rows:      {len(rows)}")
    print(f"  Without phone:      {len(rows) - len(rows_with_phone)} removed")
    print(f"  Without price:      {len(rows_with_phone) - len(rows_with_price)} removed")
    print(f"  Duplicates:        {len(rows_with_price) - len(unique_rows)} removed")
    print(f"  Final rows:         {len(unique_rows)}")
    print(f"  Backup saved:       {BACKUP_CSV}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Clean up PropertyFinder CSV")
    parser.add_argument("--keep-permit", action="store_true", help="Keep permit_number column")
    parser.add_argument("--keep-lowest-price", action="store_true", help="When deduping, keep the row with the lowest listing price per property")
    args = parser.parse_args()

    cleanup_csv(remove_permit_column=not args.keep_permit, keep_lowest_price=args.keep_lowest_price)
