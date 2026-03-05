# PropertyFinder + Replit Permit Scraper

**Hybrid scraper: collect DLD permit numbers from PropertyFinder rental listings, look them up on the Replit property-scraper app, and save landlord/owner details to a CSV (scraped lead list).**

---

## OVERVIEW

You perform the search on PropertyFinder and log in to the Replit app manually. The script connects to your Chrome (via debug port), visits each listing, extracts the DLD permit number from the "Provided by" section, submits it to the Replit app, and saves the resulting owner/unit data to `scraped_data/propertyfinder_scraped_leads.csv`.

**Key features:**
- Two-tab flow: PropertyFinder (search results + listing detail) and Replit app (permit lookup)
- Configurable limits: `--max-pages` and `--max-listings`
- Resume support: progress saved so you can continue after a stop
- Human-like delays between listings to reduce detection risk

---

## ARCHITECTURE

```
propertyfinder_scraper/
├── start_pf_chrome.ps1   # Launch Chrome with debug port + PF + Replit tabs
├── scraper.py            # Main script: CDP connect, collect URLs, extract permit, Replit lookup, save CSV
└── README.md             # This file

Output:
  scraped_data/propertyfinder_scraped_leads.csv   # Scraped lead list
  scraped_data/pf_scraping_progress.json          # Progress for --resume
```

---

## SETUP

### 1. Prerequisites

- **Chrome** (for CDP connection)
- **Python 3.9+** with Playwright
- **Replit app** account: [property-scraper-towersdubai.replit.app](https://property-scraper-towersdubai.replit.app/)

### 2. Install Dependencies

```bash
pip install playwright
playwright install chromium
```

### 3. Launch Chrome (required before running the scraper)

From project root (PowerShell):

```powershell
powershell -File propertyfinder_scraper/start_pf_chrome.ps1
```

Chrome opens with two tabs: PropertyFinder search and the Replit app.

1. In the **PropertyFinder** tab: set location (e.g. Palm Jumeirah), Rent, bedrooms/filters as needed.
2. In the **Replit** tab: log in so the app is ready for permit lookups.
3. Switch back to the PropertyFinder tab so search results are visible.

---

## USAGE

### Run the scraper

From project root:

```bash
python propertyfinder_scraper/scraper.py --max-pages 5 --max-listings 50
```

- `--max-pages` — Maximum search result pages to process (default: 5).
- `--max-listings` — Maximum individual listings to process (default: 50).

When prompted, press **Enter** in the terminal to start. The script will:

1. Collect all listing URLs from the current PropertyFinder results page.
2. For each URL: open listing → scroll to "Provided by" → read DLD permit number.
3. If no permit is found, skip and continue.
4. Switch to Replit tab → enter permit number → click "Extract Data" → wait for result.
5. Read owner name, phone, email, unit, building, etc. from the green result box.
6. Append a row to `scraped_data/propertyfinder_scraped_leads.csv`.
7. After the page’s listings are done, go to the next search results page (if any) until limits are reached.

### Resume after interruption

If the script stops (crash, Ctrl+C, or limit), run:

```bash
python propertyfinder_scraper/scraper.py --resume --max-pages 5 --max-listings 50
```

Already-processed listing URLs are read from `pf_scraping_progress.json` and skipped.

---

## OUTPUT

**CSV:** `scraped_data/propertyfinder_scraped_leads.csv`

Columns: `permit_number`, `unit_number`, `building_name`, `zone`, `size_sqm`, `land_no`, `owner_name`, `phone`, `email`, `property_value`, `room_type`, `permit_type`, `listing_url`, `listing_price`, `scraped_at`.

This file is your **scraped lead list**. You can merge or import it into your main lead pipeline (e.g. `consolidate_data.py` / `data_ingestion.py`) as needed.

---

## TROUBLESHOOTING

### "Could not connect to Chrome"

- Run `start_pf_chrome.ps1` first so Chrome is running with `--remote-debugging-port=9222`.
- Close any other Chrome instances that might be using the same port.

### "No listing URLs found"

- Ensure the PropertyFinder tab is showing **search results** (list of properties), not a single listing or the home page.
- Set your search (Palm Jumeirah, Rent, etc.) and wait for results to load before pressing Enter in the script.

### "No permit" for many listings

- Some listings do not show a DLD permit number in "Provided by". The script skips these and continues.
- Ensure you are on the listing **detail** page and, if needed, that the "Provided by" tab/section is visible (script tries to click it).

### Replit app: "Extract Data" or result box not found

- Log in to the Replit app in the second tab before starting.
- If the Replit site layout has changed, selectors in `scraper.py` (e.g. `button:has-text("Extract Data")`, `text=Permit Lookup Result`) may need to be updated.

### Duplicate or wrong data

- Use `--resume` so each listing URL is only processed once.
- If you need a fresh run, delete or rename `pf_scraping_progress.json` and optionally clear or rename the CSV.

---

## IMPORTANT REMINDERS

- **Same Chrome debug port (9222)** as other project scrapers. Do not run two such Chrome instances at once.
- **You must log in to the Replit app** in the second tab before starting; the script does not handle login.
- **PropertyFinder search is manual.** You choose location, rent, and filters; the script only automates clicking into listings and extracting permit numbers.
- **Rate politely.** The script uses 3–6 second delays between listings; avoid lowering them to reduce blocking risk.
