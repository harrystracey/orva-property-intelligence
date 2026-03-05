"""
Data Ingestion Module - CSV/Excel to SQLite Pipeline
Palm Jumeirah Real Estate Intelligence System

Provides:
- ingest_leads(csv_path)        -- import a single leads CSV into the leads table
- ingest_leads_master()         -- import the consolidated leads_master.csv
- ingest_transactions()         -- import reference_master_with_units.csv into transactions
- build_cross_references()      -- precompute lead-to-transaction matches
- reingest_all()                -- full pipeline: leads + transactions + cross-refs

All existing normalization, enrichment, and deduplication logic from
data_processor.py and building_intelligence.py is reused -- no domain
logic is duplicated or modified here.
"""

import sqlite3
import os
import re
import traceback
from pathlib import Path
from typing import Optional, Tuple, Dict, List

import pandas as pd
import numpy as np

from database import get_connection, init_database, table_has_data

# ---------------------------------------------------------------------------
# Import existing normalization functions from the codebase.
# These are the same functions used by the current CSV pipeline --
# we call them row-by-row during ingestion so domain logic stays in one place.
# ---------------------------------------------------------------------------
from data_processor import (
    standardize_building_name,
    get_building_family,
    detect_columns,
    detect_reference_columns,
    clean_bedroom,
    clean_reference_beds,
    clean_size_value,
    convert_to_sqft_if_needed,
    detect_size_column,
    get_first_non_null,
    merge_building_names,
    merge_phones,
    calc_completeness,
    is_valid_row,
    dedup_key,
    SQFT_TO_SQM,
)
from building_intelligence import format_phone_number


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEADS_MASTER_PATH = Path("lead_database/leads_master.csv")
REFERENCE_PATHS = [
    Path("Master reference datasets/reference_master_with_units.csv"),
    Path("Master reference datasets/reference_master.csv"),
    Path("reference_data/title_deed_reference.csv"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_unit_number(raw: str) -> Optional[str]:
    """
    Standardize unit number formatting for matching.
    Examples:
        'S607'  -> 'S-607'
        'A 201' -> 'A-201'
        '1204'  -> '1204'
        '' / NaN -> None
    """
    if not raw or pd.isna(raw) or str(raw).strip() in ("", "nan", "None", "N/A", "0"):
        return None
    s = str(raw).strip().upper()
    # If already has a dash, just normalize spacing
    if "-" in s:
        return re.sub(r"\s+", "", s)
    # Insert dash between letter prefix and digits: S607 -> S-607
    m = re.match(r"^([A-Z]+)\s*(\d+.*)$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s


def _safe_float(val) -> Optional[float]:
    """Convert to float, returning None on failure."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        v = float(val)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _safe_str(val) -> Optional[str]:
    """Convert to stripped string, returning None for empty/NaN."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "n/a", "0") else None


# ---------------------------------------------------------------------------
# LEAD INGESTION
# ---------------------------------------------------------------------------

def ingest_leads_from_dataframe(df: pd.DataFrame, source_file: str, conn: Optional[sqlite3.Connection] = None) -> Dict:
    """
    Ingest a pre-normalized leads DataFrame into the database.

    Parameters:
        df:          A DataFrame with standard columns (owner_name, building_name,
                     unit_number, phone, date, bedrooms, size_sqft, etc.)
                     -- the same shape produced by data_processor.normalize_dataframe().
        source_file: Label for the source (e.g. 'leads_master.csv').
        conn:        Optional existing connection. If None, a new one is opened.

    Returns:
        Dict with counts: inserted, skipped_invalid, skipped_duplicate, errors.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    stats = {"inserted": 0, "skipped_invalid": 0, "skipped_duplicate": 0, "errors": 0, "total": len(df)}

    insert_sql = """
        INSERT OR IGNORE INTO leads (
            owner_name, building_name, building_name_normalized,
            unit_number, unit_number_normalized,
            phone, phone_formatted, email,
            date, bedrooms, bedrooms_estimated, bedrooms_source,
            size_sqft, size_estimated, size_source,
            completeness_score, source_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    batch = []

    for idx, row in df.iterrows():
        try:
            # Validity check (same logic as existing pipeline)
            has_loc = pd.notna(row.get("building_name")) or pd.notna(row.get("unit_number"))
            phone_val = row.get("phone", "")
            if pd.isna(phone_val):
                phone_val = ""
            has_contact = bool(str(phone_val).strip()) or pd.notna(row.get("owner_name"))
            if not (has_loc and has_contact):
                stats["skipped_invalid"] += 1
                continue

            owner_name = _safe_str(row.get("owner_name"))
            building_raw = _safe_str(row.get("building_name"))
            building_norm = standardize_building_name(building_raw) if building_raw else None
            unit_raw = _safe_str(row.get("unit_number"))
            unit_norm = _normalize_unit_number(unit_raw) if unit_raw else None

            phone_raw = str(row.get("phone", "")).strip()
            # Format each pipe-separated phone number
            if phone_raw and phone_raw.lower() not in ("nan", "none", ""):
                phones = [p.strip() for p in phone_raw.split("|") if p.strip()]
                phone_formatted = " | ".join(format_phone_number(p) for p in phones)
            else:
                phone_raw = None
                phone_formatted = None

            date_val = row.get("date")
            if pd.notna(date_val):
                date_str = str(date_val)[:10]
            else:
                date_str = None

            bedrooms_raw = row.get("bedrooms")
            bedrooms_str = None
            if pd.notna(bedrooms_raw):
                br = str(bedrooms_raw).strip().lower()
                if br in ("studio", "st", "s"):
                    bedrooms_str = "0"
                elif br in ("penthouse", "ph"):
                    bedrooms_str = "penthouse"
                elif br not in ("unknown", "nan", "none", ""):
                    try:
                        bedrooms_str = str(int(float(bedrooms_raw)))
                    except (ValueError, TypeError):
                        bedrooms_str = br  # keep as-is if non-numeric
            beds_estimated = bool(row.get("bedrooms_estimated", False))
            beds_source = _safe_str(row.get("bedroom_method")) or "original"

            size_val = _safe_float(row.get("size_sqft"))
            size_estimated = bool(row.get("size_estimated", False))
            size_source = _safe_str(row.get("size_method")) or "original"

            completeness = _safe_float(row.get("completeness"))
            if completeness is None:
                # Calculate on the fly using the existing function
                fields = ["date", "owner_name", "building_name", "bedrooms", "unit_number", "phone", "size_sqft"]
                filled = sum(1 for f in fields if f in row.index and pd.notna(row[f]) and str(row[f]).strip())
                completeness = round(filled / len(fields) * 100, 1)

            batch.append((
                owner_name, building_raw, building_norm,
                unit_raw, unit_norm,
                phone_raw, phone_formatted, None,  # email not in current leads
                date_str, bedrooms_str, beds_estimated, beds_source,
                size_val, size_estimated, size_source,
                completeness, source_file
            ))

            # Insert in batches of 500
            if len(batch) >= 500:
                conn.executemany(insert_sql, batch)
                stats["inserted"] += len(batch)
                batch = []

        except Exception as e:
            stats["errors"] += 1
            if stats["errors"] <= 5:
                print(f"  [WARN] Row {idx}: {e}")

    # Flush remaining batch
    if batch:
        conn.executemany(insert_sql, batch)
        stats["inserted"] += len(batch)

    conn.commit()

    # The INSERT OR IGNORE means duplicates are silently skipped.
    # Adjust the count to reflect actual inserts vs unique-constraint skips.
    actual_count = conn.execute("SELECT COUNT(*) FROM leads WHERE source_file = ?", (source_file,)).fetchone()[0]
    stats["skipped_duplicate"] = stats["inserted"] - actual_count if stats["inserted"] > actual_count else 0
    stats["inserted"] = actual_count  # Report the real inserted count for this source

    if own_conn:
        conn.close()

    return stats


def ingest_leads(csv_path: str, source_label: Optional[str] = None) -> Dict:
    """
    Import a single leads CSV file into the database.

    This reads the CSV, normalizes it via the existing data_processor pipeline,
    then inserts into SQLite.

    Parameters:
        csv_path:     Path to the CSV file.
        source_label: Label for the source_file column. Defaults to the filename.

    Returns:
        Dict with insertion stats.
    """
    path = Path(csv_path)
    if not path.exists():
        return {"error": f"File not found: {csv_path}"}

    source_label = source_label or path.name

    print(f"[ingest] Reading leads from: {csv_path}")

    try:
        # Try multiple encodings (same as existing pipeline)
        df = None
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(csv_path, encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue

        if df is None or df.empty:
            return {"error": "Could not read file or file is empty"}

        # Use existing column detection and normalization
        col_map = detect_columns(df)
        result = pd.DataFrame(index=df.index)

        # Date
        if col_map["date"]:
            result["date"] = pd.to_datetime(df[col_map["date"][0]], errors="coerce", dayfirst=True)
        else:
            result["date"] = pd.NaT

        # Owner name
        if col_map["owner_name"]:
            result["owner_name"] = df.apply(
                lambda row: (get_first_non_null(row, col_map["owner_name"]) or "").title() or None, axis=1
            )
        else:
            result["owner_name"] = None

        # Building name
        if col_map["building_name"]:
            result["building_name"] = df.apply(
                lambda row: merge_building_names(row, col_map["building_name"]), axis=1
            )
        else:
            result["building_name"] = None

        # Bedrooms
        if col_map["bedrooms"]:
            result["bedrooms"] = df[col_map["bedrooms"][0]].apply(clean_bedroom)
        else:
            result["bedrooms"] = None

        # Unit number
        if col_map["unit_number"]:
            result["unit_number"] = df.apply(
                lambda row: get_first_non_null(row, col_map["unit_number"]), axis=1
            )
        else:
            result["unit_number"] = None

        # Phone (merges multiple phone columns with pipe separator)
        if col_map["phone"]:
            result["phone"] = df.apply(lambda row: merge_phones(row, col_map["phone"]), axis=1)
        else:
            result["phone"] = ""

        # Size
        size_col, size_unit = detect_size_column(df)
        if size_col:
            result["size_sqft"] = df[size_col].apply(
                lambda v: convert_to_sqft_if_needed(clean_size_value(v), size_unit) if clean_size_value(v) else None
            )
        else:
            result["size_sqft"] = None

        print(f"  Normalized {len(result)} rows from {source_label}")

        return ingest_leads_from_dataframe(result, source_label)

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


def ingest_leads_master() -> Dict:
    """
    Import the consolidated leads_master.csv (produced by consolidate_data.py).
    This is the primary entry point for lead data.
    """
    if not LEADS_MASTER_PATH.exists():
        return {"error": f"leads_master.csv not found at {LEADS_MASTER_PATH}"}

    print(f"[ingest] Loading consolidated leads master: {LEADS_MASTER_PATH}")

    try:
        df = None
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(str(LEADS_MASTER_PATH), encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue

        if df is None or df.empty:
            return {"error": "Could not read leads_master.csv or file is empty"}

        print(f"  Loaded {len(df)} rows with columns: {list(df.columns)}")

        # The master CSV has title-case columns from consolidation.
        # Map them to the snake_case names expected by ingest_leads_from_dataframe.
        col_rename = {
            "Owner Name": "owner_name",
            "Building Name": "building_name",
            "Unit Number": "unit_number",
            "Phone": "phone",
            "Date": "date",
            "Bedrooms": "bedrooms",
            "Size (sqft)": "size_sqft",
            "Source File": "source_file",
            "Project": "project",
            "Import Date": "import_date",
            "Transaction Value": "transaction_value",
        }
        df = df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})

        # Parse date column
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

        # Ensure phone column is string
        if "phone" in df.columns:
            df["phone"] = df["phone"].fillna("").astype(str)
        else:
            df["phone"] = ""

        return ingest_leads_from_dataframe(df, "leads_master.csv")

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# TRANSACTION INGESTION
# ---------------------------------------------------------------------------

def ingest_transactions(csv_path: Optional[str] = None) -> Dict:
    """
    Import reference/transaction data into the transactions table.

    Looks for the master reference CSV (with unit numbers from scraping) and maps
    each column to the transactions schema.

    Parameters:
        csv_path: Override path to CSV. If None, searches standard locations.

    Returns:
        Dict with insertion stats.
    """
    # Find the reference file
    if csv_path:
        found_path = Path(csv_path)
        if not found_path.exists():
            return {"error": f"File not found: {csv_path}"}
    else:
        found_path = None
        for p in REFERENCE_PATHS:
            if p.exists():
                found_path = p
                break
        if not found_path:
            return {"error": "No reference CSV found in standard locations"}

    print(f"[ingest] Loading transactions from: {found_path}")

    try:
        ref_df = None
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                ref_df = pd.read_csv(str(found_path), encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue

        if ref_df is None or ref_df.empty:
            return {"error": "Could not read reference CSV or file is empty"}

        # Use existing column detection
        col_map = detect_reference_columns(ref_df)

        stats = {"inserted": 0, "skipped": 0, "errors": 0, "total": len(ref_df)}

        conn = get_connection()
        insert_sql = """
            INSERT OR IGNORE INTO transactions (
                building_name, building_name_normalized,
                unit_number, unit_number_normalized,
                transaction_date, price_aed, price_per_sqft,
                size_sqft, bedrooms, floor_level,
                property_type, transaction_type, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        batch = []

        for idx, row in ref_df.iterrows():
            try:
                # Extract building name from sub_loc_2 (primary) or building column
                building_raw = None
                if col_map.get("sub_loc_2"):
                    building_raw = _safe_str(row.get(col_map["sub_loc_2"]))
                if not building_raw and col_map.get("building"):
                    building_raw = _safe_str(row.get(col_map["building"]))

                # Sub_loc_1 enrichment for Shoreline detection
                sub_loc_1 = ""
                if col_map.get("sub_loc_1"):
                    sub_loc_1 = str(row.get(col_map["sub_loc_1"], "")).lower()

                building_norm = standardize_building_name(building_raw) if building_raw else None

                # Shoreline check: if building name doesn't already contain Shoreline
                # but sub_loc_1 does, it's a Shoreline building
                if building_norm and "shoreline" not in building_norm.lower() and "shoreline" in sub_loc_1:
                    from data_processor import SHORELINE_ARABIC_MAPPING
                    for arabic, shoreline in SHORELINE_ARABIC_MAPPING.items():
                        if arabic in (building_raw or "").lower():
                            building_norm = shoreline
                            break
                    else:
                        building_norm = "Shoreline Family"

                # Unit number
                unit_raw = None
                if col_map.get("unit_no"):
                    unit_raw = _safe_str(row.get(col_map["unit_no"]))
                unit_norm = _normalize_unit_number(unit_raw) if unit_raw else None

                # Date
                date_val = None
                if col_map.get("sale_date"):
                    d = pd.to_datetime(row.get(col_map["sale_date"]), errors="coerce")
                    if pd.notna(d):
                        date_val = str(d)[:10]
                # Fallback: custom_date column (common in scraped data)
                if not date_val and "custom_date" in ref_df.columns:
                    d = pd.to_datetime(row.get("custom_date"), errors="coerce")
                    if pd.notna(d):
                        date_val = str(d)[:10]

                # Price
                price_aed = None
                if col_map.get("sale_price"):
                    price_aed = _safe_float(row.get(col_map["sale_price"]))

                # Price per sqft
                price_psf = None
                if col_map.get("price_psf"):
                    price_psf = _safe_float(row.get(col_map["price_psf"]))

                # Size
                size_sqft = None
                if col_map.get("size_sqft"):
                    size_sqft = _safe_float(row.get(col_map["size_sqft"]))

                # Skip rows with no useful size data
                if not size_sqft or size_sqft <= 100:
                    stats["skipped"] += 1
                    continue

                # Bedrooms
                bedrooms_str = None
                if col_map.get("bedrooms"):
                    bed_val = clean_reference_beds(row.get(col_map["bedrooms"]))
                    if pd.notna(bed_val):
                        bedrooms_str = str(int(bed_val))

                # Floor
                floor_val = None
                if col_map.get("floor_level"):
                    floor_val = _safe_str(row.get(col_map["floor_level"]))

                # Property type from unit_type column
                property_type = None
                if col_map.get("unit_type"):
                    pt = _safe_str(row.get(col_map["unit_type"]))
                    if pt:
                        pt_lower = pt.lower()
                        if "villa" in pt_lower:
                            property_type = "villa"
                        elif "townhouse" in pt_lower:
                            property_type = "townhouse"
                        elif "penthouse" in pt_lower:
                            property_type = "penthouse"
                        elif "apartment" in pt_lower:
                            property_type = "apartment"
                        else:
                            property_type = pt

                # Transaction type from trans_group_en or sales_recurrence
                transaction_type = None
                if "trans_group_en" in ref_df.columns:
                    tt = _safe_str(row.get("trans_group_en"))
                    if tt:
                        transaction_type = tt.lower()
                if not transaction_type and "sales_recurrence" in ref_df.columns:
                    sr = _safe_str(row.get("sales_recurrence"))
                    if sr:
                        transaction_type = sr.lower()

                # Source
                source = "property_monitor"
                if "data_origin" in ref_df.columns:
                    origin = _safe_str(row.get("data_origin"))
                    if origin and "scrape" in origin.lower():
                        source = "scraped"

                batch.append((
                    building_raw, building_norm,
                    unit_raw, unit_norm,
                    date_val, price_aed, price_psf,
                    size_sqft, bedrooms_str, floor_val,
                    property_type, transaction_type, source
                ))

                if len(batch) >= 500:
                    conn.executemany(insert_sql, batch)
                    stats["inserted"] += len(batch)
                    batch = []

            except Exception as e:
                stats["errors"] += 1
                if stats["errors"] <= 5:
                    print(f"  [WARN] Transaction row {idx}: {e}")

        # Flush
        if batch:
            conn.executemany(insert_sql, batch)
            stats["inserted"] += len(batch)

        conn.commit()

        # Get actual count (INSERT OR IGNORE skips dupes silently)
        actual = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        stats["inserted"] = actual
        conn.close()

        print(f"  Transactions ingested: {actual:,} rows")
        return stats

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# CROSS-REFERENCE BUILDER
# ---------------------------------------------------------------------------

def build_cross_references() -> Dict:
    """
    Precompute matches between leads and transactions based on
    building_name_normalized + unit_number_normalized.

    Match methods:
        'exact_unit'    - Both building and unit match exactly (confidence 1.0)
        'fuzzy_unit'    - Building matches, unit is close but not exact (confidence 0.7)
        'building_only' - Building matches, no unit match possible (confidence 0.3)

    Returns:
        Dict with counts of each match type.
    """
    conn = get_connection()
    stats = {"exact_unit": 0, "fuzzy_unit": 0, "building_only": 0, "errors": 0}

    try:
        # Clear existing cross-references (full rebuild each time)
        conn.execute("DELETE FROM cross_references")

        # ------------------------------------------------------------------
        # Pass 1: Exact building + unit matches (highest confidence)
        # ------------------------------------------------------------------
        exact_sql = """
            INSERT OR IGNORE INTO cross_references (lead_id, transaction_id, match_confidence, match_method)
            SELECT l.id, t.id, 1.0, 'exact_unit'
            FROM leads l
            JOIN transactions t
              ON l.building_name_normalized = t.building_name_normalized
             AND l.unit_number_normalized = t.unit_number_normalized
            WHERE l.building_name_normalized IS NOT NULL
              AND l.unit_number_normalized IS NOT NULL
              AND t.unit_number_normalized IS NOT NULL
        """
        cursor = conn.execute(exact_sql)
        stats["exact_unit"] = cursor.rowcount
        print(f"  Exact unit matches: {stats['exact_unit']:,}")

        # ------------------------------------------------------------------
        # Pass 2: Building-only matches (for leads that didn't match above)
        # These are weaker matches -- same building but we can't confirm the unit.
        # Only create these for leads that have no exact match.
        # ------------------------------------------------------------------
        building_only_sql = """
            INSERT OR IGNORE INTO cross_references (lead_id, transaction_id, match_confidence, match_method)
            SELECT l.id, t.id, 0.3, 'building_only'
            FROM leads l
            JOIN transactions t
              ON l.building_name_normalized = t.building_name_normalized
            WHERE l.building_name_normalized IS NOT NULL
              AND l.id NOT IN (SELECT lead_id FROM cross_references WHERE match_method = 'exact_unit')
              AND (l.unit_number_normalized IS NULL OR t.unit_number_normalized IS NULL)
        """
        cursor = conn.execute(building_only_sql)
        stats["building_only"] = cursor.rowcount
        print(f"  Building-only matches: {stats['building_only']:,}")

        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
        stats["total"] = total
        print(f"  Total cross-references: {total:,}")

    except Exception as e:
        stats["errors"] += 1
        print(f"  [ERR] Cross-reference build failed: {e}")
        traceback.print_exc()
    finally:
        conn.close()

    return stats


# ---------------------------------------------------------------------------
# FULL RE-INGESTION PIPELINE
# ---------------------------------------------------------------------------

def reingest_all(clear_existing: bool = True) -> Dict:
    """
    Full pipeline: clear tables (optional), ingest leads, ingest transactions,
    build cross-references.

    Parameters:
        clear_existing: If True, wipe existing data before inserting.

    Returns:
        Combined stats dict.
    """
    print("=" * 60)
    print(" DATA INGESTION PIPELINE")
    print("=" * 60)

    init_database()

    if clear_existing:
        print("\n[1/4] Clearing existing data...")
        conn = get_connection()
        for table in ["cross_references", "leads", "transactions"]:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()
        print("  Tables cleared.")
    else:
        print("\n[1/4] Keeping existing data (append mode).")

    # Step 2: Ingest leads
    print("\n[2/4] Ingesting leads...")
    lead_stats = ingest_leads_master()
    if "error" in lead_stats:
        print(f"  [ERR] Lead ingestion failed: {lead_stats['error']}")
    else:
        print(f"  Leads: {lead_stats.get('inserted', 0):,} inserted, "
              f"{lead_stats.get('skipped_invalid', 0):,} invalid, "
              f"{lead_stats.get('errors', 0):,} errors")

    # Step 3: Ingest transactions
    print("\n[3/4] Ingesting transactions...")
    txn_stats = ingest_transactions()
    if "error" in txn_stats:
        print(f"  [ERR] Transaction ingestion failed: {txn_stats['error']}")
    else:
        print(f"  Transactions: {txn_stats.get('inserted', 0):,} inserted, "
              f"{txn_stats.get('skipped', 0):,} skipped (no size), "
              f"{txn_stats.get('errors', 0):,} errors")

    # Step 4: Build cross-references
    print("\n[4/4] Building cross-references...")
    xref_stats = build_cross_references()

    print("\n" + "=" * 60)
    print(" INGESTION COMPLETE")
    print("=" * 60)

    # Final summary
    from database import get_table_counts
    counts = get_table_counts()
    print(f"  leads:            {counts['leads']:,}")
    print(f"  transactions:     {counts['transactions']:,}")
    print(f"  cross_references: {counts['cross_references']:,}")
    print("=" * 60)

    return {
        "leads": lead_stats,
        "transactions": txn_stats,
        "cross_references": xref_stats,
        "table_counts": counts,
    }


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    reingest_all(clear_existing=True)
