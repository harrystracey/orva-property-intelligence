# Getting Unit Numbers from Property Monitor

This guide explains how to scrape unit numbers from Property Monitor to enable full cross-referencing of sales to owners.

## The Problem

Property Monitor deliberately **excludes unit numbers from CSV exports** as a security measure to prevent competitors from getting unit-level intelligence. However, unit numbers ARE visible on the website.

**What we have:**
- Title Deed CSV: Prices, sizes, dates, building names ❌ NO unit numbers
- Lead Database CSV: Owner names, phones, unit numbers
- **Gap:** Can't match recent sales to current owners

**What we need:**
- Scrape unit numbers from the Property Monitor website
- Merge with title deed data
- Enable full cross-referencing

---

## Quick Start

### Step 1: Configure Your Credentials

Make sure these are set in `.env` or `property_research_agent/config.py`:

```
PROPERTYMONITOR_EMAIL=your_email@example.com
PROPERTYMONITOR_PASSWORD=your_password
ANTHROPIC_API_KEY=your_claude_api_key
```

### Step 2: Update Scraper Selectors

**You must provide the CSS selectors** for Property Monitor's filters. The scraper has placeholders marked with `TODO`.

**Open:** `property_research_agent/unit_number_scraper.py`

**Find and update:**

1. **`navigate_to_search()` function** — Line ~90
   - Add the URL or navigation steps to reach the transaction search page
   - Example: `await self.page.goto('https://www.propertymonitor.ae/transactions')`

2. **`apply_filters()` function** — Lines ~110-190
   - **Location Filter** (Palm Jumeirah)
   - **Transaction Type** (Title Deed + Oqood checkboxes)
   - **Date Range** (All Time)

**How to find selectors:**
1. Log into Property Monitor manually in Chrome
2. Right-click on the filter dropdown/checkbox → Inspect
3. In DevTools, right-click the highlighted element → Copy → Copy selector
4. Paste into the scraper code

### Step 3: Run the Scraper

```bash
python run_scraper.py
```

**What happens:**
- Browser opens (visible, not headless)
- Logs into Property Monitor
- Navigates to search page
- Applies filters
- Scrapes ALL pages of results
- Saves to: `scraped_data/unit_numbers_palm_jumeirah.csv`

**Duration:** ~2-4 hours for all Palm Jumeirah transactions

---

## Step 4: Merge with Title Deed Data

Once scraping completes:

```bash
python merge_unit_numbers.py
```

**What happens:**
- Loads scraped unit numbers
- Loads title deed reference data
- Matches transactions by:
  - Building name (fuzzy)
  - Transaction date (±7 days)
  - Size (±5%)
  - Bedrooms
- Outputs: `Master reference datasets/reference_master_with_units.csv`

**Match confidence levels:**
- **HIGH:** Building + exact date + size + bedrooms match
- **MEDIUM:** Building + date ±7 days + size match
- **LOW:** Building + size match only

---

## Step 5: Re-enable Cross-Referencing in AI

Now that we have unit numbers, update the system to use them:

### Update `data_processor.py`

**Line ~2509** — Update unit number handling:

```python
# OLD CODE (unit numbers marked as N/A):
sale['unit_number'] = 'N/A (not in title deed export)'

# NEW CODE (use scraped unit numbers):
unit_no = str(row.get('unit_number_scraped', '')).strip()
if unit_no and unit_no != 'nan' and unit_no != '':
    if BUILDING_INTELLIGENCE_AVAILABLE:
        sale['unit_number'] = normalize_unit_number(unit_no)
        sale['unit_number_raw'] = unit_no
    else:
        sale['unit_number'] = unit_no
else:
    sale['unit_number'] = 'N/A'
```

### Update `load_reference_data()` function

**Line ~540** — Load the new file with units:

```python
possible_paths = [
    './reference_data/title_deed_reference.csv',
    './Master reference datasets/reference_master_with_units.csv',  # NEW - prioritize this
    './Master reference datasets/reference_master.csv',
    './Master reference datasets/palm-jumeirah-market-data-harry...csv'
]
```

### Update `app.py` — Re-add cross-reference tool

**Line ~298** — Add back the tool:

```python
{
    "name": "cross_reference_unit",
    "description": "Look up owner contact for a specific unit. Use AFTER get_market_stats when you have unit numbers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "building": {"type": "string"},
            "unit_number": {"type": "string"},
            "bedrooms": {"type": "integer"},
            "size_sqft": {"type": "integer"}
        },
        "required": ["building", "unit_number"]
    }
}
```

**Line ~525** — Add handler:

```python
elif tool_name == "cross_reference_unit":
    result = cross_reference_sale_with_leads_for_ai(
        leads_df=leads_df,
        building=tool_input.get('building'),
        unit_number=tool_input.get('unit_number'),
        bedrooms=tool_input.get('bedrooms'),
        size_sqft=tool_input.get('size_sqft')
    )
```

### Update System Prompt

**Line ~364** — Replace with:

```python
system_prompt = """You are HLM, expert real estate analyst for Palm Jumeirah.

DATA SOURCES:
- Title Deeds: Prices, sizes, dates, AND unit numbers (scraped)
- Lead Database: Owner names, phones, unit numbers

WORKFLOW:
1. get_market_stats → Recent sales WITH unit numbers
2. cross_reference_unit for each sale → Find owner contacts
3. Present UNIFIED report with sales + owners matched

RESPONSE FORMAT:
**Recent Sale: Unit S-607**
- Price: AED 6M | 1,412 sqft | 2-bed | Dec 2025
- Owner: Ahmed Al Mansoori
- Phone: +971 50 558 5975 ✅
- Portfolio: Single unit owner

You can now match sales to owners!"""
```

---

## Maintenance

### Refresh Unit Numbers

Run scraper periodically (weekly/monthly) to catch new transactions:

```bash
# Scrape last 30 days only
python run_scraper.py --incremental

# Merge with existing data
python merge_unit_numbers.py --append
```

### Monitor Data Quality

Check match rates after merging:

```bash
python -c "import pandas as pd; df = pd.read_csv('Master reference datasets/reference_master_with_units.csv'); print(df['match_confidence'].value_counts())"
```

**Good match rate:** >70% high+medium confidence

---

## Troubleshooting

### Scraper Issues

**"Login failed"**
- Check credentials in config.py
- Property Monitor may have changed login page
- Update selectors in `login()` function

**"Filter not found"**
- CSS selectors have changed
- Update selectors in `apply_filters()`
- Use browser DevTools to find new selectors

**"No data extracted"**
- Table structure may have changed
- Update `extract_table_data()` JavaScript
- Check console for errors

**"Bot detected"**
- Increase delays in config.py
- Use residential proxy
- Consider 2Captcha for CAPTCHA solving

### Merge Issues

**Low match rate (<50%)**
- Building names don't match
- Check `building_intelligence.py` aliases
- Add missing building variations

**"Column not found"**
- Scraped CSV has different columns
- Update `column_mapping` in merge_unit_numbers.py

---

## Files Created

```
property_research_agent/
  └── unit_number_scraper.py      # Main scraper (YOU MUST UPDATE SELECTORS)

scraped_data/
  ├── unit_numbers_palm_jumeirah.csv       # Scraped output
  ├── unit_numbers_palm_jumeirah_TIMESTAMP.csv  # Backups
  └── scraping_progress.json       # Resume capability

Master reference datasets/
  ├── reference_master_with_units.csv       # MAIN OUTPUT - Use this!
  ├── reference_high_confidence_units.csv   # High confidence only
  └── reference_with_units_TIMESTAMP.csv    # Backups

merge_unit_numbers.py             # Merge script
run_scraper.py                    # Convenience runner
```

---

## Next Steps

1. **Provide screenshots** of Property Monitor filters (to get exact selectors)
2. **Update selectors** in `unit_number_scraper.py`
3. **Run scraper:** `python run_scraper.py`
4. **Merge data:** `python merge_unit_numbers.py`
5. **Re-enable cross-referencing** in app.py and data_processor.py
6. **Test:** "Recent sales in Shoreline 9" should now show owner contacts!

---

## Legal/Ethical Notes

✅ **You confirmed:** Checked Property Monitor's Terms of Service
⚠️ **Best practices:**
- Don't scrape more often than necessary
- Use rate limiting (built into scraper)
- Consider contacting Property Monitor about API access for commercial use
- Respect robots.txt

---

## Support

**Issues with selectors?**
- Attach screenshots of the Property Monitor interface
- Show which dropdowns/checkboxes need to be clicked
- Include any error messages from browser console

**Questions?**
- Check `property_research_agent/scraper_agent.py` for reference (existing working scraper)
- Playwright docs: https://playwright.dev/python/
