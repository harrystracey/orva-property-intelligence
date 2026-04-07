"""
reidin_processor.py — Reidin DLD Export Ingestion (Sales + Rentals)
Normalises Reidin CSV exports and saves:
  - data/reidin_master.parquet (sales — Priority 1.5 in bedroom cascade)
  - data/reidin_rentals.parquet (rentals — vacancy forecasting)

Usage (CLI):
    python reidin_processor.py --input path/to/reidin_export.csv
    python reidin_processor.py --input path/to/rentals.csv --type rentals

Usage (programmatic / Streamlit UI):
    from reidin_processor import process_reidin_export, process_reidin_rentals
    result = process_reidin_export(df)
    result = process_reidin_rentals(df)
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from building_intelligence import resolve_building_name

# ---------------------------------------------------------------------------
# Column aliases — Reidin exports vary slightly in naming
# ---------------------------------------------------------------------------
_COL_ALIASES = {
    "building_name": ["Project", "Building", "Property", "Community", "project", "property"],
    "unit_number":   ["Unit No", "Unit No.", "UnitNo", "Unit Number", "unit_no", "unit", "Unit"],
    "bedrooms":      ["Bedrooms", "Beds", "No. of Bedrooms", "bedroom", "bedrooms", "Bedroom"],
    "size_sqft":     ["Size", "Area", "Size (Sq Ft)", "Sq Ft", "size_sqft", "size_sqf", "Size (Sqf)"],
    "contract_date": ["Contract Date", "Transaction Date", "Date", "contract_date", "date"],
    "transaction_amount": ["Amount", "Price", "Transaction Amount", "Sale Price", "amount", "amount_aed", "Amount (AED)"],
    "floor_level":   ["Floor", "Floor No", "floor"],
    "view":          ["View", "view", "Primary/Secondary View"],
}

_RENTAL_COL_ALIASES = {
    "building_name":    ["Property", "Building", "Project", "Community", "property"],
    "unit_number":      ["Unit", "Unit No", "Unit No.", "unit", "unit_no"],
    "bedrooms":         ["Bedroom", "Bedrooms", "Beds", "bedrooms"],
    "size_sqft":        ["Size (Sqf)", "Size", "size_sqf", "size_sqft", "Sq Ft"],
    "floor_level":      ["Floor", "floor"],
    "view":             ["Primary / Secondary View", "Primary/Secondary View", "View", "view"],
    "rent_type":        ["Rent Type", "rent_type"],
    "date":             ["Date", "date"],
    "contract_start":   ["Start Date", "Contract Start", "contract_start", "start_date"],
    "contract_end":     ["End Date", "Contract End", "contract_end", "end_date", "Expiry Date"],
    "annual_rent":      ["Annual (AED) Amount", "Annual Rent", "annual_rent_aed",
                         "Amount (AED)", "Amount", "annual_rent", "Rent"],
    "community":        ["Community", "community"],
    "parking":          ["Parking", "parking"],
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
    """Normalise bedroom values: Studio → 'Studio', integers → string digit."""
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ("studio", "st", "s", "0"):
        return "Studio"
    m = re.search(r"(\d+)", s)
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


def _is_rental_data(df: pd.DataFrame) -> bool:
    """Auto-detect if a DataFrame contains rental data based on column presence."""
    rental_indicators = ["start date", "end date", "contract start", "contract end",
                         "annual rent", "rent type", "annual_rent_aed", "contract_start",
                         "contract_end", "rent_type"]
    lower_cols = {c.lower() for c in df.columns}
    matches = sum(1 for ind in rental_indicators if ind in lower_cols)
    return matches >= 2


def process_reidin_export(df: pd.DataFrame) -> dict:
    """
    Normalise a raw Reidin sales DataFrame and save to data/reidin_master.parquet.

    Returns a summary dict:
        {
            'rows_in': int,
            'rows_out': int,
            'buildings': int,
            'output_path': str,
            'warnings': list[str],
        }
    """
    # Auto-detect rentals
    if _is_rental_data(df):
        return process_reidin_rentals(df)

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

    raw_buildings = df[col_map["building_name"]].astype(str).str.strip()
    out["building_name"] = raw_buildings.apply(
        lambda n: (resolve_building_name(n) or n) if n and n.lower() != "nan" else None
    )

    out["unit_number"] = (
        df[col_map["unit_number"]].astype(str).str.strip().str.upper()
        .str.replace(" ", "", regex=False).str.replace("-", "", regex=False)
    )

    if col_map["bedrooms"]:
        out["bedrooms"] = df[col_map["bedrooms"]].apply(_clean_bedrooms)
    else:
        out["bedrooms"] = None
        warnings.append("No bedrooms column found — bedroom data will be missing")

    if col_map["size_sqft"]:
        raw_sizes = df[col_map["size_sqft"]].apply(_clean_size)
        if _detect_sqm(raw_sizes):
            out["size_sqft"] = (raw_sizes * 10.7639).round(0)
            warnings.append("I detected sqm values — auto-converted to sqft (×10.7639)")
        else:
            out["size_sqft"] = raw_sizes
    else:
        out["size_sqft"] = None

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
# Rental contract processing — vacancy forecasting
# ---------------------------------------------------------------------------

def process_reidin_rentals(df: pd.DataFrame) -> dict:
    """
    Normalise a Reidin rental contracts DataFrame and save to
    data/reidin_rentals.parquet. Key output: contract end dates for
    vacancy forecasting.

    Returns the same summary dict format as process_reidin_export().
    """
    warnings: list[str] = []
    rows_in = len(df)

    # ── 1. Map columns ────────────────────────────────────────────────────────
    col_map: dict[str, str | None] = {}
    for field, aliases in _RENTAL_COL_ALIASES.items():
        col_map[field] = _find_col(df, aliases)

    if col_map["building_name"] is None:
        return {
            "rows_in": rows_in, "rows_out": 0, "buildings": 0,
            "output_path": None,
            "warnings": ["ERROR: Could not find building/property column."],
        }
    if col_map["unit_number"] is None:
        return {
            "rows_in": rows_in, "rows_out": 0, "buildings": 0,
            "output_path": None,
            "warnings": ["ERROR: Could not find unit number column."],
        }

    # ── 2. Build normalised DataFrame ─────────────────────────────────────────
    out = pd.DataFrame()

    raw_buildings = df[col_map["building_name"]].astype(str).str.strip()
    out["building_name"] = raw_buildings.apply(
        lambda n: (resolve_building_name(n) or n) if n and n.lower() != "nan" else None
    )

    out["unit_number"] = (
        df[col_map["unit_number"]].astype(str).str.strip().str.upper()
        .str.replace(" ", "", regex=False).str.replace("-", "", regex=False)
    )

    if col_map["bedrooms"]:
        out["bedrooms"] = df[col_map["bedrooms"]].apply(_clean_bedrooms)
    else:
        out["bedrooms"] = None

    if col_map["size_sqft"]:
        raw_sizes = df[col_map["size_sqft"]].apply(_clean_size)
        if _detect_sqm(raw_sizes):
            out["size_sqft"] = (raw_sizes * 10.7639).round(0)
            warnings.append("Detected sqm values — auto-converted to sqft")
        else:
            out["size_sqft"] = raw_sizes
    else:
        out["size_sqft"] = None

    # Rental-specific columns
    if col_map["rent_type"]:
        out["rent_type"] = df[col_map["rent_type"]].astype(str).str.strip()
    else:
        out["rent_type"] = None

    if col_map["contract_start"]:
        out["contract_start"] = pd.to_datetime(
            df[col_map["contract_start"]], errors="coerce", dayfirst=True
        ).dt.strftime("%Y-%m-%d")
    else:
        out["contract_start"] = None
        warnings.append("No contract start date column found")

    if col_map["contract_end"]:
        out["contract_end"] = pd.to_datetime(
            df[col_map["contract_end"]], errors="coerce", dayfirst=True
        ).dt.strftime("%Y-%m-%d")
    else:
        out["contract_end"] = None
        warnings.append("No contract end date column found — vacancy forecasting disabled")

    if col_map["annual_rent"]:
        out["annual_rent"] = df[col_map["annual_rent"]].apply(_clean_size)
    else:
        out["annual_rent"] = None

    if col_map["date"]:
        out["registration_date"] = pd.to_datetime(
            df[col_map["date"]], errors="coerce", dayfirst=True
        ).dt.strftime("%Y-%m-%d")
    else:
        out["registration_date"] = None

    if col_map["community"]:
        out["community"] = df[col_map["community"]].astype(str).str.strip()
    else:
        out["community"] = None

    if col_map["floor_level"]:
        out["floor_level"] = df[col_map["floor_level"]].astype(str).str.strip()
    else:
        out["floor_level"] = None

    if col_map["view"]:
        out["view"] = df[col_map["view"]].astype(str).str.strip()
    else:
        out["view"] = None

    if col_map["parking"]:
        out["parking"] = df[col_map["parking"]].astype(str).str.strip()
    else:
        out["parking"] = None

    out["sources"] = "reidin_rental"

    # ── 3. Drop rows missing building or unit ────────────────────────────────
    out = out[
        out["building_name"].notna() &
        out["unit_number"].notna() &
        (out["building_name"].str.strip() != "") &
        (out["unit_number"].str.strip() != "") &
        (~out["unit_number"].isin(["NAN", "-", ""]))
    ].copy()

    # ── 4. Dedup — keep most recent contract per (building, unit) ─────────────
    if "contract_end" in out.columns and out["contract_end"].notna().any():
        out = (
            out.sort_values("contract_end", ascending=False)
            .drop_duplicates(subset=["building_name", "unit_number"], keep="first")
            .reset_index(drop=True)
        )
    elif "registration_date" in out.columns and out["registration_date"].notna().any():
        out = (
            out.sort_values("registration_date", ascending=False)
            .drop_duplicates(subset=["building_name", "unit_number"], keep="first")
            .reset_index(drop=True)
        )
    else:
        out = out.drop_duplicates(
            subset=["building_name", "unit_number"], keep="first"
        ).reset_index(drop=True)

    rows_out = len(out)
    buildings = out["building_name"].nunique() if rows_out > 0 else 0

    # ── 5. Vacancy forecast stats ────────────────────────────────────────────
    expiring_30 = 0
    expiring_60 = 0
    expiring_90 = 0
    if "contract_end" in out.columns and out["contract_end"].notna().any():
        today = datetime.now().strftime("%Y-%m-%d")
        end_dates = pd.to_datetime(out["contract_end"], errors="coerce")
        today_dt = pd.Timestamp(today)
        future_mask = end_dates >= today_dt
        expiring_30 = int(((end_dates - today_dt).dt.days <= 30) & future_mask).sum()
        expiring_60 = int(((end_dates - today_dt).dt.days <= 60) & future_mask).sum()
        expiring_90 = int(((end_dates - today_dt).dt.days <= 90) & future_mask).sum()
        warnings.append(
            f"Vacancy forecast: {expiring_30} units expiring in 30 days, "
            f"{expiring_60} in 60 days, {expiring_90} in 90 days"
        )

    # ── 6. Save ───────────────────────────────────────────────────────────────
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    pq_path = output_dir / "reidin_rentals.parquet"
    csv_path = output_dir / "reidin_rentals.csv"
    out.to_parquet(pq_path, index=False)
    out.to_csv(csv_path, index=False)

    return {
        "rows_in": rows_in,
        "rows_out": rows_out,
        "buildings": buildings,
        "output_path": str(pq_path),
        "warnings": warnings,
        "expiring_30": expiring_30,
        "expiring_60": expiring_60,
        "expiring_90": expiring_90,
    }


# ---------------------------------------------------------------------------
# Raw extractor output ingestion (from reidin_extractor.py)
# ---------------------------------------------------------------------------

_RAW_COL_ALIASES = {
    "building_name":      ["property", "Property", "Building", "Community"],
    "unit_number":        ["unit", "Unit", "unit_no"],
    "bedrooms":           ["bedrooms", "Bedrooms", "beds", "Bedroom"],
    "size_sqft":          ["size_sqf", "size_sqft", "Size (Sqf)", "Size"],
    "contract_date":      ["date", "Date"],
    "transaction_amount": ["amount_aed", "Amount (AED)", "Amount"],
    "floor_level":        ["floor", "Floor"],
    "view":               ["view", "View", "Primary/Secondary View"],
}

_RAW_RENTAL_COL_ALIASES = {
    "building_name":    ["property", "Property"],
    "unit_number":      ["unit", "Unit"],
    "bedrooms":         ["bedrooms", "Bedrooms", "Bedroom"],
    "size_sqft":        ["size_sqf", "Size (Sqf)"],
    "rent_type":        ["rent_type", "Rent Type"],
    "date":             ["date", "Date"],
    "contract_start":   ["contract_start", "Start Date"],
    "contract_end":     ["contract_end", "End Date"],
    "annual_rent":      ["annual_rent_aed", "Annual (AED) Amount"],
    "community":        ["community", "Community"],
    "floor_level":      ["floor", "Floor"],
    "view":             ["view", "View"],
    "parking":          ["parking", "Parking"],
}


def process_reidin_raw(raw_path: str = "data/reidin_raw_sales.csv") -> dict:
    """
    Read raw extractor CSV output and run it through normalization.
    Auto-detects sales vs rentals.
    """
    rpath = Path(raw_path)
    if not rpath.exists():
        # Fallback to old path
        old_path = Path("data/reidin_raw.csv")
        if old_path.exists():
            rpath = old_path
        else:
            return {
                "rows_in": 0, "rows_out": 0, "buildings": 0,
                "output_path": None,
                "warnings": [f"ERROR: Raw extractor output not found at {raw_path}"],
            }

    df = pd.read_csv(rpath, low_memory=False)

    if _is_rental_data(df):
        # Remap rental extractor columns
        rename: dict[str, str] = {}
        for field, aliases in _RAW_RENTAL_COL_ALIASES.items():
            for alias in aliases:
                if alias in df.columns:
                    rename[alias] = aliases[0]
                    break
        if rename:
            df = df.rename(columns=rename)
        return process_reidin_rentals(df)
    else:
        # Remap sales extractor columns
        rename: dict[str, str] = {}
        for field, aliases in _RAW_COL_ALIASES.items():
            for alias in aliases:
                if alias in df.columns:
                    rename[alias] = aliases[0]
                    break
        if rename:
            df = df.rename(columns=rename)
        return process_reidin_export(df)


def process_reidin_raw_rentals(raw_path: str = "data/reidin_raw_rentals.csv") -> dict:
    """Process raw rental extractor output explicitly."""
    return process_reidin_raw(raw_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Ingest a Reidin DLD CSV export")
    parser.add_argument("--input", required=True, help="Path to Reidin CSV export file")
    parser.add_argument("--type", default="auto", choices=["auto", "sales", "rentals"],
                        help="Data type (default: auto-detect)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    print(f"Reading {input_path} ...")
    df = pd.read_csv(input_path, encoding="utf-8", low_memory=False, on_bad_lines="skip")
    print(f"  {len(df):,} rows loaded")

    if args.type == "rentals" or (args.type == "auto" and _is_rental_data(df)):
        print("  Detected: RENTAL data")
        result = process_reidin_rentals(df)
    else:
        print("  Detected: SALES data")
        result = process_reidin_export(df)

    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  {w}")

    if result["output_path"]:
        print(f"\nIngested {result['rows_out']:,} units across {result['buildings']} buildings.")
        print(f"Output saved to: {result['output_path']}")
    else:
        print("\nIngestion failed. See warnings above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
