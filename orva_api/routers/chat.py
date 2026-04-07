"""LLM chat endpoint — HLM (High Level Matcher) AI assistant."""

import json
import sys
import time
import logging
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ..auth import get_current_user
from ..config import ANTHROPIC_API_KEY
from ..deps import DataStore, get_data_store

logger = logging.getLogger("orva_api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[list[ChatMessage]] = None


class ChatResponse(BaseModel):
    response: str
    tool_calls: int = 0


# ---------------------------------------------------------------------------
# Tool definitions (same as app.py — excluding desktop-only WhatsApp tools)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_building_intel",
        "description": "Get building intelligence: market pricing with unit numbers, owner contacts, and cross-referenced matches. Set matched_only=true when user asks for sales 'where you know the owner' or 'with contacts'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name (e.g., 'Ellington', 'Shoreline 5', 'Al Masalli', 'Fairmont')"},
                "bedrooms": {"type": "integer", "description": "Filter by bedrooms (0=studio, 1, 2, 3, 4+). Optional."},
                "matched_only": {"type": "boolean", "description": "If true, only return sales where owner contact is known. Default false."},
                "limit": {"type": "integer", "description": "Max number of recent sales to return. Default 10."}
            },
            "required": ["building"]
        }
    },
    {
        "name": "get_owner_portfolio",
        "description": "Get all properties owned by a specific person from lead database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_name": {"type": "string", "description": "Owner name"}
            },
            "required": ["owner_name"]
        }
    },
    {
        "name": "search_building_names",
        "description": "Find building by partial name. Use ONLY if get_building_intel returns no data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_term": {"type": "string", "description": "Partial building name"}
            },
            "required": ["search_term"]
        }
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
                    "description": "Type of rental query"
                },
                "days_ahead": {"type": "integer", "description": "For expiring_leases: how many days ahead (default 90)"},
                "limit": {"type": "integer", "description": "Max results to return (default 50)"}
            },
            "required": ["building", "query_type"]
        }
    },
    {
        "name": "find_listings_below_market",
        "description": "Find scraped PropertyFinder listings priced below the typical title-deed market for that building. Use when user asks for deals, undervalued, or bargains.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Optional building name filter"},
                "bedrooms": {"type": "integer", "description": "Optional bedroom filter (0=studio, 1, 2, 3)"},
                "below_pct": {"type": "number", "description": "Minimum discount below market (default 10)"},
                "limit": {"type": "integer", "description": "Max listings (default 20)"}
            },
            "required": []
        }
    },
    {
        "name": "get_propertyfinder_listings",
        "description": "Query active PropertyFinder scraped listings (rentals or sales). Returns listing details including price, furnished status, URL, and pf_listing_count (motivation signal).",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name filter. Optional."},
                "listing_type": {"type": "string", "enum": ["rent", "sell", "all"], "description": "Filter by rent or sell. Default 'all'."},
                "bedrooms": {"type": "integer", "description": "Bedroom count filter. Optional."},
                "furnished": {"type": "string", "enum": ["Furnished", "Unfurnished", "all"], "description": "Filter by furnished status. Default 'all'."},
                "unit_number": {"type": "string", "description": "Specific unit number. Optional."},
                "limit": {"type": "integer", "description": "Max results (default 50)."}
            },
            "required": []
        }
    },
    {
        "name": "get_bayut_listings",
        "description": "Get active Bayut property listings on Palm Jumeirah. Use for active listings, competition analysis, supply, motivated sellers/landlords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "listing_type": {"type": "string", "enum": ["all", "sale", "rent"], "description": "Filter by listing type. Default 'all'."},
                "building": {"type": "string", "description": "Optional building name filter."},
                "bedrooms": {"type": "integer", "description": "Optional bedroom count filter."},
                "min_price": {"type": "number", "description": "Optional minimum price in AED."},
                "max_price": {"type": "number", "description": "Optional maximum price in AED."},
                "limit": {"type": "integer", "description": "Max listings (default 30)."}
            },
            "required": []
        }
    },
    {
        "name": "get_unit_info",
        "description": "Look up confirmed unit specifications from the master unit registry. Returns bedrooms, size, view, floor, and transaction history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name"},
                "unit_number": {"type": "string", "description": "Unit number"}
            },
            "required": ["building", "unit_number"]
        }
    },
    {
        "name": "match_listing_to_owner",
        "description": "Match a portal listing against the owner lead database to identify who owns the unit. Returns owner name, phone, and confidence score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building": {"type": "string", "description": "Building name as on the portal"},
                "size_sqft": {"type": "number", "description": "Listing size in sqft. Optional but improves accuracy."},
                "bedrooms": {"type": "string", "description": "Bedroom count string. Optional."},
                "unit_number": {"type": "string", "description": "Exact unit number if visible. Optional."}
            },
            "required": ["building"]
        }
    },
]


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt(store: DataStore) -> str:
    """Build the HLM system prompt with live database stats."""
    import pandas as pd

    leads_df = store.leads_df
    ref_df = store.ref_df
    rental_df = store.rentals_df

    _total_leads = len(leads_df) if not leads_df.empty else 0
    _leads_phone = int((leads_df["phone"].fillna("").str.strip() != "").sum()) if not leads_df.empty and "phone" in leads_df.columns else 0
    _leads_bldgs = leads_df["building_name"].nunique() if not leads_df.empty and "building_name" in leads_df.columns else 0
    _ref_count = len(ref_df) if ref_df is not None and not ref_df.empty else 0
    _rental_count = len(rental_df) if rental_df is not None and not rental_df.empty else 0
    _rental_bldgs = rental_df["building_name"].nunique() if rental_df is not None and not rental_df.empty and "building_name" in rental_df.columns else 0

    # Bayut stats
    try:
        bayut_path = _root / "data" / "bayut_palm_listings.csv"
        if bayut_path.exists():
            bdf = pd.read_csv(bayut_path, low_memory=False)
            _bayut_total = len(bdf)
            _bayut_sale = int((bdf["listing_type"].str.lower() == "sale").sum()) if "listing_type" in bdf.columns else 0
            _bayut_rent = int((bdf["listing_type"].str.lower() == "rent").sum()) if "listing_type" in bdf.columns else 0
            _bayut_bldgs = bdf["building_name"].nunique() if "building_name" in bdf.columns else 0
        else:
            _bayut_total = _bayut_sale = _bayut_rent = _bayut_bldgs = 0
    except Exception:
        _bayut_total = _bayut_sale = _bayut_rent = _bayut_bldgs = 0

    return f"""You are HLM, a real estate intelligence system for Palm Jumeirah, Dubai. You help a broker find owners to call, analyse market pricing, and identify leads.

DATABASE SNAPSHOT (live)
Lead Database:     {_total_leads:,} owner records | {_leads_phone:,} with phone numbers | {_leads_bldgs} buildings
Title Deeds:       {_ref_count:,} sales transactions (Property Monitor — official DLD source)
Rental Contracts:  {_rental_count:,} records across {_rental_bldgs} buildings (PropertyMonitor Ejari + Reidin DLD merged)
Active Bayut:      {_bayut_total:,} listings ({_bayut_sale} sale, {_bayut_rent} rent, {_bayut_bldgs} buildings)
Unit Registry:     30,000+ units from 5 sources, 189 buildings

TOOLS — PICK THE RIGHT ONE IMMEDIATELY
get_building_intel         → Market prices (title deeds) + owner contacts
get_rental_intel           → Rental yields, expiring leases, tenant turnover
get_bayut_listings         → Active Bayut listings — supply analysis
get_propertyfinder_listings→ Active PF listings with owner contacts
find_listings_below_market → Listings priced below title deed market
get_unit_info              → Confirmed specs for a specific unit
get_owner_portfolio        → All properties owned by one person
search_building_names      → Fuzzy search if building name is unclear
match_listing_to_owner     → Match a portal listing to find the owner

TOOL USAGE RULES
- Default: 1 tool per response turn
- Comparisons (2 buildings): call tool twice, present side by side
- Yield at asking price: get_bayut_listings for price + get_rental_intel for rent
- Both portals: get_propertyfinder_listings first (has contacts), then get_bayut_listings

DATA SOURCES
TITLE DEEDS (Property Monitor): sale prices, sizes, bedrooms. NO unit numbers, NO phones.
LEAD DATABASE (DLD 2018-2025): unit numbers, owner names, phones. Contacts may be 1-2 years old.
RENTAL CONTRACTS (Ejari + Reidin): lease dates, annual rent, furnished status. "Renewal" = stable tenant. "New Contract" = turnover.
BAYUT/PF LISTINGS: active market supply with prices.
UNIT REGISTRY: confirmed bedrooms, sizes, views from 5 cross-referenced sources.

HARD RULES
- NEVER invent contacts, prices, phone numbers, or unit numbers
- If no contact found: say "No contact" — do not suggest alternatives
- No filler text, no unnecessary commentary
- Present title deed data and owner contacts as SEPARATE sections (they cannot be cross-matched by unit)"""


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def _execute_tool(tool_name: str, tool_input: dict, store: DataStore) -> dict | str:
    """Execute an AI tool and return the result."""
    from data_processor import (
        get_complete_building_intel_for_ai,
        get_portfolio_summary_for_ai,
        search_building_names_for_ai,
        get_listings_below_market_for_ai,
        get_propertyfinder_listings_for_ai,
    )
    from rental_processor import get_rental_intel_for_ai

    leads_df = store.leads_df
    ref_df = store.ref_df
    rental_df = store.rentals_df

    if tool_name == "get_building_intel":
        return get_complete_building_intel_for_ai(
            reference_df=ref_df,
            leads_df=leads_df,
            building=tool_input.get("building", ""),
            bedrooms=tool_input.get("bedrooms"),
            matched_only=tool_input.get("matched_only", False),
            limit=tool_input.get("limit", 10),
        )

    elif tool_name == "get_owner_portfolio":
        return get_portfolio_summary_for_ai(leads_df, **tool_input)

    elif tool_name == "search_building_names":
        return search_building_names_for_ai(ref_df, tool_input.get("search_term", ""))

    elif tool_name == "get_rental_intel":
        return get_rental_intel_for_ai(
            rental_df=rental_df if rental_df is not None else __import__("pandas").DataFrame(),
            leads_df=leads_df,
            reference_df=ref_df,
            building=tool_input.get("building", ""),
            query_type=tool_input.get("query_type", "expiring_leases"),
            bedrooms=tool_input.get("bedrooms"),
            unit_number=tool_input.get("unit_number"),
            days_ahead=tool_input.get("days_ahead", 90),
            limit=tool_input.get("limit", 50),
        )

    elif tool_name == "get_unit_info":
        from unit_registry import get_unit_info
        info = get_unit_info(tool_input.get("building", ""), tool_input.get("unit_number", ""))
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
        return {"found": False, "message": f"Unit not found: {tool_input.get('building')} {tool_input.get('unit_number')}"}

    elif tool_name == "find_listings_below_market":
        return get_listings_below_market_for_ai(
            leads_df=leads_df,
            reference_df=ref_df,
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
        import pandas as pd
        bayut_path = _root / "data" / "bayut_palm_listings.csv"
        if not bayut_path.exists():
            return {"error": "No Bayut data. Run the scraper first."}
        from data_processor import standardize_building_name
        bdf = pd.read_csv(bayut_path, low_memory=False)
        # Normalize building key
        if "building_name" in bdf.columns:
            bdf["_bkey"] = bdf["building_name"].fillna("").apply(
                lambda x: standardize_building_name(x).lower() if x else ""
            )
        lt = tool_input.get("listing_type", "all")
        if lt != "all" and "listing_type" in bdf.columns:
            bdf = bdf[bdf["listing_type"].str.lower() == lt.lower()]
        bld = tool_input.get("building")
        if bld:
            bld_key = standardize_building_name(bld).lower()
            bdf = bdf[bdf["_bkey"].str.contains(bld_key, na=False)]
        beds = tool_input.get("bedrooms")
        if beds is not None and "bedrooms" in bdf.columns:
            bdf = bdf[bdf["bedrooms"] == beds]
        minp = tool_input.get("min_price")
        if minp and "price_aed" in bdf.columns:
            bdf = bdf[bdf["price_aed"] >= minp]
        maxp = tool_input.get("max_price")
        if maxp and "price_aed" in bdf.columns:
            bdf = bdf[bdf["price_aed"] <= maxp]
        limit = int(tool_input.get("limit", 30))
        bdf = bdf.head(limit)
        cols = ["building_name", "bedrooms", "size_sqft", "price_aed", "listing_type", "view", "listing_url"]
        available = [c for c in cols if c in bdf.columns]
        return {
            "count": len(bdf),
            "listings": bdf[available].to_dict(orient="records"),
        }

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

    return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    """Send a message to HLM and get a response with tool-augmented intelligence."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured in .env")

    system_prompt = _build_system_prompt(store)

    # Build message history
    messages = []
    if req.history:
        for msg in req.history:
            messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
            timeout=30.0,
        )

        # Tool execution loop (max 3 tools, 25s timeout)
        tool_count = 0
        start_time = time.time()

        while response.stop_reason == "tool_use" and tool_count < 3:
            if time.time() - start_time > 25:
                break

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_use_blocks:
                break

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in tool_use_blocks:
                tool_count += 1
                try:
                    result = _execute_tool(block.name, block.input, store)
                except Exception as e:
                    logger.exception("Tool %s failed", block.name)
                    result = {"error": str(e)}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_results})

            # After 2 tools, force text response
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                system=system_prompt,
                tools=TOOLS if tool_count < 2 else [],
                messages=messages,
                timeout=30.0,
            )

        # Force final text if still tool_use
        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if tool_use_blocks:
                messages.append({"role": "assistant", "content": response.content})
                tool_results = [{
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": json.dumps({"status": "Limit reached - respond with data gathered"}),
                } for b in tool_use_blocks]
                messages.append({"role": "user", "content": tool_results})
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=8192,
                    system=system_prompt,
                    tools=[],
                    messages=messages,
                    timeout=30.0,
                )

        final_text = next((b.text for b in response.content if hasattr(b, "text")), None)
        logger.info("Chat response: %d chars, %d tools", len(final_text or ""), tool_count)
        return ChatResponse(
            response=final_text or "Could not generate response. Please try rephrasing.",
            tool_calls=tool_count,
        )

    except anthropic.APIError as e:
        logger.error("Anthropic API error: %s", e)
        raise HTTPException(502, f"AI service error: {str(e)[:200]}")
    except Exception as e:
        logger.exception("Chat failed")
        raise HTTPException(500, f"Internal error: {str(e)[:200]}")
