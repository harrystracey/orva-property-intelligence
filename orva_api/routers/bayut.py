"""Bayut listings browser API router."""

import sys
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, Query

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ..auth import get_current_user

router = APIRouter(prefix="/api/bayut", tags=["bayut"])

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
    import numpy as np
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, float) and (val != val):
        return None
    if hasattr(val, "item"):
        return val.item()
    return val


@router.get("")
def list_listings(
    listing_type: str = Query("", description="rent or sale"),
    building: str = Query(""),
    bedrooms: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    df = _load_bayut()
    if df.empty:
        return {"listings": [], "total": 0, "page": page, "page_size": page_size}

    filtered = df.copy()

    if listing_type:
        filtered = filtered[filtered["listing_type"].str.lower() == listing_type.lower()]

    if building:
        filtered = filtered[
            filtered["building_name"].str.contains(building, case=False, na=False)
        ]

    if bedrooms:
        if bedrooms.lower() == "studio":
            filtered = filtered[filtered["bedrooms"] == 0]
        else:
            try:
                br = float(bedrooms)
                filtered = filtered[filtered["bedrooms"] == br]
            except ValueError:
                pass

    total = len(filtered)
    start = (page - 1) * page_size
    page_df = filtered.iloc[start:start + page_size]

    listings = []
    for _, row in page_df.iterrows():
        listings.append({
            "building_name": _safe(row.get("building_name")),
            "bedrooms": _safe(row.get("bedrooms")),
            "bathrooms": _safe(row.get("bathrooms")),
            "size_sqft": _safe(row.get("size_sqft")),
            "price_aed": _safe(row.get("price_aed")),
            "view": _safe(row.get("view")),
            "listing_type": _safe(row.get("listing_type")),
            "listing_title": _safe(row.get("listing_title")),
            "listing_url": _safe(row.get("listing_url")),
            "scraped_at": _safe(row.get("scraped_at")),
        })

    return {"listings": listings, "total": total, "page": page, "page_size": page_size}


@router.get("/stats")
def bayut_stats(user: dict = Depends(get_current_user)):
    df = _load_bayut()
    if df.empty:
        return {"total": 0, "for_rent": 0, "for_sale": 0, "buildings": 0}

    return {
        "total": len(df),
        "for_rent": int((df["listing_type"].str.lower() == "rent").sum()),
        "for_sale": int((df["listing_type"].str.lower() == "sale").sum()),
        "buildings": int(df["building_name"].nunique()),
    }
