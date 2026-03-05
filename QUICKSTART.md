# Quick Start: Run Unit Number Scraper

Based on your screenshots and instructions, here's how to run the scraper:

## Test Run (Recommended First)

```bash
python run_scraper.py
```

Choose option `1` for test run with **The Fairmont Palm Residences**

This will:
1. ✅ Log into Property Monitor
2. ✅ Click search bar (red circle in screenshot)
3. ✅ Type "The Fairmont Palm Residences" slowly
4. ✅ Select from dropdown
5. ✅ Set date to "All Historical Data"
6. ✅ Set per page to 250 (maximum)
7. ✅ Click Search button
8. ✅ Extract table data with unit numbers
9. ✅ Go through first 2 pages (up to 500 records)
10. ✅ Save to: `scraped_data/unit_numbers_The_Fairmont_Palm_Residences.csv`

**Duration:** ~5-10 minutes

---

## If Test Successful

Run full Palm Jumeirah scrape:

```bash
python run_scraper.py
```

Choose option `2` for full scrape

This will search: **"The Palm Jumeirah (Dubai, Palm Jumeirah)"**
- All buildings on Palm Jumeirah
- All historical data
- 250 results per page
- Every page until end

**Duration:** 2-4 hours
**Expected records:** 10,000-20,000 transactions

---

## After Scraping Completes

Merge unit numbers with title deed data:

```bash
python merge_unit_numbers.py
```

This creates: `Master reference datasets/reference_master_with_units.csv`

---

## Then Update the AI System

The scraper workflow I've built matches your instructions:

### From Your Screenshots:

**Screenshot 1:** Search dropdown (red circle)
- ✅ Scraper clicks search bar
- ✅ Types building name slowly (100-200ms per character)
- ✅ Waits for dropdown to appear

**Screenshot 2:** Dropdown with "The Palm Jumeirah" highlighted (yellow)
- ✅ Scraper selects the highlighted option
- ✅ Handles both keyboard (Enter) and mouse click

**Screenshot 3:** Results table with unit numbers (yellow column)
- ✅ Scraper extracts entire table including unit numbers
- ✅ Handles per-page selector (sets to 250)
- ✅ Goes through all pages

### Slow Execution for Bot Detection

All actions include delays:
- **Typing:** 100-200ms between each character
- **Between actions:** 1-3 seconds (randomized)
- **After clicks:** 2-3 seconds
- **Page loads:** Wait for networkidle + 3-5 seconds

---

## Troubleshooting

### "Login failed"

Check `.env` file has:
```
PROPERTYMONITOR_EMAIL=your_email
PROPERTYMONITOR_PASSWORD=your_password
```

### "Search dropdown not found"

The scraper tries multiple common selectors. If it fails:
1. Log in manually to Property Monitor
2. Right-click the search bar → Inspect
3. Copy the CSS selector
4. Update line ~125 in `unit_number_scraper.py`

### "Table not extracted"

The scraper uses JavaScript to extract the entire table. If it returns no data:
1. Check browser console for errors (F12)
2. Verify table is visible on page
3. May need to adjust table selector

### "Bot detected / CAPTCHA"

- Scraper includes anti-bot delays
- Browser runs in non-headless mode (visible)
- If CAPTCHA appears, solve it manually
- Scraper will continue after you solve it

---

## What Happens Next

After successful scraping:

1. ✅ You'll have unit numbers for all transactions
2. ✅ Merge script matches them to title deeds
3. ✅ Update AI system to use new data
4. ✅ Cross-referencing works!

**AI query:** "Recent sales in The Fairmont"

**AI response:**
```
Recent Sale: Unit S-607 | Dec 2025
💰 AED 6,000,000 | 1,412 sqft | 2-bed

📞 Current Owner:
✅ Ahmed Al Mansoori
✅ Phone: +971 50 558 5975
   Match: High confidence
```

---

## Ready to Run

Your scraper is complete and ready. Run:

```bash
python run_scraper.py
```

Choose option 1 (test) first, then option 2 (full) when ready.
