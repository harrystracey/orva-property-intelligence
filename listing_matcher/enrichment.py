"""
Post-match enrichment — adds rental intelligence, competition data,
and transaction history to match results.

Usage:
    from listing_matcher.enrichment import enrich_matches
    enriched = enrich_matches(matches, building_name, bedrooms)
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


def _norm_building(s: str) -> str:
    return s.strip().lower().replace(" ", "").replace("-", "") if s else ""


def _norm_unit(s: str) -> str:
    return s.strip().upper().replace(" ", "").replace("-", "") if s else ""


def _load_rentals() -> pd.DataFrame:
    """Load unified rental data (cached module-level)."""
    global _rentals_cache
    if _rentals_cache is not None:
        return _rentals_cache

    try:
        import sys
        _root = str(Path(__file__).resolve().parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from rental_processor import load_rental_data
        _rentals_cache = load_rental_data()
    except Exception:
        _rentals_cache = pd.DataFrame()
    return _rentals_cache


def _load_bayut() -> pd.DataFrame:
    """Load Bayut listings."""
    global _bayut_cache
    if _bayut_cache is not None:
        return _bayut_cache

    bayut_path = Path(__file__).resolve().parent.parent / "data" / "bayut_palm_listings.csv"
    if bayut_path.exists():
        try:
            _bayut_cache = pd.read_csv(bayut_path, low_memory=False)
        except Exception:
            _bayut_cache = pd.DataFrame()
    else:
        _bayut_cache = pd.DataFrame()
    return _bayut_cache


def _load_registry() -> pd.DataFrame:
    """Load unit registry."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    reg_path = Path(__file__).resolve().parent.parent / "data" / "unit_registry.csv"
    if reg_path.exists():
        try:
            _registry_cache = pd.read_csv(reg_path, low_memory=False)
        except Exception:
            _registry_cache = pd.DataFrame()
    else:
        _registry_cache = pd.DataFrame()
    return _registry_cache


_rentals_cache: pd.DataFrame | None = None
_bayut_cache: pd.DataFrame | None = None
_registry_cache: pd.DataFrame | None = None


def get_rental_intel(building: str, unit: str) -> dict:
    """Get rental intelligence for a specific unit."""
    rentals = _load_rentals()
    if rentals.empty:
        return {}

    bldg_key = _norm_building(building)
    unit_key = _norm_unit(unit)

    # Normalize rental building names for matching
    if "_bldg_key" not in rentals.columns:
        rentals["_bldg_key"] = rentals["building_name"].fillna("").apply(_norm_building)
    if "_unit_key" not in rentals.columns:
        rentals["_unit_key"] = rentals["unit_number"].fillna("").apply(_norm_unit)

    matches = rentals[
        (rentals["_bldg_key"] == bldg_key) &
        (rentals["_unit_key"] == unit_key)
    ]

    if matches.empty:
        # Try partial building name match
        matches = rentals[
            rentals["_bldg_key"].str.contains(bldg_key[:10], na=False) &
            (rentals["_unit_key"] == unit_key)
        ]

    if matches.empty:
        return {}

    # Get most recent contract
    latest = matches.sort_values("contract_end", ascending=False).iloc[0]
    now = pd.Timestamp.now()

    contract_end = latest.get("contract_end")
    result = {
        "has_rental_data": True,
        "annual_rent": float(latest["annualized_rent"]) if pd.notna(latest.get("annualized_rent")) else None,
        "contract_end": contract_end.strftime("%Y-%m-%d") if pd.notna(contract_end) else None,
        "contract_start": latest["contract_start"].strftime("%Y-%m-%d") if pd.notna(latest.get("contract_start")) else None,
        "total_contracts": len(matches),
    }

    if pd.notna(contract_end):
        days_left = (contract_end - now).days
        result["days_remaining"] = days_left
        if days_left < 0:
            result["lease_status"] = "expired"
        elif days_left <= 30:
            result["lease_status"] = "expiring_soon"
        elif days_left <= 90:
            result["lease_status"] = "expiring"
        else:
            result["lease_status"] = "active"

    rent_recurrence = latest.get("rent_recurrence")
    if pd.notna(rent_recurrence):
        result["rent_recurrence"] = str(rent_recurrence)

    return result


def get_competition(building: str, bedrooms: Optional[int] = None) -> dict:
    """Count competing listings on Bayut for same building + beds."""
    bayut = _load_bayut()
    if bayut.empty:
        return {}

    bldg_key = _norm_building(building)

    if "_bldg_key" not in bayut.columns:
        bayut["_bldg_key"] = bayut["building_name"].fillna("").apply(_norm_building)

    bldg_listings = bayut[bayut["_bldg_key"].str.contains(bldg_key[:10], na=False)]

    if bldg_listings.empty:
        return {"total_listings": 0}

    result = {
        "total_listings": len(bldg_listings),
    }

    if "listing_type" in bldg_listings.columns:
        result["for_sale"] = int((bldg_listings["listing_type"].str.lower() == "sale").sum())
        result["for_rent"] = int((bldg_listings["listing_type"].str.lower() == "rent").sum())

    if bedrooms is not None and "bedrooms" in bldg_listings.columns:
        same_beds = bldg_listings[bldg_listings["bedrooms"] == bedrooms]
        result["same_beds_count"] = len(same_beds)
        if "price_aed" in same_beds.columns and not same_beds["price_aed"].dropna().empty:
            prices = same_beds["price_aed"].dropna()
            result["price_min"] = int(prices.min())
            result["price_max"] = int(prices.max())
            result["price_median"] = int(prices.median())

    return result


def get_registry_info(building: str, unit: str) -> dict:
    """Get confirmed unit specs from registry."""
    registry = _load_registry()
    if registry.empty:
        return {}

    bldg_key = _norm_building(building)
    unit_key = _norm_unit(unit)

    if "_bldg_key" not in registry.columns:
        registry["_bldg_key"] = registry["building_name"].fillna("").apply(_norm_building)
    if "_unit_key" not in registry.columns:
        registry["_unit_key"] = registry["unit_number"].fillna("").apply(_norm_unit)

    match = registry[
        (registry["_bldg_key"] == bldg_key) &
        (registry["_unit_key"] == unit_key)
    ]

    if match.empty:
        return {}

    row = match.iloc[0]
    result = {}
    for col in ["bedrooms", "size_sqft", "floor_level", "view", "confidence",
                "last_sale_price", "last_sale_date", "last_annual_rent"]:
        val = row.get(col)
        if pd.notna(val):
            result[col] = val if not isinstance(val, float) else (int(val) if val == int(val) else float(val))

    return result


def enrich_matches(
    matches: list[dict],
    listing_building: str = "",
    listing_bedrooms: Optional[int] = None,
    listing_price: Optional[float] = None,
) -> list[dict]:
    """
    Enrich match results with rental intel, competition, and registry data.

    Adds an 'intelligence' dict to each match result.
    Also adds building-level 'competition' to the first result.
    """
    if not matches:
        return matches

    # Building-level competition (same for all matches)
    competition = get_competition(listing_building, listing_bedrooms)

    for match in matches:
        building = match.get("building", listing_building)
        unit = match.get("unit", "")

        intel = {}

        # Rental intelligence for this specific unit
        if unit:
            rental = get_rental_intel(building, unit)
            if rental:
                intel.update(rental)

        # Registry info for this specific unit
        if unit:
            reg = get_registry_info(building, unit)
            if reg:
                intel["registry"] = reg

                # Calculate estimated yield if we have rent + sale price
                if listing_price and intel.get("annual_rent"):
                    intel["estimated_yield"] = round(
                        (intel["annual_rent"] / listing_price) * 100, 1
                    )

        # Competition (building-level)
        if competition:
            intel["competition"] = competition

        match["intelligence"] = intel

    return matches
