"""Listing Matcher API router."""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ..auth import get_current_user
from ..deps import DataStore, get_data_store

router = APIRouter(prefix="/api/matcher", tags=["matcher"])

# DataStore uses lowercase snake_case columns; matcher expects original Title Case columns
_TO_MATCHER_COLS = {
    "building_name": "Building Name",
    "unit_number": "Unit Number",
    "size_sqft": "Size (sqft)",
    "bedrooms": "Bedrooms",
    "owner_name": "Owner Name",
    "phone": "Phone",
    "phone_display": "Phone Display",
    "email": "Email",
    "source_file": "Source File",
    "date": "Date",
    "transaction_value": "Transaction Value",
}


@router.post("/match")
def match_listing(
    body: dict,
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    """
    Match a portal listing to owners in the lead database.
    Body: { building_name, unit_number?, size_sqft?, bedrooms?, listing_url? }
    """
    if not store.is_loaded or store.leads_df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    from listing_matcher.matcher import match_listing as _match

    df = store.leads_df.rename(columns=_TO_MATCHER_COLS)
    results = _match(body, df)
    return {"results": results, "count": len(results)}


@router.post("/scrape-url")
def scrape_url(
    body: dict,
    user: dict = Depends(get_current_user),
):
    """
    Scrape a Bayut or PropertyFinder listing URL and return structured data.
    Body: { "url": "https://www.bayut.com/property/details-12345.html" }
    Optionally auto-matches if auto_match=true: { "url": "...", "auto_match": true }
    """
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(400, "url is required")

    from listing_matcher.url_scraper import scrape_listing_url
    result = scrape_listing_url(url)

    if result.get("error"):
        raise HTTPException(400, result["error"])

    return result


@router.post("/scrape-and-match")
def scrape_and_match(
    body: dict,
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    """
    Scrape a listing URL, then auto-match against lead database.
    Body: { "url": "https://www.bayut.com/property/details-12345.html" }
    Returns: { listing: {...}, matches: [...], count: N }
    """
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(400, "url is required")

    if not store.is_loaded or store.leads_df.empty:
        raise HTTPException(503, "Data not loaded")

    from listing_matcher.url_scraper import scrape_listing_url
    from listing_matcher.matcher import match_listing as _match
    from listing_matcher.enrichment import enrich_matches

    listing = scrape_listing_url(url)
    if listing.get("error"):
        raise HTTPException(400, listing["error"])

    # Build match input from scraped data
    match_input = {
        "building_name": listing.get("building"),
        "bedrooms": str(listing["bedrooms"]) if listing.get("bedrooms") is not None else None,
        "size_sqft": listing.get("size_sqft"),
        "listing_url": url,
    }

    df = store.leads_df.rename(columns=_TO_MATCHER_COLS)
    matches = _match(match_input, df)

    # Enrich with rental intel, competition, and registry data
    matches = enrich_matches(
        matches,
        listing_building=listing.get("building", ""),
        listing_bedrooms=listing.get("bedrooms"),
        listing_price=listing.get("price"),
        leads_df=store.leads_df,
    )

    return {"listing": listing, "matches": matches, "count": len(matches)}


@router.get("/buildings")
def get_buildings(
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    """Return cached list of building names for autocomplete."""
    return {"buildings": store.buildings}
