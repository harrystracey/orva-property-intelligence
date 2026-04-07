"""Reidin data management — upload, status, and vacancy intelligence."""

import io
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from reidin_processor import process_reidin_export, process_reidin_rentals

from ..auth import get_current_user
from ..config import DATA_DIR, RENTALS_CSV_PATH, PARQUET_PATH
from ..deps import get_data_store

router = APIRouter(prefix="/api/reidin", tags=["reidin"])

_SALES_PARQUET = DATA_DIR / "reidin_master.parquet"
_SALES_CSV = DATA_DIR / "reidin_master.csv"
_RENTALS_PARQUET = DATA_DIR / "reidin_rentals.parquet"
_RENTALS_CSV = DATA_DIR / "reidin_rentals.csv"

# Building name aliases: PM/Reidin names → leads_master canonical names
_BLDG_ALIASES = {
    "the fairmont palm residences": "fairmont palm residences",
    "anantara residences north": "anantara residences",
    "anantara residences south": "anantara residences",
    "serenia residences east wing": "serenia living",
    "serenia residences north wing": "serenia living",
    "serenia residences west wing": "serenia living",
    "maurya": "grandeur maurya",
    "mughal": "grandeur mughal",
    "balqis residence block a": "balqis residence",
    "balqis residence block b": "balqis residence",
    "balqis residence block c": "balqis residence",
    "al shalal": "al shahla",
}

# Cache merged rentals + leads (rebuild every 5 min)
_merged_cache: pd.DataFrame | None = None
_merged_cache_at: float = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_info(parquet_path: Path, csv_path: Path) -> dict:
    """Return metadata about a reidin data file."""
    for p in [parquet_path, csv_path]:
        if p.exists():
            try:
                df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
                info = {
                    "exists": True,
                    "rows": len(df),
                    "buildings": int(df["building_name"].nunique()) if "building_name" in df.columns else 0,
                    "last_modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                }
                return info
            except Exception:
                return {"exists": True, "rows": 0, "buildings": 0, "last_modified": None, "error": "corrupt"}
    return {"exists": False, "rows": 0, "buildings": 0, "last_modified": None}


def _norm_bldg(s: pd.Series) -> pd.Series:
    """Fast vectorized building name normalization with alias resolution."""
    normed = s.fillna("").astype(str).str.strip().str.lower()
    return normed.replace(_BLDG_ALIASES)


def _norm_unit(s: pd.Series) -> pd.Series:
    """Fast vectorized unit number normalization."""
    return (
        s.fillna("").astype(str).str.strip().str.upper()
        .str.replace(" ", "", regex=False)
        .str.replace("-", "", regex=False)
    )


def _get_merged() -> pd.DataFrame:
    """
    Load, merge, deduplicate, and cross-reference rental data with leads.
    Cached for 5 minutes to avoid reprocessing on every request.
    """
    global _merged_cache, _merged_cache_at

    if _merged_cache is not None and (time.time() - _merged_cache_at) < 300:
        return _merged_cache

    frames = []

    # Source 1: PropertyMonitor Ejari data
    if RENTALS_CSV_PATH.exists():
        try:
            pm = pd.read_csv(RENTALS_CSV_PATH, low_memory=False)
            pm = pm.rename(columns={
                "annualized_rent": "annual_rent",
                "contract_type": "rent_type",
            })
            pm["source"] = "propertymonitor"
            frames.append(pm)
        except Exception:
            pass

    # Source 2: Reidin rental data
    for p in [_RENTALS_PARQUET, _RENTALS_CSV]:
        if p.exists():
            try:
                reidin = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
                if "sources" in reidin.columns:
                    reidin = reidin.rename(columns={"sources": "source"})
                elif "source" not in reidin.columns:
                    reidin["source"] = "reidin"
                frames.append(reidin)
            except Exception:
                pass
            break

    if not frames:
        _merged_cache = pd.DataFrame()
        _merged_cache_at = time.time()
        return _merged_cache

    merged = pd.concat(frames, ignore_index=True)

    # Ensure key columns exist
    for col in ["building_name", "unit_number", "contract_end", "contract_start",
                "annual_rent", "bedrooms", "size_sqft", "floor_level", "view",
                "rent_type", "source", "parking"]:
        if col not in merged.columns:
            merged[col] = None

    # Parse dates
    merged["contract_end"] = pd.to_datetime(merged["contract_end"], errors="coerce")
    merged["contract_start"] = pd.to_datetime(merged["contract_start"], errors="coerce")

    # Normalize keys (fast vectorized — no fuzzy matching)
    merged["_bldg_key"] = _norm_bldg(merged["building_name"])
    merged["_unit_key"] = _norm_unit(merged["unit_number"])

    # Dedup: keep most recent contract_end per (building, unit)
    merged = merged.sort_values("contract_end", ascending=False, na_position="last")
    merged = merged.drop_duplicates(subset=["_bldg_key", "_unit_key"], keep="first")

    # Cross-reference with leads (once, cached)
    store = get_data_store()
    if store.is_loaded and not store.leads_df.empty:
        leads = store.leads_df.copy()
        leads["_bldg_key"] = _norm_bldg(leads["building_name"])
        leads["_unit_key"] = _norm_unit(leads["unit_number"])
        leads["_has_phone"] = leads["phone"].notna() & leads["phone"].astype(str).str.strip().ne("")

        # Building-level contact counts (for fallback when no exact unit match)
        bldg_counts = leads[leads["_has_phone"]].groupby("_bldg_key").size()
        merged["building_contacts"] = merged["_bldg_key"].map(bldg_counts).fillna(0).astype(int)

        # Exact unit-level merge
        leads = leads.sort_values("_has_phone", ascending=False)
        leads = leads.drop_duplicates(subset=["_bldg_key", "_unit_key"], keep="first")

        contact_cols = ["_bldg_key", "_unit_key", "owner_name", "phone", "email"]
        available = [c for c in contact_cols if c in leads.columns]

        merged = merged.merge(
            leads[available],
            on=["_bldg_key", "_unit_key"],
            how="left",
            suffixes=("", "_lead"),
        )
        for col in ["owner_name", "phone", "email"]:
            lead_col = f"{col}_lead"
            if lead_col in merged.columns:
                if col not in merged.columns:
                    merged[col] = merged[lead_col]
                else:
                    merged[col] = merged[col].fillna(merged[lead_col])
                merged.drop(columns=[lead_col], inplace=True)
    else:
        for col in ["owner_name", "phone", "email"]:
            if col not in merged.columns:
                merged[col] = None
        merged["building_contacts"] = 0

    _merged_cache = merged
    _merged_cache_at = time.time()
    return _merged_cache


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def reidin_status(user: dict = Depends(get_current_user)):
    """Return info about existing reidin data files."""
    return {
        "sales": _file_info(_SALES_PARQUET, _SALES_CSV),
        "rentals": _file_info(_RENTALS_PARQUET, _RENTALS_CSV),
    }


@router.get("/expiring")
async def get_expiring_units(
    days: int = Query(90, ge=1, le=365),
    building: Optional[str] = Query(None),
    bedrooms: Optional[str] = Query(None),
    has_contact: Optional[bool] = Query(None),
    user: dict = Depends(get_current_user),
):
    """
    Return units with expiring or recently expired rental contracts.
    Includes contracts expiring within `days` AND contracts expired within
    the last 12 months (vacant units — the most actionable leads).
    """
    rentals = _get_merged()
    if rentals.empty:
        return {
            "units": [],
            "total": 0,
            "with_contact": 0,
            "summary": {"expiring_30": 0, "expiring_60": 0, "expiring_90": 0, "vacant": 0},
            "sources": [],
            "buildings": [],
        }

    today = pd.Timestamp.now().normalize()
    cutoff = today + pd.Timedelta(days=days)
    lookback = today - pd.Timedelta(days=365)

    # Include: expiring within N days OR expired in last 12 months (vacant)
    mask = (
        (rentals["contract_end"] >= lookback) &
        (rentals["contract_end"] <= cutoff) &
        rentals["contract_end"].notna()
    )
    result = rentals[mask].copy()

    # days_left: positive = still active, negative = already expired (vacant)
    result["days_left"] = (result["contract_end"] - today).dt.days

    # Apply filters
    if building:
        bldg_key = building.strip().lower()
        result = result[result["_bldg_key"].str.contains(bldg_key, na=False)]

    if bedrooms:
        bed_val = bedrooms.strip().lower()
        if bed_val == "studio":
            result = result[result["bedrooms"].astype(str).str.strip().str.lower().isin(["studio", "0"])]
        else:
            result = result[result["bedrooms"].astype(str).str.strip() == bed_val]

    if has_contact is True:
        result = result[
            result["phone"].notna() &
            result["phone"].astype(str).str.strip().ne("")
        ]
    elif has_contact is False:
        result = result[
            result["phone"].isna() |
            result["phone"].astype(str).str.strip().eq("")
        ]

    # Sort: expired (vacant) first, then by soonest expiry
    result = result.sort_values("days_left", ascending=True)

    # Summary stats from full dataset
    all_ends = rentals["contract_end"]
    summary = {
        "expiring_30": int(((all_ends >= today) & (all_ends <= today + pd.Timedelta(days=30))).sum()),
        "expiring_60": int(((all_ends >= today) & (all_ends <= today + pd.Timedelta(days=60))).sum()),
        "expiring_90": int(((all_ends >= today) & (all_ends <= today + pd.Timedelta(days=90))).sum()),
        "vacant": int(((all_ends < today) & (all_ends >= lookback)).sum()),
        "total_active": int((all_ends >= today).sum()),
    }

    sources = sorted(rentals["source"].dropna().unique().tolist()) if "source" in rentals.columns else []

    has_phone = result["phone"].notna() & result["phone"].astype(str).str.strip().ne("")

    def _s(v) -> str:
        """Safe string conversion handling pd.NA."""
        if pd.isna(v):
            return ""
        return str(v)

    units = []
    for _, row in result.iterrows():
        units.append({
            "building_name": _s(row.get("building_name")),
            "unit_number": _s(row.get("unit_number")),
            "bedrooms": _s(row.get("bedrooms")),
            "floor": _s(row.get("floor_level")),
            "view": _s(row.get("view")),
            "size_sqft": float(row["size_sqft"]) if pd.notna(row.get("size_sqft")) else None,
            "contract_end": row["contract_end"].strftime("%Y-%m-%d") if pd.notna(row.get("contract_end")) else None,
            "contract_start": row["contract_start"].strftime("%Y-%m-%d") if pd.notna(row.get("contract_start")) else None,
            "days_left": int(row.get("days_left", 0)),
            "annual_rent": float(row["annual_rent"]) if pd.notna(row.get("annual_rent")) else None,
            "rent_type": _s(row.get("rent_type")),
            "parking": _s(row.get("parking")),
            "owner_name": _s(row.get("owner_name")),
            "phone": _s(row.get("phone")),
            "email": _s(row.get("email")),
            "source": _s(row.get("source")),
            "building_contacts": int(row.get("building_contacts", 0)),
        })

    buildings = sorted(result["building_name"].dropna().unique().tolist()) if not result.empty else []

    return {
        "units": units,
        "total": len(units),
        "with_contact": int(has_phone.sum()),
        "summary": summary,
        "sources": sources,
        "buildings": buildings,
    }


@router.post("/upload")
async def upload_reidin_csv(
    file: UploadFile = File(...),
    data_type: str = Form("sales"),
    user: dict = Depends(get_current_user),
):
    """Upload and process a Reidin CSV export."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported")

    if data_type not in ("sales", "rentals"):
        raise HTTPException(400, "data_type must be 'sales' or 'rentals'")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content), encoding="utf-8", low_memory=False, on_bad_lines="skip")
    except Exception as e:
        raise HTTPException(400, f"Failed to parse CSV: {str(e)[:200]}")

    if len(df) == 0:
        raise HTTPException(400, "CSV file is empty")

    if data_type == "rentals":
        result = process_reidin_rentals(df)
    else:
        result = process_reidin_export(df)

    return result
