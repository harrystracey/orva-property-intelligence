"""
Unit Registry Module
Fast lookup for confirmed unit specifications (bedrooms, size, view)
"""

import pandas as pd
from pathlib import Path
from typing import Dict, Optional

REGISTRY_PATH = Path("data/unit_registry.csv")


def load_unit_registry() -> pd.DataFrame:
    """Load unit registry. Returns empty DataFrame if file missing."""
    try:
        if REGISTRY_PATH.exists():
            return pd.read_csv(REGISTRY_PATH, encoding="utf-8", low_memory=False)
        return pd.DataFrame()
    except Exception as e:
        print(f"[unit_registry] Error loading registry: {e}")
        return pd.DataFrame()


def get_unit_info(building: str, unit: str) -> Optional[Dict]:
    """
    Lookup unit in registry. Returns dict with:
    - bedrooms, size_sqft, floor_level, view, unit_position
    - confidence, sources, sale_count, rental_count
    - last_sale_price, last_sale_date, last_annual_rent
    
    Returns None if not found.
    """
    registry = load_unit_registry()
    if registry.empty:
        return None
    try:
        from data_processor import standardize_building_name
        b_std = standardize_building_name(str(building).strip())
        if b_std:
            building = b_std
    except Exception:
        pass
    # Normalize for matching (remove spaces/dashes)
    b_norm = str(building).strip().lower().replace(" ", "").replace("-", "")
    u_norm = str(unit).strip().upper().replace(" ", "").replace("-", "")
    # Create match keys in registry
    registry["_b"] = registry["building_name"].fillna("").astype(str).str.strip().str.lower().str.replace(" ", "").str.replace("-", "")
    registry["_u"] = registry["unit_number"].fillna("").astype(str).str.strip().str.upper().str.replace(" ", "").str.replace("-", "")
    match = registry[(registry["_b"] == b_norm) & (registry["_u"] == u_norm)]
    if match.empty:
        return None
    
    row = match.iloc[0]
    return {
        "building_name": row["building_name"],
        "unit_number": row["unit_number"],
        "bedrooms": row["bedrooms"],
        "size_sqft": row["size_sqft"],
        "floor_level": row["floor_level"],
        "view": row["view"] if pd.notna(row["view"]) else None,
        "unit_position": row["unit_position"] if pd.notna(row["unit_position"]) else None,
        "confidence": row["confidence"],
        "sources": row["sources"],
        "sale_count": int(row["sale_count"]) if pd.notna(row["sale_count"]) else 0,
        "rental_count": int(row["rental_count"]) if pd.notna(row["rental_count"]) else 0,
        "last_sale_price": int(row["last_sale_price"]) if pd.notna(row["last_sale_price"]) else None,
        "last_sale_date": row["last_sale_date"] if pd.notna(row["last_sale_date"]) else None,
        "last_annual_rent": int(row["last_annual_rent"]) if pd.notna(row["last_annual_rent"]) else None,
    }


def get_building_units(building: str, bedrooms: Optional[str] = None) -> pd.DataFrame:
    """
    Get all units in a building, optionally filtered by bedrooms.
    Returns DataFrame subset from registry.
    """
    registry = load_unit_registry()
    if registry.empty:
        return pd.DataFrame()
    
    b_norm = str(building).strip().lower().replace(" ", "").replace("-", "")
    registry["_b"] = registry["building_name"].fillna("").astype(str).str.strip().str.lower().str.replace(" ", "").str.replace("-", "")
    
    result = registry[registry["_b"] == b_norm].copy()
    
    if bedrooms is not None:
        result = result[result["bedrooms"] == str(bedrooms)]
    
    return result


def get_registry_stats() -> Dict:
    """Return summary stats about the registry."""
    registry = load_unit_registry()
    if registry.empty:
        return {"total": 0}
    
    return {
        "total_units": len(registry),
        "buildings": registry["building_name"].nunique(),
        "high_confidence": len(registry[registry["confidence"] == "HIGH"]),
        "medium_confidence": len(registry[registry["confidence"] == "MEDIUM"]),
        "inferred_confidence": len(registry[registry["confidence"] == "INFERRED"]),
        "with_bedrooms": len(registry[registry["bedrooms"].notna()]),
        "with_view": len(registry[registry["view"].notna()]),
        "avg_units_per_building": len(registry) / registry["building_name"].nunique(),
    }
