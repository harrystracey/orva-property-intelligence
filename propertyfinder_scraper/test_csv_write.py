"""
Regression tests for PR 4 -- PropertyFinder CSV write safety.

Covers:
  1. Values containing commas, newlines, and double quotes round-trip
     through save_to_csv -> csv.reader without field-splitting.
  2. Values with commas are no longer mutated to semicolons.
  3. Re-reading the file after multiple appends yields the same rows back.
  4. load_already_scraped_urls still recognises URLs after QUOTE_ALL write.

Run:
    python propertyfinder_scraper/test_csv_write.py
"""

import csv
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scraper as pf_scraper  # the module we're testing

failures: list[str] = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------------
# Redirect OUTPUT_CSV / PROGRESS_FILE to a temp directory for this test run
# ---------------------------------------------------------------------------
tmpdir = tempfile.mkdtemp(prefix="pf_csv_test_")
tmp_csv = Path(tmpdir) / "propertyfinder_scraped_leads.csv"

# Monkey-patch module constants used inside save_to_csv / ensure_scraped_data_dir
pf_scraper.SCRAPED_DATA = Path(tmpdir)
pf_scraper.OUTPUT_CSV = tmp_csv


# Build a minimal scraper instance that only exercises save_to_csv
class FakeScraper:
    saved_count = 0

    save_to_csv = pf_scraper.PFRentalScraper.save_to_csv if hasattr(
        pf_scraper, "PFRentalScraper"
    ) else None


# Find the real class
scraper_cls = None
for name in dir(pf_scraper):
    obj = getattr(pf_scraper, name)
    if isinstance(obj, type) and "Scraper" in name and hasattr(obj, "save_to_csv"):
        scraper_cls = obj
        break

assert scraper_cls is not None, "Could not locate scraper class with save_to_csv"


# Minimal instance: attach saved_count so the method runs
class TinyScraper(scraper_cls):  # type: ignore[misc,valid-type]
    def __init__(self):
        self.saved_count = 0


# ---------------------------------------------------------------------------
# 1. Values with commas / newlines / quotes round-trip cleanly
# ---------------------------------------------------------------------------
print("\n[1] Round-trip: commas, newlines, quotes")

tricky_row = {
    "unit_number": "S-607",
    "building_name": 'Shoreline 9 "Al Masalli"',
    "zone": "Palm Jumeirah",
    "size_sqm": "150",
    "land_no": "12345",
    "owner_name": "Smith, John Jr.",
    "phone": "971551234567",
    "property_value": "1,500,000",
    "room_type": "2 BR",
    "permit_type": "DLD",
    "listing_url": "https://example.com/listing/1",
    "listing_price": "AED 200,000/yr",
    "listing_type": "Rent",
    "furnished": "Yes",
    "scraped_at": "2026-04-23T12:00:00\nnewline-in-field",
}

s = TinyScraper()
s.save_to_csv(tricky_row)

with open(tmp_csv, "r", encoding="utf-8", newline="") as f:
    rows = list(csv.reader(f))

check(
    "file has header + 1 data row (no row split on embedded comma/newline)",
    len(rows) == 2,
    f"got {len(rows)} rows",
)
if len(rows) >= 2:
    data = dict(zip(rows[0], rows[1]))
    check("owner_name preserved with comma intact",  data.get("owner_name") == "Smith, John Jr.")
    check("property_value preserved with commas",    data.get("property_value") == "1,500,000")
    check("building_name preserved with embedded quotes", data.get("building_name") == 'Shoreline 9 "Al Masalli"')
    check(
        "scraped_at preserves embedded newline",
        data.get("scraped_at") == "2026-04-23T12:00:00\nnewline-in-field",
        f"got {data.get('scraped_at')!r}",
    )

# ---------------------------------------------------------------------------
# 2. Commas are no longer replaced with semicolons
# ---------------------------------------------------------------------------
print("\n[2] No more ',' -> ';' mutation")

with open(tmp_csv, "r", encoding="utf-8") as f:
    raw = f.read()
check(
    "raw file contains the real 'Smith, John' (not 'Smith; John')",
    "Smith, John" in raw and "Smith; John" not in raw,
)

# ---------------------------------------------------------------------------
# 3. Multiple appends compose correctly; dedup loader still finds URLs
# ---------------------------------------------------------------------------
print("\n[3] Multiple appends + dedup loader")

row2 = dict(tricky_row)
row2["unit_number"] = "S-608"
row2["listing_url"] = "https://example.com/listing/2"
row2["owner_name"] = 'Doe, "Jane" M.'
s.save_to_csv(row2)

with open(tmp_csv, "r", encoding="utf-8", newline="") as f:
    rows = list(csv.reader(f))

check("file has header + 2 rows", len(rows) == 3, f"got {len(rows)} rows")
if len(rows) >= 3:
    data2 = dict(zip(rows[0], rows[2]))
    check(
        "second row owner_name preserved with embedded quotes",
        data2.get("owner_name") == 'Doe, "Jane" M.',
        f"got {data2.get('owner_name')!r}",
    )

urls = pf_scraper.load_already_scraped_urls()
check(
    "load_already_scraped_urls returns both URLs",
    {"https://example.com/listing/1", "https://example.com/listing/2"}.issubset(urls),
    f"got {urls}",
)

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All PF CSV safety checks passed.")
