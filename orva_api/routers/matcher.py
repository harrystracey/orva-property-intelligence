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


@router.get("/buildings")
def get_buildings(
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    """Return cached list of building names for autocomplete."""
    return {"buildings": store.buildings}
