"""Client Match API router — find listings that fit a client's brief."""

import sys
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, Query

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ..auth import get_current_user

router = APIRouter(prefix="/api/client-match", tags=["client_match"])

_BAYUT_CSV = _root / "data" / "bayut_palm_listings.csv"
_df_cache: pd.DataFrame | None = None


def _load_bayut() -> pd.DataFrame:
    global _df_cache
    if _df_cache is None:
        if _BAYUT_CSV.exists():
            _df_cache = pd.read_csv(_BAYUT_CSV, low_memory=False, on_bad_lines="skip")
        else:
            _df_cache = pd.DataFrame()
    return _df_cache


def _safe(val):
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(val, "item"):
        return val.item()
    return val


@router.post("/search")
def find_matches(
    body: dict,
    user: dict = Depends(get_current_user),
):
    """
    Find Bayut listings matching a client brief.
    Body: {
      listing_type: "rent"|"sale",
      bedrooms?: number|"studio",
      budget_min?: number,
      budget_max?: number,
      building?: string,
      size_min?: number,
      size_max?: number,
    }
    """
    df = _load_bayut()
    if df.empty:
        return {"results": [], "total": 0}

    filtered = df.copy()

    listing_type = body.get("listing_type", "")
    if listing_type:
        filtered = filtered[filtered["listing_type"].str.lower() == listing_type.lower()]

    bedrooms = body.get("bedrooms")
    if bedrooms is not None:
        if str(bedrooms).lower() == "studio":
            filtered = filtered[filtered["bedrooms"] == 0]
        else:
            try:
                br = float(bedrooms)
                filtered = filtered[filtered["bedrooms"] == br]
            except (ValueError, TypeError):
                pass

    budget_min = body.get("budget_min")
    budget_max = body.get("budget_max")
    if budget_min is not None:
        filtered = filtered[filtered["price_aed"] >= float(budget_min)]
    if budget_max is not None:
        filtered = filtered[filtered["price_aed"] <= float(budget_max)]

    building = body.get("building", "")
    if building:
        filtered = filtered[
            filtered["building_name"].str.contains(building, case=False, na=False)
        ]

    size_min = body.get("size_min")
    size_max = body.get("size_max")
    if size_min is not None:
        filtered = filtered[filtered["size_sqft"] >= float(size_min)]
    if size_max is not None:
        filtered = filtered[filtered["size_sqft"] <= float(size_max)]

    # Sort by price ascending
    filtered = filtered.sort_values("price_aed", ascending=True, na_position="last")

    total = len(filtered)

    results = []
    for _, row in filtered.head(100).iterrows():
        results.append({
            "building_name": _safe(row.get("building_name")),
            "bedrooms": _safe(row.get("bedrooms")),
            "size_sqft": _safe(row.get("size_sqft")),
            "price_aed": _safe(row.get("price_aed")),
            "view": _safe(row.get("view")),
            "listing_type": _safe(row.get("listing_type")),
            "listing_title": _safe(row.get("listing_title")),
            "listing_url": _safe(row.get("listing_url")),
        })

    return {"results": results, "total": total}
