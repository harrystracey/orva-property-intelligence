"""
Listing Matcher — core matching engine.

Matches portal listing dicts (from Bayut / PropertyFinder / manual entry)
against the consolidated lead database.

Three-pass strategy:
  1. Exact unit number match          → confidence 0.95
  2. Exact size match (±1 sqft)       → confidence 0.90 (single) / 0.70 (multi)
  3. Beds + size range (±5%)          → confidence 0.60 (≤3 hits) / 0.40 (many)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    from fuzzywuzzy import fuzz
except ImportError:

    class fuzz:  # type: ignore[no-redef]
        @staticmethod
        def partial_ratio(a: str, b: str) -> int:
            a, b = str(a).lower(), str(b).lower()
            return 90 if (a in b or b in a) else 50

        @staticmethod
        def token_sort_ratio(a: str, b: str) -> int:
            return fuzz.partial_ratio(a, b)


try:
    from building_intelligence import (
        SHORELINE_TOWER_MAPPING,
        BUILDING_ALIASES,
        resolve_building_name,
        normalize_unit_number,
    )
except ImportError:
    SHORELINE_TOWER_MAPPING: dict = {}
    BUILDING_ALIASES: dict = {}

    def resolve_building_name(s: str):  # type: ignore[misc]
        return (None, None, None)

    def normalize_unit_number(s: str) -> str:  # type: ignore[misc]
        return str(s).strip().upper()


# ── Constants ─────────────────────────────────────────────────────────────────

_BASE = Path(__file__).resolve().parent.parent / "lead_database"
LEADS_PARQUET = _BASE / "leads_master.parquet"
LEADS_CSV = _BASE / "leads_master.csv"
SQM_TO_SQFT = 10.7639

# Portal-facing name → list of possible names in the leads DB
PORTAL_TO_DB_ALIASES: dict[str, list[str]] = {
    "Shoreline 1": ["Al Ramth", "Al Basri"],
    "Shoreline 2": ["Al Nabat", "Al Sahab"],
    "Shoreline 3": ["Al Murjan", "Al Anbar"],
    "Shoreline 4": ["Al Mashraba", "Al Dawaar"],
    "Shoreline 5": ["Al Khayali"],
    "Shoreline 6": ["Al Malak", "Al Msalli"],
    "Shoreline 7": ["Al Habool"],
    "Shoreline 8": ["Al Ghaf", "Al Sultana"],
    "Shoreline 9": ["Al Masalli", "Al Thamam"],
    "Shoreline 10": ["Al Hallawi", "Al Das"],
    "Shoreline 11": ["Al Anbara", "Al Khushkar"],
    "Shoreline 12": ["Jash Falqa", "Al Janahi"],
    "Shoreline 13": ["Al Shamsi", "Al Majara"],
    "Shoreline 14": ["Jash Hamad", "Al Fahad"],
    "Shoreline 15": ["Al Fattan"],
    "Shoreline 16": ["Al Shirawi"],
    "Shoreline 18": ["Al Hamri"],
    "Shoreline 19": ["Al Hatmi"],
    "Shoreline 20": ["Al Seef"],
    # Reverse: Arabic → Shoreline number aliases
    "Al Ramth": ["Shoreline 1"],
    "Al Nabat": ["Shoreline 2"],
    "Al Murjan": ["Shoreline 3"],
    "Al Mashraba": ["Shoreline 4"],
    "Al Khayali": ["Shoreline 5"],
    "Al Malak": ["Shoreline 6"],
    "Al Habool": ["Shoreline 7"],
    "Al Ghaf": ["Shoreline 8"],
    "Al Masalli": ["Shoreline 9"],
    "Al Hallawi": ["Shoreline 10"],
    "Al Anbara": ["Shoreline 11"],
    "Jash Falqa": ["Shoreline 12"],
    # Portal trade names → DLD/DB names
    "Tiara Ruby": ["TIARA RESIDENTIAL TOWER - RUBY", "Tiara Residences", "TIARA RESIDENCES"],
    "Tiara Emerald": ["TIARA RESIDENTIAL TOWER - EMERALD", "Tiara Residences", "TIARA RESIDENCES"],
    "Tiara Diamond": ["TIARA RESIDENTIAL TOWER - DIAMOND", "Tiara Residences", "TIARA RESIDENCES"],
    "Tiara Sapphire": ["TIARA RESIDENTIAL TOWER - SAPPHIRE", "Tiara Residences", "TIARA RESIDENCES"],
    "Tiara Aquamarine": ["TIARA AQUAMARINE TOWER", "Tiara Residences", "TIARA RESIDENCES"],
    "Oceana Baltic": ["OCEANA HOTEL AND APARTMENTS", "Oceana", "OCEANA RESIDENCES"],
    "The 8": ["THE 8"],
    "Palm Beach Tower 1": ["PALM BEACH TOWERS -1", "PALM BEACH TOWERS- 1", "Palm Beach Towers"],
    "Palm Beach Tower 2": ["PALM BEACH TOWERS -2", "PALM BEACH TOWERS- 2", "Palm Beach Towers"],
    "Palm Beach Tower 3": ["PALM BEACH TOWERS -3", "PALM BEACH TOWERS- 3", "Palm Beach Towers"],
    "Five Palm": ["FIVE AT PALM JUMEIRAH DUBAI", "Five Palm Jumeirah"],
    "Seven Palm": ["SEVEN HOTEL & APARTMENTS THE PALM", "Seven Palms"],
    "Royal Atlantis": ["THE ROYAL ATLANTIS RESORT & RESIDENCES", "Royal Atlantis Residences"],
    "Azure": ["AZURE RESIDENCES", "Azure Residences"],
    "Azure Residences": ["AZURE RESIDENCES", "Azure"],
    "Marina Residences 1": ["Marina Apartments 1", "Marina Residences"],
    "Marina Residences 2": ["Marina Apartments 2", "Marina Residences"],
    "Marina Residences 3": ["Marina Apartments 3", "Marina Residences"],
    "Marina Residences 4": ["Marina Apartments 4", "Marina Residences"],
    "Marina Residences 5": ["Marina Apartments 5", "Marina Residences"],
    "Marina Residences 6": ["Marina Apartments 6", "Marina Residences"],
    "Ellington Beach House": ["Ellington Beach House", "ELLINGTON BEACH HOUSE", "EBH"],
    "The Trunk": ["The Trunk-Shoreline Apartments", "Trunk Shoreline Apartments"],
    "Golden Mile 1": ["GOLDEN MILE 1"],
    "Golden Mile 2": ["GOLDEN MILE 2"],
    "Golden Mile 3": ["GOLDEN MILE 3"],
    "Fairmont North": ["FAIRMONT PALM RESIDENCE NORTH", "The Fairmont Palm Residences"],
    "Fairmont South": ["FAIRMONT PALM RESIDENCE SOUTH", "The Fairmont Palm Residences"],
    "Kempinski": ["KEMPINSKI PALM RESIDENCE"],
    "Serenia": ["SERENIA RESIDENCES THE PALM"],
    "Balqis": ["BALQIS RESIDENCE"],
    "Anantara North": ["ANANTARA RESIDENCES NORTH"],
    "Anantara South": ["ANANTARA RESIDENCES SOUTH"],
    "Viceroy": ["VICEROY PALM JUMEIRAH"],
}

# Pre-compute lowercased alias index for O(1) lookup instead of iterating the dict
_ALIAS_INDEX: dict[str, set[str]] = {}
for _portal_key, _db_names in PORTAL_TO_DB_ALIASES.items():
    _k = _portal_key.lower()
    _ALIAS_INDEX.setdefault(_k, set()).update(_db_names)
    for _db_name in _db_names:
        _ALIAS_INDEX.setdefault(_db_name.lower(), set()).update(_db_names)
        _ALIAS_INDEX[_db_name.lower()].add(_portal_key)

_PHONE_RE = re.compile(r"[^0-9]")
_BEDS_RE = re.compile(r"(\d+)")


# ── Phone Cleaning ────────────────────────────────────────────────────────────

def clean_phone(raw) -> Optional[str]:
    """Normalise any phone string/number to all-digit UAE format."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "n/a"):
        return None
    if "E+" in s.upper():
        try:
            s = str(int(float(s)))
        except Exception:
            return None
    digits = _PHONE_RE.sub("", s)
    if not digits:
        return None
    if len(digits) == 9 and digits[0] == "5":
        digits = "971" + digits
    elif len(digits) == 10 and digits[:2] == "05":
        digits = "971" + digits[1:]
    elif len(digits) == 10 and digits[0] == "5":
        digits = "971" + digits
    if len(digits) >= 11 and digits[:3] == "971":
        return digits
    return digits if len(digits) >= 9 else None


def _clean_phone_vec(series: pd.Series) -> pd.Series:
    """Vectorised phone cleaning — 10x faster than .apply(clean_phone)."""
    s = series.astype(str).str.strip()
    s = s.replace({"nan": pd.NA, "none": pd.NA, "None": pd.NA, "n/a": pd.NA, "N/A": pd.NA, "": pd.NA})
    s = s.str.replace(r"[^0-9]", "", regex=True)
    # Prefix with country code
    is_9_digit_5 = (s.str.len() == 9) & s.str.startswith("5")
    is_10_digit_05 = (s.str.len() == 10) & s.str.startswith("05")
    s = s.where(~is_9_digit_5, "971" + s)
    s = s.where(~is_10_digit_05, "971" + s.str[1:])
    # Only keep numbers with 9+ digits
    s = s.where(s.str.len() >= 9, pd.NA)
    return s


def mask_phone(phone: str) -> str:
    """971503465502 → +971 50 *** 5502"""
    if not phone:
        return ""
    d = _PHONE_RE.sub("", str(phone))
    if len(d) == 12 and d[:3] == "971":
        return f"+971 {d[3:5]} *** {d[8:]}"
    if len(d) >= 8:
        return d[:4] + "***" + d[-4:]
    return "****"


# ── Bedroom Normalisation ─────────────────────────────────────────────────────

def normalize_beds(raw) -> Optional[str]:
    """Normalise bed count to: 'Studio', '1', '2', '3', 'PH', or None."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    s = str(raw).strip().upper()
    if not s or s in ("NAN", "NONE", "N/A"):
        return None
    if s in ("STUDIO", "ST", "0", "S", "0 BR", "0BR", "STUDIO APARTMENT"):
        return "Studio"
    m = _BEDS_RE.search(s)
    if m:
        n = int(m.group(1))
        return "Studio" if n == 0 else str(n)
    if "PH" in s or "PENTHOUSE" in s:
        return "PH"
    return None


def _normalize_beds_vec(series: pd.Series) -> pd.Series:
    """Vectorised bed normalisation."""
    s = series.astype(str).str.strip().str.upper()
    s = s.replace({"NAN": pd.NA, "NONE": pd.NA, "N/A": pd.NA, "": pd.NA})
    result = pd.Series(pd.NA, index=s.index, dtype="object")
    # Studio variants
    studio_mask = s.isin({"STUDIO", "ST", "0", "S", "0 BR", "0BR", "STUDIO APARTMENT"})
    result = result.where(~studio_mask, "Studio")
    # Penthouse
    ph_mask = s.str.contains("PH|PENTHOUSE", na=False, regex=True) & ~studio_mask
    result = result.where(~ph_mask, "PH")
    # Extract leading digit for "2 B/R", "3", etc.
    nums = s.str.extract(r"(\d+)", expand=False)
    nums = nums.where(nums != "0", "Studio")
    still_empty = result.isna() & nums.notna()
    result = result.where(~still_empty, nums)
    return result


# ── Building Resolution ───────────────────────────────────────────────────────

def _shoreline_db_names(tower_num: int) -> list[str]:
    """All DB-side names for a given Shoreline tower number."""
    names = [t for t, (n, _) in SHORELINE_TOWER_MAPPING.items() if n == tower_num]
    names += ["The Trunk-Shoreline Apartments", "TRUNK SHORELINE APARTMENTS",
              "Trunk Shoreline Apartments"]
    return names


def resolve_building(building_input: str, db_building_set: set[str]) -> list[str]:
    """
    Return list of building name strings to search in leads_df.

    Uses a pre-computed set of building names instead of scanning the DataFrame
    on every call.  Search order:
      1. Exact case-insensitive match
      2. PORTAL_TO_DB_ALIASES (via _ALIAS_INDEX O(1) lookup)
      3. Shoreline number regex
      4. Arabic tower name
      5. building_intelligence canonical resolver
      6. Fuzzy fallback (≥75 score)
    """
    if not building_input:
        return []

    inp = building_input.strip()
    inp_lower = inp.lower()
    candidates: set[str] = set()

    # Pre-compute a lowered→original map once (cached externally in practice)
    db_lower_map: dict[str, str] = {b.lower(): b for b in db_building_set}

    # 1. Exact match
    if inp_lower in db_lower_map:
        candidates.add(db_lower_map[inp_lower])

    # 2. Alias index lookup — O(1) instead of iterating all aliases
    if inp_lower in _ALIAS_INDEX:
        candidates.update(_ALIAS_INDEX[inp_lower])

    # 3. "Shoreline N" or "SN" pattern
    m = re.search(r"(?:shoreline|s)\s*(\d+)", inp_lower)
    if m:
        candidates.update(_shoreline_db_names(int(m.group(1))))

    # 4. Arabic Shoreline tower name
    for tower, (num, _) in SHORELINE_TOWER_MAPPING.items():
        if tower.lower() == inp_lower or tower.lower() in inp_lower:
            candidates.update(_shoreline_db_names(num))
            break

    # 5. building_intelligence canonical resolver
    canonical, _, _ = resolve_building_name(inp)
    if canonical:
        candidates.add(canonical)
        candidates.update(BUILDING_ALIASES.get(canonical, []))

    # 6. Fuzzy fallback
    if not candidates:
        for b in db_building_set:
            if fuzz.partial_ratio(inp_lower, b.lower()) >= 75:
                candidates.add(b)

    # Only keep names actually in DB
    valid = [c for c in candidates if c in db_building_set]

    # Final fallback: token-sort fuzzy
    if not valid:
        scored = sorted(
            ((fuzz.token_sort_ratio(inp_lower, b.lower()), b) for b in db_building_set),
            reverse=True,
        )
        valid = [b for score, b in scored[:5] if score >= 65]

    return valid


# ── Leads DataFrame Loading ───────────────────────────────────────────────────

def load_leads_df() -> pd.DataFrame:
    """Load lead database (Parquet preferred, CSV fallback) with normalised columns."""
    if LEADS_PARQUET.exists():
        df = pd.read_parquet(LEADS_PARQUET)
    elif LEADS_CSV.exists():
        df = pd.read_csv(LEADS_CSV, low_memory=False)
    else:
        return pd.DataFrame()

    return _add_norm_columns(df)


def _add_norm_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add _size_sqft, _phone_clean, _beds_norm, _building_set helper columns/attrs."""
    if "_phone_clean" in df.columns:
        return df

    # Size: vectorised numeric parse
    for col in ("Size (sqft)", "Size", "Actual Size", "BUA"):
        if col in df.columns:
            df["_size_sqft"] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.strip(),
                errors="coerce",
            )
            break
    else:
        df["_size_sqft"] = np.nan

    # Phone: vectorised
    phone_col = next((c for c in ("Phone", "Mobile", "Phone 1") if c in df.columns), None)
    df["_phone_clean"] = _clean_phone_vec(df[phone_col]) if phone_col else pd.NA

    # Beds: vectorised
    bed_col = next((c for c in ("Bedrooms", "beds", "Beds") if c in df.columns), None)
    df["_beds_norm"] = _normalize_beds_vec(df[bed_col]) if bed_col else pd.NA

    # Strip whitespace from key columns
    for col in ("Building Name", "Unit Number"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


# ── Core Match Function ───────────────────────────────────────────────────────

def match_listing(listing: dict, leads_df: pd.DataFrame) -> list[dict]:
    """
    Match a portal listing dict against the leads DataFrame.

    listing keys:
        building_name  (required)
        unit_number    (optional, str)
        size_sqft      (optional, float)
        bedrooms       (optional, str/int)
        listing_url    (optional, str — pass-through)

    Returns list of match dicts sorted by confidence (desc), max 10.
    """
    if leads_df is None or leads_df.empty:
        return []

    leads_df = _add_norm_columns(leads_df)

    # Build the building name set once
    db_buildings = set(leads_df["Building Name"].dropna().unique())

    # Step 1: Resolve building
    building_names = resolve_building(listing.get("building_name", ""), db_buildings)
    if not building_names:
        return []

    filtered = leads_df[leads_df["Building Name"].isin(building_names)]
    if filtered.empty:
        return []

    def _val(v, default=""):
        """Safely extract a value, converting pd.NA / NaN to default."""
        if v is pd.NA or (isinstance(v, float) and np.isnan(v)):
            return default
        return v if v else default

    def _to_result(row: pd.Series, confidence: float, match_type: str) -> dict:
        phone = _val(row.get("_phone_clean")) or _val(row.get("Phone"))
        return {
            "building": _val(row.get("Building Name")),
            "unit": _val(row.get("Unit Number")),
            "size_sqft": row.get("_size_sqft"),
            "beds": _val(row.get("_beds_norm")) or _val(row.get("Bedrooms")),
            "owner_name": _val(row.get("Owner Name")),
            "phone": str(phone) if phone else "",
            "phone_display": mask_phone(str(phone)) if phone else "",
            "email": _val(row.get("Email", row.get("Email Address", ""))),
            "source_file": _val(row.get("Source File")),
            "transaction_date": str(_val(row.get("Date"))),
            "transaction_value": _val(row.get("Transaction Value")),
            "land_number": _val(row.get("LandNumber", row.get("Land Number", ""))),
            "confidence": confidence,
            "match_type": match_type,
        }

    results: list[dict] = []

    # Pass 1: Exact unit number
    unit_input = str(listing.get("unit_number") or "").strip().upper()
    if unit_input and unit_input not in ("", "NONE", "NAN"):
        unit_norm = normalize_unit_number(unit_input)
        db_units = filtered["Unit Number"].str.upper()
        exact = filtered[db_units.isin({unit_input, unit_norm})]
        for _, row in exact.iterrows():
            results.append(_to_result(row, 0.95, "exact_unit"))
        if results:
            return results

    # Pass 2: Exact size ±1 sqft
    size_input = listing.get("size_sqft")
    if size_input is not None and not (isinstance(size_input, float) and np.isnan(size_input)):
        size_float = float(size_input)
        adj = filtered["_size_sqft"].copy()
        adj = adj.where(adj >= 200, adj * SQM_TO_SQFT)  # sqm→sqft for small values
        size_mask = (adj >= size_float - 1.0) & (adj <= size_float + 1.0)
        size_matches = filtered[size_mask]
        n = len(size_matches)
        if n > 0:
            for _, row in size_matches.iterrows():
                results.append(_to_result(row, 0.90 if n == 1 else 0.70, "exact_size"))
            return _dedup_sort(results)

    # Pass 3: Beds + size range ±5%
    if size_input is not None and not (isinstance(size_input, float) and np.isnan(size_input)):
        size_float = float(size_input)
        tolerance = size_float * 0.05
        adj = filtered["_size_sqft"].copy()
        adj = adj.where(adj >= 200, adj * SQM_TO_SQFT)
        size_mask = (adj >= size_float - tolerance) & (adj <= size_float + tolerance)
        beds_norm = normalize_beds(listing.get("bedrooms"))
        if beds_norm:
            combo = filtered[size_mask & (filtered["_beds_norm"] == beds_norm)]
        else:
            combo = filtered[size_mask]
        n = len(combo)
        for _, row in combo.iterrows():
            results.append(_to_result(row, 0.60 if n <= 3 else 0.40, "beds_range"))

    return _dedup_sort(results)


def _dedup_sort(results: list[dict]) -> list[dict]:
    """Deduplicate by (building, unit), sort by confidence desc, cap at 10."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in sorted(results, key=lambda x: x["confidence"], reverse=True):
        key = (r["building"], r["unit"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out[:10]


# ── Coverage Analysis ─────────────────────────────────────────────────────────

def analyze_coverage(leads_df: pd.DataFrame) -> dict:
    """Return coverage statistics for the lead database."""
    if leads_df is None or leads_df.empty:
        return {}

    leads_df = _add_norm_columns(leads_df)
    grp_cols = ["Building Name", "Unit Number"]
    grp = leads_df.groupby(grp_cols)
    total_units = grp.ngroups

    has_phone = leads_df["_phone_clean"].notna() & (leads_df["_phone_clean"] != "")
    with_phone = leads_df[has_phone].groupby(grp_cols).ngroups
    with_size = leads_df[leads_df["_size_sqft"].notna()].groupby(grp_cols).ngroups

    building_stats = (
        leads_df.groupby("Building Name")
        .agg(units=("Unit Number", "nunique"), records=("Unit Number", "count"))
        .sort_values("units", ascending=False)
    )

    return {
        "total_units": total_units,
        "with_phone": with_phone,
        "phone_pct": round(with_phone / total_units * 100, 1) if total_units else 0,
        "with_size": with_size,
        "size_pct": round(with_size / total_units * 100, 1) if total_units else 0,
        "building_stats": building_stats.head(30),
    }


# ── AI Tool Adapter ───────────────────────────────────────────────────────────

def match_listing_tool(
    building: str,
    size_sqft: Optional[float] = None,
    bedrooms: Optional[str] = None,
    unit_number: Optional[str] = None,
    leads_df: Optional[pd.DataFrame] = None,
) -> str:
    """Adapter for the Claude AI assistant tool."""
    if leads_df is None or leads_df.empty:
        try:
            leads_df = load_leads_df()
        except Exception:
            return "Lead database not available."

    listing = {
        "building_name": building,
        "size_sqft": size_sqft,
        "bedrooms": bedrooms,
        "unit_number": unit_number,
    }
    matches = match_listing(listing, leads_df)

    if not matches:
        return (
            f"No owner found for '{building}' listing. "
            "Building may not be in the database, or the size/unit doesn't match any registered units."
        )

    lines = []
    for m in matches[:5]:
        emoji = "✅" if m["confidence"] >= 0.9 else "⚠️" if m["confidence"] >= 0.6 else "❓"
        phone_str = m["phone_display"] or "NOT IN DATABASE"
        lines.append(
            f"{emoji} Confidence: {m['confidence'] * 100:.0f}% ({m['match_type']})\n"
            f"   Unit: {m['unit']} | {m['building']}\n"
            f"   Owner: {m['owner_name'] or 'Unknown'}\n"
            f"   Phone: {phone_str}\n"
            f"   Size: {m['size_sqft']:.0f} sqft\n"
            f"   Beds: {m['beds'] or '?'}\n"
            f"   Last Transaction: {m['transaction_date'] or 'Unknown'}\n"
            f"   Source: {m['source_file']}"
        )
    return "\n\n".join(lines)
