"""
reidin_processor.py — Reidin DLD Export Ingestion
Normalises a Reidin CSV export to the unit_registry schema and saves
data/reidin_master.parquet (+ .csv) for Priority 1.5 in the bedroom cascade.

Usage (CLI):
    python reidin_processor.py --input path/to/reidin_export.csv

Usage (programmatic / Streamlit UI):
    from reidin_processor import process_reidin_export
    result = process_reidin_export(df)   # df is already-loaded DataFrame
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


def standardize_building_name(name):
    """
    Lazy proxy to data_processor.standardize_building_name.

    The previous direct import (`from building_intelligence import
    standardize_building_name`) was broken -- the function lives in
    data_processor, not building_intelligence -- and would raise ImportError
    as soon as this module loaded. The deferred import avoids a circular
    dependency (data_processor imports from reidin via the cascade path).
    """
    try:
        from data_processor import standardize_building_name as _impl
    except Exception:
        return None
    try:
        return _impl(name)
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Column aliases — Reidin exports vary slightly in naming
# ---------------------------------------------------------------------------
_COL_ALIASES = {
    "building_name": ["Project", "Building", "Property", "Community", "project", "property"],
    "unit_number":   ["Unit No", "Unit No.", "UnitNo", "Unit Number", "unit_no", "unit", "Unit"],
    "bedrooms":      ["Bedrooms", "Beds", "No. of Bedrooms", "bedroom", "bedrooms"],
    "size_sqft":     ["Size", "Area", "Size (Sq Ft)", "Sq Ft", "size_sqft", "size_sqf", "Size (Sqf)"],
    "contract_date": ["Contract Date", "Transaction Date", "Date", "contract_date", "date"],
    "transaction_amount": ["Amount", "Price", "Transaction Amount", "Sale Price", "amount", "amount_aed", "Amount (AED)"],
    "floor_level":   ["Floor", "Floor No", "floor"],
    "view":          ["View", "view", "Primary/Secondary View"],
}


def _find_col(df: pd.DataFrame, aliases: list) -> str | None:
    """Return the first matching column name from a list of aliases."""
    for alias in aliases:
        if alias in df.columns:
            return alias
    # Case-insensitive fallback
    lower_cols = {c.lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in lower_cols:
            return lower_cols[alias.lower()]
    return None


def _clean_bedrooms(val) -> str | None:
    """
    Normalise bedroom values. Preserves compound layouts so we don't silently
    drop the '+' half of a 2+1 / 1+Study / 3+M unit (Reidin is HIGH authority
    in the bedroom cascade; losing the modifier has caused wrong pitches).

    Mapping:
      Studio variants (studio, st, s, 0) → "Studio"
      "2 + 1", "2+1"                     → "2+1"
      "1 + Study", "1+study"             → "1+Study"
      "3 + Maid", "3+m"                  → "3+M"
      "2 BR"                             → "2"
      anything else with a digit         → "<first-digit>"
    """
    if pd.isna(val):
        return None
    s = str(val).strip()
    s_lower = s.lower()
    if s_lower in ("studio", "st", "s", "0"):
        return "Studio"
    plus = re.match(r"^\s*(\d+)\s*\+\s*([a-zA-Z0-9]+)", s)
    if plus:
        digits, modifier = plus.group(1), plus.group(2)
        if modifier.isdigit():
            return f"{digits}+{modifier}"
        m_lower = modifier.lower()
        if m_lower in ("m", "maid", "maids"):
            return f"{digits}+M"
        if m_lower in ("s", "study"):
            return f"{digits}+Study"
        return f"{digits}+{modifier.capitalize()}"
    m = re.search(r"(\d+)", s_lower)
    if m:
        return m.group(1)
    return None


def _clean_size(val) -> float | None:
    """Return float size or None."""
    if pd.isna(val):
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _detect_sqm(sizes: pd.Series) -> bool:
    """Return True if sizes look like sqm (median < 300 implies sqm for Palm units)."""
    valid = sizes.dropna()
    if valid.empty:
        return False
    return float(valid.median()) < 300


def process_reidin_export(df: pd.DataFrame) -> dict:
    """
    Normalise a raw Reidin DataFrame and save to data/reidin_master.parquet.

    Returns a summary dict:
        {
            'rows_in': int,
            'rows_out': int,
            'buildings': int,
            'output_path': str,
            'warnings': list[str],
        }
    """
    warnings: list[str] = []
    rows_in = len(df)

    # ── 1. Map columns ────────────────────────────────────────────────────────
    col_map: dict[str, str | None] = {}
    for field, aliases in _COL_ALIASES.items():
        col_map[field] = _find_col(df, aliases)

    if col_map["building_name"] is None:
        return {
            "rows_in": rows_in, "rows_out": 0, "buildings": 0,
            "output_path": None,
            "warnings": ["ERROR: I could not find a building/project column. "
                         "Expected one of: Project, Building, Community."],
        }
    if col_map["unit_number"] is None:
        return {
            "rows_in": rows_in, "rows_out": 0, "buildings": 0,
            "output_path": None,
            "warnings": ["ERROR: I could not find a unit number column. "
                         "Expected one of: Unit No, Unit Number."],
        }

    # ── 2. Build normalised DataFrame ─────────────────────────────────────────
    out = pd.DataFrame()

    # Building name — standardize via building_intelligence (non-negotiable for data integrity)
    raw_buildings = df[col_map["building_name"]].astype(str).str.strip()
    out["building_name"] = raw_buildings.apply(
        lambda n: (standardize_building_name(n) or n) if n and n.lower() != "nan" else None
    )

    # Unit number
    out["unit_number"] = (
        df[col_map["unit_number"]].astype(str).str.strip().str.upper()
        .str.replace(" ", "", regex=False).str.replace("-", "", regex=False)
    )

    # Bedrooms
    if col_map["bedrooms"]:
        out["bedrooms"] = df[col_map["bedrooms"]].apply(_clean_bedrooms)
    else:
        out["bedrooms"] = None
        warnings.append("No bedrooms column found — bedroom data will be missing")

    # Size
    if col_map["size_sqft"]:
        raw_sizes = df[col_map["size_sqft"]].apply(_clean_size)
        if _detect_sqm(raw_sizes):
            out["size_sqft"] = (raw_sizes * 10.7639).round(0)
            warnings.append("I detected sqm values — auto-converted to sqft (×10.7639)")
        else:
            out["size_sqft"] = raw_sizes
    else:
        out["size_sqft"] = None

    # Optional columns
    if col_map["contract_date"]:
        out["contract_date"] = pd.to_datetime(
            df[col_map["contract_date"]], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
    else:
        out["contract_date"] = None

    if col_map["transaction_amount"]:
        out["transaction_amount"] = df[col_map["transaction_amount"]].apply(_clean_size)
    else:
        out["transaction_amount"] = None

    if col_map["floor_level"]:
        out["floor_level"] = df[col_map["floor_level"]].astype(str).str.strip()
    else:
        out["floor_level"] = None

    if col_map["view"]:
        out["view"] = df[col_map["view"]].astype(str).str.strip()
    else:
        out["view"] = None

    out["confidence"] = "HIGH"
    out["sources"] = "reidin"

    # ── 3. Drop rows missing building or unit ────────────────────────────────
    out = out[
        out["building_name"].notna() &
        out["unit_number"].notna() &
        (out["building_name"].str.strip() != "") &
        (out["unit_number"].str.strip() != "") &
        (~out["unit_number"].isin(["NAN", "-", ""]))
    ].copy()

    # ── 4. Dedup — keep most recent contract per (building, unit) ─────────────
    if "contract_date" in out.columns and out["contract_date"].notna().any():
        out = (
            out.sort_values("contract_date", ascending=False)
            .drop_duplicates(subset=["building_name", "unit_number"], keep="first")
            .reset_index(drop=True)
        )
    else:
        out = out.drop_duplicates(subset=["building_name", "unit_number"], keep="first").reset_index(drop=True)

    rows_out = len(out)
    buildings = out["building_name"].nunique() if rows_out > 0 else 0

    # ── 5. Save ───────────────────────────────────────────────────────────────
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    pq_path = output_dir / "reidin_master.parquet"
    csv_path = output_dir / "reidin_master.csv"
    out.to_parquet(pq_path, index=False)
    out.to_csv(csv_path, index=False)

    return {
        "rows_in": rows_in,
        "rows_out": rows_out,
        "buildings": buildings,
        "output_path": str(pq_path),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Raw extractor output ingestion (from reidin_extractor.py)
# ---------------------------------------------------------------------------

# Column aliases matching reidin_extractor.py output columns
_RAW_COL_ALIASES = {
    "building_name":      ["property", "Property", "Building", "Community"],
    "unit_number":        ["unit", "Unit", "unit_no"],
    "bedrooms":           ["bedrooms", "Bedrooms", "beds"],
    "size_sqft":          ["size_sqf", "size_sqft", "Size (Sqf)", "Size"],
    "contract_date":      ["date", "Date"],
    "transaction_amount": ["amount_aed", "Amount (AED)", "Amount"],
    "floor_level":        ["floor", "Floor"],
    "view":               ["view", "View", "Primary/Secondary View"],
}


def process_reidin_raw(raw_path: str = "data/reidin_raw.csv") -> dict:
    """
    Read data/reidin_raw.csv (output of reidin_extractor.py) and run it
    through the standard normalization pipeline, including building name
    standardization via building_intelligence.standardize_building_name.

    Returns the same summary dict as process_reidin_export().
    """
    rpath = Path(raw_path)
    if not rpath.exists():
        return {
            "rows_in": 0, "rows_out": 0, "buildings": 0,
            "output_path": None,
            "warnings": [f"ERROR: Raw extractor output not found at {raw_path}"],
        }

    df = pd.read_csv(rpath, low_memory=False)

    # Remap extractor column names to the aliases process_reidin_export() understands
    rename: dict[str, str] = {}
    for field, aliases in _RAW_COL_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                rename[alias] = aliases[0]  # normalise to first alias (canonical)
                break
    if rename:
        df = df.rename(columns=rename)

    return process_reidin_export(df)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Ingest a Reidin DLD CSV export")
    parser.add_argument("--input", required=True, help="Path to Reidin CSV export file")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    print(f"Reading {input_path} ...")
    df = pd.read_csv(input_path, encoding="utf-8", low_memory=False, on_bad_lines="skip")
    print(f"  {len(df):,} rows loaded")

    result = process_reidin_export(df)

    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  WARNING: {w}")

    if result["output_path"]:
        print(f"\nI ingested {result['rows_out']:,} units across {result['buildings']} buildings.")
        print(f"Output saved to: {result['output_path']}")
        print("Reidin DLD is now active at Priority 1.5 in the bedroom cascade.")
    else:
        print("\nIngestion failed. See warnings above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
