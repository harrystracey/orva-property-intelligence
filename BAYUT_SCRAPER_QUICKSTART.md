# Bayut Scraper - Quick Start Guide

## What It Does

Scrapes Bayut.com to add unit type classifications and view data to your Unit Registry.

**Output:** Enhanced registry with Type letters (A-H) and views (Sea View, Road View, etc.) for 50-60% of your 17,002 units.

---

## Installation (One-Time)

```bash
pip install playwright beautifulsoup4
playwright install chromium
```

---

## Usage (3 Simple Steps)

### 1. Launch Chrome
```bash
python bayut_scraper/run_bayut_scrape.py --launch-chrome
```
- Chrome opens with debug mode
- Dismiss any Bayut popups/cookies
- Leave Chrome open

### 2. Start Scraping
```bash
python bayut_scraper/run_bayut_scrape.py --mode guides_only
```
- Scrapes all 143 buildings (1-2 hours)
- Saves progress after each building
- Can interrupt and resume

### 3. Merge Results
```bash
python bayut_scraper/run_bayut_scrape.py --merge
```
- Matches units to types
- Adds views from Bayut
- Output: `data/unit_registry_with_bayut.csv`

---

## Test First (Recommended)

### Single Building
```bash
python bayut_scraper/run_bayut_scrape.py --building "Shoreline 12"
```

### First 5 Buildings
```bash
python bayut_scraper/run_bayut_scrape.py --mode guides_only --limit 5
```

### Validate Parsers
```bash
cd bayut_scraper
python test_parsers.py
# Should see: ALL TESTS PASSED!
```

---

## Files Created

- `data/bayut_unit_types.csv` - Raw scraped data
- `data/unit_registry_with_bayut.csv` - Enhanced registry (after merge)
- `bayut_scraper/raw_html/` - Saved pages for debugging

---

## Expected Results

Before:
- **Units with views:** 2,352 (13.8%)

After:
- **Units with views:** ~10,000 (59%)
- **Units with types:** ~13,000 (76%)

---

## Troubleshooting

**Chrome won't connect?**
```bash
# Close all Chrome windows, then:
python bayut_scraper/run_bayut_scrape.py --launch-chrome
# Wait 5 seconds, then run scrape command
```

**Want more info?**
- Full guide: `bayut_scraper/README.md`
- Technical details: `BAYUT_SCRAPER_IMPLEMENTATION.md`

---

## Status

✅ All components implemented and tested
✅ Ready for production use
✅ Conservative rate limiting (no IP blocks)

**Recommended:** Start with `--limit 10` to test, then run full scrape.
