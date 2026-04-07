"""
Rental Data Processor Module
Palm Jumeirah Real Estate Intelligence System

Provides:
- load_rental_data()                   -- Load and clean rental CSV
- get_expiring_leases()                -- Leases expiring within N days
- get_lease_renewal_history()          -- Rental history for a specific unit
- get_rental_yield_by_building()       -- Calculate gross rental yield
- get_unit_rental_status()             -- Check if a unit is currently rented
- get_rental_intel_for_ai()            -- AI tool function for rental queries
"""

import pandas as pd
import numpy as np
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple


RENTAL_DATA_PATH = Path('scraped_data/palm_jumeirah_rentals.csv')
REIDIN_RENTALS_PARQUET = Path('data/reidin_rentals.parquet')
REIDIN_RENTALS_CSV = Path('data/reidin_rentals.csv')


# =============================================================================
# DATA LOADING
# =============================================================================

def _clean_bedrooms_numeric(val):
    """Studio -> 0, parse numbers from strings like '3 B/R' or '2'."""
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if 'studio' in s or s == 's' or s == '0':
        return 0
    match = re.search(r'(\d+)', s)
    return int(match.group(1)) if match else None


def load_rental_data() -> pd.DataFrame:
    """
    Load and clean rental data from ALL sources (PropertyMonitor + Reidin).

    Sources:
      1. scraped_data/palm_jumeirah_rentals.csv  (PropertyMonitor Ejari)
      2. data/reidin_rentals.parquet             (Reidin DLD)

    Returns:
        Unified DataFrame. Empty DataFrame if no files exist.
    """
    frames = []

    # Source 1: PropertyMonitor Ejari
    if RENTAL_DATA_PATH.exists():
        try:
            pm = pd.read_csv(RENTAL_DATA_PATH, encoding='utf-8', low_memory=False)
            if not pm.empty:
                pm['_source'] = 'propertymonitor'
                frames.append(pm)
                print(f"[rental_processor] PM: {len(pm):,} rows")
        except Exception as e:
            print(f"[rental_processor] Error loading PM: {e}")

    # Source 2: Reidin DLD
    for rpath in [REIDIN_RENTALS_PARQUET, REIDIN_RENTALS_CSV]:
        if rpath.exists():
            try:
                rdf = pd.read_parquet(rpath) if rpath.suffix == '.parquet' else pd.read_csv(rpath)
                if not rdf.empty:
                    if 'bedrooms' in rdf.columns:
                        rdf['bedrooms'] = rdf['bedrooms'].apply(
                            lambda v: 'Studio' if v == 0 else (str(int(v)) if pd.notna(v) else None)
                        )
                    rdf['_source'] = 'reidin'
                    frames.append(rdf)
                    print(f"[rental_processor] Reidin: {len(rdf):,} rows")
            except Exception as e:
                print(f"[rental_processor] Error loading Reidin: {e}")
            break

    if not frames:
        print("[rental_processor] No rental data files found.")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Parse dates
    df['contract_start'] = pd.to_datetime(df['contract_start'], errors='coerce')
    df['contract_end'] = pd.to_datetime(df['contract_end'], errors='coerce')
    if 'next_contract_date' not in df.columns:
        df['next_contract_date'] = pd.NaT
    else:
        df['next_contract_date'] = pd.to_datetime(df['next_contract_date'], errors='coerce')

    # Dedup true duplicates (prefer PM rows — richer data)
    if '_source' in df.columns and len(frames) > 1:
        source_priority = {'propertymonitor': 0, 'reidin': 1}
        df['_priority'] = df['_source'].map(source_priority).fillna(2)
        df = (
            df.sort_values('_priority')
            .drop_duplicates(subset=['building_name', 'unit_number', 'contract_start', 'contract_end'], keep='first')
            .drop(columns=['_priority'])
            .reset_index(drop=True)
        )

    # Derived fields
    df['contract_months'] = ((df['contract_end'] - df['contract_start']).dt.days / 30.44).round(0)
    if 'annualized_rent' in df.columns and 'size_sqft' in df.columns:
        df['annual_rent_psf'] = df['annualized_rent'] / df['size_sqft'].replace(0, float('nan'))
    df['bedrooms_numeric'] = df['bedrooms'].apply(_clean_bedrooms_numeric)

    print(f"[rental_processor] Total: {len(df):,} rental records")
    print(f"  Date range: {df['contract_start'].min()} to {df['contract_end'].max()}")
    print(f"  Unique buildings: {df['building_name'].nunique()}")
    print(f"  Active contracts: {(df['contract_end'] > datetime.now()).sum()}")

    return df


# =============================================================================
# LEASE EXPIRY ANALYSIS
# =============================================================================

def get_expiring_leases(rental_df: pd.DataFrame, days_ahead: int = 90, 
                        building: Optional[str] = None,
                        bedrooms: Optional[str] = None) -> pd.DataFrame:
    """
    Get leases expiring within N days from today.
    
    Parameters:
        rental_df: Rental data DataFrame
        days_ahead: Look ahead this many days (default 90)
        building: Filter by building name (optional)
        bedrooms: Filter by bedroom count (optional)
    
    Returns:
        DataFrame of expiring leases, sorted by expiry date (soonest first)
    """
    if rental_df.empty:
        return pd.DataFrame()
    
    today = datetime.now()
    cutoff = today + timedelta(days=days_ahead)
    
    # Filter to contracts expiring in the window
    expiring = rental_df[
        (rental_df['contract_end'] >= today) & 
        (rental_df['contract_end'] <= cutoff)
    ].copy()
    
    # Apply building filter
    if building and building.strip():
        building_lower = building.lower().strip()
        expiring = expiring[
            expiring['building_name'].fillna('').str.lower().str.contains(building_lower, regex=False, na=False)
        ]
    
    # Apply bedroom filter
    if bedrooms and bedrooms != 'All':
        if bedrooms == 'Studio':
            expiring = expiring[expiring['bedrooms_numeric'] == 0]
        else:
            try:
                expiring = expiring[expiring['bedrooms_numeric'] == int(bedrooms)]
            except:
                pass
    
    # Calculate days remaining
    expiring['days_remaining'] = (expiring['contract_end'] - today).dt.days
    
    # Sort by expiry date (most urgent first)
    expiring = expiring.sort_values('contract_end')
    
    return expiring


def get_active_rental_count(rental_df: pd.DataFrame) -> int:
    """Count currently active rental contracts."""
    if rental_df.empty:
        return 0
    today = datetime.now()
    return int((rental_df['contract_end'] >= today).sum())


# =============================================================================
# UNIT-SPECIFIC RENTAL ANALYSIS
# =============================================================================

def get_lease_renewal_history(rental_df: pd.DataFrame, building: str, unit: str) -> pd.DataFrame:
    """
    Get all rental contracts for a specific unit to detect renewal patterns.
    
    Parameters:
        rental_df: Rental data DataFrame
        building: Building name
        unit: Unit number
    
    Returns:
        DataFrame of rental history for the unit, sorted chronologically
    """
    if rental_df.empty:
        return pd.DataFrame()
    
    building_lower = building.lower().strip()
    unit_lower = str(unit).lower().strip()
    
    unit_history = rental_df[
        (rental_df['building_name'].fillna('').str.lower().str.contains(building_lower, regex=False, na=False)) &
        (rental_df['unit_number'].fillna('').str.lower() == unit_lower)
    ].copy()
    
    if unit_history.empty:
        return pd.DataFrame()
    
    unit_history = unit_history.sort_values('contract_start')
    
    # Use rent_recurrence field if available (Property Monitor directly tells us)
    if 'rent_recurrence' in unit_history.columns:
        unit_history['is_renewal'] = unit_history['rent_recurrence'].fillna('').str.lower() == 'renewal'
    else:
        # Fallback: Detect renewals by date proximity if rent_recurrence not available
        if len(unit_history) > 1:
            unit_history['is_renewal'] = False
            for i in range(1, len(unit_history)):
                prev_end = unit_history.iloc[i-1]['contract_end']
                curr_start = unit_history.iloc[i]['contract_start']
                if pd.notna(prev_end) and pd.notna(curr_start):
                    gap_days = (curr_start - prev_end).days
                    if -30 <= gap_days <= 60:  # Allow some overlap or gap
                        unit_history.iloc[i, unit_history.columns.get_loc('is_renewal')] = True
    
    return unit_history


def get_unit_rental_status(rental_df: pd.DataFrame, building_name: str, unit_number: str) -> Dict:
    """
    Check if a specific unit currently has an active rental contract.
    
    Returns:
        Dict with status ('active', 'expired', 'no_rental_history'), contract details
    """
    if rental_df.empty:
        return {'status': 'no_rental_data', 'contracts': 0}
    
    building_lower = building_name.lower().strip()
    unit_lower = str(unit_number).lower().strip()
    
    unit_contracts = rental_df[
        (rental_df['building_name'].fillna('').str.lower().str.contains(building_lower, regex=False, na=False)) &
        (rental_df['unit_number'].fillna('').str.lower() == unit_lower)
    ].copy()
    
    if unit_contracts.empty:
        return {'status': 'no_rental_history', 'contracts': 0}
    
    # Sort by end date desc to get latest
    unit_contracts = unit_contracts.sort_values('contract_end', ascending=False, na_position='last')
    
    today = datetime.now()
    latest = unit_contracts.iloc[0]
    
    if pd.notna(latest['contract_end']) and latest['contract_end'] > today:
        days_remaining = (latest['contract_end'] - today).days
        return {
            'status': 'active',
            'contract_end': latest['contract_end'].strftime('%Y-%m-%d'),
            'days_remaining': days_remaining,
            'annual_rent': latest['annualized_rent'],
            'contracts': len(unit_contracts),
            'furnished': latest.get('furnished', ''),
            'broker': latest.get('broker', ''),
        }
    else:
        return {
            'status': 'expired',
            'last_contract_end': latest['contract_end'].strftime('%Y-%m-%d') if pd.notna(latest['contract_end']) else 'Unknown',
            'last_annual_rent': latest['annualized_rent'],
            'contracts': len(unit_contracts),
        }


# =============================================================================
# RENTAL YIELD CALCULATION
# =============================================================================

def get_rental_yield_by_building(rental_df: pd.DataFrame, 
                                  sales_ref_df: pd.DataFrame,
                                  building_name: str, 
                                  bedrooms: Optional[str] = None) -> Dict:
    """
    Calculate rental yield for a building using rental and sales data.
    
    Formula: Gross Yield = (Avg Annual Rent / Avg Sale Price) × 100
    
    Uses:
    - Last 12 months average rent
    - Last 6 months average sale price
    
    Parameters:
        rental_df: Rental data DataFrame
        sales_ref_df: Sales reference DataFrame (from data_processor.load_reference_data)
        building_name: Building to analyze
        bedrooms: Optional bedroom filter
    
    Returns:
        Dict with yield analysis
    """
    building_lower = building_name.lower().strip()
    
    # Filter rental data
    rentals = rental_df[
        rental_df['building_name'].fillna('').str.lower().str.contains(building_lower, regex=False, na=False)
    ].copy()
    
    if bedrooms and bedrooms != 'All':
        if bedrooms == 'Studio':
            rentals = rentals[rentals['bedrooms_numeric'] == 0]
        else:
            try:
                rentals = rentals[rentals['bedrooms_numeric'] == int(bedrooms)]
            except:
                pass
    
    # Get average annual rent (last 12 months)
    one_year_ago = datetime.now() - timedelta(days=365)
    recent_rentals = rentals[
        (rentals['contract_start'] >= one_year_ago) & 
        (rentals['annualized_rent'].notna())
    ]
    
    avg_annual_rent = recent_rentals['annualized_rent'].mean() if not recent_rentals.empty else None
    avg_rent_psf = recent_rentals['annual_rent_psf'].mean() if not recent_rentals.empty else None
    
    # Get average sale price (last 6 months from sales reference data)
    six_months_ago = datetime.now() - timedelta(days=180)
    
    # Sales DataFrame has building_std column
    sales = sales_ref_df[
        sales_ref_df['building_std'].fillna('').str.lower().str.contains(building_lower, regex=False, na=False)
    ].copy()
    
    if bedrooms and bedrooms != 'All':
        if bedrooms == 'Studio':
            sales = sales[sales['bedrooms'] == 0]
        else:
            try:
                sales = sales[sales['bedrooms'] == int(bedrooms)]
            except:
                pass
    
    recent_sales = sales[
        (pd.to_datetime(sales['sale_date'], errors='coerce') >= six_months_ago) &
        (sales['sale_price_aed'].notna())
    ]
    
    avg_sale_price = recent_sales['sale_price_aed'].mean() if not recent_sales.empty else None
    avg_sale_psf = recent_sales['price_psf_aed'].mean() if not recent_sales.empty else None
    
    # Calculate yield
    if avg_annual_rent and avg_sale_price and avg_sale_price > 0:
        gross_yield = (avg_annual_rent / avg_sale_price) * 100
    else:
        gross_yield = None
    
    return {
        'building': building_name,
        'bedrooms': bedrooms,
        'avg_annual_rent': avg_annual_rent,
        'avg_rent_psf': avg_rent_psf,
        'rental_sample_size': len(recent_rentals),
        'avg_sale_price': avg_sale_price,
        'avg_sale_psf': avg_sale_psf,
        'sales_sample_size': len(recent_sales),
        'gross_yield_pct': gross_yield,
        'rental_timeframe': '12 months',
        'sales_timeframe': '6 months',
    }


# =============================================================================
# AI TOOL FUNCTION
# =============================================================================

def get_rental_intel_for_ai(rental_df: pd.DataFrame,
                             leads_df: pd.DataFrame,
                             reference_df: pd.DataFrame,
                             building: str,
                             query_type: str = 'expiring_leases',
                             bedrooms: Optional[str] = None,
                             unit_number: Optional[str] = None,
                             days_ahead: int = 90,
                             limit: int = 50) -> Dict:
    """
    Main AI tool function for rental intelligence queries.
    
    Parameters:
        rental_df: Rental data DataFrame
        leads_df: Lead/owner DataFrame
        reference_df: Sales reference DataFrame
        building: Building name to query
        query_type: Type of query ('expiring_leases', 'rental_history', 'rental_yield', 'unit_status')
        bedrooms: Optional bedroom filter
        unit_number: Specific unit (for unit_status, rental_history)
        days_ahead: For expiring_leases (default 90 days)
        limit: Max results to return
    
    Returns:
        Dict formatted for AI consumption
    """
    
    if rental_df.empty:
        return {
            'success': False,
            'error': 'No rental data available. Run rental_scraper.py first.',
            'query_type': query_type,
        }
    
    # ========================================================================
    # QUERY TYPE: EXPIRING LEASES
    # ========================================================================
    if query_type == 'expiring_leases':
        expiring = get_expiring_leases(rental_df, days_ahead, building, bedrooms)
        
        if expiring.empty:
            return {
                'success': True,
                'query_type': 'expiring_leases',
                'building': building,
                'bedrooms': bedrooms,
                'days_ahead': days_ahead,
                'count': 0,
                'message': f'No leases expiring in the next {days_ahead} days for {building}',
            }
        
        # Cross-reference with owner contacts (skip if leads missing or no required columns)
        expiring_with_contacts = []
        has_leads = (
            not leads_df.empty
            and 'building_name' in leads_df.columns
            and 'unit_number' in leads_df.columns
        )
        
        for idx, row in expiring.head(limit).iterrows():
            unit = str(row['unit_number']).lower().strip()
            bldg = row['building_name'].lower().strip()
            
            # Find matching owner in leads
            if has_leads:
                owner_match = leads_df[
                    (leads_df['building_name'].fillna('').str.lower().str.contains(bldg, regex=False, na=False)) &
                    (leads_df['unit_number'].fillna('').str.lower() == unit)
                ]
            else:
                owner_match = pd.DataFrame()
            
            lease_data = {
                'unit_number': row['unit_number'],
                'contract_end': row['contract_end'].strftime('%Y-%m-%d') if pd.notna(row['contract_end']) else '',
                'days_remaining': int(row['days_remaining']) if pd.notna(row['days_remaining']) else 0,
                'annual_rent': float(row['annualized_rent']) if pd.notna(row['annualized_rent']) else None,
                'size_sqft': float(row['size_sqft']) if pd.notna(row['size_sqft']) else None,
                'bedrooms': str(row.get('bedrooms', '')),
                'furnished': str(row.get('furnished', '')),
                'has_owner_contact': False,
                'owner_name': None,
                'owner_phone': None,
            }
            
            if not owner_match.empty:
                owner = owner_match.iloc[0]
                lease_data['has_owner_contact'] = True
                lease_data['owner_name'] = owner.get('owner_name')
                lease_data['owner_phone'] = owner.get('phone')
            
            expiring_with_contacts.append(lease_data)
        
        contacts_available = sum(1 for x in expiring_with_contacts if x['has_owner_contact'])
        
        return {
            'success': True,
            'query_type': 'expiring_leases',
            'building': building,
            'bedrooms': bedrooms,
            'days_ahead': days_ahead,
            'count': len(expiring_with_contacts),
            'total_expiring': len(expiring),
            'contacts_available': contacts_available,
            'leases': expiring_with_contacts,
        }
    
    # ========================================================================
    # QUERY TYPE: RENTAL HISTORY (for a specific unit)
    # ========================================================================
    elif query_type == 'rental_history':
        if not unit_number:
            return {
                'success': False,
                'error': 'rental_history requires unit_number parameter',
                'query_type': 'rental_history',
            }
        
        history = get_lease_renewal_history(rental_df, building, unit_number)
        
        if history.empty:
            return {
                'success': True,
                'query_type': 'rental_history',
                'building': building,
                'unit_number': unit_number,
                'count': 0,
                'message': f'No rental history found for {building}, Unit {unit_number}',
            }
        
        contracts = []
        for idx, row in history.iterrows():
            contracts.append({
                'contract_start': row['contract_start'].strftime('%Y-%m-%d') if pd.notna(row['contract_start']) else '',
                'contract_end': row['contract_end'].strftime('%Y-%m-%d') if pd.notna(row['contract_end']) else '',
                'contract_months': int(row['contract_months']) if pd.notna(row['contract_months']) else None,
                'annual_rent': float(row['annualized_rent']) if pd.notna(row['annualized_rent']) else None,
                'rent_psf': float(row['annual_rent_psf']) if pd.notna(row['annual_rent_psf']) else None,
                'is_renewal': bool(row.get('is_renewal', False)),
                'furnished': str(row.get('furnished', '')),
            })
        
        return {
            'success': True,
            'query_type': 'rental_history',
            'building': building,
            'unit_number': unit_number,
            'count': len(contracts),
            'contracts': contracts,
        }
    
    # ========================================================================
    # QUERY TYPE: RENTAL YIELD
    # ========================================================================
    elif query_type == 'rental_yield':
        yield_data = get_rental_yield_by_building(rental_df, reference_df, building, bedrooms)
        
        return {
            'success': True,
            'query_type': 'rental_yield',
            'building': building,
            'bedrooms': bedrooms,
            **yield_data,
        }
    
    # ========================================================================
    # QUERY TYPE: UNIT STATUS (is it currently rented?)
    # ========================================================================
    elif query_type == 'unit_status':
        if not unit_number:
            return {
                'success': False,
                'error': 'unit_status requires unit_number parameter',
                'query_type': 'unit_status',
            }
        
        status = get_unit_rental_status(rental_df, building, unit_number)
        
        return {
            'success': True,
            'query_type': 'unit_status',
            'building': building,
            'unit_number': unit_number,
            **status,
        }
    
    # Unknown query type
    else:
        return {
            'success': False,
            'error': f'Unknown query_type: {query_type}',
            'valid_types': ['expiring_leases', 'rental_history', 'rental_yield', 'unit_status'],
        }


# =============================================================================
# CROSS-REFERENCE WITH OWNER CONTACTS
# =============================================================================

def cross_reference_rentals_with_owners(rental_df: pd.DataFrame, 
                                        leads_df: pd.DataFrame,
                                        days_ahead: int = 90) -> pd.DataFrame:
    """
    Cross-reference expiring leases with owner contacts from the lead database.
    
    Returns:
        DataFrame of expiring leases with owner contact info where available.
    """
    today = datetime.now()
    cutoff = today + timedelta(days=days_ahead)
    
    expiring = rental_df[
        (rental_df['contract_end'] >= today) & 
        (rental_df['contract_end'] <= cutoff)
    ].copy()
    
    if expiring.empty:
        return pd.DataFrame()
    
    has_leads = (
        not leads_df.empty
        and 'building_name' in leads_df.columns
        and 'unit_number' in leads_df.columns
    )
    
    # Match with leads
    result_rows = []
    
    for idx, rental in expiring.iterrows():
        unit = str(rental['unit_number']).lower().strip()
        bldg = rental['building_name'].lower().strip()
        
        # Find owner in leads
        if has_leads:
            owner_match = leads_df[
                (leads_df['building_name'].fillna('').str.lower().str.contains(bldg, regex=False, na=False)) &
                (leads_df['unit_number'].fillna('').str.lower() == unit)
            ]
        else:
            owner_match = pd.DataFrame()
        
        row_data = {
            'building_name': rental['building_name'],
            'unit_number': rental['unit_number'],
            'contract_end': rental['contract_end'],
            'days_remaining': (rental['contract_end'] - today).days if pd.notna(rental['contract_end']) else None,
            'annual_rent': rental['annualized_rent'],
            'bedrooms': rental.get('bedrooms', ''),
            'size_sqft': rental['size_sqft'],
            'furnished': rental.get('furnished', ''),
            'has_owner_contact': not owner_match.empty,
        }
        
        if not owner_match.empty:
            owner = owner_match.iloc[0]
            row_data['owner_name'] = owner.get('owner_name')
            row_data['owner_phone'] = owner.get('phone')
            row_data['owner_email'] = owner.get('email')
            row_data['owner_nationality'] = owner.get('nationality')
        else:
            row_data['owner_name'] = None
            row_data['owner_phone'] = None
            row_data['owner_email'] = None
            row_data['owner_nationality'] = None
        
        result_rows.append(row_data)
    
    result_df = pd.DataFrame(result_rows)
    result_df = result_df.sort_values('contract_end')
    
    return result_df


# =============================================================================
# MODULE SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("Testing rental_processor module...")
    
    df = load_rental_data()
    print(f"\nLoaded {len(df)} rental records")
    
    if not df.empty:
        print(f"Buildings: {df['building_name'].nunique()}")
        print(f"Active contracts: {get_active_rental_count(df)}")
        
        # Test expiring leases
        expiring = get_expiring_leases(df, days_ahead=90)
        print(f"Leases expiring in 90 days: {len(expiring)}")
    else:
        print("No rental data available. Run rental_scraper.py first.")
