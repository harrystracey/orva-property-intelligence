"""
AI query functions for the HLM Intelligence chat tool.

Lifted from data_processor.py during PR 9 to shrink the monolith. No domain
logic changed: the same functions produce the same outputs; they just live
in a module focused on the AI-assistant role. data_processor.py re-exports
everything below for backwards compatibility with existing call sites in
app.py, orva_api/services/chat_service.py, and anywhere else.
"""

from typing import Dict, List, Optional

import pandas as pd

from data_processor import BUILDING_UNIT_SCHEMA, standardize_building_name

def search_leads_for_ai(leads_df: pd.DataFrame, building: str = None, unit_number: str = None,
                        bedrooms: int = None, min_size: int = None, max_size: int = None,
                        owner_name: str = None, limit: int = 10) -> List[Dict]:
    """
    Search enriched lead database with filters.
    Returns list of matching leads for AI assistant.
    """
    if leads_df is None or leads_df.empty:
        return []
    
    results = leads_df.copy()
    
    if building:
        results = results[results['building_name'].fillna('').str.contains(building, case=False, na=False)]
    
    if unit_number:
        results = results[results['unit_number'].fillna('').astype(str).str.contains(str(unit_number), na=False)]
    
    if bedrooms is not None:
        results = results[results['bedrooms'] == bedrooms]
    
    if min_size:
        results = results[results['size_sqft'].fillna(0) >= min_size]
    
    if max_size:
        results = results[results['size_sqft'].fillna(999999) <= max_size]
    
    if owner_name:
        results = results[results['owner_name'].fillna('').str.contains(owner_name, case=False, na=False)]
    
    # Sort by date descending
    results = results.sort_values('date', ascending=False, na_position='last')
    
    # Format for AI response
    output = []
    for _, row in results.head(limit).iterrows():
        beds = row.get('bedrooms')
        beds_str = 'Studio' if beds == 0 else f"{int(beds)}-bed" if pd.notna(beds) else 'Unknown'
        
        output.append({
            'building': row.get('building_name', 'Unknown'),
            'unit': row.get('unit_number', 'N/A'),
            'bedrooms': beds_str,
            'size_sqft': int(row['size_sqft']) if pd.notna(row.get('size_sqft')) else None,
            'size_sqm': int(row['size_sqm']) if pd.notna(row.get('size_sqm')) else None,
            'owner_name': row.get('owner_name', 'Unknown'),
            'phone': row.get('phone', ''),
            'date': row['date'].strftime('%Y-%m-%d') if pd.notna(row.get('date')) else None,
            'completeness': row.get('completeness', 0),
            'quality': row.get('data_quality', 'OK')
        })
    
    return output


def get_building_info_for_ai(reference_df: pd.DataFrame, building: str) -> Dict:
    """
    Get comprehensive building information from reference data.
    Returns building stats, typical layouts, bedroom distribution.
    """
    if reference_df is None or reference_df.empty:
        return {"error": "No reference data available"}
    
    # Search in building_std column
    building_data = reference_df[
        reference_df['building_std'].fillna('').str.contains(building, case=False, na=False)
    ]
    
    if len(building_data) == 0:
        # Try building_family
        building_data = reference_df[
            reference_df['building_family'].fillna('').str.contains(building, case=False, na=False)
        ]
    
    if len(building_data) == 0:
        return {"error": f"No data found for building: {building}"}
    
    # Get the actual building name found
    actual_building = building_data['building_std'].mode().iloc[0] if not building_data['building_std'].mode().empty else building
    
    info = {
        "building_name": actual_building,
        "building_family": building_data['building_family'].mode().iloc[0] if not building_data['building_family'].mode().empty else None,
        "total_transactions": len(building_data),
        "bedroom_distribution": {},
        "typical_sizes_sqft": {},
        "unit_schema": None
    }
    
    # Bedroom distribution
    bed_counts = building_data['bedrooms'].value_counts()
    for beds, count in bed_counts.items():
        if pd.notna(beds):
            bed_label = 'Studio' if beds == 0 else f'{int(beds)}-bed'
            info['bedroom_distribution'][bed_label] = int(count)
    
    # Average sizes by bedroom count
    for beds in building_data['bedrooms'].dropna().unique():
        sizes = building_data[building_data['bedrooms'] == beds]['size_sqft'].dropna()
        if len(sizes) > 0:
            bed_label = 'Studio' if beds == 0 else f'{int(beds)}-bed'
            info['typical_sizes_sqft'][bed_label] = {
                'avg': int(round(sizes.mean(), 0)),
                'min': int(round(sizes.min(), 0)),
                'max': int(round(sizes.max(), 0)),
                'sample_count': len(sizes)
            }
    
    # Check if we have unit schema for this building
    building_lower = building.lower()
    for schema_name in BUILDING_UNIT_SCHEMA.keys():
        if schema_name in building_lower or building_lower in schema_name:
            schema = BUILDING_UNIT_SCHEMA[schema_name]
            info['unit_schema'] = {
                'name': schema_name,
                'rules': [
                    {'units_ending': rule['unit_end'], 'bedrooms': rule['bedrooms']}
                    for rule in schema['unit_rules']
                ]
            }
            break
    
    return info


def get_market_stats_for_ai(reference_df: pd.DataFrame, building: str, bedrooms: int = None) -> Dict:
    """
    Enhanced market stats with fuzzy building name resolution.
    Returns size statistics, pricing data, and recent transactions with unit numbers.
    """
    if reference_df is None or reference_df.empty:
        return {"error": "No reference data available"}
    
    # Use building intelligence for fuzzy matching if available
    canonical_name = None
    display_name = None
    match_confidence = None
    
    if BUILDING_INTELLIGENCE_AVAILABLE:
        canonical_name, display_name, match_confidence = resolve_building_name(building)
    
    # Search building - try multiple strategies
    building_data = pd.DataFrame()
    
    # Strategy 1: Use resolved canonical name
    if canonical_name:
        building_data = reference_df[
            reference_df['building_std'].fillna('').str.contains(canonical_name, case=False, na=False, regex=False)
        ]
        if len(building_data) == 0:
            # Also check sub_loc_2 for the canonical name
            building_data = reference_df[
                reference_df['sub_loc_2'].fillna('').str.contains(canonical_name, case=False, na=False, regex=False)
            ]
    
    # Strategy 2: Direct search with original term
    if len(building_data) == 0:
        building_data = reference_df[
            reference_df['building_std'].fillna('').str.contains(building, case=False, na=False, regex=False)
        ]
    
    # Strategy 3: Search building_family
    if len(building_data) == 0:
        building_data = reference_df[
            reference_df['building_family'].fillna('').str.contains(building, case=False, na=False, regex=False)
        ]
    
    # Strategy 4: Search sub_loc_2 (original building name from data)
    if len(building_data) == 0 and 'sub_loc_2' in reference_df.columns:
        building_data = reference_df[
            reference_df['sub_loc_2'].fillna('').str.contains(building, case=False, na=False, regex=False)
        ]
    
    if len(building_data) == 0:
        # Provide helpful suggestions
        available = reference_df['building_std'].dropna().unique().tolist()[:15]
        return {
            "error": "Building not found",
            "searched": building,
            "suggestion": f"Try: {', '.join(available[:5])}... (and {len(available)-5} more)",
            "tip": "Common buildings: Shoreline, Oceana, Fairmont, Marina, Ellington, Seven Palm"
        }
    
    # Filter by bedrooms if specified
    if bedrooms is not None:
        building_data = building_data[building_data['bedrooms'] == bedrooms]
        if len(building_data) == 0:
            return {"error": f"No data for {bedrooms}-bed units in {building}"}
    
    actual_building = building_data['building_std'].mode().iloc[0] if not building_data['building_std'].mode().empty else building
    
    stats = {
        "building_searched": building,
        "building_matched": display_name or actual_building,
        "building": actual_building,
        "match_confidence": match_confidence or "direct",
        "filter": f"{bedrooms}-bed units" if bedrooms is not None else "All units",
        "total_transactions": len(building_data),
        "size_stats_sqft": {
            "average": int(round(building_data['size_sqft'].mean(), 0)),
            "min": int(round(building_data['size_sqft'].min(), 0)),
            "max": int(round(building_data['size_sqft'].max(), 0)),
            "median": int(round(building_data['size_sqft'].median(), 0))
        },
        "bedroom_breakdown": {}
    }
    
    # PRICING DATA - Critical for AI responses
    price_data = building_data[building_data['sale_price_aed'].notna()]
    if len(price_data) > 0:
        avg_price = price_data['sale_price_aed'].mean()
        stats['pricing'] = {
            "has_pricing_data": True,
            "transactions_with_price": len(price_data),
            "avg_price_aed": int(round(avg_price, 0)),
            "min_price_aed": int(round(price_data['sale_price_aed'].min(), 0)),
            "max_price_aed": int(round(price_data['sale_price_aed'].max(), 0)),
            "avg_price_usd": int(round(avg_price * 0.27, 0)),
            "min_price_usd": int(round(price_data['sale_price_aed'].min() * 0.27, 0)),
            "max_price_usd": int(round(price_data['sale_price_aed'].max() * 0.27, 0)),
        }
        
        # Price per sqft
        psf_data = price_data[price_data['price_psf_aed'].notna()]
        if len(psf_data) > 0:
            stats['pricing']['avg_psf_aed'] = int(round(psf_data['price_psf_aed'].mean(), 0))
            stats['pricing']['min_psf_aed'] = int(round(psf_data['price_psf_aed'].min(), 0))
            stats['pricing']['max_psf_aed'] = int(round(psf_data['price_psf_aed'].max(), 0))
        
        # Date range
        date_data = price_data[price_data['sale_date'].notna()]
        if len(date_data) > 0:
            min_date = date_data['sale_date'].min()
            max_date = date_data['sale_date'].max()
            stats['pricing']['date_range'] = f"{min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}"
        
        # Recent sales (top 10 by date) with complete transaction details
        recent = price_data.nlargest(10, 'sale_date') if 'sale_date' in price_data.columns and price_data['sale_date'].notna().any() else price_data.head(10)
        stats['recent_sales'] = []
        for _, row in recent.iterrows():
            # Basic pricing info
            sale = {
                'price_aed': int(row['sale_price_aed']) if pd.notna(row.get('sale_price_aed')) else None,
                'price_usd': int(row['sale_price_aed'] * 0.27) if pd.notna(row.get('sale_price_aed')) else None,
                'size_sqft': int(row['size_sqft']) if pd.notna(row.get('size_sqft')) else None,
                'bedrooms': 'Studio' if row.get('bedrooms') == 0 else f"{int(row['bedrooms'])}-bed" if pd.notna(row.get('bedrooms')) else 'Unknown',
            }
            
            # Price per sqft
            if pd.notna(row.get('price_psf_aed')):
                sale['psf_aed'] = int(row['price_psf_aed'])
            
            # Transaction date with data age
            if pd.notna(row.get('sale_date')):
                sale['date'] = row['sale_date'].strftime('%Y-%m-%d')
                if BUILDING_INTELLIGENCE_AVAILABLE:
                    sale['data_age'] = calculate_data_age(row['sale_date'])
            
            # Unit number - now available from scraped Property Monitor data
            unit_no = str(row.get('unit_no', '')).strip()
            if unit_no and unit_no != 'nan' and unit_no != '':
                if BUILDING_INTELLIGENCE_AVAILABLE:
                    sale['unit_number'] = normalize_unit_number(unit_no)
                else:
                    sale['unit_number'] = unit_no
                sale['unit_number_raw'] = unit_no
            else:
                sale['unit_number'] = 'N/A'
            
            # Floor level
            floor = str(row.get('floor_level', '')).strip()
            sale['floor'] = floor if floor and floor != 'nan' else 'N/A'
            
            # Developer (seller for primary sales)
            developer = str(row.get('developer', '')).strip()
            sale['developer'] = developer if developer and developer != 'nan' else 'N/A'
            
            # View type
            view = str(row.get('view', '')).strip()
            sale['view'] = view if view and view != 'nan' else 'N/A'
            
            # Unit type validation
            if BUILDING_INTELLIGENCE_AVAILABLE and pd.notna(row.get('bedrooms')):
                is_valid, validation_msg = validate_unit_type(actual_building, row['bedrooms'])
                if not is_valid:
                    sale['unit_type_valid'] = False
                    sale['validation_warning'] = validation_msg
                else:
                    sale['unit_type_valid'] = True
            
            # Data source indicator
            sale['data_source'] = 'Property Monitor Title Deed'
            sale['confidence'] = 'high'
            
            stats['recent_sales'].append(sale)
    else:
        stats['pricing'] = {
            "has_pricing_data": False,
            "note": "Size data available but no pricing in reference data for this building"
        }
    
    # Breakdown by bedroom
    for beds in building_data['bedrooms'].dropna().unique():
        bed_data = building_data[building_data['bedrooms'] == beds]
        bed_label = 'Studio' if beds == 0 else f'{int(beds)}-bed'
        breakdown = {
            'count': len(bed_data),
            'avg_sqft': int(round(bed_data['size_sqft'].mean(), 0)) if len(bed_data) > 0 else 0
        }
        # Add pricing to breakdown
        bed_price_data = bed_data[bed_data['sale_price_aed'].notna()]
        if len(bed_price_data) > 0:
            breakdown['avg_price_aed'] = int(round(bed_price_data['sale_price_aed'].mean(), 0))
            breakdown['avg_price_usd'] = int(round(bed_price_data['sale_price_aed'].mean() * 0.27, 0))
            psf = bed_price_data[bed_price_data['price_psf_aed'].notna()]
            if len(psf) > 0:
                breakdown['avg_psf_aed'] = int(round(psf['price_psf_aed'].mean(), 0))
        stats['bedroom_breakdown'][bed_label] = breakdown
    
    return stats


def _get_median_market_price(reference_df: pd.DataFrame, building: str, bedrooms: Optional[int] = None) -> Optional[float]:
    """Return median sale_price_aed for building (and optional bedrooms). Uses same building resolution as get_market_stats_for_ai."""
    if reference_df is None or reference_df.empty or 'sale_price_aed' not in reference_df.columns:
        return None
    canonical_name = None
    if BUILDING_INTELLIGENCE_AVAILABLE:
        canonical_name, _, _ = resolve_building_name(building)
    building_data = pd.DataFrame()
    if canonical_name:
        building_data = reference_df[
            reference_df['building_std'].fillna('').str.contains(canonical_name, case=False, na=False, regex=False)
        ]
        if len(building_data) == 0 and 'sub_loc_2' in reference_df.columns:
            building_data = reference_df[
                reference_df['sub_loc_2'].fillna('').str.contains(canonical_name, case=False, na=False, regex=False)
            ]
    if len(building_data) == 0:
        building_data = reference_df[
            reference_df['building_std'].fillna('').str.contains(building, case=False, na=False, regex=False)
        ]
    if len(building_data) == 0 and 'building_family' in reference_df.columns:
        building_data = reference_df[
            reference_df['building_family'].fillna('').str.contains(building, case=False, na=False, regex=False)
        ]
    if len(building_data) == 0 and 'sub_loc_2' in reference_df.columns:
        building_data = reference_df[
            reference_df['sub_loc_2'].fillna('').str.contains(building, case=False, na=False, regex=False)
        ]
    if building_data.empty:
        return None
    if bedrooms is not None:
        building_data = building_data[building_data['bedrooms'] == bedrooms]
    price_data = building_data[building_data['sale_price_aed'].notna()]
    if len(price_data) == 0:
        return None
    return float(price_data['sale_price_aed'].median())


def _parse_listing_price_to_aed(val) -> Optional[float]:
    """Parse listing_price string to numeric AED (handles commas, M, million)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().replace(',', '')
    if not s or s.lower() in ('nan', '', 'n/a'):
        return None
    mult = 1.0
    if s.upper().endswith('M'):
        s = s[:-1].strip()
        mult = 1e6
    elif 'million' in s.lower():
        s = re.sub(r'million', '', s, flags=re.I).strip()
        mult = 1e6
    elif s.upper().endswith('K'):
        s = s[:-1].strip()
        mult = 1e3
    n = pd.to_numeric(s, errors='coerce')
    if pd.isna(n) or n <= 0:
        return None
    return float(n * mult)


def get_listings_below_market_for_ai(
    leads_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    building: Optional[str] = None,
    bedrooms: Optional[int] = None,
    below_pct: float = 10,
    limit: int = 25
) -> Dict:
    """
    Find scraped PropertyFinder listings priced below the median title-deed market for that building (and optional bedrooms).
    Returns list of dicts with listing_price_aed, market_benchmark_aed, discount_pct, and listing/owner fields.
    """
    if leads_df is None or leads_df.empty:
        return {"listings": [], "message": "No lead data available"}
    if reference_df is None or reference_df.empty:
        return {"listings": [], "message": "No title deed reference data available"}

    if 'listing_price' not in leads_df.columns:
        return {"listings": [], "message": "No scraped listings with listing_price in database"}

    # Filter to rows with non-empty listing_price
    has_price = leads_df['listing_price'].fillna('').astype(str).str.strip() != ''
    candidates = leads_df[has_price].copy()

    # Optional building filter (substring match on building_name)
    if building and building.strip():
        build_lower = building.strip().lower()
        candidates = candidates[
            candidates['building_name'].fillna('').astype(str).str.lower().str.contains(build_lower, regex=False, na=False)
        ]
    if bedrooms is not None:
        candidates = candidates[candidates['bedrooms'] == bedrooms]

    if candidates.empty:
        return {"listings": [], "message": "No listings match the filters"}

    # Parse listing_price to numeric AED
    candidates['_listing_aed'] = candidates['listing_price'].apply(_parse_listing_price_to_aed)
    candidates = candidates[candidates['_listing_aed'].notna() & (candidates['_listing_aed'] > 0)]

    if candidates.empty:
        return {"listings": [], "message": "No valid numeric listing prices found"}

    results = []
    for _, row in candidates.iterrows():
        bname = (row.get('building_name') or '').strip() or None
        beds = row.get('bedrooms')
        if pd.isna(beds):
            beds = None
        else:
            try:
                beds = int(beds)
            except (TypeError, ValueError):
                beds = None
        median_price = _get_median_market_price(reference_df, bname or '', beds) if bname else None
        if median_price is None or median_price <= 0:
            continue
        listing_aed = row['_listing_aed']
        discount_pct = (1 - listing_aed / median_price) * 100
        if discount_pct < below_pct:
            continue
        results.append({
            "building_name": bname,
            "unit_number": str(row.get('unit_number') or '').strip() or None,
            "bedrooms": beds,
            "size_sqft": int(row['size_sqft']) if pd.notna(row.get('size_sqft')) and row['size_sqft'] else None,
            "listing_price_aed": int(round(listing_aed, 0)),
            "market_benchmark_aed": int(round(median_price, 0)),
            "discount_pct": round(discount_pct, 1),
            "listing_url": str(row.get('listing_url') or '').strip() or None,
            "owner_name": str(row.get('owner_name') or '').strip() or None,
            "phone": str(row.get('phone') or '').strip() or None,
            "listing_type": str(row.get('listing_type') or '').strip() or None,
        })

    results.sort(key=lambda x: x["discount_pct"], reverse=True)
    results = results[:limit]
    return {"listings": results, "count": len(results)}


def get_portfolio_summary_for_ai(leads_df: pd.DataFrame, owner_name: str) -> Dict:
    """
    Get portfolio summary for a specific owner.
    Returns all properties owned and aggregate stats.
    """
    if leads_df is None or leads_df.empty:
        return {"error": "No lead data available"}
    
    owner_leads = leads_df[
        leads_df['owner_name'].fillna('').str.contains(owner_name, case=False, na=False)
    ]
    
    if len(owner_leads) == 0:
        return {"error": f"No properties found for owner: {owner_name}"}
    
    # Get unique owner name (most common match)
    actual_owner = owner_leads['owner_name'].mode().iloc[0] if not owner_leads['owner_name'].mode().empty else owner_name
    
    portfolio = {
        "owner_name": actual_owner,
        "total_properties": len(owner_leads),
        "buildings": list(owner_leads['building_name'].dropna().unique()),
        "units": list(owner_leads['unit_number'].dropna().unique()),
        "total_bedrooms": int(owner_leads['bedrooms'].dropna().sum()),
        "total_size_sqft": int(owner_leads['size_sqft'].dropna().sum()),
        "phone_numbers": list(set([
            p.strip() for phones in owner_leads['phone'].dropna() 
            for p in str(phones).split('|') if p.strip()
        ])),
        "properties": []
    }
    
    # List individual properties
    for _, row in owner_leads.iterrows():
        beds = row.get('bedrooms')
        beds_str = 'Studio' if beds == 0 else f"{int(beds)}-bed" if pd.notna(beds) else 'Unknown'
        
        portfolio['properties'].append({
            'building': row.get('building_name', 'Unknown'),
            'unit': row.get('unit_number', 'N/A'),
            'bedrooms': beds_str,
            'size_sqft': int(row['size_sqft']) if pd.notna(row.get('size_sqft')) else None
        })
    
    return portfolio


def find_potential_owners_for_ai(leads_df: pd.DataFrame, building: str, bedrooms: int = None, 
                                  floor: str = None, size_sqft: int = None,
                                  unit_number: str = None) -> Dict:
    """
    Find potential current owners in lead database that match a title deed transaction.
    Enhanced with fuzzy building matching, unit number matching, and phone validation.
    
    Priority matching:
    1. Exact unit number match (if provided)
    2. Building + bedrooms + size match
    3. Building + floor match
    """
    if leads_df is None or leads_df.empty:
        return {"error": "No lead data available"}
    
    # Use building intelligence for fuzzy matching if available
    building_std = building
    display_name = building
    if BUILDING_INTELLIGENCE_AVAILABLE:
        canonical, display_name, _ = resolve_building_name(building)
        if canonical:
            building_std = canonical
    else:
        building_std = standardize_building_name(building) or building
    
    # Filter by building
    matches = leads_df[
        leads_df['building_name'].fillna('').str.contains(building_std, case=False, na=False, regex=False) |
        leads_df['building_name'].fillna('').str.contains(building, case=False, na=False, regex=False)
    ].copy()
    
    if len(matches) == 0:
        return {"found": False, "reason": f"No leads found for building: {display_name or building}"}
    
    # STRATEGY 1: Exact unit number match (highest priority)
    if unit_number and unit_number not in ['N/A', 'nan', '']:
        unit_normalized = unit_number
        if BUILDING_INTELLIGENCE_AVAILABLE:
            unit_normalized = normalize_unit_number(unit_number)
        
        # Normalize unit numbers in matches for comparison
        matches['unit_normalized'] = matches['unit_number'].apply(
            lambda x: normalize_unit_number(x) if BUILDING_INTELLIGENCE_AVAILABLE else str(x).strip()
        )
        
        unit_matches = matches[matches['unit_normalized'] == unit_normalized]
        if len(unit_matches) > 0:
            matches = unit_matches
    
    # STRATEGY 2: Filter by bedrooms if specified
    if bedrooms is not None and len(matches) > 1:
        bed_matches = matches[matches['bedrooms'] == bedrooms]
        if len(bed_matches) > 0:
            matches = bed_matches
    
    # STRATEGY 3: Filter by approximate size (within 10% tolerance)
    if size_sqft and size_sqft > 0 and len(matches) > 1:
        tolerance = size_sqft * 0.10
        size_matches = matches[
            (matches['size_sqft'] >= size_sqft - tolerance) & 
            (matches['size_sqft'] <= size_sqft + tolerance)
        ]
        if len(size_matches) > 0:
            matches = size_matches
    
    # STRATEGY 4: Filter by floor if specified
    if floor and floor not in ['N/A', 'nan', ''] and len(matches) > 1:
        floor_matches = matches[
            matches['unit_number'].fillna('').str.contains(str(floor), case=False, na=False)
        ]
        if len(floor_matches) > 0:
            matches = floor_matches
    
    if len(matches) == 0:
        return {
            "found": False, 
            "reason": "No matching units found with given criteria",
            "suggestion": "Try broader search or check building name"
        }
    
    # Determine match type
    match_type = "exact_unit" if unit_number and len(matches) == 1 else \
                 "exact_match" if len(matches) == 1 else "multiple_candidates"
    
    # Return potential matches with enhanced data
    results = {
        "found": True,
        "match_count": len(matches),
        "match_type": match_type,
        "confidence": "high" if match_type == "exact_unit" else "medium" if len(matches) <= 3 else "low",
        "building_matched": display_name or building_std,
        "potential_owners": []
    }
    
    for _, row in matches.head(5).iterrows():
        phone_raw = str(row.get('phone', '')).strip()
        has_phone = phone_raw and phone_raw != 'nan' and phone_raw != 'No phone'
        
        owner_data = {
            "owner_name": str(row.get('owner_name', 'N/A')),
            "unit_number": str(row.get('unit_number', 'N/A')),
            "bedrooms": 'Studio' if row.get('bedrooms') == 0 else f"{int(row['bedrooms'])}-bed" if pd.notna(row.get('bedrooms')) else 'Unknown',
            "size_sqft": int(row['size_sqft']) if pd.notna(row.get('size_sqft')) else None,
            "phone": phone_raw if has_phone else 'No phone',
            "date_in_db": str(row.get('date', 'N/A'))
        }
        
        # Add phone validation
        if has_phone and BUILDING_INTELLIGENCE_AVAILABLE:
            phone_validation = validate_phone_number(phone_raw)
            owner_data['phone_quality'] = phone_validation.get('quality', '⚠️')
            owner_data['phone_status'] = phone_validation.get('status', 'unknown')
            owner_data['phone_formatted'] = format_phone_number(phone_raw)
        
        # Add data age
        if 'date' in row and pd.notna(row.get('date')) and BUILDING_INTELLIGENCE_AVAILABLE:
            owner_data['data_age'] = calculate_data_age(row['date'])
        
        results["potential_owners"].append(owner_data)
    
    return results


def cross_reference_sale_with_leads_for_ai(leads_df: pd.DataFrame, building: str, 
                                            bedrooms: int = None, floor: str = None,
                                            size_sqft: int = None, sale_date: str = None,
                                            unit_number: str = None, buyer_name: str = None) -> Dict:
    """
    Cross-reference a title deed sale with the lead database.
    Enhanced with unit number matching and portfolio investor detection.
    
    Parameters:
    - building: Building name (supports fuzzy matching)
    - unit_number: Unit number from title deed (highest priority match)
    - bedrooms: Number of bedrooms
    - floor: Floor number/level
    - size_sqft: Size in square feet
    - buyer_name: Buyer name for fuzzy matching (if unit not found)
    """
    result = find_potential_owners_for_ai(
        leads_df=leads_df,
        building=building,
        bedrooms=bedrooms,
        floor=floor,
        size_sqft=size_sqft,
        unit_number=unit_number
    )
    
    if result.get("found"):
        # Generic names to ignore when checking portfolios
        GENERIC_NAMES = {'seller', 'buyer', 'owner', 'n/a', 'na', 'unknown', 'tbd', 
                         'not available', 'pending', 'none', ''}
        
        # Check for portfolio owners (same owner with multiple units)
        for owner in result.get("potential_owners", []):
            owner_name = owner.get("owner_name", "")
            
            # Skip generic names
            if not owner_name or owner_name.lower() in GENERIC_NAMES:
                continue
            
            # Find all units by this owner
            owner_units = leads_df[
                leads_df['owner_name'].fillna('').str.contains(owner_name, case=False, na=False, regex=False)
            ]
            
            if len(owner_units) > 1:
                # Calculate total portfolio value if size data available
                total_sqft = owner_units['size_sqft'].sum() if 'size_sqft' in owner_units.columns else 0
                
                owner["portfolio"] = {
                    "is_investor": True,
                    "investor_type": "Portfolio Investor" if len(owner_units) >= 3 else "Multi-Unit Owner",
                    "total_units": len(owner_units),
                    "unit_numbers": owner_units['unit_number'].dropna().tolist()[:10],
                    "total_sqft": int(total_sqft) if total_sqft > 0 else None,
                    "buildings": owner_units['building_name'].unique().tolist()[:5]
                }
            else:
                owner["portfolio"] = {
                    "is_investor": False,
                    "investor_type": "Single Unit Owner",
                    "total_units": 1
                }
        
        # Add matching methodology note
        if unit_number and result.get("match_type") == "exact_unit":
            result["note"] = (
                "✅ EXACT UNIT MATCH: Found owner info for this specific unit. "
                "Contact info is from lead database."
            )
        else:
            result["note"] = (
                "Matched from lead database by building + criteria. "
                "Verify ownership before contacting (data may be outdated)."
            )
    else:
        # Provide helpful failure info
        if buyer_name and buyer_name not in ['N/A', 'nan', '', 'Unknown']:
            # Try to find by name as fallback
            name_matches = leads_df[
                leads_df['owner_name'].fillna('').str.contains(buyer_name.split()[0], case=False, na=False, regex=False)
            ]
            if len(name_matches) > 0:
                result["possible_name_match"] = True
                result["name_match_count"] = len(name_matches)
                result["suggestion"] = f"No unit match, but found {len(name_matches)} leads with similar name"
    
    return result


def get_building_units_for_ai(leads_df: pd.DataFrame, building: str, bedrooms: int = None) -> Dict:
    """
    Get all units in a building with owner contact information.
    Enhanced with phone validation and data quality indicators.
    """
    if leads_df is None or leads_df.empty:
        return {"error": "No lead data available"}
    
    # Generic names to filter out
    GENERIC_NAMES = {'seller', 'buyer', 'owner', 'n/a', 'na', 'unknown', 'tbd', 
                     'not available', 'pending', 'none', ''}
    
    # Use building intelligence for fuzzy matching if available
    building_std = building
    display_name = building
    if BUILDING_INTELLIGENCE_AVAILABLE:
        canonical, display_name, _ = resolve_building_name(building)
        if canonical:
            building_std = canonical
    else:
        building_std = standardize_building_name(building) or building
    
    # Search for building - bidirectional containment
    # Forward: search term in building_name (e.g. "Fairmont" in "The Fairmont Palm Residence North")
    # Reverse: building_name in search term (e.g. "Fairmont" contained in "The Fairmont Palm Residences")
    building_std_lower = building_std.lower()
    building_lower = building.lower()
    matches = leads_df[
        leads_df['building_name'].fillna('').str.contains(building_std, case=False, na=False, regex=False) |
        leads_df['building_name'].fillna('').str.contains(building, case=False, na=False, regex=False) |
        leads_df['building_name'].fillna('').apply(lambda x: bool(x) and x.lower() in building_std_lower) |
        leads_df['building_name'].fillna('').apply(lambda x: bool(x) and x.lower() in building_lower)
    ].copy()
    
    if len(matches) == 0:
        return {"found": False, "reason": f"No leads found for: {building}"}
    
    # Filter by bedrooms if specified
    if bedrooms is not None:
        matches = matches[matches['bedrooms'] == bedrooms]
        if len(matches) == 0:
            return {"found": False, "reason": f"No {bedrooms}-bed units found"}
    
    # Sort by unit number
    matches = matches.sort_values('unit_number')
    
    # Get unique units - prioritize entries with real owner names and phones
    units = []
    units_with_contacts = []
    seen_units = set()
    
    for _, row in matches.iterrows():
        unit = str(row.get('unit_number', '')).strip()
        if unit and unit != 'nan' and unit not in seen_units:
            seen_units.add(unit)
            phone_raw = str(row.get('phone', '')).strip()
            owner = str(row.get('owner_name', 'N/A')).strip()
            
            # Check if owner name is generic
            is_generic = owner.lower() in GENERIC_NAMES
            has_phone = phone_raw and phone_raw != 'nan' and phone_raw != 'No phone'
            
            # Normalize unit number
            unit_normalized = unit
            if BUILDING_INTELLIGENCE_AVAILABLE:
                unit_normalized = normalize_unit_number(unit)
            
            unit_data = {
                "unit_number": unit_normalized,
                "unit_number_raw": unit,
                "owner_name": owner if not is_generic else "Unknown",
                "phone": phone_raw if has_phone else 'No phone',
                "bedrooms": 'Studio' if row.get('bedrooms') == 0 else f"{int(row['bedrooms'])}-bed" if pd.notna(row.get('bedrooms')) else 'N/A',
                "size_sqft": int(row['size_sqft']) if pd.notna(row.get('size_sqft')) else None
            }
            
            # Split multiple phone numbers
            if has_phone and '|' in phone_raw:
                unit_data['phones'] = [p.strip() for p in phone_raw.split('|') if p.strip()]
            
            # Add phone validation
            if has_phone and BUILDING_INTELLIGENCE_AVAILABLE:
                # Validate the first phone number
                first_phone = phone_raw.split('|')[0].strip() if '|' in phone_raw else phone_raw
                phone_validation = validate_phone_number(first_phone)
                unit_data['phone_quality'] = phone_validation.get('quality', '⚠️')
                unit_data['phone_status'] = phone_validation.get('status', 'unknown')
                unit_data['phone_formatted'] = format_phone_number(first_phone)
            
            # Add data age if date available
            if 'date' in row and pd.notna(row.get('date')):
                unit_data['date'] = str(row['date'])[:10]  # YYYY-MM-DD format
                if BUILDING_INTELLIGENCE_AVAILABLE:
                    unit_data['data_age'] = calculate_data_age(row['date'])
            
            # Prioritize units with contacts
            if has_phone or not is_generic:
                units_with_contacts.append(unit_data)
            else:
                units.append(unit_data)
    
    # Combine: contacts first, then rest
    all_units = units_with_contacts + units
    
    # Identify portfolio owners (exclude generic names)
    real_owners = matches[~matches['owner_name'].fillna('').str.lower().isin(GENERIC_NAMES)]
    owner_counts = real_owners['owner_name'].value_counts()
    portfolio_owners = owner_counts[owner_counts > 1].to_dict()
    
    return {
        "found": True,
        "building": building_std,
        "filter": f"{bedrooms}-bed units" if bedrooms else "All units",
        "total_units": len(all_units),
        "units_with_phone": sum(1 for u in all_units if u['phone'] != 'No phone'),
        "units_with_real_owner": len(units_with_contacts),
        "portfolio_owners": [
            {"name": name, "unit_count": count} 
            for name, count in list(portfolio_owners.items())[:5]
        ],
        "units": all_units[:25]  # Return top 25 units (contacts first)
    }


def get_complete_building_intel_for_ai(reference_df: pd.DataFrame, leads_df: pd.DataFrame, 
                                        building: str, bedrooms: int = None,
                                        matched_only: bool = False, limit: int = 10) -> Dict:
    """
    COMPREHENSIVE FUNCTION: Get market stats + lead contacts in ONE call.
    
    Cross-referencing by unit number between title deeds and lead database.
    
    Parameters:
        matched_only: If True, only return sales where we have owner contact info.
        limit: Max number of recent sales to return (default 10).
    
    Returns:
        - SECTION A: Market Activity (title deeds with unit numbers and pricing)
        - SECTION B: Owner Directory (lead database with contacts)
        - SECTION C: Cross-referenced matches (sale + owner linked by unit number)
    """
    result = {
        "building_searched": building,
        "filter": f"{bedrooms}-bed" if bedrooms else "All bedrooms",
        "matched_only_mode": matched_only
    }
    
    # ═══════════════════════════════════════════════════════════════════
    # SECTION A: MARKET ACTIVITY (Title Deeds with unit numbers)
    # ═══════════════════════════════════════════════════════════════════
    market_stats = get_market_stats_for_ai(reference_df, building, bedrooms)
    
    if "error" in market_stats:
        result["section_a_market_activity"] = {
            "available": False, 
            "error": market_stats["error"],
            "source": "Title Deeds (Property Monitor)"
        }
    else:
        result["section_a_market_activity"] = {
            "available": True,
            "source": "Title Deeds (Property Monitor - scraped with unit numbers)",
            "building_matched": market_stats.get("building_matched", building),
            "match_confidence": market_stats.get("match_confidence", "direct"),
            "total_transactions": market_stats.get("total_transactions", 0),
            "pricing": market_stats.get("pricing", {}),
            "size_stats": market_stats.get("size_stats_sqft", {}),
            "bedroom_breakdown": market_stats.get("bedroom_breakdown", {}),
            "recent_sales": market_stats.get("recent_sales", []),
            "note": "Unit numbers included from scraped data"
        }
    
    # ═══════════════════════════════════════════════════════════════════
    # UNIT-NUMBER FALLBACK: If no market data by building name
    # Use unit numbers from lead database to find transactions
    # This handles cases where Property Monitor groups buildings differently
    # (e.g., "The 8" filed under "The Crescent")
    # ═══════════════════════════════════════════════════════════════════
    unit_fallback_used = False
    parent_building_note = None
    
    if (not result["section_a_market_activity"]["available"] and 
        leads_df is not None and not leads_df.empty):
        
        # First, try to find leads for this building
        building_std = building
        if BUILDING_INTELLIGENCE_AVAILABLE:
            canonical, _, _ = resolve_building_name(building)
            if canonical:
                building_std = canonical
        
        # Search for leads using same bidirectional logic
        building_std_lower = building_std.lower()
        building_lower = building.lower()
        temp_leads = leads_df[
            leads_df['building_name'].fillna('').str.contains(building_std, case=False, na=False, regex=False) |
            leads_df['building_name'].fillna('').str.contains(building, case=False, na=False, regex=False) |
            leads_df['building_name'].fillna('').apply(lambda x: bool(x) and x.lower() in building_std_lower) |
            leads_df['building_name'].fillna('').apply(lambda x: bool(x) and x.lower() in building_lower)
        ]
        
        if len(temp_leads) > 0:
            # Extract unit numbers from leads
            lead_unit_numbers = []
            for _, row in temp_leads.iterrows():
                unit_raw = str(row.get('unit_number', '')).strip()
                if unit_raw and unit_raw != 'nan' and unit_raw != '':
                    lead_unit_numbers.append(unit_raw)
                    if BUILDING_INTELLIGENCE_AVAILABLE:
                        lead_unit_numbers.append(normalize_unit_number(unit_raw))
            
            # Remove duplicates
            lead_unit_numbers = list(set([u for u in lead_unit_numbers if u]))
            
            if lead_unit_numbers:
                # Search reference data for these unit numbers
                unit_matches = reference_df[
                    reference_df['unit_no'].fillna('').astype(str).str.strip().isin(lead_unit_numbers)
                ]
                
                # Filter by bedrooms if specified
                if bedrooms is not None and len(unit_matches) > 0:
                    unit_matches = unit_matches[unit_matches['bedrooms'] == bedrooms]
                
                if len(unit_matches) > 0:
                    # Found transactions by unit number!
                    unit_fallback_used = True
                    parent_building = unit_matches['building_std'].mode().iloc[0] if 'building_std' in unit_matches.columns and not unit_matches['building_std'].mode().empty else unit_matches['sub_loc_2'].mode().iloc[0] if not unit_matches['sub_loc_2'].mode().empty else 'Unknown'
                    parent_building_note = f"Transactions found under '{parent_building}' by matching unit numbers"
                    
                    # Build market stats from these matched transactions
                    # Use similar logic to get_market_stats_for_ai but with the filtered data
                    stats = {
                        "building_searched": building,
                        "building_matched": f"{building} (units found in {parent_building})",
                        "match_confidence": "unit_number_fallback",
                        "total_transactions": len(unit_matches),
                        "fallback_note": parent_building_note
                    }
                    
                    # Size stats
                    if 'size_sqft' in unit_matches.columns:
                        stats["size_stats_sqft"] = {
                            "average": int(round(unit_matches['size_sqft'].mean(), 0)),
                            "min": int(round(unit_matches['size_sqft'].min(), 0)),
                            "max": int(round(unit_matches['size_sqft'].max(), 0)),
                            "median": int(round(unit_matches['size_sqft'].median(), 0))
                        }
                    
                    # Pricing data
                    price_data = unit_matches[unit_matches['sale_price_aed'].notna()]
                    if len(price_data) > 0:
                        avg_price = price_data['sale_price_aed'].mean()
                        stats['pricing'] = {
                            "has_pricing_data": True,
                            "transactions_with_price": len(price_data),
                            "avg_price_aed": int(round(avg_price, 0)),
                            "min_price_aed": int(round(price_data['sale_price_aed'].min(), 0)),
                            "max_price_aed": int(round(price_data['sale_price_aed'].max(), 0)),
                            "avg_price_usd": int(round(avg_price * 0.27, 0)),
                        }
                        
                        # Price per sqft
                        psf_data = price_data[price_data['price_psf_aed'].notna()]
                        if len(psf_data) > 0:
                            stats['pricing']['avg_psf_aed'] = int(round(psf_data['price_psf_aed'].mean(), 0))
                    
                    # Recent sales
                    recent = price_data.nlargest(10, 'sale_date') if 'sale_date' in price_data.columns and price_data['sale_date'].notna().any() else price_data.head(10)
                    stats['recent_sales'] = []
                    for _, row in recent.iterrows():
                        sale = {
                            'price_aed': int(row['sale_price_aed']) if pd.notna(row.get('sale_price_aed')) else None,
                            'price_usd': int(row['sale_price_aed'] * 0.27) if pd.notna(row.get('sale_price_aed')) else None,
                            'size_sqft': int(row['size_sqft']) if pd.notna(row.get('size_sqft')) else None,
                            'bedrooms': 'Studio' if row.get('bedrooms') == 0 else f"{int(row['bedrooms'])}-bed" if pd.notna(row.get('bedrooms')) else 'Unknown',
                            'unit_number': str(row.get('unit_no', 'N/A')).strip() if pd.notna(row.get('unit_no')) else 'N/A',
                            'floor': str(row.get('floor_level', 'N/A')).strip() if pd.notna(row.get('floor_level')) else 'N/A',
                        }
                        if pd.notna(row.get('price_psf_aed')):
                            sale['psf_aed'] = int(row['price_psf_aed'])
                        if pd.notna(row.get('sale_date')):
                            sale['date'] = row['sale_date'].strftime('%Y-%m-%d')
                            if BUILDING_INTELLIGENCE_AVAILABLE:
                                sale['data_age'] = calculate_data_age(row['sale_date'])
                        stats['recent_sales'].append(sale)
                    
                    # Update Section A with fallback data
                    result["section_a_market_activity"] = {
                        "available": True,
                        "source": f"Title Deeds (via unit number matching from {parent_building})",
                        "building_matched": stats["building_matched"],
                        "match_confidence": "unit_number_fallback",
                        "total_transactions": stats["total_transactions"],
                        "pricing": stats.get("pricing", {}),
                        "size_stats": stats.get("size_stats_sqft", {}),
                        "recent_sales": stats.get("recent_sales", []),
                        "note": parent_building_note
                    }
    
    # ═══════════════════════════════════════════════════════════════════
    # BUILD FULL CONTACT LOOKUP (uncapped - for cross-referencing)
    # This queries ALL leads for the building, not just the top 20/25
    # ═══════════════════════════════════════════════════════════════════
    full_contact_lookup = {}
    GENERIC_NAMES = {'seller', 'buyer', 'owner', 'n/a', 'na', 'unknown', 'tbd', 
                     'not available', 'pending', 'none', ''}
    
    if leads_df is not None and not leads_df.empty:
        # Resolve building name for search
        building_std = building
        if BUILDING_INTELLIGENCE_AVAILABLE:
            canonical, _, _ = resolve_building_name(building)
            if canonical:
                building_std = canonical
        
        # Search leads - bidirectional containment
        # Forward: search term in building_name; Reverse: building_name in search term
        building_std_lower = building_std.lower()
        building_lower = building.lower()
        all_leads = leads_df[
            leads_df['building_name'].fillna('').str.contains(building_std, case=False, na=False, regex=False) |
            leads_df['building_name'].fillna('').str.contains(building, case=False, na=False, regex=False) |
            leads_df['building_name'].fillna('').apply(lambda x: bool(x) and x.lower() in building_std_lower) |
            leads_df['building_name'].fillna('').apply(lambda x: bool(x) and x.lower() in building_lower)
        ]
        
        # Filter by bedrooms if specified
        if bedrooms is not None and len(all_leads) > 0:
            all_leads = all_leads[all_leads['bedrooms'] == bedrooms]
        
        # Build lookup: normalized unit number -> contact info (ALL contacts)
        for _, row in all_leads.iterrows():
            unit_raw = str(row.get('unit_number', '')).strip()
            if not unit_raw or unit_raw == 'nan':
                continue
            
            unit_key = unit_raw.upper()
            if BUILDING_INTELLIGENCE_AVAILABLE:
                unit_key = normalize_unit_number(unit_raw).upper()
            
            owner = str(row.get('owner_name', 'N/A')).strip()
            is_generic = owner.lower() in GENERIC_NAMES
            phone_raw = str(row.get('phone', '')).strip()
            has_phone = phone_raw and phone_raw != 'nan' and phone_raw != 'No phone'
            
            # Only store contacts with real owner names or phone numbers
            if not is_generic or has_phone:
                # Keep the best contact per unit (prefer one with phone)
                existing = full_contact_lookup.get(unit_key)
                if existing is None or (has_phone and existing.get('phone') == 'No phone'):
                    contact_info = {
                        "unit_number": normalize_unit_number(unit_raw) if BUILDING_INTELLIGENCE_AVAILABLE else unit_raw,
                        "owner_name": owner if not is_generic else "Unknown",
                        "phone": phone_raw if has_phone else 'No phone',
                    }
                    # Split multiple phone numbers
                    if has_phone and '|' in phone_raw:
                        contact_info['phones'] = [p.strip() for p in phone_raw.split('|') if p.strip()]
                    if has_phone and BUILDING_INTELLIGENCE_AVAILABLE:
                        phone_validation = validate_phone_number(phone_raw.split('|')[0].strip())  # Validate first number
                        contact_info['phone_formatted'] = format_phone_number(phone_raw.split('|')[0].strip())
                        contact_info['phone_quality'] = phone_validation.get('quality', 'unknown')
                    # Add date if available
                    if 'date' in row and pd.notna(row.get('date')):
                        contact_info['date'] = str(row['date'])[:10]  # YYYY-MM-DD format
                        if BUILDING_INTELLIGENCE_AVAILABLE:
                            contact_info['data_age'] = calculate_data_age(row['date'])
                    full_contact_lookup[unit_key] = contact_info
    
    # ═══════════════════════════════════════════════════════════════════
    # SECTION B: OWNER DIRECTORY (Lead Database)
    # ═══════════════════════════════════════════════════════════════════
    building_units = get_building_units_for_ai(leads_df, building, bedrooms)
    
    if not building_units.get("found", False):
        result["section_b_owner_directory"] = {
            "available": False, 
            "error": building_units.get("reason", "No leads found"),
            "source": "Lead Database (Historical DLD Data)",
            "total_contacts_in_full_lookup": len(full_contact_lookup)
        }
    else:
        result["section_b_owner_directory"] = {
            "available": True,
            "source": "Lead Database (Historical DLD Data 2018-2025)",
            "total_units_tracked": building_units.get("total_units", 0),
            "units_with_phone": building_units.get("units_with_phone", 0),
            "phone_coverage_pct": round(building_units.get("units_with_phone", 0) / max(building_units.get("total_units", 1), 1) * 100, 1),
            "portfolio_investors": building_units.get("portfolio_owners", []),
            "contacts": building_units.get("units", [])[:20],
            "note": "Contacts may be previous owners if unit sold recently"
        }
    
    # ═══════════════════════════════════════════════════════════════════
    # SECTION C: CROSS-REFERENCED MATCHES
    # Uses FULL contact lookup (not capped) for maximum match coverage
    # ═══════════════════════════════════════════════════════════════════
    cross_references = []
    unmatched_sales = []
    
    recent_sales = result.get("section_a_market_activity", {}).get("recent_sales", [])
    
    for sale in recent_sales:
        unit = str(sale.get('unit_number', '')).strip().upper()
        if BUILDING_INTELLIGENCE_AVAILABLE:
            unit = normalize_unit_number(sale.get('unit_number', '')).upper()
        
        if unit and unit != 'N/A' and unit in full_contact_lookup:
            contact = full_contact_lookup[unit]
            cross_references.append({
                "unit_number": sale.get('unit_number'),
                "sale_date": sale.get('date', 'N/A'),
                "sale_price_aed": sale.get('price_aed'),
                "price_usd": sale.get('price_usd'),
                "size_sqft": sale.get('size_sqft'),
                "bedrooms": sale.get('bedrooms'),
                "psf_aed": sale.get('psf_aed'),
                "floor": sale.get('floor', 'N/A'),
                "owner_name": contact.get('owner_name', 'Unknown'),
                "phone": contact.get('phone', 'No phone'),
                "phone_formatted": contact.get('phone_formatted', ''),
                "match_type": "unit_number",
                "match_confidence": "high",
                "note": "Contact may be previous owner if unit sold recently"
            })
        else:
            unmatched_sales.append({
                "unit_number": sale.get('unit_number'),
                "sale_date": sale.get('date', 'N/A'),
                "sale_price_aed": sale.get('price_aed'),
                "price_usd": sale.get('price_usd'),
                "size_sqft": sale.get('size_sqft'),
                "bedrooms": sale.get('bedrooms'),
                "psf_aed": sale.get('psf_aed'),
                "floor": sale.get('floor', 'N/A'),
                "status": "No contact available"
            })
    
    result["section_c_cross_references"] = {
        "available": len(cross_references) > 0,
        "total_matches": len(cross_references),
        "total_unmatched": len(unmatched_sales),
        "total_sales_checked": len(recent_sales),
        "match_rate_pct": round(len(cross_references) / max(len(recent_sales), 1) * 100, 1),
        "matches": cross_references[:limit],
        "note": "Matched by unit number between title deed sales and lead database contacts"
    }
    
    # In matched_only mode, replace recent_sales with only the matched ones
    if matched_only:
        result["section_a_market_activity"]["recent_sales"] = []  # Clear unfiltered sales
        result["matched_transactions"] = cross_references[:limit]
        result["mode"] = "matched_only"
        result["message"] = f"Showing {min(len(cross_references), limit)} of {len(cross_references)} sales with known contacts"
    else:
        # Include unmatched sales separately so AI can show both
        result["section_c_cross_references"]["unmatched_sales"] = unmatched_sales[:limit]
    
    # ═══════════════════════════════════════════════════════════════════
    # DATA STATUS
    # ═══════════════════════════════════════════════════════════════════
    result["data_status"] = {
        "cross_reference_possible": True,
        "unit_numbers_available": True,
        "total_contacts_in_building": len(full_contact_lookup),
        "source": "Unit numbers scraped from Property Monitor website (Feb 2026)",
        "notes": [
            "Cross-referenced contacts shown in Section C",
            "Lead database contacts may be PREVIOUS owners if unit sold recently",
            "Verify ownership before contacting on recently sold units"
        ]
    }
    
    return result


def search_building_names_for_ai(reference_df: pd.DataFrame, search_term: str) -> Dict:
    """
    Search for buildings matching a search term.
    Returns all possible name variations.
    Use when a building search returns no results to find the correct name.
    """
    if reference_df is None or reference_df.empty:
        return {"error": "No reference data available"}
    
    search_lower = search_term.lower()
    
    # Search in building_std column
    matches = reference_df[
        reference_df['building_std'].fillna('').str.lower().str.contains(search_lower, na=False)
    ]
    
    # If no matches, try building_family
    if len(matches) == 0:
        matches = reference_df[
            reference_df['building_family'].fillna('').str.lower().str.contains(search_lower, na=False)
        ]
    
    # If still no matches, try sub_loc_2 (original building name)
    if len(matches) == 0 and 'sub_loc_2' in reference_df.columns:
        matches = reference_df[
            reference_df['sub_loc_2'].fillna('').str.lower().str.contains(search_lower, na=False)
        ]
    
    # If still no matches, try sub_loc_1 (area/location)
    if len(matches) == 0 and 'sub_loc_1' in reference_df.columns:
        matches = reference_df[
            reference_df['sub_loc_1'].fillna('').str.lower().str.contains(search_lower, na=False)
        ]
    
    if len(matches) == 0:
        # List all unique building names as suggestions
        all_buildings = reference_df['building_std'].dropna().unique().tolist()
        return {
            "found": False,
            "search_term": search_term,
            "message": f"No buildings found matching '{search_term}'",
            "suggestion": "Try a different search term or check spelling",
            "available_buildings": sorted(all_buildings)[:20]  # First 20 buildings
        }
    
    # Get unique building names with counts
    building_counts = matches['building_std'].value_counts().to_dict()
    
    building_info = []
    for name, count in building_counts.items():
        if pd.notna(name) and name:
            # Get bedroom breakdown
            bldg_data = matches[matches['building_std'] == name]
            beds_breakdown = bldg_data['bedrooms'].value_counts().to_dict()
            beds_str = ", ".join([
                f"{'Studio' if b == 0 else f'{int(b)}-bed'}: {c}" 
                for b, c in sorted(beds_breakdown.items()) if pd.notna(b)
            ])
            
            building_info.append({
                'name': name,
                'transaction_count': count,
                'bedroom_breakdown': beds_str
            })
    
    # Sort by transaction count
    building_info.sort(key=lambda x: x['transaction_count'], reverse=True)
    
    return {
        "found": True,
        "search_term": search_term,
        "total_transactions": len(matches),
        "buildings_found": len(building_info),
        "matches": building_info[:10]  # Top 10 matches
    }


def list_all_buildings_for_ai(reference_df: pd.DataFrame) -> Dict:
    """
    List all unique buildings in reference data with transaction counts.
    Use when user asks "what buildings do you have data for?"
    """
    if reference_df is None or reference_df.empty:
        return {"error": "No reference data available"}
    
    building_counts = reference_df['building_std'].value_counts().to_dict()
    
    buildings = []
    for name, count in building_counts.items():
        if pd.notna(name) and name:
            buildings.append({
                'name': name,
                'transaction_count': count
            })
    
    buildings.sort(key=lambda x: x['transaction_count'], reverse=True)
    
    return {
        "total_buildings": len(buildings),
        "total_transactions": len(reference_df),
        "buildings": buildings
    }


def get_propertyfinder_listings_for_ai(
    leads_df: pd.DataFrame,
    building: str = None,
    listing_type: str = "all",
    bedrooms: int = None,
    furnished: str = "all",
    unit_number: str = None,
    limit: int = 50
) -> str:
    """Query PropertyFinder scraped listings with filters. Returns formatted results for AI."""
    if leads_df.empty or 'source' not in leads_df.columns:
        return "No PropertyFinder data available."

    pf = leads_df[leads_df['source'].str.contains('propertyfinder', case=False, na=False)].copy()
    if pf.empty:
        return "No PropertyFinder listings found."

    if building:
        pf = pf[pf['building_name'].str.contains(building, case=False, na=False)]
    if listing_type != "all" and 'listing_type' in pf.columns:
        pf = pf[pf['listing_type'].str.lower() == listing_type.lower()]
    if bedrooms is not None:
        pf = pf[pf['bedrooms'] == bedrooms]
    if furnished != "all" and 'furnished' in pf.columns:
        pf = pf[pf['furnished'].str.contains(furnished, case=False, na=False)]
    if unit_number:
        pf = pf[pf['unit_number'].str.contains(unit_number, case=False, na=False)]

    pf = pf.head(limit)
    if pf.empty:
        return f"No PropertyFinder listings match filters: building={building}, type={listing_type}, beds={bedrooms}, furnished={furnished}"

    lines = [f"**PropertyFinder Listings** ({len(pf)} results)\n"]
    for _, row in pf.iterrows():
        owner = row.get('owner_name', 'Unknown')
        unit = row.get('unit_number', '—')
        beds = row.get('bedrooms')
        beds_str = 'Studio' if beds == 0 else f"{int(beds)}-bed" if pd.notna(beds) else '—'
        price = row.get('listing_price', '—')
        furn = row.get('furnished', '—')
        url = row.get('listing_url', '')
        count = row.get('pf_listing_count', 1)
        priority = f" [Listed {count}x - HIGH PRIORITY]" if count > 1 else ""
        lines.append(f"• **Unit {unit}** | {beds_str} | {price}{priority}")
        lines.append(f"  Owner: {owner} | Furnished: {furn}")
        if url:
            lines.append(f"  Link: {url}")
        lines.append("")
    return "\n".join(lines)
