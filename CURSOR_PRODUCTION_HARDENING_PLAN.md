# CURSOR PLANNING PROMPT — Production Hardening

**Project:** Palm Jumeirah Real Estate Intelligence System
**Objective:** Harden existing codebase from personal tool → production-grade, multi-tenant-ready product. NO new features. Infrastructure, stability, and code quality only.

---

## SYSTEM CONTEXT

You are working on a Streamlit-based real estate intelligence application. Before making ANY changes, read the full `PROJECT_SUMMARY.md` in the project root. It contains the complete architecture, file structure, data flow, and technical debt inventory. Treat it as your source of truth.

**Current State:**
- ~6,000 lines of Python across 20+ modules
- Main app: `app.py` (1,205 lines) — Streamlit multi-page UI
- Core logic: `data_processor.py` (3,200+ lines) — data loading, cleaning, enrichment, AI tools
- Building intelligence: `building_intelligence.py` (546 lines) — fuzzy matching, aliases, validation
- Chat system: `chat_manager.py` (172 lines) — JSON-based chat persistence
- Client data: `client_data_manager.py` — notes, reminders, follow-ups
- Scraper: `property_research_agent/` — Playwright + Claude for PropertyMonitor.ae
- Data: 18,250+ title deed transactions, 28,000+ lead contacts, all in CSV/Excel

**Tech Stack:** Python 3.8+, Streamlit, Pandas, Anthropic Claude API (Sonnet 4), Playwright, FuzzyWuzzy, OpenPyXL

---

## RULES OF ENGAGEMENT

1. **ZERO new features.** Every change must harden, refactor, or stabilize existing functionality.
2. **Do not break existing workflows.** The app must remain functional after every phase. If a refactor touches data loading, verify the lead search page still works. If it touches AI tools, verify the chat page still returns correct results.
3. **Preserve all domain logic exactly.** The building aliases, Shoreline mappings, bedroom estimation cascades, size ranges, and cross-referencing logic are battle-tested against real Dubai market data. Do not "optimize" or "simplify" these unless explicitly asked. Copy them verbatim into new modules.
4. **Ask before deleting.** If you think a file, function, or code block is unused, flag it — don't remove it.
5. **Commit after each phase.** Each phase below is a logical unit of work. Complete it, verify it works, then commit before moving to the next.

---

## PHASE 1: SECURITY & HYGIENE

**Priority:** CRITICAL — Do this first, no exceptions.

### Tasks:
1. **Remove hardcoded API key from `start_app.ps1`.**
   - Replace with environment variable read from `.env`
   - If PowerShell needs to set the env var, read it from `.env` file dynamically
   - Verify `.env` is in `.gitignore` (it should be already)

2. **Audit git history for exposed secrets.**
   - Run: `git log --all --full-history -p -- start_app.ps1 | grep -i "sk-ant"`
   - If any API keys appear in history, flag immediately — key rotation required
   - Document findings

3. **Standardize environment variable handling.**
   - All secrets must flow through `python-dotenv` and `.env` only
   - Create `.env.example` with placeholder values for onboarding:
     ```
     ANTHROPIC_API_KEY=sk-ant-your-key-here
     PROPERTYMONITOR_EMAIL=your-email@example.com
     PROPERTYMONITOR_PASSWORD=your-password-here
     ```

### Verification:
- App starts without any hardcoded credentials
- `grep -r "sk-ant" .` returns zero results (excluding `.env`)
- `.env.example` exists in repo root

---

## PHASE 2: DATABASE MIGRATION (CSV → SQLite)

**Priority:** HIGH — This is the single biggest architectural improvement.

### Objective:
Replace in-memory CSV loading with SQLite. The app currently loads all CSVs into Pandas DataFrames on every startup. Migrate to a persistent SQLite database with CSV import as an ingestion pathway.

### Schema Design:

```sql
-- Lead contacts (from uploaded CSV files)
CREATE TABLE leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_name TEXT,
    building_name TEXT,
    building_name_normalized TEXT,  -- Output of fuzzy matching
    unit_number TEXT,
    unit_number_normalized TEXT,    -- Standardized format (S-607, not S607)
    phone TEXT,
    phone_formatted TEXT,           -- +971 50 123 4567 format
    email TEXT,
    date TEXT,                      -- Transaction/registration date
    bedrooms TEXT,                  -- Could be "Studio", "1", "2", etc.
    bedrooms_estimated BOOLEAN DEFAULT FALSE,  -- Was this estimated?
    bedrooms_source TEXT,           -- "schema", "pattern", "size", "default", "original"
    size_sqft REAL,
    size_estimated BOOLEAN DEFAULT FALSE,
    size_source TEXT,               -- "bedrooms", "building_avg", "original"
    completeness_score REAL,        -- 0.0 to 1.0
    source_file TEXT,               -- Which CSV this came from
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_name, building_name_normalized, unit_number_normalized)
);

-- Title deed reference transactions (from PropertyMonitor)
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    unit_number_normalized TEXT,
    transaction_date TEXT,
    price_aed REAL,
    size_sqft REAL,
    bedrooms TEXT,
    property_type TEXT,             -- "apartment", "villa", "townhouse", "penthouse"
    transaction_type TEXT,          -- "sale", "resale", "off-plan"
    source TEXT,                    -- "property_monitor", "scraped", "manual"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(building_name_normalized, unit_number_normalized, transaction_date, price_aed)
);

-- Cross-reference matches (precomputed joins)
CREATE TABLE cross_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    transaction_id INTEGER REFERENCES transactions(id),
    match_confidence REAL,          -- 0.0 to 1.0
    match_method TEXT,              -- "exact_unit", "fuzzy_unit", "building_only"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lead_id, transaction_id)
);

-- Scraped unit numbers
CREATE TABLE scraped_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    unit_number_normalized TEXT,
    scraped_date TIMESTAMP,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Client notes and reminders (migrate from JSON)
CREATE TABLE client_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT,                 -- hash(owner_name + building + unit)
    owner_name TEXT,
    building_name TEXT,
    unit_number TEXT,
    note_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE client_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT,
    owner_name TEXT,
    building_name TEXT,
    unit_number TEXT,
    reminder_text TEXT,
    due_date TIMESTAMP,
    status TEXT DEFAULT 'pending',  -- "pending", "done", "snoozed"
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_leads_building ON leads(building_name_normalized);
CREATE INDEX idx_leads_unit ON leads(unit_number_normalized);
CREATE INDEX idx_leads_phone ON leads(phone);
CREATE INDEX idx_leads_bedrooms ON leads(bedrooms);
CREATE INDEX idx_transactions_building ON transactions(building_name_normalized);
CREATE INDEX idx_transactions_unit ON transactions(unit_number_normalized);
CREATE INDEX idx_transactions_date ON transactions(transaction_date);
CREATE INDEX idx_cross_refs_lead ON cross_references(lead_id);
CREATE INDEX idx_cross_refs_transaction ON cross_references(transaction_id);
CREATE INDEX idx_client_notes_client ON client_notes(client_id);
CREATE INDEX idx_client_reminders_status ON client_reminders(status, due_date);
```

### Implementation Steps:

1. **Create `database.py` module** — connection management, schema creation, migration utilities.
2. **Create `data_ingestion.py` module** — CSV/Excel → SQLite import pipeline. This replaces the "load all CSVs on startup" pattern. Must apply all existing normalization, enrichment, and deduplication logic during ingestion.
3. **Create `migrate_existing_data.py` script** — one-time migration of current CSV files and JSON client data into SQLite.
4. **Refactor `data_processor.py`** to query SQLite instead of in-memory DataFrames. Keep Pandas for presentation layer (query results → DataFrame → Streamlit display).
5. **Refactor `client_data_manager.py`** to read/write from `client_notes` and `client_reminders` tables instead of JSON files.
6. **Keep CSV upload functionality** in the UI — user uploads a new lead CSV → ingestion pipeline processes it → writes to SQLite.

### Database Location:
- `./data/palm_intelligence.db` (SQLite file)
- Add to `.gitignore`
- Backup strategy: daily copy with timestamp

### Verification:
- App startup time drops significantly (no full CSV load)
- Lead search returns identical results to current CSV-based system
- AI chat returns identical results
- Client notes and reminders persist correctly
- New CSV upload ingests correctly into database

---

## PHASE 3: SPLIT `data_processor.py`

**Priority:** HIGH — Required for maintainability and testability.

### Target Module Structure:

```
full_scraping_bot/
├── core/
│   ├── __init__.py
│   ├── database.py              # SQLite connection, schema, queries (from Phase 2)
│   ├── data_ingestion.py        # CSV/Excel → SQLite pipeline (from Phase 2)
│   ├── enrichment.py            # Bedroom estimation, size estimation, completeness scoring
│   ├── cross_reference.py       # Title deed ↔ lead matching logic
│   ├── ai_tools.py              # get_building_intel, get_owner_portfolio, search_building_names
│   └── config.py                # All constants: SIZE_RANGES, BUILDING_DEFAULT_BEDROOMS, BUILDING_UNIT_SCHEMA
```

### Migration Rules:
- `config.py` gets ALL hardcoded dictionaries and magic numbers currently scattered across `data_processor.py` and `building_intelligence.py`. This includes: `SIZE_RANGES`, `BUILDING_DEFAULT_BEDROOMS`, `BUILDING_UNIT_SCHEMA`, `SHORELINE_TOWER_MAPPING`, `BUILDING_ALIASES`, and any threshold values (fuzzy match cutoffs, etc.).
- `enrichment.py` gets: bedroom estimation cascade (schema → pattern → size → default), size estimation, completeness scoring, phone formatting, unit number normalization. These functions should now operate on individual records or database queries, not full DataFrames.
- `cross_reference.py` gets: the matching logic that links transactions to leads by building + unit number. Should work against SQLite queries.
- `ai_tools.py` gets: `get_complete_building_intel_for_ai()`, `get_portfolio_summary_for_ai()`, `search_building_names_for_ai()`. These are the three functions exposed to Claude via function calling. They should query SQLite and return formatted dictionaries.
- `building_intelligence.py` stays as-is (it's already clean at 546 lines) but should import constants from `core/config.py` instead of defining its own.

### Verification:
- All imports resolve correctly
- `app.py` import paths updated
- AI chat page returns identical results to before refactor
- Lead search page returns identical results

---

## PHASE 4: STRUCTURED LOGGING

**Priority:** MEDIUM — Essential for debugging and audit trails.

### Implementation:

1. **Install `loguru`** — add to `requirements.txt`
2. **Create `core/logger.py`:**
   ```python
   from loguru import logger
   import sys

   logger.remove()  # Remove default handler

   # Console output (development)
   logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {module}:{function}:{line} | {message}")

   # File output (persistent logs)
   logger.add(
       "logs/app_{time:YYYY-MM-DD}.log",
       level="DEBUG",
       rotation="1 day",
       retention="30 days",
       format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {module}:{function}:{line} | {message}"
   )
   ```
3. **Replace every `print()` statement** across all modules with appropriate log level:
   - `print(f"Loaded {len(df)} records")` → `logger.info(f"Loaded {len(df)} records")`
   - `print(f"Error: {e}")` → `logger.error(f"Data loading failed: {e}")`
   - Debug/trace info → `logger.debug()`
4. **Add logging to critical paths:**
   - Data ingestion: records loaded, duplicates removed, enrichment stats
   - AI queries: query text, tool calls made, response time
   - Cross-referencing: matches found, confidence distribution
   - Client actions: note added, reminder set, follow-up completed
   - Scraper: pages visited, data extracted, errors encountered

### Add `logs/` to `.gitignore`.

### Verification:
- Zero `print()` statements remain in codebase (excluding Streamlit-specific `st.write`)
- `logs/` folder populates on app run
- Log files contain structured, queryable entries

---

## PHASE 5: TESTING

**Priority:** MEDIUM — Focused on high-risk areas only.

### Test Structure:
```
tests/
├── __init__.py
├── test_building_intelligence.py    # Building name resolution
├── test_enrichment.py               # Bedroom & size estimation
├── test_cross_reference.py          # Transaction ↔ lead matching
├── test_data_ingestion.py           # CSV import validation
└── test_config.py                   # Config integrity checks
```

### Test Cases (write these specific tests):

**`test_building_intelligence.py`:**
- "Fairmont" → "The Fairmont Palm Residences"
- "Al Masalli" → "Shoreline 9"
- "Oceana Caribbean" → "Oceana"
- "shoreline 5" (lowercase) → "Shoreline 5"
- "KMPNSKI" (typo) → "Kempinski" (if fuzzy threshold met)
- Unknown building → returns None or low-confidence result
- All 20 Shoreline Arabic names resolve to correct tower numbers

**`test_enrichment.py`:**
- Shoreline unit "S-607" → 2BR (6th floor schema)
- Unit containing "2BR" in text → 2 bedrooms
- Size 550 sqft with no bedroom data → Studio
- Size 1400 sqft with no bedroom data → 2BR
- Bedroom "Studio" → estimated size ~550 sqft
- Bedroom "3" → estimated size ~2100 sqft
- Unit with existing bedroom data → NOT overwritten by estimation

**`test_cross_reference.py`:**
- Exact unit match (same building + same normalized unit) → match
- Normalized unit match ("S607" in leads, "S-607" in transactions) → match
- Same building, different unit → no match
- Different building, same unit → no match
- Case-insensitive building match → match

**`test_data_ingestion.py`:**
- Valid CSV imports correct number of records
- Duplicate rows are deduplicated
- Missing columns are handled gracefully (no crash)
- Malformed phone numbers are cleaned
- Empty CSV produces zero records (no crash)
- Mixed encoding CSV (latin1) imports correctly

### Test Framework: `pytest`
- Add `pytest` to `requirements.txt`
- Add `pytest.ini` or section in `pyproject.toml`
- Tests should use small fixture data (5-10 records), not production CSVs

### Verification:
- `pytest` passes with all tests green
- Tests run in under 10 seconds (no real API calls, no real database)

---

## PHASE 6: SCRAPER RESILIENCE

**Priority:** LOW — Last because it's the least urgent for productization.

### Tasks:

1. **Extract CSS selectors into config:**
   - Create `property_research_agent/selectors.py` or `selectors.yaml`
   - All PropertyMonitor-specific selectors in one place
   - When PM updates their UI, update one file

2. **Add scraped data validation:**
   - Unit numbers must match expected patterns (regex per building type)
   - Prices must be within sane AED ranges (e.g., 500K–200M for Palm Jumeirah)
   - Dates must be valid and not in the future
   - Flag anomalies in log, don't write to database

3. **Add scraping run metadata:**
   - Log: start time, end time, records scraped, errors, buildings covered
   - Store in `scraping_runs` table in SQLite
   - Enables tracking scraping health over time

### Verification:
- Scraper still functions identically
- Invalid scraped data is caught before database write
- Selector changes require editing only one file

---

## COMPLETION CRITERIA

The system is production-hardened when ALL of the following are true:

- [ ] Zero hardcoded secrets in codebase or git history
- [ ] SQLite database replaces CSV-in-memory loading
- [ ] `data_processor.py` is decomposed into `core/` modules
- [ ] All `print()` replaced with structured logging
- [ ] Core test suite passes (building matching, estimation, cross-referencing, ingestion)
- [ ] Scraper selectors are externalized
- [ ] App produces identical outputs to pre-refactor baseline
- [ ] `README.md` updated with new architecture, setup instructions, and migration guide

---

## IMPORTANT REMINDERS

- **Test after every phase.** Run the app, search for leads, query the AI chat, check client profiles. If anything is broken, fix it before moving on.
- **The domain logic is sacred.** The Shoreline mappings, building aliases, bedroom estimation cascades, and size ranges represent months of real-world validation against Palm Jumeirah market data. Do not modify, simplify, or "clean up" these values.
- **When in doubt, ask.** If a refactor decision could go multiple ways, present the options rather than picking one.
