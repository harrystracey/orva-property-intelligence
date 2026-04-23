"""
HLM Chat Service — core logic for AI property intelligence chat.
Migrated from app.py (Streamlit) to standalone service for FastAPI.
"""

import json
import time
import re
import uuid
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator

import pandas as pd
import anthropic

from ..config import ANTHROPIC_API_KEY, CHAT_HISTORY_DIR, PROJECT_ROOT, BAYUT_CSV_PATH, RENTALS_CSV_PATH
from .. import _sys_paths  # noqa: F401 -- puts project root on sys.path


# Default to the current latest Sonnet. Override with CLAUDE_MODEL if you need
# to pin to a specific snapshot, downgrade to Haiku for cheaper runs, or
# upgrade when a newer model lands, without redeploying code.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

from data_processor import standardize_building_name  # noqa: E402
from ai_queries import (  # noqa: E402
    get_complete_building_intel_for_ai,
    get_portfolio_summary_for_ai,
    search_building_names_for_ai,
    get_listings_below_market_for_ai,
    get_propertyfinder_listings_for_ai,
)
from rental_processor import load_rental_data, get_rental_intel_for_ai  # noqa: E402

# --------------------------------------------------------------------------- #
#  Tool Definitions (10 query tools — no WhatsApp)
# --------------------------------------------------------------------------- #

TOOLS = [
    {
        "name": "get_building_intel",
        "description": "Get building intelligence: market pricing with unit numbers, owner contacts, and cross-referenced matches. Set matched_only=true when user asks for sales 'where you know the owner' or 'with contacts'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name (e.g., 'Ellington', 'Shoreline 5', 'Al Masalli', 'Fairmont')"},
                "bedrooms": {"type": "integer", "description": "Filter by bedrooms (0=studio, 1, 2, 3, 4+). Optional."},
                "matched_only": {"type": "boolean", "description": "If true, only return sales where owner contact is known from lead database. Default false."},
                "limit": {"type": "integer", "description": "Max number of recent sales to return. Default 10."},
            },
            "required": ["building"],
        },
    },
    {
        "name": "get_owner_portfolio",
        "description": "Get all properties owned by a specific person from lead database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_name": {"type": "string", "description": "Owner name"},
            },
            "required": ["owner_name"],
        },
    },
    {
        "name": "search_building_names",
        "description": "Find building by partial name. Use ONLY if get_building_intel returns no data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_term": {"type": "string", "description": "Partial building name"},
            },
            "required": ["search_term"],
        },
    },
    {
        "name": "get_rental_intel",
        "description": "Get rental transaction data, lease expiry information, and rental yield analysis for a building or unit on Palm Jumeirah",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name"},
                "bedrooms": {"type": "string", "description": "Bedroom count filter (optional)"},
                "unit_number": {"type": "string", "description": "Specific unit number (optional)"},
                "query_type": {
                    "type": "string",
                    "enum": ["expiring_leases", "rental_history", "rental_yield", "unit_status"],
                    "description": "Type of rental query",
                },
                "days_ahead": {"type": "integer", "description": "For expiring_leases: how many days ahead to look (default 90)"},
                "limit": {"type": "integer", "description": "Max results to return (default 50)"},
            },
            "required": ["building", "query_type"],
        },
    },
    {
        "name": "find_listings_below_market",
        "description": "Find scraped PropertyFinder listings priced below the typical title-deed market for that building (and optionally bedroom count). Use when the user asks for properties below market, good deals, undervalued, or bargains.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Optional building name filter"},
                "bedrooms": {"type": "integer", "description": "Optional bedroom filter (0=studio, 1, 2, 3)"},
                "below_pct": {"type": "number", "description": "Minimum discount below market (default 10 = at least 10% below median)"},
                "limit": {"type": "integer", "description": "Max number of listings to return (default 20)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_propertyfinder_listings",
        "description": "Query active PropertyFinder scraped listings (rentals or sales). Use when user asks about current listings, available units, furnished/unfurnished rentals, or PropertyFinder data. Returns listing details including price, furnished status, URL, and how many times each unit is listed (pf_listing_count = priority).",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name filter. Optional."},
                "listing_type": {"type": "string", "enum": ["rent", "sell", "all"], "description": "Filter by rent or sell. Default 'all'."},
                "bedrooms": {"type": "integer", "description": "Bedroom count filter (0=studio, 1, 2, 3). Optional."},
                "furnished": {"type": "string", "enum": ["Furnished", "Unfurnished", "all"], "description": "Filter by furnished status. Default 'all'."},
                "unit_number": {"type": "string", "description": "Specific unit number. Optional."},
                "limit": {"type": "integer", "description": "Max results (default 50)."},
            },
            "required": [],
        },
    },
    {
        "name": "get_bayut_listings",
        "description": "Get active Bayut property listings on Palm Jumeirah. Use when user asks about active listings, motivated sellers/landlords currently on Bayut, competition analysis, how many units are listed, or current market supply. Returns live listing prices, sizes, views, and Bayut URLs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "listing_type": {"type": "string", "enum": ["all", "sale", "rent"], "description": "Filter by listing type. Default 'all'."},
                "building": {"type": "string", "description": "Optional building name filter."},
                "bedrooms": {"type": "integer", "description": "Optional bedroom count filter (1, 2, 3, 4)."},
                "min_price": {"type": "number", "description": "Optional minimum price in AED."},
                "max_price": {"type": "number", "description": "Optional maximum price in AED."},
                "limit": {"type": "integer", "description": "Max listings to return (default 30)."},
            },
            "required": [],
        },
    },
    {
        "name": "get_unit_info",
        "description": "Look up confirmed unit specifications from the master unit registry (cross-referenced from leads, sales, and rentals). Returns bedrooms, size, view, floor, and transaction history for a specific unit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name (e.g., 'Shoreline 9', 'Fairmont')"},
                "unit_number": {"type": "string", "description": "Unit number (e.g., '1003', 'S-607')"},
            },
            "required": ["building", "unit_number"],
        },
    },
    {
        "name": "match_listing_to_owner",
        "description": (
            "Match a portal listing (Bayut/PF/Dubizzle) against the owner lead database "
            "to identify who owns the unit. Use when the agent asks 'who owns the X-bed in "
            "Shoreline 10 listed at Y', 'find the owner of unit 607 in Ellington', or "
            "'match this listing'. Returns owner name, phone, and confidence score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name as on the portal"},
                "size_sqft": {"type": "number", "description": "Listing size in sqft. Optional but strongly improves accuracy."},
                "bedrooms": {"type": "string", "description": "Bedroom count string: '1', '2', '3', 'Studio', 'PH'. Optional."},
                "unit_number": {"type": "string", "description": "Exact unit number if visible in listing. Optional."},
            },
            "required": ["building"],
        },
    },
    {
        "name": "validate_trakheesi_listing",
        "description": (
            "Resolve a Trakheesi/Madmoun listing GUID to verified property details "
            "(building, zone, size, beds, agency, permit number, status) via the DLD API, "
            "then auto-cross-reference with the lead database to find the owner's name "
            "and phone number. Use when the user provides a Madmoun GUID, a Trakheesi URL, "
            "or asks to look up a specific DLD listing. Takes ~20s."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "guid_or_url": {
                    "type": "string",
                    "description": "The Madmoun GUID string or full Trakheesi validation URL",
                },
            },
            "required": ["guid_or_url"],
        },
    },
]


# --------------------------------------------------------------------------- #
#  Bayut Listings Loader (extracted from app.py)
# --------------------------------------------------------------------------- #

def _load_bayut_listings() -> pd.DataFrame:
    if not BAYUT_CSV_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(BAYUT_CSV_PATH, encoding="utf-8", low_memory=False)
    df["_building_key"] = (
        df["building_name"].fillna("").str.lower()
        .str.replace(r"[\s\-]", "", regex=True)
    )
    return df


def get_bayut_listings_for_ai(listing_type="all", building=None, bedrooms=None,
                               min_price=None, max_price=None, limit=30):
    df = _load_bayut_listings()
    if df.empty:
        return "No Bayut listings data available. Run the Bayut scraper first."

    if listing_type and listing_type != "all":
        df = df[df["listing_type"].str.lower() == listing_type.lower()]
    if building:
        std = standardize_building_name(building) or building
        bkey = std.strip().lower().replace(" ", "").replace("-", "")
        df = df[df["_building_key"].str.contains(bkey, na=False)]
    if bedrooms is not None:
        df = df[pd.to_numeric(df["bedrooms"], errors="coerce").round() == int(bedrooms)]
    if min_price is not None:
        df = df[pd.to_numeric(df["price_aed"], errors="coerce") >= min_price]
    if max_price is not None:
        df = df[pd.to_numeric(df["price_aed"], errors="coerce") <= max_price]

    if df.empty:
        return "No Bayut listings found matching those filters."

    total = len(df)
    sale_n = int((df["listing_type"].str.lower() == "sale").sum())
    rent_n = int((df["listing_type"].str.lower() == "rent").sum())
    buildings_n = df["building_name"].nunique()
    last_scraped = ""
    if "scraped_at" in df.columns:
        ts = df["scraped_at"].dropna()
        if not ts.empty:
            last_scraped = f" — last updated {str(ts.max())[:10]}"

    lines = [
        f"BAYUT LISTINGS ({total} total: {sale_n} for sale, {rent_n} for rent, {buildings_n} buildings{last_scraped})",
        "",
        f"{'Building':<30} {'Type':<5} {'Beds':<5} {'Size sqft':<10} {'Price AED':<14} {'View':<18} URL",
        "-" * 120,
    ]

    display = df.head(limit)
    for _, r in display.iterrows():
        bld = str(r.get("building_name", ""))[:29]
        typ = str(r.get("listing_type", ""))[:4].upper()
        beds = str(int(r["bedrooms"])) if pd.notna(r.get("bedrooms")) else "-"
        size = f"{int(r['size_sqft']):,}" if pd.notna(r.get("size_sqft")) else "-"
        price = f"AED {int(r['price_aed']):,}" if pd.notna(r.get("price_aed")) else "-"
        view = str(r.get("view", "") or "")[:17]
        url = str(r.get("listing_url", "") or "")
        lines.append(f"{bld:<30} {typ:<5} {beds:<5} {size:<10} {price:<14} {view:<18} {url}")

    if total > limit:
        lines.append(f"\n... {total - limit} more listings (use building/bedroom/price filters to narrow down)")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  System Prompt Builder
# --------------------------------------------------------------------------- #

def build_system_prompt(data_store) -> str:
    """Build the HLM system prompt with live database stats."""
    leads_df = data_store.leads_df
    reference_df = data_store.ref_df

    bayut_df = _load_bayut_listings()
    _bayut_total = len(bayut_df) if not bayut_df.empty else 0
    _bayut_sale = int((bayut_df["listing_type"].str.lower() == "sale").sum()) if not bayut_df.empty else 0
    _bayut_rent = int((bayut_df["listing_type"].str.lower() == "rent").sum()) if not bayut_df.empty else 0
    _bayut_bldgs = bayut_df["building_name"].nunique() if not bayut_df.empty else 0
    _bayut_date = str(bayut_df["scraped_at"].dropna().max())[:10] if not bayut_df.empty and "scraped_at" in bayut_df.columns else "unknown"
    _total_leads = len(leads_df) if not leads_df.empty else 0
    _leads_phone = int((leads_df["phone"].fillna("").str.strip() != "").sum()) if not leads_df.empty and "phone" in leads_df.columns else 0
    _leads_bldgs = leads_df["building_name"].nunique() if not leads_df.empty and "building_name" in leads_df.columns else 0
    _ref_count = len(reference_df) if reference_df is not None and not reference_df.empty else 0

    return f"""You are HLM, a real estate intelligence system for Palm Jumeirah, Dubai. You help a broker find owners to call, analyse market pricing, and identify leads.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATABASE SNAPSHOT (live)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lead Database:     {_total_leads:,} owner records | {_leads_phone:,} with phone numbers | {_leads_bldgs} buildings (DLD 2018-2025)
Title Deeds:       {_ref_count:,} sales transactions (Property Monitor - official government source)
Unit Registry:     30,000+ units cross-referenced from 5 sources across 189 buildings
                   Confirmed bedrooms, sizes, views, floor levels with HIGH/MEDIUM/INFERRED confidence
Active Bayut:      {_bayut_total:,} listings ({_bayut_sale} for sale, {_bayut_rent} for rent, {_bayut_bldgs} buildings) - updated {_bayut_date}
PropertyFinder:    Scraped sale/rent listings merged into lead database (with owner contacts where matched)
Rental Contracts:  Ejari data (last 3 years) - lease dates, yields, turnover history

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOLS - PICK THE RIGHT ONE IMMEDIATELY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
get_building_intel          -> Market prices (title deeds) + owner contacts for a building
get_rental_intel            -> Rental yields, expiring leases, tenant turnover history
get_bayut_listings          -> Active Bayut listings - who is currently selling/renting, supply analysis
get_propertyfinder_listings -> Active PF listings with owner contacts (pf_listing_count = motivation)
find_listings_below_market  -> Listings priced below title deed market (deals / undervalued)
get_unit_info               -> Confirmed specs for a specific unit (beds, size, view, floor)
get_owner_portfolio         -> All properties owned by one person
search_building_names       -> Fuzzy search if building name is unclear
match_listing_to_owner      -> Match a portal listing to owner in lead database
validate_trakheesi_listing  -> Look up DLD Trakheesi/Madmoun GUID for property details + owner

TOOL USAGE RULES
- Default: 1 tool per response turn.
- EXCEPTION - Comparisons: When user asks to compare 2 buildings (e.g. "Shoreline vs Oceana", "Palm Views East vs West"), call the tool TWICE (once per building) and present results side by side.
- EXCEPTION - Yield at asking price: call get_bayut_listings for the asking price -> then call get_rental_intel for current rent -> compute (annual_rent / asking_price) x 100 = gross yield.
- EXCEPTION - Both Bayut & PF: when user asks who is listed on both platforms, call get_propertyfinder_listings first (has owner contacts), then get_bayut_listings to cross-check supply.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA SOURCES - WHAT EACH CONTAINS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TITLE DEEDS (Property Monitor - highest reliability)
  Sale prices, dates, sizes, bedroom counts, building names
  NO unit numbers in CSV exports (government security measure)
  NO owner phone numbers
  -> Use for: Pricing analysis, transaction volumes, market trends

LEAD DATABASE (DLD consolidated - 2018-2025)
  Unit numbers, owner names, phone numbers, building names
  Contacts may be 1-2 years old (owner may have sold)
  -> Use for: Who to call, portfolio analysis

UNIT REGISTRY (cross-referenced from 5 sources)
  Confirmed bedrooms, sizes, views, floor levels
  Last sale price + date, last rental price
  -> Use get_unit_info for any specific unit lookup

BAYUT LISTINGS (scraped - updated {_bayut_date})
  Active listings with price, size, beds, view, Bayut URL
  Identifies motivated sellers/landlords currently marketing
  -> Use get_bayut_listings to query

PROPERTYFINDER LISTINGS (scraped + merged with owners)
  listing_type (rent/sell), price, furnished status, URL
  pf_listing_count: 5+ = very motivated owner
  -> Use get_propertyfinder_listings

RENTAL CONTRACTS (Ejari - last 3 years)
  Lease start/end, annual rent, unit details, furnished
  rent_recurrence: "Renewal" = same tenant / "New Contract" = new tenant
  -> Use get_rental_intel

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL LIMITATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Property Monitor title deed exports DO NOT include unit numbers. We CANNOT directly match a recent sale to a current owner. Title deed data and owner contact data are SEPARATE - always present them as two distinct sections.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUILDING NAME HANDLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fuzzy matching is built in. Examples:
- "Shoreline 9" / "Al Masalli" -> Al Masalli (Tower 9)
- "Fairmont" -> The Fairmont Palm Residences
- "The 8" / "The Eight" -> Eight at Palm Jumeirah

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNIT NUMBER SCHEMAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MARINA (1-6)  Format: [floor][unit][letter] e.g. "0401D"
  A=3BR(3,979sqft) B=3BR(2,199sqft) C=2BR(1,621sqft) D=2BR(1,680sqft)
  F=4BR(6,753sqft) G=4BR(5,973sqft) H=5BR(9,555sqft)
  Views: units 01-03=Palm lagoon side | units 05-07=Arabian Gulf side

PALM TOWER  Format: [floor][unit] e.g. "3406"
  Studio~446-525sqft | 1BR~900-951sqft | 2BR~1,842-2,118sqft | 3BR~2,589sqft

SHORELINE (1-20)  Format: [floor][unit] e.g. "607"=Floor6 Unit07
  1=Al Ramth, 2=Al Nabat, 3=Al Sultana, 4=Al Tamr, 5=Al Jeer,
  6=Al Shahla, 7=Al Khudrawi, 8=Al Sarrood, 9=Al Msalli,
  10=Al Dabas, 11=Al Habool, 12=Al Haseer, 13=Al Ameera,
  14=Al Hallawi, 15=Al Das, 16=Al Khushkar, 17=Al Hamri,
  18=Al Safeena, 19=Al Basri, 20=Al Ghozlan

ELLINGTON BEACH HOUSE  Format: [Tower]-[Floor][Unit] e.g. "N-604"
  N=North Tower (sea view) | S=South Tower (garden/inland view)
  G=ground floor (G01, G02...). No studios - 1BR, 2BR, 3BR only.

AZURE RESIDENCES  Blocks A, B, C, D. e.g. "Block D, Unit 703"=Block D Floor7 Unit03
OCEANA  Sub-buildings: Adriatic, Aegean, Atlantic, Caribbean, Pacific, Baltic, Southern, Ruby, Luce, Emerald, Diamond, Tanzanite, Aquamarine
FRONDS  Letters A-P = individual fronds. Units = villa numbers on frond.
CANAL COVES  E=East, W=West
PALM VIEWS  E=East tower, W=West tower

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRICING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Default to LAST 6 MONTHS for averages/PSF unless user specifies otherwise
- Label timeframe clearly: "6-Month Avg: AED X.XXM | AED X,XXX/sqft"
- <3 transactions in 6 months -> expand to 12 months and note it
- Gross Rental Yield = (Annual Rent / Purchase Price) x 100
- Typical Palm Jumeirah yields: 5-8% for apartments
- Budget search (e.g. "what can I get for AED 2M"): use get_bayut_listings with max_price=<AED value>
- Highly motivated sellers: use get_propertyfinder_listings and look for pf_listing_count >= 3
- Tenants who just moved out / new tenants only: use get_rental_intel with query_type="rental_history" and note entries with rent_recurrence="New Contract"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE FORMATTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Owner tables - column order: Unit | Owner | Phone | Beds | Size | Date
- Show ALL phone numbers for every contact (if "phone" contains " | " those are multiple numbers - show all)
- Flag portfolio investors (2+ units) prominently
- Sort by unit number ascending by default
- Lead contacts may be previous owners if unit sold recently - note once at bottom

Lease intelligence:
- "Renewal" = same tenant renewed -> stable, less likely to sell
- "New Contract" = new tenant -> higher turnover, owner may be tired, open to selling
- Expiring in 1-3 months = HOT lead

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA LIMITATIONS - WHAT WE CANNOT DO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Nationality / origin of owner: NOT available. Cannot find "Russian", "British", or "Chinese" owners.
- Listing age / days on market: NOT in data. PF and Bayut scraped data has no listing date. Cannot answer "listed 90+ days".
- Who hasn't been contacted yet: NOT tracked here. The WhatsApp log is separate from this system.
- Sea view vs non-sea view pricing from title deeds: CANNOT DO - title deeds have no view data. For view info use get_unit_info on specific units.
- Cross-building rankings (e.g. "which building has best yield across all Palm", "most price growth"): NOT possible - tools are per-building only. If asked, say so and offer to check specific buildings the user names.
- Portfolio owners across all buildings (no building specified): ask the user to name a building, or use get_owner_portfolio if the owner name is known.
- WhatsApp campaigns: NOT available in this interface. Direct the user to use the WhatsApp page in the app for campaigns and messaging.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HARD RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NEVER suggest "contact DLD" - the broker does not do this
- NEVER invent contacts, prices, phone numbers, or unit numbers
- If no contact found: say "No contact" - do not suggest alternatives
- No filler text, no unnecessary commentary"""


# --------------------------------------------------------------------------- #
#  Tool Executor
# --------------------------------------------------------------------------- #

def _get_shoreline_display_name(building_name: str) -> str:
    try:
        from building_intelligence import SHORELINE_TOWER_MAPPING
        for tower_name, (number, _aliases) in SHORELINE_TOWER_MAPPING.items():
            if tower_name.lower() == building_name.lower():
                return f"{building_name} (Shoreline {number})"
    except ImportError:
        pass
    return building_name


def _clean_beds_from_dld(beds_str: str) -> str | None:
    if not beds_str:
        return None
    s = beds_str.strip()
    if "studio" in s.lower():
        return "Studio"
    if "penthouse" in s.lower() or s.lower() == "ph":
        return "PH"
    m = re.search(r"(\d+)", s)
    if m:
        return m.group(1)
    return s


def execute_tool(tool_name: str, tool_input: dict, data_store) -> str | dict:
    """Execute a single tool and return its result."""
    leads_df = data_store.leads_df
    reference_df = data_store.ref_df

    if tool_name == "get_building_intel":
        return get_complete_building_intel_for_ai(
            reference_df=reference_df,
            leads_df=leads_df,
            building=tool_input.get("building", ""),
            bedrooms=tool_input.get("bedrooms"),
            matched_only=tool_input.get("matched_only", False),
            limit=tool_input.get("limit", 10),
        )

    elif tool_name == "get_owner_portfolio":
        return get_portfolio_summary_for_ai(leads_df, **tool_input)

    elif tool_name == "search_building_names":
        return search_building_names_for_ai(reference_df, tool_input.get("search_term", ""))

    elif tool_name == "get_rental_intel":
        rental_df = load_rental_data()
        return get_rental_intel_for_ai(
            rental_df=rental_df,
            leads_df=leads_df,
            reference_df=reference_df,
            building=tool_input.get("building", ""),
            query_type=tool_input.get("query_type", "expiring_leases"),
            bedrooms=tool_input.get("bedrooms"),
            unit_number=tool_input.get("unit_number"),
            days_ahead=tool_input.get("days_ahead", 90),
            limit=tool_input.get("limit", 50),
        )

    elif tool_name == "get_unit_info":
        from unit_registry import get_unit_info
        building = tool_input.get("building", "")
        unit = tool_input.get("unit_number", "")
        info = get_unit_info(building, unit)
        if info:
            return {
                "found": True,
                "building": info["building_name"],
                "unit": info["unit_number"],
                "bedrooms": info["bedrooms"],
                "size_sqft": info["size_sqft"],
                "floor": info["floor_level"],
                "view": info["view"] or "Not available",
                "position": info["unit_position"],
                "confidence": info["confidence"],
                "sources": info["sources"],
                "transaction_history": {
                    "sale_count": info["sale_count"],
                    "rental_count": info["rental_count"],
                    "last_sale_price": info["last_sale_price"],
                    "last_sale_date": info["last_sale_date"],
                    "last_annual_rent": info["last_annual_rent"],
                },
            }
        return {"found": False, "message": f"Unit not found in registry: {building} {unit}"}

    elif tool_name == "find_listings_below_market":
        return get_listings_below_market_for_ai(
            leads_df=leads_df,
            reference_df=reference_df,
            building=tool_input.get("building") or None,
            bedrooms=tool_input.get("bedrooms"),
            below_pct=float(tool_input.get("below_pct", 10)),
            limit=int(tool_input.get("limit", 20)),
        )

    elif tool_name == "get_propertyfinder_listings":
        return get_propertyfinder_listings_for_ai(
            leads_df,
            building=tool_input.get("building"),
            listing_type=tool_input.get("listing_type", "all"),
            bedrooms=tool_input.get("bedrooms"),
            furnished=tool_input.get("furnished", "all"),
            unit_number=tool_input.get("unit_number"),
            limit=tool_input.get("limit", 50),
        )

    elif tool_name == "get_bayut_listings":
        return get_bayut_listings_for_ai(
            listing_type=tool_input.get("listing_type", "all"),
            building=tool_input.get("building"),
            bedrooms=tool_input.get("bedrooms"),
            min_price=tool_input.get("min_price"),
            max_price=tool_input.get("max_price"),
            limit=int(tool_input.get("limit", 30)),
        )

    elif tool_name == "match_listing_to_owner":
        try:
            from listing_matcher.matcher import match_listing_tool, load_leads_df as _load_leads
            _matcher_leads = _load_leads()
            return match_listing_tool(
                building=tool_input.get("building", ""),
                size_sqft=tool_input.get("size_sqft"),
                bedrooms=tool_input.get("bedrooms"),
                unit_number=tool_input.get("unit_number"),
                leads_df=_matcher_leads,
            )
        except Exception as e:
            return {"error": f"Matcher error: {e}"}

    elif tool_name == "validate_trakheesi_listing":
        try:
            from scraper.dld_validator import validate_listing, extract_guid_from_url
            from listing_matcher.matcher import match_listing_tool as _match_tool, load_leads_df as _load_leads_dld

            raw = tool_input.get("guid_or_url", "").strip()
            guid = extract_guid_from_url(raw) or raw
            dld_res = validate_listing(guid)

            if not dld_res["success"]:
                return (
                    f"DLD lookup failed: {dld_res['error']}\n\n"
                    "Tips:\n"
                    "- Verify the GUID came from a Madmoun QR code\n"
                    "- Try again - browser automation can occasionally fail\n"
                    "- The GUID may be invalid or expired"
                )

            _start = dld_res["permit_start"][:10] if dld_res["permit_start"] else "N/A"
            _end = dld_res["permit_end"][:10] if dld_res["permit_end"] else "N/A"
            _display_bld = _get_shoreline_display_name(dld_res["building"])
            out = (
                f"PROPERTY DETAILS (from DLD Trakheesi)\n"
                f"Building: {_display_bld} ({dld_res['building_ar']})\n"
                f"Zone: {dld_res['zone']}\n"
                f"Size: {dld_res['size_sqm']} sqm / {dld_res['size_sqft']:,.0f} sqft\n"
                f"Bedrooms: {dld_res['beds']}\n"
                f"Floor: {dld_res['floor'] or 'N/A'}\n"
                f"Value: AED {dld_res['value']:,.0f}\n"
                f"Type: {dld_res['permit_type']}\n"
                f"Agency: {dld_res['agency']}\n"
                f"Permit: {dld_res['permit_number']}\n"
                f"Status: {dld_res['permit_status']}\n"
                f"Valid: {_start} -> {_end}\n"
            )
            _beds_clean = _clean_beds_from_dld(dld_res["beds"])
            try:
                _leads = _load_leads_dld()
                _owner_text = _match_tool(
                    building=dld_res["building"],
                    size_sqft=dld_res["size_sqft"] or None,
                    bedrooms=_beds_clean,
                    leads_df=_leads,
                )
                out += f"\nOWNER MATCH (lead database):\n{_owner_text}"
            except Exception as me:
                out += f"\nOwner lookup failed: {me}"
            return out
        except ImportError:
            return {"error": "Trakheesi validator not available on this server (requires Playwright)."}
        except Exception as e:
            return {"error": f"DLD validator error: {e}"}

    return {"error": f"Unknown tool: {tool_name}"}


# --------------------------------------------------------------------------- #
#  Chat History I/O
# --------------------------------------------------------------------------- #

def _user_chat_dir(username: str) -> Path:
    d = CHAT_HISTORY_DIR / username
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_chat(username: str, first_message: str | None = None) -> dict:
    chat_id = uuid.uuid4().hex[:8]
    name = (first_message or "New chat")[:50].strip()
    chat = {
        "id": chat_id,
        "name": name,
        "created": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "messages": [],
    }
    _save_chat_file(username, chat_id, chat)
    return chat


def load_chat(username: str, chat_id: str) -> dict | None:
    p = _user_chat_dir(username) / f"{chat_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_chat_file(username: str, chat_id: str, chat_data: dict):
    d = _user_chat_dir(username)
    tmp = d / f"{chat_id}.tmp"
    final = d / f"{chat_id}.json"
    tmp.write_text(json.dumps(chat_data, default=str, indent=2), encoding="utf-8")
    tmp.replace(final)


def list_chats(username: str) -> list[dict]:
    d = _user_chat_dir(username)
    chats = []
    for p in d.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            chats.append({
                "id": data["id"],
                "name": data.get("name", "Untitled"),
                "last_updated": data.get("last_updated", ""),
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            continue
    chats.sort(key=lambda c: c["last_updated"], reverse=True)
    return chats


def delete_chat(username: str, chat_id: str) -> bool:
    p = _user_chat_dir(username) / f"{chat_id}.json"
    if p.exists():
        p.unlink()
        return True
    return False


# --------------------------------------------------------------------------- #
#  Main Chat Runner (synchronous — called via asyncio.to_thread)
# --------------------------------------------------------------------------- #

def run_chat(
    message: str,
    chat_id: str | None,
    username: str,
    data_store,
) -> Generator[dict, None, None]:
    """
    Run a chat turn. Yields status dicts as SSE events:
      {"type": "status", "text": "Thinking..."}
      {"type": "status", "text": "Searching Shoreline 9 data..."}
      {"type": "done", "content": "...", "chat_id": "..."}
      {"type": "error", "text": "..."}
    """
    if not ANTHROPIC_API_KEY:
        yield {"type": "error", "text": "AI service not configured. Set ANTHROPIC_API_KEY."}
        return

    if not data_store.is_loaded:
        yield {"type": "error", "text": "Data is still loading. Please try again in 30 seconds."}
        return

    # Load or create chat
    if chat_id:
        chat = load_chat(username, chat_id)
        if not chat:
            yield {"type": "error", "text": "Chat not found."}
            return
    else:
        chat = create_chat(username, first_message=message)
        chat_id = chat["id"]

    yield {"type": "status", "text": "Thinking..."}

    # Build messages for Claude API (strip timestamps, keep role+content only)
    stored_messages = chat.get("messages", [])
    # Truncate to last 20 user-visible messages to avoid context overflow
    # But keep the full internal messages (with tool results) for Claude context
    api_messages = []
    for m in stored_messages:
        api_messages.append({"role": m["role"], "content": m["content"]})

    # Trim if too long (keep last 20 exchanges)
    if len(api_messages) > 40:
        api_messages = api_messages[-40:]

    api_messages.append({"role": "user", "content": message})

    # Build system prompt
    system_prompt = build_system_prompt(data_store)

    # Claude API call with tool loop
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8192,
            system=system_prompt,
            tools=TOOLS,
            messages=api_messages,
            timeout=30.0,
        )

        MAX_TOOLS = 3
        tool_count = 0
        start_time = time.time()

        while response.stop_reason == "tool_use" and tool_count < MAX_TOOLS:
            if time.time() - start_time > 25:
                break

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_use_blocks:
                break

            api_messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in tool_use_blocks:
                tool_name = block.name
                tool_input = block.input
                tool_count += 1

                # Emit status for the tool being called
                friendly_name = tool_name.replace("_", " ").replace("get ", "").title()
                building = tool_input.get("building", "")
                status_text = f"Searching {building} data..." if building else f"Running {friendly_name}..."
                yield {"type": "status", "text": status_text}

                try:
                    result = execute_tool(tool_name, tool_input, data_store)
                except Exception as e:
                    result = {"error": str(e)}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            api_messages.append({"role": "user", "content": tool_results})

            # After 2 tools, force text response (no more tool calls)
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=8192,
                system=system_prompt,
                tools=TOOLS if tool_count < 2 else [],
                messages=api_messages,
                timeout=30.0,
            )

        # Force final response if still trying to use tools
        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if tool_use_blocks:
                api_messages.append({"role": "assistant", "content": response.content})
                tool_results = [
                    {
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": json.dumps({"status": "Limit reached - respond with data gathered"}),
                    }
                    for b in tool_use_blocks
                ]
                api_messages.append({"role": "user", "content": tool_results})

                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=8192,
                    system=system_prompt,
                    tools=[],
                    messages=api_messages,
                    timeout=30.0,
                )

        # Extract final text
        final_text = next((b.text for b in response.content if hasattr(b, "text")), None)
        if not final_text:
            final_text = "Could not generate response. Please try rephrasing."

        # Save to chat history (user-visible messages only — not tool internals)
        now = datetime.now(timezone.utc).isoformat()
        chat["messages"].append({"role": "user", "content": message, "timestamp": now})
        chat["messages"].append({"role": "assistant", "content": final_text, "timestamp": now})
        chat["last_updated"] = now
        if len(chat["messages"]) == 2:
            chat["name"] = message[:50].strip()
        _save_chat_file(username, chat_id, chat)

        yield {"type": "done", "content": final_text, "chat_id": chat_id}

    except anthropic.RateLimitError:
        yield {"type": "error", "text": "AI is busy. Please wait 1-2 minutes and try again."}
    except anthropic.AuthenticationError:
        yield {"type": "error", "text": "AI authentication error. Please notify admin."}
    except Exception as e:
        yield {"type": "error", "text": f"Error: {str(e)[:200]}"}
