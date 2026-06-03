# ORVA — Property Intelligence Platform

> Full-stack real estate intelligence SaaS for Dubai's Palm Jumeirah market. Built entirely solo from scratch.

<p align="center">
  <img src="screenshots/01-lead-search.svg" alt="Lead Search — 78,975 Palm Jumeirah owner contacts" width="100%"/>
</p>

---

## What it does

ORVA is a production-grade property intelligence platform built for Dubai real estate agents working the Palm Jumeirah market. It turns a database of **78,975 owner contacts** and **36,500+ DLD transactions** into actionable outreach intelligence.

At its core:
- **Search any of 78,975 Palm Jumeirah owner contacts** by building, unit, bedroom count, size, and completeness score — ranked so the best leads surface first
- **AI-powered market analysis** via a Claude-backed chat interface with 12 custom property tools (portfolio lookup, yield calculation, expiring lease identification, building intel, and more)
- **WhatsApp campaign automation** with dual-account support, real-time progress, and a 36-message/day rate limit that persists across restarts
- **Lease expiry intelligence** — cross-reference 4,569 Ejari rental contracts with owner data to surface landlords whose tenants are leaving in the next 30–90 days
- **Listing matching** — match a live Bayut/PropertyFinder listing to the unit owner in the database in under a second

---

## Screenshots

| | |
|---|---|
| <img src="screenshots/02-ai-chat.svg" alt="HLM AI Chat" width="100%"/> | <img src="screenshots/03-whatsapp-campaign.svg" alt="WhatsApp Campaign Builder" width="100%"/> |
| **HLM AI Chat** — Claude-powered market intelligence with 12 custom property tools | **WhatsApp Campaigns** — Dual-account automation, rate-limited at 36/day, live progress |

| | |
|---|---|
| <img src="screenshots/04-client-profile.svg" alt="Client Profile" width="100%"/> | <img src="screenshots/05-lease-expiry.svg" alt="Lease Expiry Dashboard" width="100%"/> |
| **Client Profile** — Full CRM: portfolio, notes, call log, follow-up reminders | **Lease Expiry** — Ejari rental contracts cross-referenced with owner contacts |

<p align="center">
  <img src="screenshots/06-mobile-nav.svg" alt="Mobile UI" width="320"/>
  <br/>
  <em>Mobile-first UI — works on phone while walking into meetings</em>
</p>

---

## Tech Stack

**Frontend**
![Next.js](https://img.shields.io/badge/Next.js_16-black?logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_v4-06B6D4?logo=tailwindcss&logoColor=white)
![React](https://img.shields.io/badge/React_19-61DAFB?logo=react&logoColor=black)

**Backend**
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.11-3776AB?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite_WAL-003B57?logo=sqlite&logoColor=white)
![Alembic](https://img.shields.io/badge/Alembic-6B7280)

**AI / Automation**
![Anthropic](https://img.shields.io/badge/Claude_3.7_Sonnet-D97706?logo=anthropic)
![Playwright](https://img.shields.io/badge/Playwright-45ba4b?logo=playwright&logoColor=white)

**Infrastructure**
![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?logo=docker&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-009639?logo=nginx&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu_22.04_VPS-E95420?logo=ubuntu&logoColor=white)

---

## Architecture

```
                        orvauae.com (HTTPS)
                              │
                          [nginx]
                         /         \
              ┌──────────┐       ┌──────────────┐
              │ orva-web │       │   orva_api   │
              │ Next.js  │──────▶│   FastAPI    │
              │ :3000    │       │   :8000      │
              └──────────┘       └──────┬───────┘
                                        │
                         ┌──────────────┼──────────────┐
                         │              │              │
                    ┌────▼────┐  ┌──────▼──────┐  ┌───▼──────┐
                    │ SQLite  │  │  CSV/Parquet │  │ Baileys  │
                    │  WAL    │  │  78K leads   │  │ WhatsApp │
                    │ 15 tbls │  │  36.5K DLD   │  │ :3001/02 │
                    └─────────┘  └─────────────┘  └──────────┘
```

**Three services, one `docker-compose.yml`:**

| Service | Tech | Role |
|---|---|---|
| `web` | Next.js 16, React 19, Tailwind v4 | Customer-facing UI |
| `api` | FastAPI, Python 3.11, Pydantic | REST API + AI tools |
| `wa-1` / `wa-2` | Node.js, Baileys | WhatsApp automation |

---

## Data Engine

The core of the platform is a **10-priority bedroom inference cascade** that determines the correct number of bedrooms for a lead when the source data is incomplete:

```
Priority 0:   Exact DLD reference lookup (title deed)
Priority 1:   Original data in the lead file
Priority 1.5: Live PropertyMonitor DLD lookup
Priority 2:   Unit registry (6-source merged CSV, ~30K units)
Priority 2.3: Live PropertyFinder scraper lookup
Priority 2.6: Bayut size-match (±75 sqft consensus)
Priority 3:   Static building schema (Shoreline, Oceana, etc.)
Priority 3.5: Dynamic schema (auto-learned suffix patterns)
Priority 4:   Unit pattern table
Priority 5:   Size-based inference
Priority 6:   Building defaults
```

This matters because sending a pitch to an owner with the wrong bedroom count destroys credibility. The cascade runs on every lead at load time.

---

## Key Features

### 🔍 Lead Search
- **78,975 Palm Jumeirah owner contacts** with phone numbers, transaction history, unit details
- Filter by building, bedrooms, size range — sorted by completeness score
- Paginated at 250/page, exports full results to CSV
- Per-lead completeness scoring (phone 30% · name 25% · unit 20% · beds 15% · size 10%)

### 🤖 HLM — AI Property Intelligence
- Claude Sonnet 3.7 with **12 custom property tools** via tool-use API
- Tools include: `search_leads_for_ai`, `get_building_info_for_ai`, `get_market_stats_for_ai`, `get_listings_below_market_for_ai`, `get_portfolio_summary_for_ai`, `find_potential_owners_for_ai`, `cross_reference_sale_with_leads_for_ai`, `get_complete_building_intel_for_ai`, `get_propertyfinder_listings_for_ai`, and more
- Streamed responses via Server-Sent Events (SSE)
- Persistent chat history per conversation

### 📱 WhatsApp Campaigns
- Dual WhatsApp account support (2 Baileys Node.js servers)
- 36-message/day rate limit persisted to CSV across restarts
- Campaign builder: filter leads → preview queue → send with live progress
- Message log, reply detection, excluded-phone-number management
- Personalised message templates that adapt based on owner type

### 🏠 Lease Expiry Dashboard
- 4,569 Ejari rental contracts from PropertyMonitor
- Cross-reference expiring leases against owner contact database
- Filter by window (30/60/90/180 days), building, bedrooms
- 62% of expiring leases have matched owner contact data
- Export to CSV for targeted calling campaigns

### 📊 Listing Matcher
- Match a Bayut / PropertyFinder listing URL → owner in database
- Three-pass confidence scoring: exact unit (95%) → exact size (90%) → beds + size range (40–60%)
- Sub-second results from the 78K lead index

### 👥 Contacts CRM
- Standalone contacts separate from the owner database (buyers, tenants, brokers)
- Properties, linked leads, budget ranges, notes, follow-ups, call log
- Auto-link to lead database by phone number on creation

---

## Database

SQLite (WAL mode) with **15 tables** and full Alembic migration history:

```sql
leads            -- 78,975 owner records from 6 source files
transactions     -- 36,500 DLD title deed sales
cross_references -- precomputed lead↔transaction joins
rentals          -- 4,569 Ejari rental contracts (market rent intel)
bayut_listings   -- active listings from public Bayut scraper
pf_listings      -- PropertyFinder public scraper output
unit_registry    -- ~30K units merged from all 6 sources
contacts         -- standalone CRM contacts (buyers/tenants/brokers)
contact_properties
contact_lead_links
client_notes
client_reminders
call_log
whatsapp_messages
scraped_units
```

Multi-tenant ready: every table carries a `tenant_id` column (default `'orva'`). Schema changes are versioned via Alembic.

---

## API

**8 FastAPI routers, 50+ endpoints:**

| Router | Example endpoints |
|---|---|
| `auth` | `POST /api/auth/login`, `GET /api/auth/me` |
| `leads` | `GET /api/leads?building=Shoreline&bedrooms=2` |
| `clients` | `GET /api/clients/{id}`, `POST /api/clients/{id}/notes` |
| `contacts` | Full CRUD, property management, lead auto-linking |
| `listings` | `GET /api/lease-expiry`, `POST /api/match/listing`, `GET /api/bayut/listings`, `POST /api/client-match` |
| `chat` | `POST /api/chat` (SSE streaming), conversation history |
| `whatsapp` | Campaign builder, stats, `GET /api/whatsapp/progress` (SSE) |
| `admin` | `GET /api/admin/health`, `GET /api/admin/backup` |

JWT authentication with 7-day expiry. Token carried in `Authorization: Bearer` header or `?token=` query param (for SSE endpoints that browser can't authenticate via headers).

---

## Testing

**12 regression suites, 200+ checks**, all passing:

| Suite | What it tests |
|---|---|
| `test_bedroom_accuracy.py` | 10-priority cascade correctness |
| `test_ai_queries_split.py` | AI tool module isolation |
| `test_data_consolidation.py` | SQLite schema + 6-source importer pipeline |
| `test_sqlite_cutover_and_hardening.py` | SQLite-first loader, tenant_id migration, admin endpoints |
| `test_alembic_and_tenants.py` | Alembic upgrade/downgrade, multi-tenant isolation |
| `test_restricted_scrapers_removed.py` | Phase-2 cleanup enforcement |
| `orva_api/test_contacts_router.py` | Contacts API (CRUD, auth, 409 dedup, 422 validation) |
| `orva_api/test_listings_router.py` | Lease/Bayut/Match endpoints, empty-data safety |
| `orva_api/test_cleanup.py` | API hygiene: sys.path, model constant, typed params |
| `orva_api/test_auth_hardening.py` | JWT security, short-secret rejection |
| `whatsapp_bot/test_ban_prevention.py` | Rate limiting, exclusion list, phone normalisation |
| `propertyfinder_scraper/test_csv_write.py` | CSV safety, quote escaping, dedup |

---

## Deployment

Single-command deploy via Docker Compose:

```bash
git pull
alembic upgrade head
docker compose up -d --build
```

Four containers:
- `api` — FastAPI (non-root user, `HEALTHCHECK` every 30s)
- `web` — Next.js standalone build
- `wa-1` / `wa-2` — WhatsApp Baileys servers

Nginx handles SSL termination and proxies `/api/*` to the FastAPI container.

---

## The Engineering Story

This started as a 4,500-line Streamlit script. Over the course of an intensive development arc it was restructured into a production multi-tenant platform:

- **9 code-quality PRs** — bedroom cascade accuracy, ban-risk hardening, auth security, typed API, Docker hardening
- **SaaS conversion** — deleted restricted scrapers, ported all Streamlit pages to Next.js, moved from CSV-per-source to unified SQLite
- **13 regressions fixed** — in production, across auth, SQLite WAL, nginx routing, mixed-content HTTPS, timeout vectorisation
- **Net result**: −12,000 lines removed, +10,000 lines of real production code added

The commit history in this repo tells the full story.

---

## About

Built by **Harry Stracey** — a Dubai real estate broker who taught himself to code to solve a problem that existing tools couldn't.

No framework tutorials. No bootcamp. Just: "this needs to exist, how do I build it."

> *"What is this, it's not a Streamlit app anymore."*

---

*Palm Jumeirah, Dubai — 2025–2026*
