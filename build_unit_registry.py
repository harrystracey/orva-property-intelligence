"""
Unit Registry Builder
Cross-reference leads, sales, rental, PropertyMonitor, and Bayut listings data
to create master unit registry.

Reads from:
- lead_database/leads_master.csv                          (78,556+ leads)
- Master reference datasets/reference_master_with_units.csv (18,250+ sales)
- scraped_data/palm_jumeirah_rentals.csv                  (rentals)
- scraped_data/unit_numbers_palm_jumeirah.csv             (PropertyMonitor DLD transactions)
- data/bayut_palm_listings.csv                            (Bayut listings — building-level)
- scraped_data/propertyfinder_scraped_leads.csv           (PF scraper — DLD permit data with unit numbers)

Outputs:
- data/unit_registry.csv (master registry with confirmed unit types)
"""

import pandas as pd
import re
from pathlib import Path
from collections import Counter
from data_processor import standardize_building_name

# Paths
LEADS_PATH   = Path("lead_database/leads_master.csv")
SALES_PATH   = Path("Master reference datasets/reference_master_with_units.csv")
RENTALS_PATH = Path("scraped_data/palm_jumeirah_rentals.csv")
PM_PATH      = Path("scraped_data/unit_numbers_palm_jumeirah.csv")
BAYUT_PATH   = Path("data/bayut_palm_listings.csv")
PF_PATH      = Path("scraped_data/propertyfinder_scraped_leads.csv")
OUTPUT_PATH  = Path("data/unit_registry.csv")

print("=" * 80)
print("UNIT REGISTRY BUILDER")
print("=" * 80)

# ---------------------------------------------------------------------------
# Step 1: Load data sources
# ---------------------------------------------------------------------------

print("\n[Step 1] Loading data sources...")

leads = pd.read_csv(LEADS_PATH, encoding="utf-8", on_bad_lines="skip", low_memory=False)
print(f"  Leads: {len(leads):,} records")

sales = pd.read_csv(SALES_PATH, encoding="utf-8", on_bad_lines="skip", low_memory=False)
print(f"  Sales (reference master): {len(sales):,} records")

rentals = pd.read_csv(RENTALS_PATH, encoding="utf-8", on_bad_lines="skip", low_memory=False)
print(f"  Rentals: {len(rentals):,} records")

pm_raw = pd.read_csv(PM_PATH, encoding="utf-8", on_bad_lines="skip", low_memory=False)
print(f"  PropertyMonitor transactions: {len(pm_raw):,} records")

# Rename PropertyMonitor columns to clean names using column index
# (original column names contain the full filter option lists)
pm_col_map = {
    pm_raw.columns[4]:  "building_name",    # Community / Building (primary)
    pm_raw.columns[5]:  "sub_community",    # Sub Community (more specific when present)
    pm_raw.columns[6]:  "bedrooms",         # Beds
    pm_raw.columns[8]:  "size_sqft",        # Unit Size (sq ft)
    pm_raw.columns[13]: "floor_level",      # Floor Level
    pm_raw.columns[14]: "unit_number",      # Unit No.
    pm_raw.columns[19]: "view",             # View
    pm_raw.columns[7]:  "price_aed",        # Price (AED)
    pm_raw.columns[0]:  "transaction_date", # Evidence Date
}
pm = pm_raw.rename(columns=pm_col_map)[list(pm_col_map.values())].copy()
# Resolve effective building name: use sub_community when populated, else building_name
pm["effective_building"] = pm["sub_community"].where(
    pm["sub_community"].notna() & (pm["sub_community"].str.strip() != "") & (pm["sub_community"].str.strip() != "-"),
    other=pm["building_name"]
)
print(f"  PropertyMonitor columns mapped OK")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def normalize_unit_number(unit):
    """Normalize unit number (strip, upper)."""
    if pd.isna(unit):
        return None
    return str(unit).strip().upper()


def normalize_bedrooms(br):
    """Normalize bedrooms to clean string: Studio, 1, 2, 3, 4, 5, 6."""
    if pd.isna(br):
        return None
    br_str = str(br).strip().lower()
    if br_str in ("studio", "st", "s", "0", "0.0"):
        return "Studio"
    if br_str in ("penthouse", "ph"):
        return "Penthouse"
    try:
        br_int = int(float(br_str))
        if 1 <= br_int <= 10:
            return str(br_int)
    except (ValueError, TypeError):
        pass
    match = re.search(r"(\d)", br_str)
    if match:
        return str(match.group(1))
    return None


def extract_floor_position(unit):
    """
    Extract floor and position from unit number.
    Returns (floor, position) tuple.

    Examples:
    - "1205" → (12, "05")
    - "903"  → (9, "03")
    - "S-607" → (6, "07")
    - "PH01" → ("PH", "01")
    - "G01"  → ("G", "01")
    """
    if pd.isna(unit):
        return (None, None)

    unit_str = str(unit).strip().upper()
    unit_str = re.sub(r"^[A-Z]-", "", unit_str)

    if unit_str.startswith("PH"):
        digits = re.sub(r"\D", "", unit_str)
        return ("PH", digits[-2:] if len(digits) >= 2 else digits)

    if unit_str.startswith("G"):
        digits = re.sub(r"\D", "", unit_str)
        return ("G", digits[-2:] if len(digits) >= 2 else digits)

    digits = re.sub(r"\D", "", unit_str)
    if not digits:
        return (None, None)

    if len(digits) >= 3:
        floor = int(digits[:-2])
        position = digits[-2:]
        return (floor, position)

    return (None, None)


def match_key(building, unit):
    b = str(building).strip().lower().replace(" ", "").replace("-", "")
    u = str(unit).strip().upper().replace(" ", "").replace("-", "")
    return f"{b}|{u}"


# ---------------------------------------------------------------------------
# Step 2: Process leads
# (leads_master.csv uses Title Case column names)
# ---------------------------------------------------------------------------

print("\n[Step 2] Processing leads...")
leads_units = []
for idx, row in leads.iterrows():
    building = row.get("Building Name")
    unit = row.get("Unit Number")
    bedrooms = row.get("Bedrooms")
    size = row.get("Size (sqft)")

    if pd.isna(building) or pd.isna(unit):
        continue

    building_norm = standardize_building_name(str(building))
    unit_norm = normalize_unit_number(unit)
    br_norm = normalize_bedrooms(bedrooms)
    size_val = None
    if pd.notna(size):
        try:
            size_val = float(str(size).replace(",", ""))
            # Detect sqm stored as sqft: no Palm apartment is under 300 sqft
            if size_val < 300:
                size_val = round(size_val * 10.764, 1)
        except (ValueError, TypeError):
            pass

    if building_norm and unit_norm:
        floor, position = extract_floor_position(unit_norm)
        leads_units.append({
            "building_name": building_norm,
            "unit_number": unit_norm,
            "bedrooms": br_norm,
            "size_sqft": size_val,
            "floor_level": floor,
            "unit_position": position,
            "source": "lead"
        })

leads_df = pd.DataFrame(leads_units)
print(f"  Extracted {len(leads_df):,} lead unit records")

# ---------------------------------------------------------------------------
# Step 3: Process reference sales
# ---------------------------------------------------------------------------

# Developer → building name lookup for cases where sub_loc only gives the community
# e.g. Ellington Beach House is in "The Crescent" community but identified by developer
_DEVELOPER_BUILDING_MAP = {
    "ellington properties": "Ellington Beach House",
    "seven tides":          "Seven Palm",
    "muraba":               "Muraba Residences",
    "como residences":      "Como Residences",
    "omniyat":              "One at Palm Jumeirah",
}

print("\n[Step 3] Processing reference sales...")
sales_units = []
for idx, row in sales.iterrows():
    building = row.get("sub_loc_2") or row.get("sub_loc_3")
    unit = row.get("unit_no")
    bedrooms = row.get("no_beds")
    size = row.get("unit_size_sqft")
    price = row.get("total_sales_price_val")
    date = row.get("custom_date")

    if pd.isna(building) or pd.isna(unit):
        continue

    # If developer uniquely identifies the building, use that instead of community name
    developer = str(row.get("developer") or "").strip().lower()
    if developer in _DEVELOPER_BUILDING_MAP:
        building = _DEVELOPER_BUILDING_MAP[developer]

    building_norm = standardize_building_name(str(building))
    unit_norm = normalize_unit_number(unit)
    br_norm = normalize_bedrooms(bedrooms)
    size_val = float(size) if pd.notna(size) else None
    price_val = float(price) if pd.notna(price) else None

    if building_norm and unit_norm:
        floor, position = extract_floor_position(unit_norm)
        sales_units.append({
            "building_name": building_norm,
            "unit_number": unit_norm,
            "bedrooms": br_norm,
            "size_sqft": size_val,
            "floor_level": floor,
            "unit_position": position,
            "sale_price": price_val,
            "sale_date": str(date) if pd.notna(date) else None,
            "source": "sale"
        })

sales_df = pd.DataFrame(sales_units)
print(f"  Extracted {len(sales_df):,} sales records")

# ---------------------------------------------------------------------------
# Step 4: Process rentals
# ---------------------------------------------------------------------------

print("\n[Step 4] Processing rentals...")
rentals_units = []
for idx, row in rentals.iterrows():
    building = row.get("building_name")
    unit = row.get("unit_number")
    bedrooms = row.get("bedrooms")
    size = row.get("size_sqft")
    view = row.get("view")
    floor = row.get("floor_level")
    rent = row.get("annualized_rent")

    if pd.isna(building) or pd.isna(unit):
        continue

    building_norm = standardize_building_name(str(building))
    unit_norm = normalize_unit_number(unit)
    br_norm = normalize_bedrooms(bedrooms)
    size_val = float(size) if pd.notna(size) else None
    rent_val = float(rent) if pd.notna(rent) else None
    view_val = str(view).strip() if pd.notna(view) and str(view).strip() != "-" else None

    if building_norm and unit_norm:
        floor_ext, position = extract_floor_position(unit_norm)
        rentals_units.append({
            "building_name": building_norm,
            "unit_number": unit_norm,
            "bedrooms": br_norm,
            "size_sqft": size_val,
            "floor_level": floor_ext or floor,
            "unit_position": position,
            "view": view_val,
            "annual_rent": rent_val,
            "source": "rental"
        })

rentals_df = pd.DataFrame(rentals_units)
print(f"  Extracted {len(rentals_df):,} rental records")

# ---------------------------------------------------------------------------
# Step 5: Process PropertyMonitor DLD transactions
# (Most authoritative bedroom source — actual title deed data)
# ---------------------------------------------------------------------------

print("\n[Step 5] Processing PropertyMonitor transactions...")
pm_units = []
for idx, row in pm.iterrows():
    # Use effective_building: sub_community when present (more specific), else community
    building = row.get("effective_building") or row.get("building_name")
    unit = row.get("unit_number")
    bedrooms = row.get("bedrooms")
    size = row.get("size_sqft")
    view = row.get("view")
    floor = row.get("floor_level")
    price = row.get("price_aed")
    date = row.get("transaction_date")

    if pd.isna(building) or pd.isna(unit):
        continue

    # Skip rows where unit number is clearly a filter header or empty
    unit_str = str(unit).strip()
    if not unit_str or unit_str in ("-", "Unit No.", "nan"):
        continue

    building_norm = standardize_building_name(str(building))
    unit_norm = normalize_unit_number(unit)
    br_norm = normalize_bedrooms(bedrooms)
    size_val = None
    if pd.notna(size):
        try:
            size_val = float(str(size).replace(",", ""))
        except (ValueError, TypeError):
            pass
    price_val = None
    if pd.notna(price):
        try:
            price_val = float(str(price).replace(",", ""))
        except (ValueError, TypeError):
            pass
    view_val = str(view).strip() if pd.notna(view) and str(view).strip() not in ("-", "") else None

    if building_norm and unit_norm:
        floor_ext, position = extract_floor_position(unit_norm)
        # PM stores all Shoreline towers as "Shoreline Apartments" → standardize returns "Shoreline Family"
        # Expand into one record per individual Shoreline tower so the registry can merge with leads
        _shoreline_individual = [
            "Al Ramth", "Al Nabat", "Al Murjan", "Al Mashraba", "Al Khayali",
            "Al Malak", "Al Habool", "Al Ghaf", "Al Masalli", "Al Hallawi",
            "Al Anbara", "Jash Falqa", "Al Shamsi", "Jash Hamad",
            "Al Basri", "Al Sahab", "Al Anbar", "Al Dawaar", "Al Msalli",
            "Al Sultana", "Al Thamam", "Al Das", "Al Khushkar", "Al Janahi",
            "Al Majara", "Al Fahad", "Al Fattan", "Al Shirawi", "Al Hamri",
            "Al Hatmi", "Al Seef",
        ]
        if building_norm == "Shoreline Family":
            target_buildings = _shoreline_individual
        else:
            target_buildings = [building_norm]
        for bname in target_buildings:
            pm_units.append({
                "building_name": bname,
                "unit_number": unit_norm,
                "bedrooms": br_norm,
                "size_sqft": size_val,
                "floor_level": floor_ext,
                "unit_position": position,
                "view": view_val,
                "sale_price": price_val,
                "sale_date": str(date) if pd.notna(date) else None,
                "source": "pm"
            })

pm_df = pd.DataFrame(pm_units)
print(f"  Extracted {len(pm_df):,} PropertyMonitor records")
pm_with_beds = pm_df["bedrooms"].notna().sum() if not pm_df.empty else 0
print(f"  Of which {pm_with_beds:,} have bedroom data")

# ---------------------------------------------------------------------------
# Step 5b: Process PropertyFinder scraped leads (DLD permit data — unit + bedroom)
# ---------------------------------------------------------------------------

print("\n[Step 5b] Processing PropertyFinder scraped data...")
pf_units = []
if PF_PATH.exists():
    pf_raw = pd.read_csv(PF_PATH, encoding="utf-8", on_bad_lines="skip", low_memory=False)
    print(f"  PF records: {len(pf_raw):,}")
    for idx, row in pf_raw.iterrows():
        building = row.get("building_name")
        unit = row.get("unit_number")
        room_type = row.get("room_type")
        size_sqm_raw = row.get("size_sqm")

        if pd.isna(building) or pd.isna(unit):
            continue
        unit_str = str(unit).strip()
        if not unit_str or unit_str in ("-", "nan"):
            continue

        building_norm = standardize_building_name(str(building))
        unit_norm = normalize_unit_number(unit)
        br_norm = normalize_bedrooms(room_type) if pd.notna(room_type) else None

        # Parse size: "133.04 sqm" → sqft
        size_val = None
        if pd.notna(size_sqm_raw):
            try:
                sqm = float(str(size_sqm_raw).replace("sqm", "").replace(",", "").strip())
                size_val = round(sqm * 10.7639, 1)
            except (ValueError, TypeError):
                pass

        if building_norm and unit_norm:
            floor_ext, position = extract_floor_position(unit_norm)
            pf_units.append({
                "building_name": building_norm,
                "unit_number": unit_norm,
                "bedrooms": br_norm,
                "size_sqft": size_val,
                "floor_level": floor_ext,
                "unit_position": position,
                "source": "pf"
            })
else:
    print(f"  [SKIP] {PF_PATH} not found")

pf_df = pd.DataFrame(pf_units) if pf_units else pd.DataFrame(
    columns=["building_name", "unit_number", "bedrooms", "size_sqft", "floor_level", "unit_position", "source"])
pf_with_beds = pf_df["bedrooms"].notna().sum() if not pf_df.empty else 0
print(f"  Extracted {len(pf_df):,} PF records, {pf_with_beds:,} with bedroom data")

# ---------------------------------------------------------------------------
# Step 6: Merge all sources by (building, unit)
# ---------------------------------------------------------------------------

print("\n[Step 6] Merging all sources by building + unit...")

leads_df["_key"] = leads_df.apply(lambda r: match_key(r["building_name"], r["unit_number"]), axis=1)
sales_df["_key"] = sales_df.apply(lambda r: match_key(r["building_name"], r["unit_number"]), axis=1)
rentals_df["_key"] = rentals_df.apply(lambda r: match_key(r["building_name"], r["unit_number"]), axis=1)
pm_df["_key"] = pm_df.apply(lambda r: match_key(r["building_name"], r["unit_number"]), axis=1)
pf_df["_key"] = pf_df.apply(lambda r: match_key(r["building_name"], r["unit_number"]), axis=1)

all_keys = (
    set(leads_df["_key"].unique())
    | set(sales_df["_key"].unique())
    | set(rentals_df["_key"].unique())
    | set(pm_df["_key"].unique())
    | set(pf_df["_key"].unique())
)
print(f"  Total unique (building, unit) combinations: {len(all_keys):,}")

registry = []

for key in all_keys:
    lead_rows   = leads_df[leads_df["_key"] == key]
    sale_rows   = sales_df[sales_df["_key"] == key]
    rental_rows = rentals_df[rentals_df["_key"] == key]
    pm_rows     = pm_df[pm_df["_key"] == key]
    pf_rows     = pf_df[pf_df["_key"] == key]

    # Canonical building and unit name — prefer PM > PF > sale > lead > rental
    # (PM, PF, and sale names come from DLD data, most standardized)
    if not pm_rows.empty:
        building = pm_rows.iloc[0]["building_name"]
        unit = pm_rows.iloc[0]["unit_number"]
    elif not pf_rows.empty:
        building = pf_rows.iloc[0]["building_name"]
        unit = pf_rows.iloc[0]["unit_number"]
    elif not sale_rows.empty:
        building = sale_rows.iloc[0]["building_name"]
        unit = sale_rows.iloc[0]["unit_number"]
    elif not lead_rows.empty:
        building = lead_rows.iloc[0]["building_name"]
        unit = lead_rows.iloc[0]["unit_number"]
    else:
        building = rental_rows.iloc[0]["building_name"]
        unit = rental_rows.iloc[0]["unit_number"]

    # Bedroom resolution — strict priority tiers:
    #   Tier 1 (highest): PropertyMonitor DLD transactions — ground truth
    #   Tier 2: Reference sales (title deed DLD data)
    #   Tier 3: PF scraper + leads + rentals — can occasionally be wrong, used only as fallback
    bedrooms_pm = []
    bedrooms_sales = []
    bedrooms_supporting = []

    for br in pm_rows["bedrooms"].dropna():
        if br:
            bedrooms_pm.append(br)
    for br in sale_rows["bedrooms"].dropna():
        if br:
            bedrooms_sales.append(br)
    # PF, leads, and rentals are supporting — only used when PM and sales have no data
    for br in pf_rows["bedrooms"].dropna():
        if br:
            bedrooms_supporting.append(br)
    for br in lead_rows["bedrooms"].dropna():
        if br:
            bedrooms_supporting.append(br)
    for br in rental_rows["bedrooms"].dropna():
        if br:
            bedrooms_supporting.append(br)

    # Use PM first (most authoritative), then sales, then supporting sources
    if bedrooms_pm:
        br_counter = Counter(bedrooms_pm)
        bedrooms_final = br_counter.most_common(1)[0][0]
    elif bedrooms_sales:
        br_counter = Counter(bedrooms_sales)
        bedrooms_final = br_counter.most_common(1)[0][0]
    elif bedrooms_supporting:
        br_counter = Counter(bedrooms_supporting)
        bedrooms_final = br_counter.most_common(1)[0][0]
    else:
        bedrooms_final = None

    # Size: median across all sources, filter outliers
    sizes_list = []
    for df_src in [pm_rows, pf_rows, sale_rows, lead_rows, rental_rows]:
        if not df_src.empty:
            sizes_list.extend([s for s in df_src["size_sqft"].dropna() if s and s > 0])

    if sizes_list:
        median_size = sorted(sizes_list)[len(sizes_list) // 2]
        filtered_sizes = [s for s in sizes_list if abs(s - median_size) <= 50]
        size_final = sum(filtered_sizes) / len(filtered_sizes)
    else:
        size_final = None

    # Floor and position
    floor_final = None
    position_final = None
    for df_src in [pm_rows, pf_rows, sale_rows, lead_rows, rental_rows]:
        if not df_src.empty:
            if pd.notna(df_src.iloc[0]["floor_level"]):
                floor_final = df_src.iloc[0]["floor_level"]
            if pd.notna(df_src.iloc[0]["unit_position"]):
                position_final = df_src.iloc[0]["unit_position"]
            if floor_final and position_final:
                break

    # View (prefer PM, then rental)
    view_final = None
    for df_src in [pm_rows, rental_rows]:
        if not df_src.empty:
            views = [v for v in df_src["view"].dropna() if v]
            if views:
                view_final = views[0]
                break

    # Sources and confidence
    sources = []
    sale_count = 0
    rental_count = 0
    pm_count = len(pm_rows)

    if not pm_rows.empty:
        sources.append("pm")
        sale_count += pm_count  # PM records are transactions
    if not pf_rows.empty:
        sources.append("pf")
    if not sale_rows.empty:
        sources.append("sale")
        sale_count += len(sale_rows)
    if not lead_rows.empty:
        sources.append("lead")
    if not rental_rows.empty:
        sources.append("rental")
        rental_count = len(rental_rows)

    # Confidence:
    #   HIGH — PM or sales (DLD) confirmed bedrooms, or 2+ independent sources agree
    #   MEDIUM — single source (lead/rental/pf only)
    #   LOW — no bedroom data
    has_dld_beds = bool(bedrooms_pm) or bool(bedrooms_sales)
    source_count = len(sources)
    if has_dld_beds or source_count >= 2:
        confidence = "HIGH"
    elif source_count == 1:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # Last sale price and date (from PM and reference sales combined)
    all_sales = []
    for df_src in [pm_rows, sale_rows]:
        if not df_src.empty and "sale_price" in df_src.columns:
            for _, r in df_src.iterrows():
                if pd.notna(r.get("sale_price")) and pd.notna(r.get("sale_date")):
                    all_sales.append((str(r["sale_date"]), r["sale_price"]))

    last_sale_price = None
    last_sale_date = None
    if all_sales:
        all_sales_sorted = sorted(all_sales, key=lambda x: x[0], reverse=True)
        last_sale_date = all_sales_sorted[0][0]
        last_sale_price = all_sales_sorted[0][1]

    # Last annual rent
    last_annual_rent = None
    if not rental_rows.empty:
        rental_with_rent = rental_rows.dropna(subset=["annual_rent"])
        if not rental_with_rent.empty:
            last_annual_rent = rental_with_rent["annual_rent"].max()

    registry.append({
        "building_name": building,
        "unit_number": unit,
        "bedrooms": bedrooms_final,
        "size_sqft": round(size_final, 1) if size_final else None,
        "floor_level": floor_final,
        "view": view_final,
        "unit_position": position_final,
        "confidence": confidence,
        "sources": ",".join(sources),
        "sale_count": sale_count,
        "rental_count": rental_count,
        "last_sale_price": round(last_sale_price) if last_sale_price and pd.notna(last_sale_price) else None,
        "last_sale_date": last_sale_date,
        "last_annual_rent": round(last_annual_rent) if last_annual_rent and pd.notna(last_annual_rent) else None,
    })

registry_df = pd.DataFrame(registry)
print(f"  Registry entries: {len(registry_df):,}")

# ---------------------------------------------------------------------------
# Step 7: Enrich with Bayut listing data (building-level size->bedroom inference)
# ---------------------------------------------------------------------------

print("\n[Step 7] Loading Bayut listing data for size->bedroom inference...")

if BAYUT_PATH.exists():
    bayut_raw = pd.read_csv(BAYUT_PATH, encoding="utf-8", on_bad_lines="skip", low_memory=False)
    print(f"  Bayut listings: {len(bayut_raw):,} records")

    bayut_valid = bayut_raw.dropna(subset=["building_name", "bedrooms", "size_sqft"]).copy()
    bayut_valid = bayut_valid[bayut_valid["size_sqft"] > 0]

    # Build per-building size->bedroom lookup: {building_key: [(beds_norm, min_s, max_s, median_s)]}
    bayut_size_table = {}
    for building in bayut_valid["building_name"].unique():
        b_data = bayut_valid[bayut_valid["building_name"] == building]
        building_key = str(building).strip().lower().replace(" ", "").replace("-", "")
        size_ranges = []
        for beds in b_data["bedrooms"].unique():
            beds_norm = normalize_bedrooms(beds)
            if not beds_norm:
                continue
            bed_sizes = b_data[b_data["bedrooms"] == beds]["size_sqft"].dropna().tolist()
            if len(bed_sizes) >= 2:
                min_s = min(bed_sizes)
                max_s = max(bed_sizes)
                median_s = sorted(bed_sizes)[len(bed_sizes) // 2]
                size_ranges.append((beds_norm, min_s, max_s, median_s))
        if size_ranges:
            bayut_size_table[building_key] = size_ranges

    print(f"  Built size->bedroom table for {len(bayut_size_table):,} buildings")

    # Apply to registry: fill missing bedrooms using size ranges from Bayut
    bayut_inferred = 0
    no_beds_mask = registry_df["bedrooms"].isna() & registry_df["size_sqft"].notna()

    for idx in registry_df[no_beds_mask].index:
        building = registry_df.at[idx, "building_name"]
        size = registry_df.at[idx, "size_sqft"]
        if not size:
            continue
        building_key = str(building).strip().lower().replace(" ", "").replace("-", "")
        ranges = bayut_size_table.get(building_key)
        if not ranges:
            continue

        # Find beds whose size range contains this unit (with 10% + 50 sqft tolerance)
        best_match = None
        best_dist = float("inf")
        for beds_norm, min_s, max_s, median_s in ranges:
            tolerance = (max_s - min_s) * 0.1 + 50
            if (min_s - tolerance) <= size <= (max_s + tolerance):
                dist = abs(size - median_s)
                if dist < best_dist:
                    best_dist = dist
                    best_match = beds_norm

        if best_match:
            registry_df.at[idx, "bedrooms"] = best_match
            if registry_df.at[idx, "confidence"] not in ("HIGH", "MEDIUM"):
                registry_df.at[idx, "confidence"] = "BAYUT_INFERRED"
            bayut_inferred += 1

    print(f"  Inferred bedrooms for {bayut_inferred:,} units from Bayut size data")

else:
    print(f"  [SKIP] {BAYUT_PATH} not found — run Bayut scraper first:")
    print(f"         python bayut_scraper/run_palm_listings.py")


# ---------------------------------------------------------------------------
# Step 8: View inference by position within building
# ---------------------------------------------------------------------------

print("\n[Step 8] Inferring views by unit position...")

view_inferred_count = 0
for building in registry_df["building_name"].unique():
    building_units = registry_df[registry_df["building_name"] == building]

    for position in building_units["unit_position"].dropna().unique():
        position_units = building_units[building_units["unit_position"] == position]
        known_views = position_units["view"].dropna().unique()

        if len(known_views) > 0:
            view_val = known_views[0]
            for idx in position_units[position_units["view"].isna()].index:
                registry_df.at[idx, "view"] = view_val
                if registry_df.at[idx, "confidence"] not in ("HIGH",):
                    registry_df.at[idx, "confidence"] = "INFERRED"
                view_inferred_count += 1

print(f"  Inferred views for {view_inferred_count:,} units")

# ---------------------------------------------------------------------------
# Step 9: Save
# ---------------------------------------------------------------------------

print("\n[Step 9] Saving unit registry...")

OUTPUT_PATH.parent.mkdir(exist_ok=True)
registry_df.to_csv(OUTPUT_PATH, index=False)
print(f"  Saved to: {OUTPUT_PATH}")

# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------

print("\n" + "=" * 80)
print("UNIT REGISTRY STATISTICS")
print("=" * 80)

total_units = len(registry_df)
high_conf          = len(registry_df[registry_df["confidence"] == "HIGH"])
medium_conf        = len(registry_df[registry_df["confidence"] == "MEDIUM"])
inferred_conf      = len(registry_df[registry_df["confidence"] == "INFERRED"])
bayut_inferred_conf = len(registry_df[registry_df["confidence"] == "BAYUT_INFERRED"])
with_bedrooms = len(registry_df[registry_df["bedrooms"].notna()])
with_view = len(registry_df[registry_df["view"].notna()])
buildings = registry_df["building_name"].nunique()

print(f"\nTotal unique units: {total_units:,}")
print(f"  - HIGH confidence (DLD-confirmed or 2+ sources): {high_conf:,} ({100*high_conf/total_units:.1f}%)")
print(f"  - MEDIUM confidence (1 source):                  {medium_conf:,} ({100*medium_conf/total_units:.1f}%)")
print(f"  - INFERRED (view inferred by position):          {inferred_conf:,} ({100*inferred_conf/total_units:.1f}%)")
print(f"  - BAYUT_INFERRED (size->bedroom from Bayut):      {bayut_inferred_conf:,} ({100*bayut_inferred_conf/total_units:.1f}%)")
print(f"\nUnits with confirmed bedrooms: {with_bedrooms:,} ({100*with_bedrooms/total_units:.1f}%)")
print(f"Units with view data:          {with_view:,} ({100*with_view/total_units:.1f}%)")
print(f"\nBuildings covered: {buildings:,}")

print(f"\nBedroom distribution:")
br_dist = registry_df["bedrooms"].value_counts().sort_index()
for br, count in br_dist.items():
    print(f"  {br}: {count:,} units")

print("\n" + "=" * 80)
print("DONE! Unit registry created successfully.")
print("=" * 80)
