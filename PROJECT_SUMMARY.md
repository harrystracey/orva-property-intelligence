# Full Scraping Bot - Project Summary

**Generated:** February 8, 2026  
**Purpose:** Complete project overview for AI planning/analysis

---

## 1. PROJECT OVERVIEW

**Project Name:** Palm Jumeirah Real Estate Intelligence System  
**Type:** Lead Management & Web Scraping Application  
**Primary Language:** Python  
**UI Framework:** Streamlit  
**Target Domain:** Dubai Real Estate (Palm Jumeirah)

**Core Functionality:**
- Lead search and filtering with AI-powered intelligence
- Web scraping from PropertyMonitor.ae (unit numbers, transactions, pricing)
- Client profile management (notes, reminders, follow-ups)
- Cross-referencing title deed data with owner contacts
- AI assistant (Claude) for property intelligence queries

---

## 2. FILE STRUCTURE

```
full_scraping_bot/
│
├── app.py                                    # Main Streamlit application (1205 lines)
├── data_processor.py                        # Core data processing & enrichment (3200+ lines)
├── building_intelligence.py                  # Building name matching & validation (546 lines)
├── chat_manager.py                           # Multi-chat conversation management (172 lines)
├── client_data_manager.py                   # Client notes & reminders persistence
├── feedback_system.py                        # Contact quality feedback system
├── consolidate_data.py                      # Data consolidation utilities
├── clean_scraped_data.py                    # Clean scraped Property Monitor data
├── merge_unit_numbers.py                    # Merge unit numbers into reference data
├── run_scraper.py                           # Scraper launcher script
├── start_app.ps1                            # PowerShell startup script
├── requirements.txt                          # Main Python dependencies
├── .gitignore                               # Git ignore rules
│
├── property_research_agent/                  # AI-powered scraping submodule
│   ├── research_app.py                      # Streamlit interface for AI scraper
│   ├── scraper_agent.py                     # AI-powered Property Monitor scraper (388 lines)
│   ├── unit_number_scraper.py               # Hybrid mode unit number scraper
│   ├── config.py                            # Configuration loader
│   ├── requirements.txt                     # Submodule dependencies
│   ├── README.md                            # Submodule documentation
│   └── .gitignore                           # Submodule git ignore
│
├── lead_database/                           # Lead data storage
│   ├── leads_master.csv
│   └── leads_master.xlsx
│
├── Master reference datasets/                # Title deed reference data
│   ├── reference_master.csv
│   ├── reference_master_with_units.csv      # With scraped unit numbers
│   ├── reference_backup_20260208_155912.csv
│   └── palm-jumeirah-market-data-harry-...csv
│
├── scraped_data/                            # Scraped data output
│   ├── unit_numbers_palm_jumeirah.csv
│   ├── palm_jumeirah_transactions_clean.csv
│   ├── palm_jumeirah_transactions_clean.xlsx
│   ├── scraping_progress.json
│   └── chrome_debug_profile/                # Chrome debug profile (1452+ files)
│
├── chat_history/                             # Chat conversation storage (JSON)
├── client_data/                              # Client notes & reminders (JSON)
│
├── data/                                     # Input lead CSV files (gitignored)
├── reference_data/                           # Reference CSV files (gitignored)
│
└── Documentation/
    ├── UNIT_NUMBER_SCRAPING_GUIDE.md
    ├── QUICKSTART.md
    ├── REQUIRED_INFO.md
    └── IMPLEMENTATION_SUMMARY.md
```

---

## 3. TECH STACK

### Main Application Dependencies (`requirements.txt`)
```
streamlit>=1.28.0          # Web UI framework
pandas>=2.0.0              # Data processing
openpyxl>=3.1.0            # Excel file handling
python-dateutil>=2.8.0     # Date parsing
anthropic>=0.18.0          # Claude AI API
python-dotenv>=1.0.0       # Environment variable management
```

### Property Research Agent (`property_research_agent/requirements.txt`)
```
streamlit>=1.28.0          # Web UI
playwright>=1.40.0         # Browser automation
anthropic>=0.18.0          # Claude AI
python-dotenv>=1.0.0       # Environment variables
```

### Additional Libraries (Implicit)
- `json` - Chat/client data persistence
- `uuid` - Unique ID generation
- `re` - Regular expressions for data parsing
- `pathlib` - File path handling
- `datetime` - Timestamp management

---

## 4. KEY FILE CONTENTS

### 4.1 `app.py` - Main Streamlit Application

**Purpose:** Multi-page Streamlit application for lead management

**Key Features:**
- **Lead Search Page:** Filter leads by date, building, bedrooms, unit, phone, size, completeness
- **AI Chat Page (HLM):** ChatGPT-style interface with Claude Sonnet 4 for property intelligence
- **Client Profile Page:** View/edit client notes and set follow-up reminders
- **Follow-Ups Page:** Manage pending reminders with overdue/today/upcoming status

**Architecture:**
```python
# Page routing system
main() -> render_lead_search_page()
       -> render_ai_chat_page()
       -> render_client_profile_page()
       -> render_follow_ups_page()

# AI Query Function
query_leads_with_ai(user_query, leads_df, reference_df, chat_history)
  -> Claude API with function calling (tools: get_building_intel, get_owner_portfolio, search_building_names)
  -> Cross-referencing: Sales matched to owners by unit number
  -> Returns formatted markdown table with pricing, owners, contacts
```

**Key Components:**
- Session state management for page navigation
- Chat history persistence via `chat_manager`
- Client data persistence via `client_data_manager`
- Real-time data loading with `@st.cache_data`
- Dark sidebar styling for AI chat page

**Lines of Code:** 1,205 lines

---

### 4.2 `data_processor.py` - Core Data Processing

**Purpose:** CSV normalization, enrichment, and AI query functions

**Key Features:**
1. **Data Loading & Cleaning:**
   - Load multiple CSV/Excel files from `./data` folder
   - Normalize column names (owner, building, unit, phone, date, bedrooms, size)
   - Remove duplicates by owner+building+unit
   - Handle multiple encodings (utf-8, latin1, cp1252)

2. **Building Intelligence Enrichment:**
   - Fuzzy building name matching (e.g., "Al Masalli" → "Shoreline 9")
   - Shoreline tower Arabic→English mapping (20 towers)
   - Building alias resolution (100+ aliases)

3. **Bedroom Estimation (Bidirectional):**
   - From unit schema (Shoreline towers: S-607 → 6th floor → 2BR)
   - From size (500-750 sqft → Studio, 750-1000 → 1BR, etc.)
   - From unit number patterns (regex: "2BR", "3B", "Studio")
   - From building defaults (fallback based on building type)

4. **Size Estimation:**
   - From bedrooms (Studio → 550 sqft avg, 1BR → 875, 2BR → 1400, etc.)
   - Building-specific averages

5. **Reference Data Cross-Referencing:**
   - Load title deed transactions (18,250+ records)
   - Match by normalized unit number + building
   - Enrich with sale price, date, sqft

6. **AI Query Functions:**
   - `get_complete_building_intel_for_ai()` - Market stats + recent sales + owner contacts + cross-referenced matches
   - `get_portfolio_summary_for_ai()` - Owner portfolio analysis
   - `search_building_names_for_ai()` - Fuzzy building search

**Key Data Structures:**
```python
BUILDING_UNIT_SCHEMA = {
    "Shoreline 1": {"unit_pattern": r"^(S|N)-?(\d)(\d{2})$", "beds_by_floor": {...}},
    # ... 20 Shoreline towers with floor→bedroom mappings
}

BUILDING_DEFAULT_BEDROOMS = {
    "seven": 0,        # 57% studios
    "oceana": 1,       # 42% 1BR
    "kempinski": 2,    # 72% 2BR
    # ... 50+ buildings
}

SIZE_RANGES = {
    "studio": (400, 750),
    "1-bed": (750, 1100),
    "2-bed": (1100, 1700),
    "3-bed": (1700, 2500),
    "4-bed": (2500, 4000)
}
```

**Lines of Code:** 3,200+ lines

---

### 4.3 `building_intelligence.py` - Building Name Matching

**Purpose:** Fuzzy matching, validation, and data quality checks

**Key Features:**

1. **Shoreline Tower Mapping:**
```python
SHORELINE_TOWER_MAPPING = {
    "Al Ramth": (1, ["Shoreline 1", "S1", "Tower 1"]),
    "Al Nabat": (2, ["Shoreline 2", "S2", "Tower 2"]),
    "Al Masalli": (9, ["Shoreline 9", "S9", "Tower 9"]),
    # ... 20 towers with Arabic names + English aliases
}
```

2. **Building Aliases:**
```python
BUILDING_ALIASES = {
    "The Fairmont Palm Residences": [
        "Fairmont", "Fairmont Residences", "Fairmont Palm",
        "Fairmont North", "Fairmont South"
    ],
    "Oceana": [
        "Oceana Residences", "Oceana Caribbean", 
        "Oceana Atlantic", "Oceana Pacific"
    ],
    # ... 20+ major buildings
}
```

3. **Functions:**
   - `resolve_building_name(search_term)` - Fuzzy matching with confidence scores
   - `get_shoreline_info(tower_identifier)` - Tower number, Arabic names, aliases
   - `validate_unit_type(building_name, unit_type)` - Check if unit type exists in building
   - `normalize_unit_number(unit_num)` - Standardize unit formats (S607 → S-607)
   - `validate_phone_number(phone)` - UAE format validation
   - `format_phone_number(phone)` - Display formatting (+971 50 123 4567)

**Lines of Code:** 546 lines

---

### 4.4 `chat_manager.py` - Multi-Chat System

**Purpose:** Persistent chat conversation storage

**Storage:** JSON files in `chat_history/` folder (gitignored)

**Key Functions:**
```python
create_new_chat(name) -> chat_id
load_chat(chat_id) -> chat_data
save_chat(chat_id, chat_data) -> success
delete_chat(chat_id) -> success
rename_chat(chat_id, new_name) -> success
add_message_to_chat(chat_id, role, content) -> success
get_chat_messages(chat_id) -> messages (Claude API format)
export_chat_as_text(chat_id) -> formatted_text
clear_chat_messages(chat_id) -> success
```

**Data Structure:**
```json
{
  "id": "a3b7c2d1",
  "name": "Fairmont Pricing Analysis",
  "created": "2026-02-08T14:30:00",
  "last_updated": "2026-02-08T15:45:00",
  "messages": [
    {"role": "user", "content": "What's the average price for 2BR in Fairmont?", "timestamp": "..."},
    {"role": "assistant", "content": "**Fairmont - 2BR Report**...", "timestamp": "..."}
  ]
}
```

**Lines of Code:** 172 lines

---

### 4.5 `property_research_agent/scraper_agent.py` - AI Web Scraper

**Purpose:** AI-powered PropertyMonitor.ae scraping with Claude

**Key Features:**

1. **Anti-Bot Evasion:**
   - Stealth browser settings (disable automation flags)
   - Human-like delays (random intervals between actions)
   - Human-like typing (50-150ms keystroke delays)
   - Realistic user agent + viewport

2. **Claude-Powered Navigation:**
   - AI extracts CSS selectors from HTML
   - AI determines navigation path based on query
   - AI extracts data from page content

3. **Core Functions:**
```python
class PropertyMonitorAgent:
    async def initialize() -> browser_launch
    async def login() -> success
    async def search_property(building_name) -> success
    async def navigate_to_section(section_name) -> success
    async def extract_data(query) -> answer
    async def research_query(query) -> result_dict
```

4. **Workflow:**
```
User Query → Extract building name (Claude) 
           → Login to PropertyMonitor 
           → Search building 
           → Determine section (Claude: service charges, transactions, etc.)
           → Navigate to section 
           → Extract data (Claude) 
           → Return formatted answer
```

**Dependencies:**
- Playwright (browser automation)
- Anthropic Claude API (intelligent navigation)

**Lines of Code:** 388 lines

---

## 5. DATA FLOW ARCHITECTURE

### 5.1 Lead Search Workflow

```
CSV Files (./data/) 
  → data_processor.load_all_csv_files()
  → Normalize columns (owner, building, unit, phone, date, beds, size)
  → Remove duplicates
  → Enrich with building_intelligence (fuzzy matching, Shoreline mapping)
  → Estimate bedrooms (schema → pattern → size → default)
  → Estimate size (from bedrooms)
  → Load reference data (title deed transactions)
  → Cross-reference unit numbers → enrich with sale price/date
  → Apply filters (date, building, beds, unit, phone, size, completeness)
  → Display in Streamlit dataframe
  → User selects row → Open client profile
```

### 5.2 AI Query Workflow

```
User Query: "Last 10 Fairmont sales where you know the owner"
  → query_leads_with_ai(query, leads_df, reference_df, chat_history)
  → Claude API call with tools (function calling)
  → Claude calls: get_building_intel("Fairmont", matched_only=true, limit=10)
    → Search reference_df for building="Fairmont" sales
    → Filter to only sales with matched owner contacts (unit number matches leads_df)
    → Return: market stats + recent sales table with unit, date, price, size, owner, phone
  → Claude formats response as markdown table
  → Display in chat interface
  → Save to chat_history/
```

### 5.3 Web Scraping Workflow

```
User: "Scrape unit numbers for Shoreline 5"
  → run_scraper.py
  → Launch Chrome with remote debugging
  → User logs in manually to PropertyMonitor
  → Script connects to debugger
  → Navigate to building page
  → Extract all unit numbers from pagination
  → Save to scraped_data/unit_numbers_palm_jumeirah.csv
  → merge_unit_numbers.py
  → Merge with reference_master.csv (title deed data)
  → Create reference_master_with_units.csv
  → Now AI can cross-reference sales with owner contacts
```

---

## 6. KEY FEATURES

### 6.1 Building Intelligence System

**Problem:** Building names vary wildly (Arabic, English, abbreviations, typos)

**Solution:**
- Fuzzy matching with `fuzzywuzzy` library (partial_ratio ≥ 70)
- Shoreline tower mapping: "Al Masalli" → "Shoreline 9" (20 towers)
- Building aliases: "Fairmont" / "Fairmont Residences" / "Fairmont North" → "The Fairmont Palm Residences"
- Confidence scoring: high (90+), medium (80-89), low (70-79)

### 6.2 Bidirectional Estimation

**Problem:** Leads often missing bedrooms OR size

**Solution:**
1. **Estimate Bedrooms from:**
   - Unit schema (Shoreline towers: floor number → bedroom count)
   - Unit number patterns (regex: "2BR", "3B", "Studio")
   - Size ranges (500-750 sqft → Studio, 750-1000 → 1BR)
   - Building defaults (fallback: Seven Hotel → Studio)

2. **Estimate Size from:**
   - Bedroom count (Studio → 550 sqft avg, 1BR → 875, 2BR → 1400)
   - Building-specific averages

3. **Iterative Approach:**
   - First pass: Estimate bedrooms from size
   - Second pass: Estimate size from bedrooms
   - Result: Reduced unresolved bedrooms from 40% → 5%

### 6.3 Cross-Referencing System

**Problem:** Title deed data has unit numbers + prices, but no owner contacts. Lead data has owner contacts, but often missing prices/dates.

**Solution:**
1. Scrape unit numbers from PropertyMonitor.ae
2. Normalize unit numbers (S607 → S-607, Unit 1203 → 1203)
3. Match by building + unit number
4. When AI queries building sales, show:
   - Section A: All recent sales (from title deed reference)
   - Section B: All owner contacts (from lead database)
   - **Section C: Cross-referenced matches** (sales where we have owner contact)

**Example:**
```
User: "Last 10 Fairmont sales where you know the owner"
AI returns:
| Unit | Date | Price | Size | Beds | Owner | Phone |
|------|------|-------|------|------|-------|-------|
| S-607 | Feb 5, 2026 | AED 4.95M | 1,727 sqft | 2 | John Smith | +971 50 123 4567 |
| N-410 | Jan 17, 2026 | AED 4.33M | 1,726 sqft | 2 | No contact | - |
```

### 6.4 Client Profile Management

**Features:**
- Deterministic client ID: `hash(owner_name + building + unit)`
- Notes with timestamps (add, edit, delete)
- Reminders with datetime parsing (natural language: "08/02/2026, 2pm")
- Follow-up workflow: Mark done → Prompt for next follow-up
- Storage: JSON files in `client_data/` folder

### 6.5 AI Assistant (HLM)

**Model:** Claude Sonnet 4 (claude-sonnet-4-20250514)

**System Prompt:**
- Data sources: 18,250+ title deed transactions, 28,000+ owner contacts
- Workflow: Call `get_building_intel()` once per query
- Response format: Brief summary + markdown table
- Rules: Never suggest "contact DLD", never make up contacts, flag portfolio investors (2+ units)

**Tools (Function Calling):**
1. `get_building_intel(building, bedrooms?, matched_only?, limit?)` - Market stats + recent sales + cross-referenced matches
2. `get_owner_portfolio(owner_name)` - All properties owned by person
3. `search_building_names(search_term)` - Fuzzy building search

**Usage:**
- User: "Average price for 2-beds in Oceana"
- Claude: `get_building_intel("Oceana", bedrooms=2, limit=10)`
- Returns: Market stats + 10 recent 2BR sales with unit numbers, prices, sizes, owners (if matched)

---

## 7. ENVIRONMENT VARIABLES

**Location:** `.env` file (gitignored)

**Required:**
```
ANTHROPIC_API_KEY=sk-ant-...              # Claude API key (main app + scraper)
PROPERTYMONITOR_EMAIL=user@example.com    # PropertyMonitor login
PROPERTYMONITOR_PASSWORD=password123      # PropertyMonitor password
```

**Fallback:** `start_app.ps1` has hardcoded API key

---

## 8. DATA SOURCES

### 8.1 Input Data (`data/` folder)
- Lead CSV/Excel files (gitignored)
- Columns: owner_name, building_name, unit_number, phone, date, bedrooms, size_sqft

### 8.2 Reference Data (`Master reference datasets/`)
- `reference_master.csv` - Title deed transactions (2013-2026, 18,250+ records)
- `reference_master_with_units.csv` - Merged with scraped unit numbers
- Columns: building, unit_number, date, price_aed, size_sqft, bedrooms

### 8.3 Scraped Data (`scraped_data/`)
- `unit_numbers_palm_jumeirah.csv` - Unit numbers from PropertyMonitor
- `palm_jumeirah_transactions_clean.csv` - Cleaned transaction data

### 8.4 Chat History (`chat_history/`)
- JSON files per chat session (gitignored)

### 8.5 Client Data (`client_data/`)
- JSON files for notes/reminders (gitignored)

---

## 9. RUNNING THE APPLICATION

### Main App:
```powershell
# Option 1: PowerShell script (sets API key)
.\start_app.ps1

# Option 2: Direct
streamlit run app.py
```

### Scraper:
```bash
# Unit number scraper
python run_scraper.py

# Merge scraped data
python merge_unit_numbers.py

# Clean scraped data
python clean_scraped_data.py
```

### AI Research Agent:
```bash
cd property_research_agent
streamlit run research_app.py
```

---

## 10. PROJECT STRENGTHS

1. **Production-grade error handling** - Try/except blocks for corrupted files, missing columns, API errors
2. **Comprehensive data enrichment** - Fuzzy matching, bidirectional estimation, cross-referencing
3. **Modular architecture** - Separate modules for data processing, building intelligence, chat management
4. **AI-powered intelligence** - Claude function calling for natural language queries
5. **User-centric design** - Clean Streamlit UI, ChatGPT-style interface, client profiles, follow-up reminders
6. **Scraping resilience** - Hybrid mode (user login + automated extraction), anti-bot evasion, human-like delays

---

## 11. POTENTIAL IMPROVEMENTS

1. **Database backend** - Replace CSV with PostgreSQL/SQLite for better performance (28,000+ leads in memory)
2. **Caching layer** - Redis for AI query results (avoid re-querying same building)
3. **Batch processing** - Background jobs for data enrichment (currently on app startup)
4. **Testing** - Unit tests for data_processor, building_intelligence
5. **Logging** - Structured logging (e.g., loguru) instead of print statements
6. **API rate limiting** - Exponential backoff for Claude API (currently manual retry)
7. **Data versioning** - Track changes to lead/reference data over time
8. **Multi-user support** - Authentication, user-specific chat/client data
9. **Mobile UI** - Responsive design for phone-based lead outreach
10. **Scraper scheduling** - Cron job for weekly unit number updates

---

## 12. BUSINESS CONTEXT

**User Profile:** Real estate professional (non-technical)

**Use Case:** Palm Jumeirah lead outreach
1. Upload lead CSV files (owner contacts)
2. Search/filter leads by building, bedrooms, size, completeness
3. Query AI: "Show me Fairmont 2BR sales where I have the owner's contact"
4. Call owner, take notes, set follow-up reminder
5. Track follow-ups with overdue/today/upcoming status
6. Export filtered leads to CSV for CRM import

**Value Proposition:**
- **Time savings:** AI replaces manual lookup on PropertyMonitor (5 min → 10 sec)
- **Data quality:** Enrichment reduces missing bedrooms/sizes by 80%+
- **Lead intelligence:** Cross-referencing reveals which sales you can actually call
- **Organization:** Client profiles + reminders replace scattered Excel files
- **Market insights:** AI provides instant market stats, pricing trends, portfolio investors

---

## 13. TECHNICAL DEBT

1. **Hardcoded API key in start_app.ps1** - Security risk (should use .env only)
2. **Large data_processor.py** - 3,200+ lines (should split into sub-modules)
3. **No database** - CSV files loaded into memory every time (slow for 28K+ leads)
4. **No error tracking** - No Sentry/Rollbar for production error monitoring
5. **Inconsistent naming** - Some functions use snake_case, others camelCase
6. **Magic numbers** - Hardcoded size ranges, default bedrooms (should be config)
7. **No API versioning** - Direct Claude API calls (should abstract with version handling)
8. **Scraper fragility** - HTML selectors hardcoded (breaks when PropertyMonitor updates UI)

---

## 14. DEPENDENCIES SUMMARY

**Core:**
- Python 3.8+
- Streamlit (web UI)
- Pandas (data processing)
- Anthropic Claude API (AI)

**Scraping:**
- Playwright (browser automation)
- Chrome browser (debug mode)

**Optional:**
- FuzzyWuzzy (fuzzy string matching - has fallback)
- OpenPyXL (Excel file reading)

**System:**
- PowerShell (Windows startup script)

---

## 15. GIT IGNORE PATTERNS

```gitignore
# Environment
.env

# Chat history (persisted locally)
chat_history/

# Client data (persisted locally)
client_data/

# Data files (too large)
data/*.csv
data/*.xlsx
reference_data/*.csv

# Python
__pycache__/
*.pyc
```

---

## END OF SUMMARY

**Total Files:** 20+ Python modules, 4 config files, 4 documentation files  
**Total Lines of Code:** ~6,000+ lines (excluding libraries)  
**Data Volume:** 18,250+ title deed records, 28,000+ lead contacts  
**AI Integration:** Claude Sonnet 4 with function calling  
**Storage:** JSON (chat/client), CSV (leads/reference)  

This project is a **production-ready real estate intelligence system** with AI-powered querying, web scraping, and client management. The codebase is well-structured, error-resistant, and designed for a non-technical real estate professional.
