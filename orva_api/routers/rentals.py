"""Rental / lease expiry API router."""

import sys
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, Query

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from rental_processor import get_expiring_leases, get_active_rental_count  # noqa: E402

from ..auth import get_current_user
from ..deps import DataStore, get_data_store

router = APIRouter(prefix="/api/rentals", tags=["rentals"])


def _safe(val):
    """Convert pandas NA / NaT / NaN to None."""
    import pandas as pd
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(val, "item"):
        return val.item()
    return val


@router.get("/stats")
def rental_stats(
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    """Return overview stats: active contracts, expiring in 30/60/90 days."""
    df = store.rentals_df
    if df is None or df.empty:
        return {"active_count": 0, "expiring_30": 0, "expiring_60": 0, "expiring_90": 0, "total_records": 0}

    active = get_active_rental_count(df)
    exp30 = len(get_expiring_leases(df, days_ahead=30))
    exp60 = len(get_expiring_leases(df, days_ahead=60))
    exp90 = len(get_expiring_leases(df, days_ahead=90))
    return {
        "active_count": active,
        "expiring_30": exp30,
        "expiring_60": exp60,
        "expiring_90": exp90,
        "total_records": len(df),
    }


@router.get("/expiring")
def expiring_leases(
    days: int = Query(90, ge=1, le=365),
    building: str = Query(""),
    bedrooms: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    """Return leases expiring within N days, with pagination."""
    df = store.rentals_df
    if df is None or df.empty:
        return {"leases": [], "total": 0, "page": page, "page_size": page_size}

    expiring = get_expiring_leases(df, days_ahead=days, building=building or None, bedrooms=bedrooms or None)

    total = len(expiring)
    start = (page - 1) * page_size
    page_df = expiring.iloc[start:start + page_size]

    # Determine which columns exist
    cols = expiring.columns.tolist()

    def row_to_dict(row):
        out = {
            "building_name": _safe(row.get("building_name")),
            "unit_number": _safe(row.get("unit_number")),
            "bedrooms": _safe(row.get("bedrooms_numeric")),
            "size_sqft": _safe(row.get("size_sqft")),
            "annualized_rent": _safe(row.get("annualized_rent")),
            "days_remaining": int(row.get("days_remaining", 0)),
            "tenant_name": _safe(row.get("tenant_name")) if "tenant_name" in cols else None,
            "owner_name": _safe(row.get("owner_name")) if "owner_name" in cols else None,
        }
        # Dates as ISO strings
        for field in ("contract_start", "contract_end"):
            val = row.get(field)
            try:
                import pandas as pd
                out[field] = val.isoformat() if pd.notna(val) else None
            except Exception:
                out[field] = str(val) if val else None
        return out

    leases = [row_to_dict(row) for _, row in page_df.iterrows()]

    return {"leases": leases, "total": total, "page": page, "page_size": page_size}
