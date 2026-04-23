"""
Regression tests for PR 2 -- Bedroom accuracy.

Covers:
  1. Reidin _clean_bedrooms preserves "2+1" / "1+Study" / "3+M" compounds,
     still returns "Studio" for studio variants, still handles "2 BR" / "3".
  2. Bayut listing_parser drops rows that have no bedrooms AND no size AND
     no unit_type (view-only noise).
  3. validate_unit_type logs once per unknown building.

Run: python test_bedroom_accuracy.py
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "bayut_scraper"))

from reidin_processor import _clean_bedrooms
from bayut_scraper.listing_parser import parse_listings_page
from building_intelligence import (
    validate_unit_type,
    _UNKNOWN_VALIDATION_BUILDINGS,
)


failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------------
# 1. Reidin bedroom normalization preserves compound layouts
# ---------------------------------------------------------------------------
print("\n[1] Reidin _clean_bedrooms")

cases = [
    ("Studio",         "Studio"),
    ("studio",         "Studio"),
    ("S",              "Studio"),
    ("0",              "Studio"),
    ("1",              "1"),
    ("2",              "2"),
    ("3",              "3"),
    ("2 BR",           "2"),
    ("3 bedroom",      "3"),
    ("2+1",            "2+1"),
    ("2 + 1",          "2+1"),
    ("3+M",            "3+M"),
    ("3 + Maid",       "3+M"),
    ("3+maids",        "3+M"),
    ("1+Study",        "1+Study"),
    ("1 + study",      "1+Study"),
    ("2 + maid",       "2+M"),
    ("4+M",            "4+M"),
    ("N/A",            None),
    ("",               None),
]

for raw, expected in cases:
    got = _clean_bedrooms(raw)
    check(
        f"{raw!r} -> {expected!r}",
        got == expected,
        f"got={got!r}",
    )

# ---------------------------------------------------------------------------
# 2. Bayut listing filter drops view-only rows
# ---------------------------------------------------------------------------
print("\n[2] Bayut listing filter")

view_only_html = """
<article class="property-card">
  <h2 class="title">Full Sea View Apartment</h2>
  <a href="/listing/123">View</a>
</article>
"""
view_only_rows = parse_listings_page(view_only_html, "Shoreline 9")
check(
    "view-only row is dropped",
    len(view_only_rows) == 0,
    f"got {len(view_only_rows)} rows: {view_only_rows!r}",
)

proper_html = """
<article class="property-card">
  <h2 class="title">2 Beds | 3 Baths | 1,550 sqft Full Sea View</h2>
  <a href="/listing/456">View</a>
</article>
"""
proper_rows = parse_listings_page(proper_html, "Shoreline 9")
check(
    "row with beds/size is kept",
    len(proper_rows) == 1,
    f"got {len(proper_rows)} rows",
)
if proper_rows:
    check("kept row has bedrooms=2",  proper_rows[0].get("bedrooms") == "2")
    check("kept row has size_sqft=1550.0", proper_rows[0].get("size_sqft") == 1550.0)

size_only_html = """
<article class="property-card">
  <p>1,200 sqft with palm view</p>
  <a href="/listing/789">View</a>
</article>
"""
size_only_rows = parse_listings_page(size_only_html, "Shoreline 9")
check(
    "size-only row is kept (useful for Priority 2.6 size-match)",
    len(size_only_rows) == 1,
    f"got {len(size_only_rows)} rows",
)

# ---------------------------------------------------------------------------
# 3. validate_unit_type logs once per unknown building
# ---------------------------------------------------------------------------
print("\n[3] validate_unit_type unknown-building warning")

_UNKNOWN_VALIDATION_BUILDINGS.clear()

buf = io.StringIO()
with redirect_stdout(buf):
    is_valid_1, _ = validate_unit_type("FakeBuilding_Nonexistent_XYZ", "2")
    is_valid_2, _ = validate_unit_type("FakeBuilding_Nonexistent_XYZ", "3")
    is_valid_3, _ = validate_unit_type("AnotherFakeBuilding_ABC", "1")

output = buf.getvalue()

check("first call to unknown building returns valid=True",   is_valid_1 is True)
check("second call to same building returns valid=True",     is_valid_2 is True)
check("first call to a different unknown building returns valid=True", is_valid_3 is True)
check(
    "first unknown building logged once",
    output.count("FakeBuilding_Nonexistent_XYZ") == 1,
    f"seen {output.count('FakeBuilding_Nonexistent_XYZ')} time(s)",
)
check(
    "second unknown building also logged",
    "AnotherFakeBuilding_ABC" in output,
)

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All bedroom-accuracy checks passed.")
