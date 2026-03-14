"""
Campaign Manager - Build message queues from lead and rental data
Handles landlord lease expiry and cold owner campaigns.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from message_log import should_skip_phone
from message_templates import generate_message, format_first_name
from data_processor import load_reference_data, standardize_building_name
from bot import format_phone_for_whatsapp

try:
    from building_intelligence import normalize_unit_number
    _has_normalize_unit = True
except ImportError:
    _has_normalize_unit = False


# Data paths (project root so they work when cwd is whatsapp_bot/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEADS_PATH = _PROJECT_ROOT / 'data' / 'leads_master_v3.csv'
RENTALS_PATH = _PROJECT_ROOT / 'scraped_data' / 'palm_jumeirah_rentals.csv'
PF_LEADS_PATH = _PROJECT_ROOT / 'scraped_data' / 'propertyfinder_scraped_leads.csv'
PROPSPACE_LEADS_PATH = _PROJECT_ROOT / 'scraped_data' / 'propspace_leads.csv'

# Area filter: map area name -> list of building name substrings (lowercase). Lead/rental is kept if building contains any.
AREA_BUILDING_KEYWORDS = {
    "Palm Jumeirah": [
        "shoreline", "oceana", "fairmont", "ellington", "seven", "palm tower", "marina", "tiara",
        "anantara", "kempinski", "serenia", "balqis", "golden mile", "the 8", "palm beach",
        "viceroy", "atlantis", "vista mare", "azizi", "palm views", "frond", "crescent", "palm",
    ],
    "Dubai Marina": ["marina 1", "marina 2", "marina 3", "marina 4", "marina 5", "marina 6", "palm marina", "marina residence"],
    "JBR": ["jbr", "jumeirah beach residence", "the walk"],
}

# Building filter alias: "shoreline" -> match PropertyFinder Shoreline tower names (building_name is tower, not "Shoreline")
SHORELINE_BUILDING_KEYWORDS = [
    "abu keibal", "al haseer", "al das", "al basri", "al khushkar", "al habool", "al hallawi",
    "jash falqa", "al sarrood", "al hamri", "al tamr", "al nabat", "al khudrawi", "al hatimi",
    "al dabas", "al shahla",
]


def _filter_by_building(df: pd.DataFrame, building_col: str, building_filter: Optional[str]) -> pd.DataFrame:
    """Apply building filter. If filter is 'shoreline', match Shoreline tower names; else substring match."""
    if not building_filter or not building_filter.strip():
        return df
    b = building_filter.strip()
    col = df[building_col].fillna("").astype(str).str.lower()
    if b.lower() == "shoreline":
        mask = pd.Series(False, index=df.index)
        for kw in SHORELINE_BUILDING_KEYWORDS:
            mask = mask | col.str.contains(kw, regex=False, na=False)
        out = df[mask]
        print(f"  [FILTER] Building 'shoreline' (towers): {len(df)} -> {len(out)} rows")
        return out
    out = df[col.str.contains(b, case=False, na=False)]
    print(f"  [FILTER] Building '{building_filter}': {len(out)} rows")
    return out


def _filter_by_area(df: pd.DataFrame, building_col: str, area_filter: Optional[str]) -> pd.DataFrame:
    """Filter dataframe to rows whose building_col value contains any keyword for the given area."""
    if not area_filter or not area_filter.strip() or area_filter.strip().lower() == "all":
        return df
    area = area_filter.strip()
    keywords = AREA_BUILDING_KEYWORDS.get(area)
    if not keywords:
        return df
    col = df[building_col].fillna("").astype(str).str.lower()
    mask = pd.Series(False, index=df.index)
    for kw in keywords:
        mask = mask | col.str.contains(kw, regex=False, na=False)
    out = df[mask]
    print(f"  [FILTER] Area '{area}': {len(df)} -> {len(out)} rows")
    return out


def load_leads() -> pd.DataFrame:
    """Load the master lead list."""
    if not LEADS_PATH.exists():
        print(f"[ERROR] Leads file not found: {LEADS_PATH}")
        return pd.DataFrame()
    
    df = pd.read_csv(LEADS_PATH, encoding='utf-8', low_memory=False)
    print(f"[OK] Loaded {len(df):,} leads")
    return df


def load_rentals() -> pd.DataFrame:
    """Load rental transaction data."""
    if not RENTALS_PATH.exists():
        print(f"[WARN] Rentals file not found: {RENTALS_PATH}")
        return pd.DataFrame()
    df = pd.read_csv(RENTALS_PATH, encoding='utf-8', low_memory=False)
    df['contract_end'] = pd.to_datetime(df['contract_end'], errors='coerce')
    print(f"[OK] Loaded {len(df):,} rental records")
    return df


def _norm_unit(x):
    """Normalize unit number for matching; same logic as data_processor."""
    if _has_normalize_unit and normalize_unit_number is not None:
        return normalize_unit_number(x) if x is not None and (pd.notna(x) and str(x).strip()) else 'N/A'
    return str(x).strip().upper() if x is not None and pd.notna(x) else 'N/A'


def build_landlord_lease_expiry_queue(
    days_ahead: int = 90,
    building_filter: Optional[str] = None,
    bedrooms_filter: Optional[str] = None,
    area_filter: Optional[str] = None,
) -> List[Dict]:
    """
    Build queue for landlords with expiring leases.
    Cross-reference rentals with leads to find owner contact info.
    """
    rentals_df = load_rentals()
    leads_df = load_leads()
    
    if rentals_df.empty or leads_df.empty:
        print("[ERROR] Cannot build queue: missing rental or lead data")
        return []
    
    # Get expiring leases
    today = datetime.now()
    cutoff = today + timedelta(days=days_ahead)
    
    expiring = rentals_df[
        (rentals_df['contract_end'] >= today) & 
        (rentals_df['contract_end'] <= cutoff)
    ].copy()
    
    print(f"[OK] Found {len(expiring)} leases expiring in next {days_ahead} days")
    
    # Apply filters
    if building_filter and building_filter.strip():
        expiring = expiring[
            expiring['building_name'].fillna('').str.contains(
                building_filter, case=False, na=False
            )
        ]
        print(f"  [FILTER] Building '{building_filter}': {len(expiring)} leases")
    
    if bedrooms_filter and bedrooms_filter != 'All':
        expiring = expiring[expiring['bedrooms'].astype(str) == str(bedrooms_filter)]
        print(f"  [FILTER] Bedrooms '{bedrooms_filter}': {len(expiring)} leases")
    if area_filter and area_filter.strip() and area_filter.strip().lower() != 'all':
        expiring = _filter_by_area(expiring, 'building_name', area_filter)
    
    # Cross-reference with leads to find owner contacts
    queue = []
    
    for idx, rental in expiring.iterrows():
        unit = str(rental['unit_number']).lower().strip()
        bldg = str(rental['building_name']).lower().strip()
        
        # Find owner in leads
        owner_match = leads_df[
            (leads_df['building_name'].fillna('').str.lower().str.contains(bldg, na=False)) &
            (leads_df['unit_number'].fillna('').str.lower() == unit)
        ]
        
        if owner_match.empty:
            continue
        
        owner = owner_match.iloc[0]
        phone = owner.get('phone_primary')
        
        if not phone or pd.isna(phone):
            continue
        
        # Check if owner has multiple units (for template selection)
        owner_name_clean = str(owner.get('owner_name', '')).strip()
        unit_count = len(leads_df[leads_df['owner_name'] == owner_name_clean]) if owner_name_clean else 1
        
        queue.append({
            'phone': phone,
            'owner_name': owner.get('owner_name'),
            'building': rental['building_name'],
            'unit': rental['unit_number'],
            'bedrooms': rental.get('bedrooms', ''),
            'contract_end': rental['contract_end'],
            'is_portfolio': unit_count >= 2,
            'campaign_type': 'landlord_lease_expiry'
        })
    
    print(f"[OK] Built queue: {len(queue)} landlords with contact info")
    return queue


def build_cold_owner_queue(
    building_filter: Optional[str] = None,
    bedrooms_filter: Optional[str] = None,
    portfolio_only: bool = False,
    limit: Optional[int] = None,
    area_filter: Optional[str] = None,
) -> List[Dict]:
    """
    Build queue for cold owner outreach.
    Filters leads by building/bedrooms, identifies portfolio investors.
    """
    leads_df = load_leads()
    
    if leads_df.empty:
        print("[ERROR] Cannot build queue: no lead data")
        return []
    
    filtered = leads_df.copy()
    
    # Apply filters
    if building_filter and building_filter.strip():
        filtered = filtered[
            filtered['building_name'].fillna('').str.contains(
                building_filter, case=False, na=False
            )
        ]
        print(f"  [FILTER] Building '{building_filter}': {len(filtered)} leads")
    if area_filter and area_filter.strip() and area_filter.strip().lower() != 'all':
        filtered = _filter_by_area(filtered, 'building_name', area_filter)
    if bedrooms_filter and bedrooms_filter != 'All':
        filtered = filtered[filtered['bedrooms'].astype(str) == str(bedrooms_filter)]
        print(f"  [FILTER] Bedrooms '{bedrooms_filter}': {len(filtered)} leads")
    
    # Only keep leads with phone numbers
    filtered = filtered[filtered['phone_primary'].notna() & (filtered['phone_primary'] != '')]
    print(f"  [FILTER] With phone: {len(filtered)} leads")
    
    # Identify portfolio investors (owner with 2+ units)
    owner_counts = filtered.groupby('owner_name').size()
    portfolio_owners = set(owner_counts[owner_counts >= 2].index)
    
    # Build queue
    queue = []
    
    for idx, lead in filtered.iterrows():
        owner_name = lead.get('owner_name', '')
        if not owner_name or pd.isna(owner_name):
            continue
        
        is_portfolio = owner_name in portfolio_owners
        
        # Skip if portfolio_only mode and this is not a portfolio investor
        if portfolio_only and not is_portfolio:
            continue
        
        queue.append({
            'phone': lead.get('phone_primary'),
            'owner_name': owner_name,
            'building': lead.get('building_name'),
            'unit': lead.get('unit_number'),
            'bedrooms': lead.get('bedrooms', ''),
            'is_portfolio': is_portfolio,
            'campaign_type': 'cold_owner'
        })
    
    # Dedup by phone (same owner may appear multiple times with different units)
    seen_phones = set()
    deduped = []
    for item in queue:
        if item['phone'] not in seen_phones:
            deduped.append(item)
            seen_phones.add(item['phone'])
    
    queue = deduped
    print(f"[OK] Queue after phone dedup: {len(queue)} unique contacts")
    
    # Apply limit if specified
    if limit and len(queue) > limit:
        queue = queue[:limit]
        print(f"  [LIMIT] Capped to {limit} contacts")
    
    portfolio_count = sum(1 for q in queue if q['is_portfolio'])
    print(f"  Portfolio investors: {portfolio_count}")
    print(f"  Single-unit owners: {len(queue) - portfolio_count}")
    
    return queue


def build_recent_sale_queue(
    since_days: int = 90,
    building_filter: Optional[str] = None,
    limit: Optional[int] = None,
    title_deed_only: bool = True,
    resale_only: bool = True,
    area_filter: Optional[str] = None,
) -> List[Dict]:
    """
    Build queue for recent-sale follow-up: owners who sold (title deed) recently,
    matched to leads using same standardized building + normalized unit logic as UI.
    Uses load_reference_data() from data_processor for consistency.
    """
    ref_df, _ = load_reference_data()
    leads_df = load_leads()
    if ref_df is None or ref_df.empty or leads_df.empty:
        print("[ERROR] Cannot build recent-sale queue: missing reference or lead data")
        return []
    if 'building_std' not in ref_df.columns or 'unit_no' not in ref_df.columns or 'sale_date' not in ref_df.columns:
        print("[ERROR] Reference data missing building_std/unit_no/sale_date")
        return []
    cutoff = datetime.now() - timedelta(days=since_days)
    recent = ref_df[
        ref_df['sale_date'].notna() & (pd.to_datetime(ref_df['sale_date'], errors='coerce') >= cutoff)
    ].copy()
    if title_deed_only and 'trans_group_en' in recent.columns:
        recent = recent[recent['trans_group_en'].fillna('').str.strip().str.lower() == 'title deed']
    if resale_only and 'sales_recurrence' in recent.columns:
        recent = recent[recent['sales_recurrence'].fillna('').str.strip().str.lower() == 'resale']
    if building_filter and building_filter.strip():
        recent = recent[
            recent['building_std'].fillna('').str.contains(building_filter, case=False, na=False)
        ]
        print(f"  [FILTER] Building '{building_filter}': {len(recent)} recent sales")
    if area_filter and area_filter.strip() and area_filter.strip().lower() != 'all':
        recent = _filter_by_area(recent, 'building_std', area_filter)
    print(f"[OK] Found {len(recent)} sales in last {since_days} days")
    recent['_b'] = recent['building_std'].fillna('').astype(str).str.strip().str.lower()
    recent['_u'] = recent['unit_no'].apply(_norm_unit)
    recent = recent[recent['_u'].fillna('') != 'N/A']
    # Lead keys: standardized building + normalized unit (same as data_processor)
    leads_df = leads_df.copy()
    leads_df['_b'] = leads_df['building_name'].apply(
        lambda x: (standardize_building_name(x) or '').lower()
    )
    leads_df['_u'] = leads_df['unit_number'].apply(_norm_unit)
    lead_lookup = leads_df[leads_df['_u'] != 'N/A'].set_index(['_b', '_u'])
    queue = []
    seen_phones = set()
    for _, row in recent.iterrows():
        key = (row['_b'], row['_u'])
        if key not in lead_lookup.index:
            continue
        owner = lead_lookup.loc[key]
        if isinstance(owner, pd.DataFrame):
            owner = owner.iloc[0]
        phone = owner.get('phone_primary')
        if not phone or pd.isna(phone) or str(phone).strip() == '':
            continue
        if phone in seen_phones:
            continue
        seen_phones.add(phone)
        queue.append({
            'phone': phone,
            'owner_name': owner.get('owner_name'),
            'building': row['building_std'],
            'unit': row['unit_no'],
            'bedrooms': owner.get('bedrooms', ''),
            'is_portfolio': False,
            'campaign_type': 'recent_sale'
        })
    if limit and len(queue) > limit:
        queue = queue[:limit]
        print(f"  [LIMIT] Capped to {limit}")
    print(f"[OK] Recent-sale queue: {len(queue)} contacts")
    return queue


def build_portfolio_owner_queue(
    min_units: int = 3,
    building_filter: Optional[str] = None,
    bedrooms_filter: Optional[str] = None,
    limit: Optional[int] = None,
    area_filter: Optional[str] = None,
) -> List[Dict]:
    """
    Build queue for portfolio owner outreach (dedicated campaign).
    One message per owner with >= min_units units. Queue items include unit_count and buildings.
    """
    leads_df = load_leads()
    if leads_df.empty:
        print("[ERROR] Cannot build queue: no lead data")
        return []

    filtered = leads_df.copy()
    if building_filter and building_filter.strip():
        filtered = filtered[
            filtered['building_name'].fillna('').str.contains(
                building_filter, case=False, na=False
            )
        ]
        print(f"  [FILTER] Building '{building_filter}': {len(filtered)} leads")
    if area_filter and area_filter.strip() and area_filter.strip().lower() != 'all':
        filtered = _filter_by_area(filtered, 'building_name', area_filter)
    if bedrooms_filter and bedrooms_filter != 'All':
        filtered = filtered[filtered['bedrooms'].astype(str) == str(bedrooms_filter)]
        print(f"  [FILTER] Bedrooms '{bedrooms_filter}': {len(filtered)} leads")
    filtered = filtered[filtered['phone_primary'].notna() & (filtered['phone_primary'] != '')]
    print(f"  [FILTER] With phone: {len(filtered)} leads")

    owner_groups = filtered.groupby('owner_name', dropna=False)
    queue = []
    for owner_name, grp in owner_groups:
        if not owner_name or (isinstance(owner_name, float) and pd.isna(owner_name)):
            continue
        unit_count = len(grp)
        if unit_count < min_units:
            continue
        phone = grp['phone_primary'].iloc[0]
        if not phone or pd.isna(phone) or str(phone).strip() == '':
            continue
        buildings_list = grp['building_name'].dropna().unique().tolist()
        buildings_str = ', '.join(str(b) for b in buildings_list[:5]) if buildings_list else 'Palm Jumeirah'
        if len(buildings_list) > 5:
            buildings_str += f' and {len(buildings_list) - 5} more'
        first_building = grp['building_name'].iloc[0] if grp['building_name'].notna().any() else 'Palm Jumeirah'
        queue.append({
            'phone': phone,
            'owner_name': owner_name,
            'building': first_building,
            'unit': 'multiple',
            'bedrooms': '',
            'unit_count': unit_count,
            'buildings': buildings_str,
            'is_portfolio': True,
            'campaign_type': 'portfolio_owner'
        })

    if limit and len(queue) > limit:
        queue = queue[:limit]
        print(f"  [LIMIT] Capped to {limit}")
    print(f"[OK] Portfolio owner queue: {len(queue)} contacts (min {min_units} units)")
    return queue


def build_active_seller_queue(
    building_filter: Optional[str] = None,
    limit: Optional[int] = None,
    area_filter: Optional[str] = None,
) -> List[Dict]:
    """
    Build queue for people actively selling (current PropertyFinder listings).
    Loads from propertyfinder_scraped_leads.csv; dedup by phone.
    """
    if not PF_LEADS_PATH.exists():
        print(f"[ERROR] PropertyFinder leads not found: {PF_LEADS_PATH}")
        print("  Run the PropertyFinder scraper first to populate this file.")
        return []

    df = pd.read_csv(PF_LEADS_PATH, encoding='utf-8', low_memory=False)
    required = ['owner_name', 'phone', 'building_name', 'unit_number']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"[ERROR] PF CSV missing columns: {missing}")
        return []

    filtered = df.copy()
    ph = filtered['phone'].fillna('').astype(str).str.strip()
    filtered = filtered[(ph != '') & (ph.str.lower() != 'n/a')]
    if 'listing_type' in filtered.columns:
        lt = filtered['listing_type'].fillna('').astype(str).str.lower()
        filtered = filtered[lt.str.contains('sell', na=False) | (lt == '')]
        print(f"  [FILTER] Listing type sell (or blank): {len(filtered)} rows")
    print(f"  [FILTER] With phone: {len(filtered)} rows")

    filtered = _filter_by_building(filtered, 'building_name', building_filter)
    if area_filter and area_filter.strip() and area_filter.strip().lower() != 'all':
        filtered = _filter_by_area(filtered, 'building_name', area_filter)

    queue = []
    seen_phones = set()
    for _, row in filtered.iterrows():
        phone = str(row['phone']).strip()
        if phone in seen_phones:
            continue
        seen_phones.add(phone)
        building = str(row.get('building_name', '')).strip() or 'Palm Jumeirah'
        unit = str(row.get('unit_number', '')).strip() or ''
        bedrooms = str(row.get('room_type', '')).strip() if pd.notna(row.get('room_type')) else ''
        listing_price = str(row.get('listing_price', '')).strip() if pd.notna(row.get('listing_price')) and str(row.get('listing_price', '')).strip() else ''
        queue.append({
            'phone': phone,
            'owner_name': row.get('owner_name', ''),
            'building': building,
            'unit': unit,
            'bedrooms': bedrooms,
            'listing_price': listing_price,
            'is_portfolio': False,
            'campaign_type': 'active_seller'
        })

    if limit and len(queue) > limit:
        queue = queue[:limit]
        print(f"  [LIMIT] Capped to {limit}")
    print(f"[OK] Active seller queue: {len(queue)} contacts")
    return queue


def build_active_renter_queue(
    building_filter: Optional[str] = None,
    limit: Optional[int] = None,
    area_filter: Optional[str] = None,
) -> List[Dict]:
    """
    Build queue for people actively listing for rent (PropertyFinder rental listings).
    Same CSV as active_seller; filter by listing_type containing 'rent'. Dedup by phone.
    """
    if not PF_LEADS_PATH.exists():
        print(f"[ERROR] PropertyFinder leads not found: {PF_LEADS_PATH}")
        print("  Run the PropertyFinder scraper on a RENT search to populate this file.")
        return []

    df = pd.read_csv(PF_LEADS_PATH, encoding='utf-8', low_memory=False)
    required = ['owner_name', 'phone', 'building_name', 'unit_number']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"[ERROR] PF CSV missing columns: {missing}")
        return []

    filtered = df.copy()
    ph = filtered['phone'].fillna('').astype(str).str.strip()
    filtered = filtered[(ph != '') & (ph.str.lower() != 'n/a')]
    if 'listing_type' in filtered.columns:
        filtered = filtered[filtered['listing_type'].fillna('').astype(str).str.lower().str.contains('rent', na=False)]
        print(f"  [FILTER] Listing type rent: {len(filtered)} rows")
    print(f"  [FILTER] With phone: {len(filtered)} rows")

    filtered = _filter_by_building(filtered, 'building_name', building_filter)
    if area_filter and area_filter.strip() and area_filter.strip().lower() != 'all':
        filtered = _filter_by_area(filtered, 'building_name', area_filter)

    queue = []
    seen_phones = set()
    for _, row in filtered.iterrows():
        phone = str(row['phone']).strip()
        if phone in seen_phones:
            continue
        seen_phones.add(phone)
        building = str(row.get('building_name', '')).strip() or 'Palm Jumeirah'
        unit = str(row.get('unit_number', '')).strip() or ''
        bedrooms = str(row.get('room_type', '')).strip() if pd.notna(row.get('room_type')) else ''
        queue.append({
            'phone': phone,
            'owner_name': row.get('owner_name', ''),
            'building': building,
            'unit': unit,
            'bedrooms': bedrooms,
            'is_portfolio': False,
            'campaign_type': 'active_renter'
        })

    if limit and len(queue) > limit:
        queue = queue[:limit]
        print(f"  [LIMIT] Capped to {limit}")
    print(f"[OK] Active renter queue: {len(queue)} contacts")
    return queue


def apply_dedup_to_queue(queue: List[Dict], days_window: int = 30) -> List[Dict]:
    """
    Remove phones that were messaged recently or are not on WhatsApp.
    Uses formatted phone (first number only) so dedup matches message_log.
    At most one entry per normalized phone per run (same-run dedup).
    Returns filtered queue.
    """
    filtered = []
    skipped_recent = 0
    skipped_not_on_wa = 0
    seen_normalized = set()

    for item in queue:
        normalized = format_phone_for_whatsapp(item.get('phone'))
        if normalized is None:
            skipped_recent += 1
            continue
        if normalized in seen_normalized:
            skipped_recent += 1
            continue
        should_skip, reason = should_skip_phone(normalized, days_window)
        if should_skip:
            if reason == 'not_on_whatsapp':
                skipped_not_on_wa += 1
            else:
                skipped_recent += 1
            continue

        filtered.append(item)
        seen_normalized.add(normalized)

    print(f"[DEDUP] {len(queue)} -> {len(filtered)} after dedup")
    print(f"  Skipped (already conversed or duplicate): {skipped_recent}")
    print(f"  Skipped (not on WhatsApp): {skipped_not_on_wa}")
    
    return filtered


def shuffle_queue(queue: List[Dict]) -> List[Dict]:
    """
    Shuffle queue to avoid messaging same building consecutively.
    """
    shuffled = queue.copy()
    random.shuffle(shuffled)
    return shuffled


def generate_messages_for_queue(queue: List[Dict]) -> List[Dict]:
    """
    Generate personalized messages for each item in the queue.
    Skips corporate entities (returns None for those items).
    """
    messaged_queue = []
    skipped_corporate = 0
    
    for item in queue:
        kwargs = dict(
            campaign_type=item['campaign_type'],
            owner_name=item['owner_name'],
            building=item['building'],
            unit=item['unit'],
            bedrooms=item.get('bedrooms'),
            is_portfolio=item.get('is_portfolio', False)
        )
        if item.get('campaign_type') == 'portfolio_owner':
            kwargs['unit_count'] = item.get('unit_count')
            kwargs['buildings'] = item.get('buildings')
        if item.get('campaign_type') == 'active_seller':
            kwargs['listing_price'] = item.get('listing_price', '')
        if item.get('campaign_type') in ('propspace_tenant', 'propspace_buyer'):
            kwargs['budget_max'] = item.get('budget_max')
        msg_data = generate_message(**kwargs)
        
        if not msg_data:
            # Corporate entity or unparseable name
            skipped_corporate += 1
            continue
        
        item['message'] = msg_data['message']
        item['template_type'] = msg_data['template_type']
        # Generate a follow-up message for propspace leads (used when existing chat detected)
        if item.get('campaign_type') in ('propspace_tenant', 'propspace_buyer'):
            followup_type = item['campaign_type'] + '_followup'
            followup_kwargs = dict(kwargs)
            followup_kwargs['campaign_type'] = followup_type
            followup_data = generate_message(**followup_kwargs)
            if followup_data:
                item['followup_message'] = followup_data['message']
                item['followup_template_type'] = followup_data['template_type']
        messaged_queue.append(item)
    
    if skipped_corporate > 0:
        print(f"[SKIP] Removed {skipped_corporate} corporate entities")
    
    return messaged_queue


def build_propspace_leads_queue(
    location: Optional[str] = None,
    lead_type: Optional[str] = None,
    beds: Optional[int] = None,
    sub_status_filter: str = 'all',
    limit: Optional[int] = None,
) -> List[Dict]:
    """
    Build a campaign queue from scraped PropSpace buyer/tenant enquiry leads.
    These are WARM leads — people who already enquired on Palm Jumeirah properties.
    The message pitch is: "I can help you find what you are looking for."

    location: filter by sub_location contains (e.g. "Palm Views")
    lead_type: "Tenant", "Buyer", or None (both)
    beds: filter by beds_min == beds (only if detail-scraped; None = all)
    sub_status_filter: "new" = Not yet contacted only, "all" = all open leads
    limit: cap queue size
    """
    if not PROPSPACE_LEADS_PATH.exists():
        print(f"[ERROR] {PROPSPACE_LEADS_PATH} not found. Run PropSpace scraper first.")
        return []

    try:
        df = pd.read_csv(PROPSPACE_LEADS_PATH, encoding="utf-8", dtype=str)
    except Exception as e:
        print(f"[ERROR] Could not load PropSpace leads: {e}")
        return []

    if df.empty:
        print("[WARN] PropSpace leads file is empty.")
        return []

    print(f"[PROPSPACE] Loaded {len(df)} rows")

    # Keep only Open leads
    if "status" in df.columns:
        df = df[df["status"].str.strip().str.lower() == "open"]
        print(f"[PROPSPACE] {len(df)} open leads")

    # sub_status filter
    if sub_status_filter == "new" and "sub_status" in df.columns:
        df = df[df["sub_status"].str.strip().str.lower() == "not yet contacted"]
        print(f"[PROPSPACE] {len(df)} not-yet-contacted leads")

    # lead_type filter
    if lead_type and lead_type.lower() in ("tenant", "buyer") and "lead_type" in df.columns:
        df = df[df["lead_type"].str.strip().str.lower() == lead_type.lower()]
        print(f"[PROPSPACE] {len(df)} {lead_type} leads")

    # location filter (sub_location)
    if location and "sub_location" in df.columns:
        mask = df["sub_location"].fillna("").str.lower().str.contains(location.lower(), na=False)
        df = df[mask]
        print(f"[PROPSPACE] {len(df)} leads in location={location!r}")

    # beds filter
    if beds is not None and "beds_min" in df.columns:
        beds_col = pd.to_numeric(df["beds_min"], errors="coerce")
        df = df[beds_col == int(beds)]
        print(f"[PROPSPACE] {len(df)} leads with beds_min={beds}")

    if df.empty:
        print("[WARN] No leads after filters.")
        return []

    # Sort by enquiry_date descending, dedup by phone (keep most recent)
    if "enquiry_date" in df.columns:
        df = df.sort_values("enquiry_date", ascending=False, na_position="last")
    df = df.drop_duplicates(subset=["phone"], keep="first")
    print(f"[PROPSPACE] {len(df)} unique phone numbers")

    queue = []
    for _, row in df.iterrows():
        phone = str(row.get("phone", "")).strip()
        if not phone or phone == "nan":
            continue

        first = str(row.get("first_name", "")).strip()
        last = str(row.get("last_name", "")).strip()
        full_name = " ".join(p for p in [first, last] if p and p != "nan").strip()
        if not full_name:
            full_name = "Owner"
        # Skip placeholder names inserted by CRM auto-import
        _skip_names = {"new whatsapp lead", "unknown lead", "new lead", "na", "n/a"}
        if full_name.lower().strip() in _skip_names:
            continue

        building = str(row.get("sub_location", "")).strip()
        if not building or building == "nan":
            building = str(row.get("location", "Palm Jumeirah")).strip()
        # Clean up placeholder and ugly suffixes
        if building in ("-", "-- -", "- -", "nan"):
            building = "Palm Jumeirah"
        # Remove " (all)" suffix (e.g. "Shoreline Apartments (all)" -> "Shoreline Apartments")
        building = building.replace(" (all)", "").strip()

        beds_min = row.get("beds_min", "")
        try:
            bedrooms = str(int(float(beds_min))) if beds_min and str(beds_min).strip() not in ("", "nan") else None
        except (ValueError, TypeError):
            bedrooms = None

        lt = str(row.get("lead_type", "Tenant")).strip()
        # Map to template type: propspace_tenant or propspace_buyer
        campaign_subtype = "propspace_buyer" if lt.lower() == "buyer" else "propspace_tenant"

        budget_max = row.get("budget_max", "")
        try:
            budget_max = int(float(budget_max)) if budget_max and str(budget_max).strip() not in ("", "nan") else None
        except (ValueError, TypeError):
            budget_max = None

        queue.append({
            "phone": phone,
            "owner_name": full_name,
            "building": building,
            "unit": "",
            "bedrooms": bedrooms,
            "budget_max": budget_max,
            "lead_type": lt,
            "source": str(row.get("source", "")).strip(),
            "is_portfolio": False,
            "campaign_type": campaign_subtype,  # propspace_tenant or propspace_buyer
        })

    if limit:
        queue = queue[:limit]

    print(f"[PROPSPACE] Queue: {len(queue)} leads ready")
    return queue

