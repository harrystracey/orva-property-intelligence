# Bayut Scraper - Unit Registry Phase 2

Scrapes Bayut.com to fill gaps in the unit registry with unit type classifications and view data.

---

## Overview

The Bayut scraper extracts:
1. **Unit type specifications** (Type A-H → bedrooms + bathrooms + size) per building
2. **View data** per unit type (sea view, road view, garden view, etc.)
3. **Individual listing data** (unit numbers + views + sizes from active listings)

**Anti-Bot Strategy:** Uses Playwright with Chrome debug mode (same pattern as Property Monitor scraper). You browse manually, the script automates extraction.

---

## Architecture

```
bayut_scraper/
├── bayut_urls.py              # URL mapping for Palm Jumeirah buildings
├── building_guide_parser.py    # Parse building guide text for type→view mappings
├── floor_plan_parser.py        # Parse floor plan pages for type→bedroom→bathroom
├── listing_parser.py           # Parse individual listings for unit→view data
├── scraper.py                  # Playwright automation (Chrome debug mode)
├── run_bayut_scrape.py         # CLI entry point
├── test_parsers.py             # Parser validation tests
├── raw_html/                   # Saved HTML for debugging (auto-created)
└── chrome_debug_profile/       # Chrome profile for debug mode (auto-created)
```

---

## Data Sources on Bayut

### 1. Building Guide Pages (BEST - structured text with views)

**URL:** `https://www.bayut.com/buildings/{building-slug}/`

**Example:** https://www.bayut.com/buildings/al-haseer/ (Shoreline 12)

**Content:**
- "Type-F covers around 2,055 sq. ft. offering panoramic sea views"
- "Type-D 2-bed flats are the smallest with a covered area of 1,582 sq. ft."
- "Type E unit usually covers around 1,646 sq. ft. and offers views of the road"

**Extracts:** Type letter → bedrooms → size range → view description

### 2. Floor Plan Pages (structured type list)

**URL:** `https://www.bayut.com/floorplans/dubai/palm-jumeirah/{community}/{building}/`

**Example:** https://www.bayut.com/floorplans/dubai/palm-jumeirah/shoreline-apartments/al-hamri/

**Content:**
- Type B: 1 bedroom, 2 bathrooms
- Type D: 2 bedrooms, 3 bathrooms
- Type A: 3 bedrooms, 4 bathrooms

**Extracts:** Type letter → bedrooms → bathrooms

### 3. Individual Listings (unit numbers + views)

**URL:** `https://www.bayut.com/to-rent/apartments/dubai/palm-jumeirah/{community}/{building}/`

**Content:**
- "Vacant | Full Sea And Burj View | D Type"
- "2-bed, 3-bath, 1,550 sqft apartment"
- Unit numbers sometimes in description

**Extracts:** Unit number (if present) → bedrooms → size → view → type letter

---

## Installation

```bash
# Install dependencies
pip install beautifulsoup4 playwright

# Install Playwright browsers
playwright install chromium
```

---

## Usage

### Step 1: Test Parsers

```bash
cd bayut_scraper
python test_parsers.py
```

Expected output: `ALL TESTS PASSED!`

### Step 2: Launch Chrome

```bash
python bayut_scraper/run_bayut_scrape.py --launch-chrome
```

This opens Chrome with debug port 9222. Dismiss any Bayut popups/cookies.

### Step 3: Scrape

#### Mode: Guides Only (Recommended First)
Fast, structured data. Scrapes building guides + floor plans.

```bash
python bayut_scraper/run_bayut_scrape.py --mode guides_only
```

#### Mode: Building Guides Only
```bash
python bayut_scraper/run_bayut_scrape.py --mode building_guides
```

#### Mode: Floor Plans Only
```bash
python bayut_scraper/run_bayut_scrape.py --mode floor_plans
```

#### Mode: Full (Includes Listings)
**WARNING:** Slow! Scrapes guides + floor plans + listings (2-3 pages each).

```bash
python bayut_scraper/run_bayut_scrape.py --mode full
```

#### Single Building
```bash
python bayut_scraper/run_bayut_scrape.py --building "Shoreline 12"
```

#### Limit Number of Buildings
```bash
python bayut_scraper/run_bayut_scrape.py --mode guides_only --limit 10
```

### Step 4: Merge with Unit Registry

```bash
python bayut_scraper/run_bayut_scrape.py --merge
```

**Output:** `data/unit_registry_with_bayut.csv`

---

## Output Format

### `data/bayut_unit_types.csv`

```
building_name   — Normalized name (e.g., "Shoreline 12")
unit_type       — Type letter (e.g., "D", "F", "A")
bedrooms        — Bedroom count
bathrooms       — Bathroom count
size_sqft       — Size from Bayut (may be approximate)
view            — View description
source          — "building_guide" / "floor_plan" / "listing"
source_text     — Original text extracted from (for audit)
```

### Merge Logic

After scraping, merge integrates Bayut data with Phase 1 unit registry:

```
1. Load unit_registry.csv (from Phase 1)
2. Load bayut_unit_types.csv (from scraping)
3. For each unit in registry:
   - Match to Bayut type by: (building + bedrooms + closest size)
   - Inherit view from matched type
   - Add unit_type_bayut column
   - Add view_bayut column
   - Update confidence = "BAYUT_MATCHED"
4. Save to: unit_registry_with_bayut.csv
```

**Example:**
```
Registry: Shoreline 12, Unit 903, 2-bed, 1,582 sqft, view=None
Bayut:    Shoreline 12, Type D, 2-bed, 1,582 sqft, Road View
Result:   Unit 903 = Type D = Road View ✅
```

---

## Scraping Order

1. **Floor plan pages first** (fast, structured) → type → bedrooms → bathrooms
2. **Building guide pages second** (fast, text parsing) → type → size → view
3. **Merge with unit registry** → match units to types
4. **Listings last** (slow, supplementary) → only for remaining gaps

---

## Rate Limiting

- **5-10 second delays** between pages
- **8-15 second delays** between buildings
- **Extra delays** for listing pages (7-12 seconds)

**IMPORTANT:** Do NOT scrape aggressively. Bayut will block IPs.

---

## Building URL Mappings

Shoreline towers use **Arabic names** on Bayut:

```python
'Shoreline 1': 'al-ramth'
'Shoreline 9': 'al-msalli'
'Shoreline 12': 'al-haseer'
'Shoreline 17': 'al-hamri'
```

See `bayut_urls.py` for complete mapping (143 buildings).

---

## Debugging

### Raw HTML

All scraped pages are saved to `bayut_scraper/raw_html/` as `.html` files for debugging.

Example:
```
Shoreline_12_guide.html
Shoreline_12_floorplan.html
Oceana_listings_rent_p1.html
```

### Common Issues

**Chrome won't connect:**
```
[ERROR] Could not connect to Chrome
```

Solution:
1. Close ALL Chrome windows
2. Run `--launch-chrome` again
3. Wait 5 seconds, then run scrape command

**403 Forbidden:**
```
[ERROR] Navigation failed: 403
```

Solution: Bayut blocked your IP. Wait 1 hour, then try again with longer delays.

**No unit types extracted:**
```
[EXTRACTED] 0 unit types
```

Solution:
1. Check `raw_html/` folder for the saved HTML
2. Open the HTML in a browser
3. Verify page loaded correctly (not a 404/403)
4. If page is correct, parser may need updating

---

## Parser Logic

### Building Guide Parser

Uses regex patterns to extract from natural language:

```python
# Patterns matched:
- "Type-F covers around 2,055 sq. ft. offering panoramic sea views"
- "Type D unit usually covers around 1,646 sq. ft."
- "2-bed flats are the smallest with a covered area of 1,582 sq. ft."

# Extracted:
- Type letter: "Type[\s-]?([A-H]\d?)"
- Bedrooms: r'(\d)[- ]?bed'
- Size: r'([\d,]+)\s*sq\.?\s*\.?\s*ft'
- View: 35+ view keyword patterns (panoramic sea, full sea, road view, etc.)
```

### Floor Plan Parser

Extracts from structured HTML:

```python
# Pattern: "Type X: Y bedroom(s), Z bathroom(s)"
- Type B: 1 bedroom, 2 bathrooms
- Type D: 2 bedrooms, 3 bathrooms
```

### Listing Parser

Extracts from listing cards:

```python
# Extracts:
- Bedrooms: r'(\d+)\s*(?:Bed|BR|bedroom)'
- Bathrooms: r'(\d+)\s*(?:Bath|BA|bathroom)'
- Size: r'([\d,]+)\s*(?:sq\.?\s*ft|sqft)'
- Unit type: r'Type[\s-]?([A-H]\d?)'
- View: 35+ keyword patterns
```

---

## Statistics

After successful scraping, expect:

- **Building Guides:** 30-50 buildings with guide pages
- **Floor Plans:** 100+ buildings with floor plan pages
- **Type Records:** 200-400 unique (building, type) combinations
- **Total Runtime (guides_only):** 1-2 hours for all buildings
- **Total Runtime (full):** 4-6 hours for all buildings

---

## Next Steps After Scraping

1. **Review CSV:** `data/bayut_unit_types.csv`
2. **Merge:** `python bayut_scraper/run_bayut_scrape.py --merge`
3. **Check Results:** `data/unit_registry_with_bayut.csv`
4. **Update App:** Restart Streamlit app to use enhanced registry

---

## Troubleshooting

### Playwright Not Found

```bash
pip install playwright
playwright install chromium
```

### BeautifulSoup Not Found

```bash
pip install beautifulsoup4 lxml
```

### Chrome Debug Port Already in Use

```bash
# Find process using port 9222
netstat -ano | findstr :9222

# Kill process (replace PID)
taskkill /F /PID <PID>
```

### Scraping Too Slow

Use `guides_only` mode instead of `full`. Listings are optional and very slow.

### Some Buildings Not Found

Check `bayut_urls.py` - building may not be in mapping. Search Bayut manually for the correct slug and add it.

---

## Technical Notes

- **Chrome Debug Port:** 9222 (same as Property Monitor scraper)
- **User-Agent:** Playwright default (real Chrome)
- **Cookies:** Manual dismissal required before scraping
- **Cloudflare:** Not usually present on Bayut, but if it appears, dismiss manually
- **Concurrency:** Sequential only (no parallel requests to avoid blocking)

---

## Examples

### Quick Test (Single Building)

```bash
python bayut_scraper/run_bayut_scrape.py --launch-chrome
# ... dismiss popups in Chrome ...
python bayut_scraper/run_bayut_scrape.py --building "Shoreline 12"
```

### Full Shoreline Scrape

```bash
python bayut_scraper/run_bayut_scrape.py --launch-chrome
# ... dismiss popups ...
python bayut_scraper/run_bayut_scrape.py --mode guides_only --limit 20
```

### Scrape and Merge

```bash
python bayut_scraper/run_bayut_scrape.py --mode guides_only
# ... wait 1-2 hours ...
python bayut_scraper/run_bayut_scrape.py --merge
# ... check unit_registry_with_bayut.csv ...
```

---

## Project Integration

This scraper is **Phase 2** of the Unit Registry system:

- **Phase 1:** `build_unit_registry.py` - Cross-reference leads/sales/rentals
- **Phase 2:** `bayut_scraper/` - Add unit types and views from Bayut
- **Phase 3:** (Future) Integrate into Streamlit UI for validation

---

## Status

✅ **Complete and tested**
- All parsers validated
- URL mappings for 143 buildings
- Chrome debug mode working
- Merge logic implemented

**Ready for:** Production scraping

---

## Support

For issues:
1. Check `raw_html/` folder for saved pages
2. Run `test_parsers.py` to verify parser logic
3. Test single building first before scraping all
4. Use `--limit 5` to test on small subset
