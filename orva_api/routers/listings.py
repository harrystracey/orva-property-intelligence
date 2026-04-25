"""Listings router -- lease-expiry, matcher, bayut, client-match.

These four endpoints cover the four orva-web pages that were stubs:
  /api/lease-expiry         -- expiring lease dashboard
  /api/match/listing        -- match a listing (building/unit/size/beds) to owners
  /api/bayut/listings       -- browse active Bayut listings
  /api/client-match         -- find owners matching a client's requirements

The first three are read-only and operate over data that's already loaded
into the DataStore (leads_df) plus on-disk files (rental CSV, bayut CSV).
The fourth (/client-match) ranks owners against buyer/tenant requirements
using the same logic as the Streamlit page.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from .. import _sys_paths  # noqa: F401 -- puts project root on sys.path

from ..auth import get_current_user
from ..deps import DataStore, get_data_store
from ..schemas.listings import (
    ExpiringLease, LeaseExpiryResponse,
    MatchListingRequest, MatchedOwner, MatchListingResponse,
    BayutListing, BuildingSummary, BayutListingsResponse,
    ClientMatchRequest, OwnerMatchResult, ClientMatchResponse,
)


router = APIRouter(prefix="/api", tags=["listings"])


# ---------------------------------------------------------------------------
# Lazy data loaders -- these read from disk on first call. Once Phase 5B
# lands they'll switch to SQLite reads, but the public API stays the same.
# ---------------------------------------------------------------------------

_BAYUT_CSV = Path("data/bayut_palm_listings.csv")


def _load_rentals_df() -> pd.DataFrame:
    """Load rental data via rental_processor; empty DF if no file."""
    try:
        from rental_processor import load_rental_data  # noqa: E402
        return load_rental_data()
    except Exception:
        return pd.DataFrame()


def _load_bayut_df() -> pd.DataFrame:
    """Load active Bayut listings from CSV (Phase 5B will switch to SQLite)."""
    if not _BAYUT_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(_BAYUT_CSV, encoding="utf-8", low_memory=False, on_bad_lines="skip")
        return df
    except Exception:
        return pd.DataFrame()


def _safe(val):
    """pandas-friendly NaN/None coercion."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, str) and not val.strip():
        return None
    return val


def _safe_str(val) -> Optional[str]:
    v = _safe(val)
    return str(v) if v is not None else None


def _safe_float(val) -> Optional[float]:
    v = _safe(val)
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Lease expiry
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/lease-expiry", response_model=LeaseExpiryResponse)
def lease_expiry(
    days_ahead: int = Query(90, ge=1, le=730),
    building: Optional[str] = None,
    bedrooms: Optional[str] = None,
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
) -> LeaseExpiryResponse:
    """Expiring leases cross-referenced with owner contacts."""
    rentals_df = _load_rentals_df()
    if rentals_df.empty:
        return LeaseExpiryResponse(
            leases=[], total=0, with_contact=0,
            active_rentals_total=0, unique_buildings=0,
            expiry_window_days=days_ahead,
        )

    from rental_processor import (  # noqa: E402
        cross_reference_rentals_with_owners, get_active_rental_count,
    )

    cross = cross_reference_rentals_with_owners(
        rental_df=rentals_df,
        leads_df=store.leads_df,
        days_ahead=days_ahead,
    )

    if cross.empty:
        return LeaseExpiryResponse(
            leases=[], total=0, with_contact=0,
            active_rentals_total=int(get_active_rental_count(rentals_df)),
            unique_buildings=int(rentals_df["building_name"].nunique()),
            expiry_window_days=days_ahead,
        )

    if building:
        cross = cross[
            cross["building_name"].fillna("").str.lower().str.contains(
                building.lower(), regex=False, na=False
            )
        ]
    if bedrooms:
        if bedrooms.lower() == "studio":
            cross = cross[
                cross["bedrooms"].fillna("").astype(str).str.lower().str.contains(
                    "studio", regex=False, na=False,
                )
            ]
        else:
            cross = cross[cross["bedrooms"].astype(str).str.strip() == bedrooms]

    leases: list[ExpiringLease] = []
    for _, r in cross.iterrows():
        contract_end = r.get("contract_end")
        leases.append(ExpiringLease(
            building_name=_safe_str(r.get("building_name")),
            unit_number=_safe_str(r.get("unit_number")),
            bedrooms=_safe_str(r.get("bedrooms")),
            size_sqft=_safe_float(r.get("size_sqft")),
            contract_end=str(contract_end)[:10] if pd.notna(contract_end) else None,
            days_remaining=int(r["days_remaining"]) if pd.notna(r.get("days_remaining")) else None,
            annual_rent=_safe_float(r.get("annual_rent")),
            has_owner_contact=bool(r.get("has_owner_contact", False)),
            owner_name=_safe_str(r.get("owner_name")),
            owner_phone=_safe_str(r.get("owner_phone")),
            owner_email=_safe_str(r.get("owner_email")),
        ))

    with_contact = sum(1 for L in leases if L.has_owner_contact)
    return LeaseExpiryResponse(
        leases=leases,
        total=len(leases),
        with_contact=with_contact,
        active_rentals_total=int(get_active_rental_count(rentals_df)),
        unique_buildings=int(rentals_df["building_name"].nunique()),
        expiry_window_days=days_ahead,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Listing matcher (manual lookup -- DLD permit lookup is intentionally NOT
# ported because it requires a Playwright browser running reCAPTCHA, which
# doesn't fit a stateless SaaS backend.)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/match/listing", response_model=MatchListingResponse)
def match_listing(
    req: MatchListingRequest,
    user: dict = Depends(get_current_user),
) -> MatchListingResponse:
    """Match a listing (building/unit/size/beds) against the leads database."""
    from listing_matcher.matcher import (  # noqa: E402
        match_listing as do_match, analyze_coverage, load_leads_df,
    )
    leads = load_leads_df()
    if leads.empty:
        raise HTTPException(
            status_code=503,
            detail="Lead database not available. Run consolidate_data.py / migration first.",
        )

    raw_matches = do_match(
        listing={
            "building_name": req.building_name,
            "unit_number": req.unit_number,
            "size_sqft": req.size_sqft,
            "bedrooms": req.bedrooms,
        },
        leads_df=leads,
    )

    matches = [
        MatchedOwner(
            building=m.get("building", ""),
            unit=m.get("unit", ""),
            size_sqft=_safe_float(m.get("size_sqft")),
            beds=_safe_str(m.get("beds")),
            owner_name=m.get("owner_name") or "",
            phone=m.get("phone") or "",
            phone_display=m.get("phone_display") or "",
            email=_safe_str(m.get("email")),
            transaction_date=_safe_str(m.get("transaction_date")),
            transaction_value=_safe_float(m.get("transaction_value")),
            confidence=float(m.get("confidence", 0)),
            match_type=m.get("match_type", ""),
        )
        for m in raw_matches
    ]

    try:
        coverage = analyze_coverage(leads)
    except Exception:
        coverage = {"total_units": len(leads)}

    return MatchListingResponse(matches=matches, coverage=coverage)


# ═══════════════════════════════════════════════════════════════════════════
# Bayut active listings
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/bayut/listings", response_model=BayutListingsResponse)
def bayut_listings(
    listing_type: Optional[str] = Query(None, description="'sale' or 'rent'"),
    building: Optional[str] = None,
    bedrooms: Optional[str] = None,
    price_min: Optional[float] = Query(None, ge=0),
    price_max: Optional[float] = Query(None, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    user: dict = Depends(get_current_user),
) -> BayutListingsResponse:
    """Filtered list of Bayut listings + per-building summary."""
    df = _load_bayut_df()
    if df.empty:
        return BayutListingsResponse(
            listings=[], total=0,
            sale_count=0, rent_count=0, unique_buildings=0,
            building_summary=[], last_scraped=None,
        )

    filtered = df.copy()
    if listing_type:
        filtered = filtered[
            filtered["listing_type"].fillna("").str.lower() == listing_type.lower()
        ]
    if building:
        filtered = filtered[
            filtered["building_name"].fillna("").str.lower().str.contains(
                building.lower(), regex=False, na=False,
            )
        ]
    if bedrooms:
        filtered = filtered[
            filtered["bedrooms"].astype(str).str.strip() == bedrooms
        ]
    if price_min is not None and "price_aed" in filtered.columns:
        filtered = filtered[
            filtered["price_aed"].isna() | (filtered["price_aed"] >= price_min)
        ]
    if price_max is not None and "price_aed" in filtered.columns:
        filtered = filtered[
            filtered["price_aed"].isna() | (filtered["price_aed"] <= price_max)
        ]

    sale_count = int((filtered["listing_type"].fillna("").str.lower() == "sale").sum()) if "listing_type" in filtered.columns else 0
    rent_count = int((filtered["listing_type"].fillna("").str.lower() == "rent").sum()) if "listing_type" in filtered.columns else 0
    unique_buildings = int(filtered["building_name"].nunique()) if "building_name" in filtered.columns else 0

    listings: list[BayutListing] = []
    # Sort by scraped_at desc when present; cap at limit
    if "scraped_at" in filtered.columns:
        filtered = filtered.sort_values("scraped_at", ascending=False)
    for _, r in filtered.head(limit).iterrows():
        listings.append(BayutListing(
            listing_url=_safe_str(r.get("listing_url")),
            listing_type=_safe_str(r.get("listing_type")),
            building_name=_safe_str(r.get("building_name")),
            unit_number=_safe_str(r.get("unit_number")),
            bedrooms=_safe_str(r.get("bedrooms")),
            bathrooms=_safe_str(r.get("bathrooms")),
            size_sqft=_safe_float(r.get("size_sqft")),
            price_aed=_safe_float(r.get("price_aed")),
            rent_period=_safe_str(r.get("rent_period")),
            view_type=_safe_str(r.get("view")) or _safe_str(r.get("view_type")),
            agent_name=_safe_str(r.get("agent_name")),
            agency=_safe_str(r.get("agency")),
            listed_date=_safe_str(r.get("listed_date")),
            scraped_at=_safe_str(r.get("scraped_at")),
        ))

    # Per-building summary
    building_rows: list[BuildingSummary] = []
    if "building_name" in filtered.columns and not filtered.empty:
        grouped = (
            filtered.groupby("building_name", dropna=True)
            .agg(
                listings=("building_name", "count"),
                avg_beds=("bedrooms", lambda s: pd.to_numeric(s, errors="coerce").mean()),
                avg_size=("size_sqft", "mean") if "size_sqft" in filtered.columns else ("building_name", "count"),
                avg_price=("price_aed", "mean") if "price_aed" in filtered.columns else ("building_name", "count"),
                types=("listing_type", lambda s: "/".join(sorted(set(str(x).upper() for x in s.dropna())))) if "listing_type" in filtered.columns else ("building_name", "count"),
            )
            .reset_index()
            .sort_values("listings", ascending=False)
        )
        for _, gr in grouped.head(20).iterrows():
            building_rows.append(BuildingSummary(
                building_name=str(gr["building_name"]),
                listings=int(gr["listings"]),
                avg_beds=_safe_float(gr.get("avg_beds")),
                avg_size=_safe_float(gr.get("avg_size")),
                avg_price=_safe_float(gr.get("avg_price")),
                types=str(gr.get("types") or ""),
            ))

    last_scraped = None
    if "scraped_at" in df.columns and df["scraped_at"].notna().any():
        last_scraped = str(df["scraped_at"].max())[:10]

    return BayutListingsResponse(
        listings=listings,
        total=len(filtered),
        sale_count=sale_count,
        rent_count=rent_count,
        unique_buildings=unique_buildings,
        building_summary=building_rows,
        last_scraped=last_scraped,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Client match -- rank owners against a client's requirements
# ═══════════════════════════════════════════════════════════════════════════

def _make_client_id(owner_name: str, building: str, unit: str) -> str:
    from client_data_manager import make_client_id  # noqa: E402
    return make_client_id(name=owner_name, building=building, unit=unit)


@router.post("/client-match", response_model=ClientMatchResponse)
def client_match(
    req: ClientMatchRequest,
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
) -> ClientMatchResponse:
    """Rank owners by how well they match a buyer/tenant client's requirements."""
    if req.transaction_type.lower() not in ("sale", "rent"):
        raise HTTPException(status_code=422, detail="transaction_type must be 'sale' or 'rent'")

    df = store.leads_df
    if df is None or df.empty:
        return ClientMatchResponse(matches=[], total=0)

    # Building filter
    results = df.copy()
    if req.buildings:
        results = results[results["building_name"].isin(req.buildings)]

    # Bedroom filter
    if req.bedrooms and req.bedrooms.lower() != "any":
        if req.bedrooms == "5+":
            results = results[results["bedrooms"].apply(
                lambda b: pd.notna(b) and any(
                    str(b).strip().startswith(str(x)) for x in range(5, 20)
                )
            )]
        elif req.bedrooms.lower() == "studio":
            results = results[
                results["bedrooms"].astype(str).str.lower().str.contains("studio", na=False)
            ]
        else:
            results = results[results["bedrooms"].astype(str).str.strip() == req.bedrooms]

    if results.empty:
        return ClientMatchResponse(matches=[], total=0)

    # Bayut active listings: building -> [{beds, price, url, ltype}]
    bayut_df = _load_bayut_df()
    bayut_lookup: dict[str, list[dict]] = {}
    if not bayut_df.empty:
        for _, bl in bayut_df.iterrows():
            bk = str(bl.get("building_name", "")).strip().lower().replace(" ", "").replace("-", "")
            if not bk:
                continue
            bayut_lookup.setdefault(bk, []).append({
                "beds": str(int(bl["bedrooms"])) if pd.notna(bl.get("bedrooms")) else None,
                "price": _safe_float(bl.get("price_aed")),
                "url": _safe_str(bl.get("listing_url")) or "",
                "ltype": str(bl.get("listing_type", "")).lower(),
            })

    txn_lower = req.transaction_type.lower()
    bmin, bmax = req.budget_min, req.budget_max
    sea_view = req.sea_view_only

    scored: list[OwnerMatchResult] = []
    for _, row in results.iterrows():
        bkey = str(row.get("building_name", "")).strip().lower().replace(" ", "").replace("-", "")

        # Active listing for this building (matching beds + transaction type)
        beds_str = str(row.get("bedrooms", "")).strip()
        active = next(
            (bl for bl in bayut_lookup.get(bkey, [])
             if bl["ltype"] == txn_lower and (bl["beds"] == beds_str or not bl["beds"])),
            None,
        )

        # Sea view filter
        view = _safe_str(row.get("view"))
        if sea_view and view and "sea" not in view.lower():
            continue

        # Budget filter via active listing price (best signal we have without registry)
        if active and active.get("price") and bmin is not None and bmax is not None:
            px = active["price"]
            if not (bmin * 0.7 <= px <= bmax * 1.3):
                continue

        # Score
        score = 0.0
        factors: list[str] = []
        if active:
            score += 50
            factors.append("active_listing")
        if pd.notna(row.get("phone")):
            score += 20
            factors.append("has_phone")
        if pd.notna(row.get("size_sqft")):
            score += 5
        if view and "sea" in view.lower():
            score += 10
            factors.append("sea_view")
        if not req.bedrooms or req.bedrooms.lower() == "any":
            pass
        elif beds_str == req.bedrooms:
            score += 15
            factors.append("exact_bedrooms")

        owner = _safe_str(row.get("owner_name"))
        building = _safe_str(row.get("building_name"))
        unit = _safe_str(row.get("unit_number"))
        if not owner or not building:
            continue
        scored.append(OwnerMatchResult(
            client_id=_make_client_id(owner, building or "", unit or ""),
            owner_name=owner,
            phone=_safe_str(row.get("phone")),
            building_name=building,
            unit_number=unit,
            bedrooms=_safe_str(row.get("bedrooms")),
            size_sqft=_safe_float(row.get("size_sqft")),
            last_sale_price=_safe_float(row.get("transaction_value")),
            last_sale_date=str(row["date"])[:10] if pd.notna(row.get("date")) else None,
            last_annual_rent=None,
            has_active_listing=active is not None,
            active_listing_url=active["url"] if active else None,
            active_listing_price=active["price"] if active else None,
            score=score,
            score_factors=factors,
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return ClientMatchResponse(
        matches=scored[: req.limit],
        total=len(scored),
    )
