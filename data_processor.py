"""
Data Processor Module for Real Estate Lead CSV Normalization
Enhanced with bidirectional estimation + unit schema inference
Palm Jumeirah Intelligence System - Production Build
"""

import pandas as pd
import re
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Import unit registry for confirmed bedroom/size lookups
try:
    from unit_registry import load_unit_registry as _load_unit_registry
    UNIT_REGISTRY_AVAILABLE = True
except ImportError:
    UNIT_REGISTRY_AVAILABLE = False

# Import building intelligence module for fuzzy matching.
# Deliberately do NOT import BUILDING_ALIASES from building_intelligence here:
# that dict is keyed on canonical names ("The Fairmont Palm Residences" -> list
# of display variations) and is consumed by app.py / listing_matcher.
# The BUILDING_ALIASES defined below is a *different* dict, keyed on lowercase
# short names ("fairmont" -> list of lowercase alternates) and is used for
# fuzzy substring matching inside standardize_building_name(). Keeping them
# separate avoids breaking the canonical-name consumers.
try:
    from building_intelligence import (
        resolve_building_name,
        validate_unit_type,
        normalize_unit_number,
        validate_phone_number,
        format_phone_number,
        calculate_data_age,
        get_shoreline_info,
        SHORELINE_TOWER_MAPPING,
        BUILDING_SPECS,
    )
    BUILDING_INTELLIGENCE_AVAILABLE = True
except ImportError:
    BUILDING_INTELLIGENCE_AVAILABLE = False
    print("[WARN] building_intelligence.py not found - using fallback functions")


# =============================================================================
# BUILDING ALIAS MAPPING SYSTEM (local fuzzy-match table, lowercase keys)
# See note above for why this is separate from building_intelligence.BUILDING_ALIASES.
# =============================================================================

if BUILDING_INTELLIGENCE_AVAILABLE:
    SHORELINE_ARABIC_MAPPING = {}
    for tower, (num, aliases) in SHORELINE_TOWER_MAPPING.items():
        tower_lower = tower.lower()
        SHORELINE_ARABIC_MAPPING[tower_lower] = f"Shoreline {num}"
        for alias in aliases:
            SHORELINE_ARABIC_MAPPING[alias.lower()] = f"Shoreline {num}"
else:
    SHORELINE_ARABIC_MAPPING = {}

BUILDING_ALIASES = {
    'shoreline': ['shoreline', 'shoreline apartments'],
    'tiara': ['tiara', 'tiara residences', 'tiara residence', 'tiara united'],
    'azure': ['azure', 'azure residences', 'azure residence'],
    'oceana': ['oceana', 'oceana residences', 'oceana residence', 'oceana atlantic', 'oceana pacific', 'oceana southern', 'oceana caribbean', 'dukes oceana'],
    'caribbean': ['caribbean', 'oceana caribbean'],
    'anantara': ['anantara', 'anantara residences', 'anantara residence', 'anantara north', 'anantara south'],
    'kempinski': ['kempinski', 'kempinski residences', 'kempinski residence', 'kempinski palm'],
    'fairmont': ['fairmont', 'fairmont residences', 'fairmont residence', 'fairmont palm', 'fairmont north', 'fairmont south'],
    'serenia': ['serenia', 'serenia residences', 'serenia residence', 'serenia living'],
    'balqis': ['balqis', 'balqis residences', 'balqis residence'],
    'palm beach towers': ['palm beach towers', 'palm beach tower', 'pbt', 'palm beach'],
    'golden mile': ['golden mile', 'golden mile residences', 'golden mile palms'],
    'marina residences': ['marina residences', 'marina residence', 'marina apartments', 'marina apartment', 'palm marina'],
    'grandeur': ['grandeur', 'grandeur residences', 'grandeur residence'],
    'viceroy': ['viceroy', 'viceroy residences', 'viceroy palm', 'viceroy hotel'],
    'seven': ['seven', 'seven hotel', 'seven palm', '7 palm'],
    'palm tower': ['palm tower', 'the palm tower'],
    'the 8': ['the 8', 'the eight'],
    'palm views': ['palm views', 'palm views east', 'palm views west'],
    'royal amwaj': ['royal amwaj', 'amwaj'],
    'azizi mina': ['azizi mina', 'azizi'],
    'club vista mare': ['club vista mare', 'vista mare'],
    'sls': ['sls', 'sls residences', 'sls palm'],
    'royal atlantis': ['royal atlantis', 'atlantis residences'],
    'one palm': ['one palm', 'one at palm'],
    'raffles': ['raffles', 'raffles palm'],
    'ellington': ['ellington', 'ellington beach'],
    'the crescent': ['the crescent', 'crescent'],
}

# =============================================================================
# BUILDING DEFAULT BEDROOMS (Most common bedroom from reference data)
# Used as final fallback when no other method works
# Based on analysis of title_deed_reference.csv distributions
# =============================================================================

BUILDING_DEFAULT_BEDROOMS = {
    # Hotel-style (mostly studios)
    'seven': 0,           # 57% studio, 32% 1BR
    'palm tower': 0,      # 48% studio, 50% 1BR  
    'viceroy': 0,         # Hotel apartments - studios
    'fairmont': 1,        # Mix of studio/1BR
    
    # Residential (mostly 1-2BR)
    'oceana': 1,          # 42% 1BR, 17% studio
    'palm beach': 1,      # 47% 1BR, 33% 2BR
    'serenia': 2,         # 49% 2BR, 28% 3BR
    'balqis': 2,          # 39% 2BR
    'kempinski': 2,       # 72% 2BR
    'azizi': 1,           # 67% 1BR
    'palm views': 1,      # Assume 1BR
    'royal amwaj': 2,     # Residential
    'the 8': 1,           # Mix
    'club vista mare': 2,
    'sls': 1,
    'royal atlantis': 2,
    'grandeur': 2,
    'one palm': 3,        # Luxury
    'raffles': 2,
    'ellington': 2,
    'azure': 2,           # From reference
    
    # Shoreline already has schema
    'shoreline': 2,       # Fallback if schema fails
    'tiara': 2,
    'anantara': 2,
    'marina': 2,
    'golden mile': 1,
    
    # Additional buildings for remaining unresolved
    'royal bay': 2,       # Residential
    'ocean house': 2,
    'como': 2,
    'carat': 4,           # Luxury villas
    'orla': 3,            # Luxury
    'six senses': 2,
    'w residences': 2,
    'luce': 2,
    'atlantic': 1,        # Oceana family
    'pacific': 1,
    'southern': 1,
    'baltic': 1,          # Dukes Oceana family
    'canal cove': 3,      # Townhouses
    'garden homes': 4,    # Villas
    'signature villas': 5,
    'frond': 4,           # Villa plots
}


# =============================================================================
# UNIT NUMBER → BEDROOM SCHEMA MAPPING
# Manual override table for high-frequency buildings
# Format: building_pattern -> [(unit_range_start, unit_range_end, bedrooms), ...]
# Unit numbers are interpreted as: floor*100 + unit (e.g., 1205 = floor 12, unit 05)
# =============================================================================

BUILDING_UNIT_SCHEMA = {
    # SHORELINE APARTMENTS (1-20): Standardized layout
    'shoreline': {
        'pattern': r'shoreline',
        'unit_rules': [
            {'unit_end': ['01', '02', '03'], 'bedrooms': 3},
            {'unit_end': ['04', '05', '06'], 'bedrooms': 2},
            {'unit_end': ['07', '08', '09'], 'bedrooms': 1},
            {'unit_end': ['10', '11', '12'], 'bedrooms': 0},
        ]
    },
    
    # OCEANA (all towers): Based on reference data
    'oceana': {
        'pattern': r'oceana|caribbean|atlantic|pacific|southern',
        'unit_rules': [
            {'unit_end': ['01', '02', '03'], 'bedrooms': 0},  # Studios 17%
            {'unit_end': ['04', '05', '06', '07', '08'], 'bedrooms': 1},  # 1BR 42%
            {'unit_end': ['09', '10', '11'], 'bedrooms': 2},  # 2BR 17%
            {'unit_end': ['12', '13', '14', '15'], 'bedrooms': 3},  # 3BR 23%
        ]
    },
    
    # SEVEN PALM: 57% studio, 32% 1BR from reference
    'seven': {
        'pattern': r'seven|7\s*palm',
        'unit_rules': [
            {'unit_end': ['01', '02', '03', '04', '05', '06', '07'], 'bedrooms': 0},  # Studios
            {'unit_end': ['08', '09', '10', '11', '12'], 'bedrooms': 1},  # 1BR
        ]
    },
    
    # PALM TOWER: 48% studio, 50% 1BR
    'palm tower': {
        'pattern': r'palm\s*tower',
        'unit_rules': [
            {'unit_end': ['01', '02', '03', '04', '05', '06'], 'bedrooms': 0},
            {'unit_end': ['07', '08', '09', '10', '11', '12'], 'bedrooms': 1},
        ]
    },
    
    # PALM BEACH TOWERS: 47% 1BR, 33% 2BR
    'palm beach': {
        'pattern': r'palm\s*beach',
        'unit_rules': [
            {'unit_end': ['01', '02', '03', '04', '05', '06'], 'bedrooms': 1},
            {'unit_end': ['07', '08', '09', '10'], 'bedrooms': 2},
            {'unit_end': ['11', '12', '13', '14'], 'bedrooms': 3},
        ]
    },
    
    # SERENIA: 49% 2BR, 28% 3BR
    'serenia': {
        'pattern': r'serenia',
        'unit_rules': [
            {'unit_end': ['01', '02'], 'bedrooms': 1},
            {'unit_end': ['03', '04', '05', '06', '07'], 'bedrooms': 2},
            {'unit_end': ['08', '09', '10', '11'], 'bedrooms': 3},
        ]
    },
    
    # BALQIS: Mixed (39% 2BR, 24% 5BR)
    'balqis': {
        'pattern': r'balqis',
        'unit_rules': [
            {'unit_end': ['01', '02'], 'bedrooms': 0},
            {'unit_end': ['03', '04', '05'], 'bedrooms': 2},
            {'unit_end': ['06', '07', '08'], 'bedrooms': 3},
            {'unit_end': ['09', '10'], 'bedrooms': 4},
        ]
    },
    
    # KEMPINSKI: 72% 2BR
    'kempinski': {
        'pattern': r'kempinski',
        'unit_rules': [
            {'unit_end': ['01', '02', '03', '04', '05', '06', '07', '08'], 'bedrooms': 2},
            {'unit_end': ['09', '10'], 'bedrooms': 3},
            {'unit_end': ['11', '12'], 'bedrooms': 4},
        ]
    },
    
    # VICEROY: Hotel-style
    'viceroy': {
        'pattern': r'viceroy',
        'unit_rules': [
            {'unit_end': ['01', '02', '03', '04', '05', '06'], 'bedrooms': 0},
            {'unit_end': ['07', '08', '09', '10', '11', '12'], 'bedrooms': 1},
        ]
    },
    
    # TIARA: Luxury
    'tiara': {
        'pattern': r'tiara',
        'unit_rules': [
            {'unit_end': ['01', '02'], 'bedrooms': 3},
            {'unit_end': ['03', '04', '05', '06'], 'bedrooms': 2},
            {'unit_end': ['07', '08', '09', '10'], 'bedrooms': 1},
        ]
    },
    
    # FAIRMONT: Mix
    'fairmont': {
        'pattern': r'fairmont',
        'unit_rules': [
            {'unit_end': ['01', '02', '03'], 'bedrooms': 0},
            {'unit_end': ['04', '05', '06', '07', '08'], 'bedrooms': 1},
            {'unit_end': ['09', '10', '11', '12'], 'bedrooms': 2},
            {'unit_end': ['13', '14', '15'], 'bedrooms': 3},
        ]
    },
    
    # MARINA RESIDENCES
    'marina': {
        'pattern': r'marina(?!\s*residences\s*\d)',  # Avoid matching numbered ones
        'unit_rules': [
            {'unit_end': ['01', '02'], 'bedrooms': 3},
            {'unit_end': ['03', '04', '05', '06'], 'bedrooms': 2},
            {'unit_end': ['07', '08', '09', '10'], 'bedrooms': 1},
            {'unit_end': ['11', '12'], 'bedrooms': 0},
        ]
    },
    
    # GOLDEN MILE
    'golden mile': {
        'pattern': r'golden\s*mile',
        'unit_rules': [
            {'unit_end': ['01', '02', '03'], 'bedrooms': 2},
            {'unit_end': ['04', '05', '06', '07'], 'bedrooms': 1},
            {'unit_end': ['08', '09', '10'], 'bedrooms': 0},
        ]
    },
    
    # ANANTARA: From reference
    'anantara': {
        'pattern': r'anantara',
        'unit_rules': [
            {'unit_end': ['01', '02'], 'bedrooms': 3},
            {'unit_end': ['03', '04', '05'], 'bedrooms': 2},
            {'unit_end': ['06', '07', '08', '09'], 'bedrooms': 1},
        ]
    },
    
    # AZIZI MINA: 67% 1BR
    'azizi': {
        'pattern': r'azizi',
        'unit_rules': [
            {'unit_end': ['01', '02', '03', '04', '05', '06', '07', '08'], 'bedrooms': 1},
            {'unit_end': ['09', '10', '11'], 'bedrooms': 2},
        ]
    },
    
    # PALM VIEWS
    'palm views': {
        'pattern': r'palm\s*views',
        'unit_rules': [
            {'unit_end': ['01', '02', '03', '04', '05'], 'bedrooms': 1},
            {'unit_end': ['06', '07', '08', '09', '10'], 'bedrooms': 2},
        ]
    },
    
    # THE 8
    'the 8': {
        'pattern': r'the\s*8|the\s*eight',
        'unit_rules': [
            {'unit_end': ['01', '02', '03', '04', '05', '06'], 'bedrooms': 1},
            {'unit_end': ['07', '08', '09', '10', '11', '12'], 'bedrooms': 2},
        ]
    },
}


def infer_bedrooms_from_unit_schema(building: str, unit_number: str) -> Optional[Dict]:
    """
    Infer bedroom count from building-specific unit number patterns.
    Returns: {'bedrooms': int, 'method': str, 'confidence': str} or None
    """
    if not building or not unit_number:
        return None
    
    building_lower = str(building).lower().strip()
    unit_str = str(unit_number).strip()
    
    # Extract digits from unit number
    digits = ''.join(filter(str.isdigit, unit_str))
    if not digits:
        return None
    
    # Get unit ending (last 2 digits)
    unit_end = digits[-2:].zfill(2) if len(digits) >= 2 else digits.zfill(2)
    
    # Find matching building schema
    for schema_name, schema in BUILDING_UNIT_SCHEMA.items():
        if re.search(schema['pattern'], building_lower):
            # Check unit rules
            for rule in schema['unit_rules']:
                if unit_end in rule['unit_end']:
                    return {
                        'bedrooms': rule['bedrooms'],
                        'method': f'Schema ({schema_name.title()})',
                        'confidence': 'High'
                    }
    
    return None


def get_building_default_bedrooms(building: str) -> Optional[Dict]:
    """
    Get default bedroom count for a building based on reference data distribution.
    Used as final fallback when no other method works.
    Returns: {'bedrooms': int, 'method': str, 'confidence': str} or None
    """
    if not building:
        return None
    
    building_lower = str(building).lower().strip()
    
    # Check each building key
    for bldg_key, default_beds in BUILDING_DEFAULT_BEDROOMS.items():
        if bldg_key in building_lower:
            return {
                'bedrooms': default_beds,
                'method': f'Default ({bldg_key.title()})',
                'confidence': 'Low'
            }
    
    return None


# =============================================================================
# SIZE-BASED BEDROOM INFERENCE (with building context)
# =============================================================================

# Refined size ranges per bedroom count (sqft)
# Based on Palm Jumeirah market data
PALM_BEDROOM_SIZE_RANGES = {
    0: {'min': 300, 'max': 700, 'typical': 450},      # Studio
    1: {'min': 650, 'max': 1100, 'typical': 850},     # 1BR
    2: {'min': 1000, 'max': 1600, 'typical': 1300},   # 2BR
    3: {'min': 1500, 'max': 2500, 'typical': 1900},   # 3BR
    4: {'min': 2300, 'max': 4000, 'typical': 3000},   # 4BR
    5: {'min': 3500, 'max': 10000, 'typical': 5000},  # 5BR+
}


def infer_bedrooms_from_size_definitive(size_sqft: float, building: str = None) -> Optional[Dict]:
    """
    Definitively infer bedroom count from size.
    Only returns a result if the size clearly falls into one category.
    Returns: {'bedrooms': int, 'method': str, 'confidence': str} or None
    """
    if pd.isna(size_sqft) or size_sqft <= 0:
        return None
    
    size = float(size_sqft)
    
    # Find best match with confidence scoring
    matches = []
    for beds, ranges in PALM_BEDROOM_SIZE_RANGES.items():
        if ranges['min'] <= size <= ranges['max']:
            # Calculate how well it fits (closer to typical = higher confidence)
            distance = abs(size - ranges['typical'])
            range_width = ranges['max'] - ranges['min']
            fit_score = 1 - (distance / range_width)
            matches.append((beds, fit_score, ranges))
    
    if not matches:
        # Edge cases
        if size < 300:
            return {'bedrooms': 0, 'method': 'Size (Small)', 'confidence': 'Low'}
        if size > 5000:
            return {'bedrooms': 5, 'method': 'Size (Large)', 'confidence': 'Low'}
        return None
    
    # If only one match, use it
    if len(matches) == 1:
        beds, fit, ranges = matches[0]
        conf = 'High' if fit > 0.6 else 'Medium' if fit > 0.3 else 'Low'
        return {'bedrooms': beds, 'method': 'Size', 'confidence': conf}
    
    # Multiple matches - pick best fit
    matches.sort(key=lambda x: x[1], reverse=True)
    best = matches[0]
    second = matches[1]
    
    # If best fit is significantly better, use it
    if best[1] - second[1] > 0.2:
        conf = 'Medium'
    else:
        conf = 'Low'  # Ambiguous
    
    return {'bedrooms': best[0], 'method': 'Size', 'confidence': conf}


# =============================================================================
# STANDARD BUILDING/FAMILY HELPERS
# =============================================================================

def standardize_building_name(raw_name) -> Optional[str]:
    """Bidirectional building name standardization."""
    if pd.isna(raw_name) or str(raw_name).strip() == '' or str(raw_name).strip() == '0':
        return None
    
    raw_lower = str(raw_name).lower().strip()
    
    for arabic, shoreline in SHORELINE_ARABIC_MAPPING.items():
        if arabic in raw_lower or raw_lower == arabic:
            return shoreline
    
    shoreline_match = re.search(r'shoreline\s*(\d+)', raw_lower)
    if shoreline_match:
        num = int(shoreline_match.group(1))
        if 1 <= num <= 20:
            return f"Shoreline {num}"
    
    for canonical, aliases in BUILDING_ALIASES.items():
        for alias in aliases:
            if alias.lower() in raw_lower:
                return canonical.title()
    
    if 'shoreline' in raw_lower:
        return 'Shoreline Family'
    
    return str(raw_name).strip().title()


def get_building_family(building_name: str) -> str:
    """Group buildings into families with similar layouts."""
    if not building_name:
        return 'Unknown'
    
    building_lower = str(building_name).lower()
    
    if 'shoreline' in building_lower:
        return 'Shoreline Family'
    if 'tiara' in building_lower:
        return 'Tiara Family'
    if 'oceana' in building_lower or 'caribbean' in building_lower:
        return 'Oceana Family'
    if 'fairmont' in building_lower:
        return 'Fairmont Family'
    if 'anantara' in building_lower:
        return 'Anantara Family'
    if 'golden mile' in building_lower:
        return 'Golden Mile Family'
    if 'palm beach' in building_lower:
        return 'Palm Beach Family'
    if 'marina' in building_lower:
        return 'Marina Family'
    if 'viceroy' in building_lower:
        return 'Viceroy Family'
    if 'seven' in building_lower:
        return 'Seven Family'
    
    return building_name


def parse_building_search(search_query: str) -> Optional[List[str]]:
    if not search_query or not search_query.strip():
        return None
    query = search_query.lower().strip()
    
    for arabic, shoreline in SHORELINE_ARABIC_MAPPING.items():
        if arabic in query or query == arabic:
            return [shoreline]
    
    range_match = re.search(r'(\w+)?\s*(\d+)\s*-\s*(\d+)', query)
    if range_match:
        prefix = range_match.group(1) or 'shoreline'
        start, end = int(range_match.group(2)), int(range_match.group(3))
        return [f"{prefix.title()} {i}" for i in range(start, min(end + 1, 21))]
    
    if query == 'shoreline':
        return [f"Shoreline {i}" for i in range(1, 21)]
    
    num_match = re.search(r'(\w+)\s+(\d+)', query)
    if num_match:
        return [f"{num_match.group(1).title()} {num_match.group(2)}"]
    
    return [search_query.strip()]


# =============================================================================
# REFERENCE DATA LOADING
# =============================================================================

SQFT_TO_SQM = 0.092903
SQM_TO_SQFT = 10.7639


def load_reference_data(ref_path: str = './reference_data/title_deed_reference.csv') -> Tuple[Optional[pd.DataFrame], Dict]:
    """Load master reference dataset from multiple possible locations."""
    ref_stats = {
        'loaded': False,
        'record_count': 0,
        'unique_buildings': 0,
        'unique_families': 0,
        'units_with_patterns': 0,
        'error': None
    }
    # Resolve paths from project root so this works when cwd is e.g. whatsapp_bot
    _root = Path(__file__).resolve().parent
    possible_paths = [
        _root / 'Master reference datasets' / 'reference_master_with_units.csv',
        _root / 'Master reference datasets' / 'reference_master.csv',
        _root / 'reference_data' / 'title_deed_reference.csv',
        Path(ref_path) if not ref_path.startswith('./') else _root / ref_path[2:],
        _root / 'Master reference datasets' / 'palm-jumeirah-market-data-harry-stracey-e-and-t-real-estate-broker-llc-05-02-2026-79c428f41d5f7d494678e182d99a373da2a11876.csv',
    ]
    # Find the first existing file
    found_path = None
    for path in possible_paths:
        p = path if isinstance(path, Path) else Path(path)
        if p.exists():
            found_path = str(p)
            print(f"[INFO] Found reference data at: {found_path}")
            break
    # If no predefined path works, search directories
    if not found_path:
        for search_dir in [_root / 'reference_data', _root / 'Master reference datasets']:
            if search_dir.exists():
                ref_files = list(search_dir.glob('*.csv'))
                if ref_files:
                    found_path = str(ref_files[0])
                    print(f"[INFO] Found reference data at: {found_path}")
                    break
    
    if not found_path:
        ref_stats['error'] = "No reference CSV found in any location"
        return None, ref_stats
    
    ref_path = found_path
    
    try:
        ref_df = None
        for enc in ['utf-8', 'latin-1', 'cp1252']:
            try:
                ref_df = pd.read_csv(ref_path, encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue
        
        if ref_df is None or ref_df.empty:
            ref_stats['error'] = "Reference file empty"
            return None, ref_stats
        
        col_mapping = detect_reference_columns(ref_df)
        
        if not col_mapping.get('size_sqft'):
            ref_stats['error'] = "No size column in reference"
            return None, ref_stats
        
        result = pd.DataFrame()
        
        if col_mapping.get('sub_loc_1'):
            result['sub_loc_1'] = ref_df[col_mapping['sub_loc_1']].fillna('')
        else:
            result['sub_loc_1'] = ''
        
        if col_mapping.get('sub_loc_2'):
            result['sub_loc_2'] = ref_df[col_mapping['sub_loc_2']].fillna('')
        elif col_mapping.get('building'):
            result['sub_loc_2'] = ref_df[col_mapping['building']].fillna('')
        else:
            result['sub_loc_2'] = ''
        
        _DEVELOPER_BUILDING_MAP = {
            "ellington properties": "Ellington Beach House",
            "seven tides":          "Seven Palm",
            "muraba":               "Muraba Residences",
            "omniyat":              "One at Palm Jumeirah",
        }

        def enhance_building_match(row):
            sub_loc_1 = str(row['sub_loc_1']).lower()
            sub_loc_2 = str(row['sub_loc_2'])
            # Developer uniquely identifies certain buildings within a community
            developer = str(row.get('developer', '') or '').strip().lower()
            if developer in _DEVELOPER_BUILDING_MAP:
                return _DEVELOPER_BUILDING_MAP[developer]
            std_name = standardize_building_name(sub_loc_2)
            if std_name and 'shoreline' not in std_name.lower() and 'shoreline' in sub_loc_1:
                for arabic, shoreline in SHORELINE_ARABIC_MAPPING.items():
                    if arabic in sub_loc_2.lower():
                        return shoreline
                return 'Shoreline Family'
            return std_name

        result['building_std'] = result.apply(enhance_building_match, axis=1)
        result['building_family'] = result['building_std'].apply(get_building_family)
        
        if col_mapping.get('unit_no'):
            result['unit_no'] = ref_df[col_mapping['unit_no']].fillna('').astype(str).str.strip()
        else:
            result['unit_no'] = ''
        
        result['size_sqft'] = pd.to_numeric(ref_df[col_mapping['size_sqft']], errors='coerce')
        
        if col_mapping.get('size_sqm'):
            result['size_sqm'] = pd.to_numeric(ref_df[col_mapping['size_sqm']], errors='coerce')
        else:
            result['size_sqm'] = result['size_sqft'] * SQFT_TO_SQM
        
        if col_mapping.get('bedrooms'):
            result['bedrooms'] = ref_df[col_mapping['bedrooms']].apply(clean_reference_beds)
        else:
            result['bedrooms'] = None
        
        # Add pricing columns
        if col_mapping.get('sale_price'):
            result['sale_price_aed'] = pd.to_numeric(ref_df[col_mapping['sale_price']], errors='coerce')
        else:
            result['sale_price_aed'] = None
        
        if col_mapping.get('price_psf'):
            result['price_psf_aed'] = pd.to_numeric(ref_df[col_mapping['price_psf']], errors='coerce')
        else:
            result['price_psf_aed'] = None
        
        if col_mapping.get('sale_date'):
            result['sale_date'] = pd.to_datetime(ref_df[col_mapping['sale_date']], errors='coerce')
        else:
            result['sale_date'] = None
        
        # Transaction detail columns
        if col_mapping.get('floor_level'):
            result['floor_level'] = ref_df[col_mapping['floor_level']].fillna('').astype(str).str.strip()
        else:
            result['floor_level'] = ''
        
        if col_mapping.get('developer'):
            result['developer'] = ref_df[col_mapping['developer']].fillna('').astype(str).str.strip()
        else:
            result['developer'] = ''
        
        if col_mapping.get('view'):
            result['view'] = ref_df[col_mapping['view']].fillna('').astype(str).str.strip()
        else:
            result['view'] = ''

        if col_mapping.get('trans_group_en'):
            result['trans_group_en'] = ref_df[col_mapping['trans_group_en']].fillna('').astype(str).str.strip()
        else:
            result['trans_group_en'] = ''

        if col_mapping.get('sales_recurrence'):
            result['sales_recurrence'] = ref_df[col_mapping['sales_recurrence']].fillna('').astype(str).str.strip()
        else:
            result['sales_recurrence'] = ''

        result = result.dropna(subset=['size_sqft'])
        result = result[result['size_sqft'] > 100]
        
        # Log pricing data availability
        pricing_count = result['sale_price_aed'].notna().sum()
        print(f"   - Records with pricing: {pricing_count:,}")
        
        ref_stats['loaded'] = True
        ref_stats['records_with_pricing'] = int(pricing_count)
        ref_stats['record_count'] = len(result)
        ref_stats['unique_buildings'] = result['building_std'].dropna().nunique()
        ref_stats['unique_families'] = result['building_family'].dropna().nunique()
        ref_stats['units_with_patterns'] = (result['unit_no'] != '').sum()
        if 'sale_date' in result.columns and result['sale_date'].notna().any():
            sale_dates = pd.to_datetime(result['sale_date'], errors='coerce').dropna()
            if not sale_dates.empty:
                ref_stats['sale_date_min'] = sale_dates.min().strftime('%Y-%m-%d')
                ref_stats['sale_date_max'] = sale_dates.max().strftime('%Y-%m-%d')
            else:
                ref_stats['sale_date_min'] = None
                ref_stats['sale_date_max'] = None
        else:
            ref_stats['sale_date_min'] = None
            ref_stats['sale_date_max'] = None

        print(f"[OK] Loaded {len(result):,} reference records")
        print(f"   - Unique buildings: {ref_stats['unique_buildings']}")
        print(f"   - Unique families: {ref_stats['unique_families']}")
        
        return result, ref_stats
        
    except Exception as e:
        ref_stats['error'] = str(e)
        print(f"[ERR] Error loading reference data: {e}")
        return None, ref_stats


def detect_reference_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Detect columns in reference data including pricing."""
    mapping = {
        'sub_loc_1': None, 'sub_loc_2': None, 'building': None,
        'unit_no': None, 'size_sqft': None, 'size_sqm': None,
        'bedrooms': None, 'unit_type': None,
        # Pricing columns
        'sale_price': None, 'price_psf': None, 'price_psm': None, 'sale_date': None,
        # Transaction detail columns
        'floor_level': None, 'developer': None, 'view': None,
        'trans_group_en': None, 'sales_recurrence': None
    }
    
    col_lower_map = {str(c).lower().strip(): c for c in df.columns}
    
    for pattern in ['sub_loc_1', 'subloc1', 'sub loc 1', 'location1', 'area']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['sub_loc_1'] = col
                break
    
    for pattern in ['sub_loc_2', 'subloc2', 'sub loc 2', 'location2', 'building name']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l and col != mapping['sub_loc_1']:
                mapping['sub_loc_2'] = col
                break
    
    for pattern in ['building', 'project', 'property name']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l and col not in [mapping['sub_loc_1'], mapping['sub_loc_2']]:
                mapping['building'] = col
                break
    
    for pattern in ['unit_no', 'unit no', 'unitno', 'unit number', 'unit_number', 'property_number']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['unit_no'] = col
                break
    
    priority_sqft = ['unit_size_sqft', 'unit size sqft', 'built_up_area_sqft', 'bua_sqft', 'actual_sqft']
    for pattern in priority_sqft:
        for col_l, col in col_lower_map.items():
            norm = re.sub(r'[^a-z0-9]', '', col_l)
            norm_pattern = re.sub(r'[^a-z0-9]', '', pattern)
            if norm_pattern in norm or norm in norm_pattern:
                mapping['size_sqft'] = col
                break
        if mapping['size_sqft']:
            break
    
    if not mapping['size_sqft']:
        for col_l, col in col_lower_map.items():
            if 'plot' in col_l:
                continue
            if 'sqft' in col_l or 'sq ft' in col_l:
                mapping['size_sqft'] = col
                break
    
    for pattern in ['unit_size_sqm', 'built_up_area_sqm', 'bua_sqm', 'sqm', 'sq m']:
        for col_l, col in col_lower_map.items():
            if 'plot' in col_l:
                continue
            if pattern in col_l:
                mapping['size_sqm'] = col
                break
        if mapping['size_sqm']:
            break
    
    for pattern in ['no_beds', 'beds', 'bedrooms', 'bedroom', 'br', 'no_of_beds']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['bedrooms'] = col
                break
        if mapping['bedrooms']:
            break
    
    for pattern in ['unit_type', 'property_type', 'type']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['unit_type'] = col
                break
        if mapping['unit_type']:
            break
    
    # Pricing columns - sale price
    for pattern in ['total_sales_price_val', 'total_sales_price', 'sales_price', 'sale_price', 'price']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l and 'sqft' not in col_l and 'sqm' not in col_l:
                mapping['sale_price'] = col
                break
        if mapping['sale_price']:
            break
    
    # Price per sqft
    for pattern in ['sales_price_sqft', 'price_sqft', 'price_per_sqft', 'psf']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l or ('price' in col_l and 'sqft' in col_l):
                mapping['price_psf'] = col
                break
        if mapping['price_psf']:
            break
    
    # Sale date
    for pattern in ['custom_date', 'sale_date', 'transaction_date', 'date']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['sale_date'] = col
                break
        if mapping['sale_date']:
            break
    
    # Floor level
    for pattern in ['floor_level', 'floor_no', 'floor', 'level']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['floor_level'] = col
                break
        if mapping['floor_level']:
            break
    
    # Developer name (can be seller for primary sales)
    for pattern in ['dev_name', 'developer', 'developer_name', 'seller']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['developer'] = col
                break
        if mapping['developer']:
            break
    
    # View type
    for pattern in ['custom_view', 'view', 'view_type']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['view'] = col
                break
        if mapping['view']:
            break

    # Transaction type (Title Deed vs Oqood)
    for pattern in ['trans_group_en', 'trans_group', 'transaction_group', 'transaction_type']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['trans_group_en'] = col
                break
        if mapping['trans_group_en']:
            break

    # Sale recurrence (Resale vs Initial Sale)
    for pattern in ['sales_recurrence', 'sale_recurrence', 'recurrence']:
        for col_l, col in col_lower_map.items():
            if pattern in col_l:
                mapping['sales_recurrence'] = col
                break
        if mapping['sales_recurrence']:
            break

    return mapping


def clean_reference_beds(val) -> Optional[int]:
    """Clean bedroom value: 's' -> 0 (studio)."""
    if pd.isna(val) or str(val).strip() == '':
        return None
    s = str(val).strip().lower()
    if s == 's' or 'studio' in s:
        return 0
    try:
        return int(float(s))
    except:
        return None


# =============================================================================
# SIZE COLUMN DETECTION FOR LEAD FILES
# =============================================================================

SIZE_PRIORITY_SQFT = [
    'unit_size_sqft', 'unit size sqft', 'unitsize_sqft',
    'built_up_area_sqft', 'built up area sqft', 'bua_sqft',
    'actual_sqft', 'actual size sqft'
]
SIZE_PRIORITY_SQM = [
    'unit_size_sqm', 'unit size sqm', 'unitsize_sqm',
    'built_up_area_sqm', 'built up area sqm', 'bua_sqm',
    'actual_sqm', 'actual size sqm'
]
SIZE_EXCLUSIONS = ['plot', 'land', 'garden', 'balcony', 'terrace']


def detect_size_column(df: pd.DataFrame) -> Tuple[Optional[str], str]:
    """Detect size column in lead files with proper priority."""
    col_lower_map = {str(c).lower().strip(): c for c in df.columns}
    
    def is_excluded(col_lower: str) -> bool:
        return any(excl in col_lower for excl in SIZE_EXCLUSIONS)
    
    for pattern in SIZE_PRIORITY_SQFT:
        for col_l, col in col_lower_map.items():
            if is_excluded(col_l):
                continue
            norm_col = re.sub(r'[^a-z0-9]', '', col_l)
            norm_pattern = re.sub(r'[^a-z0-9]', '', pattern)
            if norm_pattern in norm_col or norm_col in norm_pattern:
                return col, 'sqft'
    
    for pattern in SIZE_PRIORITY_SQM:
        for col_l, col in col_lower_map.items():
            if is_excluded(col_l):
                continue
            norm_col = re.sub(r'[^a-z0-9]', '', col_l)
            norm_pattern = re.sub(r'[^a-z0-9]', '', pattern)
            if norm_pattern in norm_col or norm_col in norm_pattern:
                return col, 'sqm'
    
    for col_l, col in col_lower_map.items():
        if is_excluded(col_l):
            continue
        if 'sqft' in col_l or 'sq ft' in col_l:
            return col, 'sqft'
    
    for col_l, col in col_lower_map.items():
        if is_excluded(col_l):
            continue
        if 'sqm' in col_l or 'sq m' in col_l:
            return col, 'sqm'
    
    # CRITICAL: For generic "Size" or "Area" columns, analyze the data
    # Most Dubai lead files use sqm (small values like 150-500)
    for pattern in ['size', 'area', 'bua']:
        for col_l, col in col_lower_map.items():
            if is_excluded(col_l):
                continue
            if pattern in col_l:
                # Analyze values to determine unit
                unit = _detect_unit_from_values(df[col])
                return col, unit
    
    return None, 'unknown'


def _detect_unit_from_values(series: pd.Series) -> str:
    """
    Analyze size values to determine if they're sqft or sqm.
    
    Logic:
    - sqm values for Palm Jumeirah apartments: typically 50-500
    - sqft values for Palm Jumeirah apartments: typically 500-5000
    - If median < 600 and most values < 1000, likely sqm
    """
    numeric = pd.to_numeric(series, errors='coerce').dropna()
    if numeric.empty:
        return 'unknown'
    
    # Filter to reasonable range
    valid = numeric[(numeric >= 30) & (numeric <= 100000)]
    if valid.empty:
        return 'unknown'
    
    median = valid.median()
    pct_under_600 = (valid < 600).sum() / len(valid)
    
    # sqm detection: median < 600 AND most values under 600
    # This captures typical apartment sizes in sqm (50-500 sqm)
    if median < 600 and pct_under_600 > 0.5:
        return 'sqm'
    
    # If median > 1000, likely sqft
    if median > 1000:
        return 'sqft'
    
    # For values in the ambiguous 600-1000 range, assume sqm
    # (a 600 sqm apartment = 6,458 sqft = huge luxury unit)
    # (a 600 sqft apartment = 56 sqm = tiny studio)
    # Most lead files in Dubai use sqm
    if median < 1000:
        return 'sqm'
    
    return 'unknown'


def clean_size_value(val) -> Optional[float]:
    """Extract numeric size value."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s.lower() in ['nan', 'none', 'null', '', '-', 'n/a']:
        return None
    s = s.replace(',', '')
    match = re.search(r'[\d.]+', s)
    if match:
        try:
            num = float(match.group())
            if 30 <= num <= 100000:
                return num
        except:
            pass
    return None


def convert_to_sqft_if_needed(size_val: float, detected_unit: str) -> float:
    """
    Convert size to sqft, handling auto-detection for 'unknown' unit.
    
    Additional sanity check: if after conversion/no-conversion the value
    seems impossibly small for sqft (< 300), it was probably sqm.
    """
    if size_val is None:
        return None
    
    if detected_unit == 'sqft':
        # Already sqft, but sanity check
        # If value < 300, it's suspiciously small for sqft
        if size_val < 300:
            # Likely was sqm mistakenly labeled as sqft
            return size_val * SQM_TO_SQFT
        return size_val
    
    if detected_unit == 'sqm':
        return size_val * SQM_TO_SQFT
    
    # For 'unknown': apply heuristic
    # Values < 800 are almost certainly sqm (800 sqm = 8600 sqft = mansion)
    # Values > 1500 are likely sqft (1500 sqm = 16,000 sqft = huge villa)
    if size_val < 800:
        return size_val * SQM_TO_SQFT
    
    # Ambiguous range 800-1500: could be either
    # Lean towards sqft since that's more common for this range
    return size_val


# =============================================================================
# EXACT UNIT LOOKUP (building + unit -> bedrooms, size from reference)
# =============================================================================

def _norm_unit_for_lookup(x) -> str:
    """Normalize unit number for exact lookup key; same as used in recent-transaction matching."""
    if BUILDING_INTELLIGENCE_AVAILABLE and normalize_unit_number is not None:
        out = normalize_unit_number(x) if x is not None and (pd.notna(x) and str(x).strip()) else 'N/A'
    else:
        out = str(x).strip().upper() if x is not None and pd.notna(x) else 'N/A'
    return out if out != 'N/A' else ''


def build_exact_unit_lookup(reference_df: pd.DataFrame) -> Dict:
    """
    Build dict keyed by (building_std_lower, normalized_unit) -> {bedrooms, size_sqft, size_sqm}.
    When a unit appears multiple times, use the most recent transaction (latest sale_date).
    """
    if reference_df is None or reference_df.empty:
        return {}
    if 'building_std' not in reference_df.columns or 'unit_no' not in reference_df.columns:
        return {}
    ref = reference_df[
        reference_df['building_std'].notna() &
        reference_df['unit_no'].notna() &
        reference_df['bedrooms'].notna() &
        reference_df['size_sqft'].notna() &
        (reference_df['size_sqft'] > 100)
    ].copy()
    if ref.empty:
        return {}
    ref['_b'] = ref['building_std'].fillna('').astype(str).str.strip().str.lower()
    ref['_u'] = ref['unit_no'].apply(_norm_unit_for_lookup)
    ref = ref[ref['_u'] != '']
    if ref.empty:
        return {}
    if 'sale_date' in ref.columns:
        ref['_sale_date'] = pd.to_datetime(ref['sale_date'], errors='coerce')
        ref = ref.sort_values('_sale_date', ascending=False, na_position='last')
    latest = ref.groupby(['_b', '_u'], as_index=False).first()
    lookup = {}
    for _, row in latest.iterrows():
        key = (str(row['_b']), str(row['_u']))
        try:
            beds = int(float(row['bedrooms']))
        except (TypeError, ValueError):
            continue
        try:
            sqft = float(row['size_sqft'])
        except (TypeError, ValueError):
            continue
        if sqft < 100:
            continue
        sqm = round(sqft * SQFT_TO_SQM, 1)
        lookup[key] = {'bedrooms': beds, 'size_sqft': round(sqft, 0), 'size_sqm': sqm}
    print(f"[OK] Exact unit lookup built with {len(lookup):,} entries")
    return lookup


# =============================================================================
# SIZE ESTIMATION FROM BEDROOMS
# =============================================================================

def build_size_estimation_table(reference_df: pd.DataFrame) -> Dict:
    """Build 3-tier size estimation table."""
    if reference_df is None or reference_df.empty:
        return {}
    
    estimation_table = {}
    
    ref_valid = reference_df[
        reference_df['building_std'].notna() & 
        reference_df['bedrooms'].notna() &
        reference_df['size_sqft'].notna() &
        (reference_df['size_sqft'] > 100)
    ].copy()
    
    if ref_valid.empty:
        return {}
    
    # TIER 1: Specific building + bedrooms
    for (building, bedrooms), group in ref_valid.groupby(['building_std', 'bedrooms']):
        if pd.isna(building) or pd.isna(bedrooms):
            continue
        sizes_sqft = group['size_sqft'].dropna()
        if len(sizes_sqft) > 0:
            count = len(sizes_sqft)
            conf = 'High' if count >= 5 else 'Medium' if count >= 2 else 'Low'
            
            key = (str(building).lower(), int(bedrooms), 'specific')
            estimation_table[key] = {
                'avg_sqft': round(sizes_sqft.mean(), 0),
                'min_sqft': round(sizes_sqft.min(), 0),
                'max_sqft': round(sizes_sqft.max(), 0),
                'avg_sqm': round(sizes_sqft.mean() * SQFT_TO_SQM, 1),
                'sample_count': count,
                'confidence': conf
            }
    
    # TIER 2: Building family + bedrooms
    for (family, bedrooms), group in ref_valid.groupby(['building_family', 'bedrooms']):
        if pd.isna(family) or pd.isna(bedrooms):
            continue
        sizes_sqft = group['size_sqft'].dropna()
        if len(sizes_sqft) > 0:
            count = len(sizes_sqft)
            conf = 'High' if count >= 10 else 'Medium' if count >= 5 else 'Low'
            
            key = (str(family).lower(), int(bedrooms), 'family')
            estimation_table[key] = {
                'avg_sqft': round(sizes_sqft.mean(), 0),
                'min_sqft': round(sizes_sqft.min(), 0),
                'max_sqft': round(sizes_sqft.max(), 0),
                'avg_sqm': round(sizes_sqft.mean() * SQFT_TO_SQM, 1),
                'sample_count': count,
                'confidence': conf
            }
    
    # TIER 3: Palm-wide average per bedroom
    for bedrooms, group in ref_valid.groupby('bedrooms'):
        if pd.isna(bedrooms):
            continue
        sizes_sqft = group['size_sqft'].dropna()
        if len(sizes_sqft) > 0:
            key = ('palm jumeirah', int(bedrooms), 'palmwide')
            estimation_table[key] = {
                'avg_sqft': round(sizes_sqft.mean(), 0),
                'min_sqft': round(sizes_sqft.min(), 0),
                'max_sqft': round(sizes_sqft.max(), 0),
                'avg_sqm': round(sizes_sqft.mean() * SQFT_TO_SQM, 1),
                'sample_count': len(sizes_sqft),
                'confidence': 'Low'
            }
    
    print(f"[OK] Size estimation table built with {len(estimation_table)} entries")
    return estimation_table


def build_bedroom_prediction_table(reference_df: pd.DataFrame) -> Dict:
    """Build size ranges per building+bedroom for reverse prediction."""
    if reference_df is None or reference_df.empty:
        return {}
    
    prediction_table = {}
    
    ref_valid = reference_df[
        reference_df['building_std'].notna() & 
        reference_df['bedrooms'].notna() &
        reference_df['size_sqft'].notna() &
        (reference_df['size_sqft'] > 100)
    ].copy()
    
    if ref_valid.empty:
        return {}
    
    # Building-specific ranges
    for (building, bedrooms), group in ref_valid.groupby(['building_std', 'bedrooms']):
        if pd.isna(building) or pd.isna(bedrooms):
            continue
        sizes = group['size_sqft'].dropna()
        if len(sizes) >= 2:
            key = (str(building).lower(), int(bedrooms))
            prediction_table[key] = {
                'min': sizes.min(),
                'max': sizes.max(),
                'avg': sizes.mean(),
                'count': len(sizes)
            }
    
    # Family-level ranges
    for (family, bedrooms), group in ref_valid.groupby(['building_family', 'bedrooms']):
        if pd.isna(family) or pd.isna(bedrooms):
            continue
        sizes = group['size_sqft'].dropna()
        if len(sizes) >= 3:
            key = (str(family).lower() + '_family', int(bedrooms))
            prediction_table[key] = {
                'min': sizes.min(),
                'max': sizes.max(),
                'avg': sizes.mean(),
                'count': len(sizes)
            }
    
    print(f"[OK] Bedroom prediction table built with {len(prediction_table)} entries")
    return prediction_table


def estimate_size_from_bedrooms(building: str, bedrooms, estimation_table: Dict) -> Dict:
    """Estimate size from bedrooms using 3-tier fallback."""
    result = {
        'size_sqft': None,
        'size_sqm': None,
        'method': 'No Data',
        'confidence': 'None'
    }
    
    if not building or pd.isna(bedrooms):
        return result
    
    building_lower = str(building).lower()
    building_family = get_building_family(building).lower()
    
    try:
        beds_int = int(float(bedrooms))
    except:
        return result
    
    # TIER 1: Specific building
    key_specific = (building_lower, beds_int, 'specific')
    if key_specific in estimation_table:
        stats = estimation_table[key_specific]
        return {
            'size_sqft': stats['avg_sqft'],
            'size_sqm': stats['avg_sqm'],
            'method': 'Reference',
            'confidence': stats['confidence']
        }
    
    # TIER 2: Building family
    key_family = (building_family, beds_int, 'family')
    if key_family in estimation_table:
        stats = estimation_table[key_family]
        return {
            'size_sqft': stats['avg_sqft'],
            'size_sqm': stats['avg_sqm'],
            'method': 'Family',
            'confidence': stats['confidence']
        }
    
    # TIER 3: Palm-wide
    key_palmwide = ('palm jumeirah', beds_int, 'palmwide')
    if key_palmwide in estimation_table:
        stats = estimation_table[key_palmwide]
        return {
            'size_sqft': stats['avg_sqft'],
            'size_sqm': stats['avg_sqm'],
            'method': 'Palm Avg',
            'confidence': 'Low'
        }
    
    return result


# =============================================================================
# UNIT PATTERN RECOGNITION
# =============================================================================

def extract_unit_pattern(unit_str) -> Optional[str]:
    """Extract unit pattern from unit number (last 2 digits)."""
    if pd.isna(unit_str) or str(unit_str).strip() == '':
        return None
    
    unit_clean = str(unit_str).strip().upper()
    unit_clean = re.sub(r'(UNIT|APT|PH|FLAT|NO\.?)', '', unit_clean).strip()
    
    digits = ''.join(filter(str.isdigit, unit_clean))
    
    if len(digits) == 0:
        return None
    
    if len(digits) >= 2:
        return digits[-2:]
    return digits.zfill(2)


def build_unit_pattern_table(reference_df: pd.DataFrame) -> Dict:
    """Build unit pattern recognition table."""
    if reference_df is None or reference_df.empty:
        return {}
    
    valid_refs = reference_df[
        (reference_df['unit_no'] != '') & 
        reference_df['bedrooms'].notna() &
        reference_df['size_sqft'].notna() &
        (reference_df['size_sqft'] > 100)
    ].copy()
    
    if valid_refs.empty:
        return {}
    
    valid_refs['unit_pattern'] = valid_refs['unit_no'].apply(extract_unit_pattern)
    valid_refs = valid_refs[valid_refs['unit_pattern'].notna()]
    
    if valid_refs.empty:
        return {}
    
    unit_pattern_table = {}
    
    for (building, pattern), group in valid_refs.groupby(['building_std', 'unit_pattern']):
        if pd.isna(pattern) or pattern == '' or pd.isna(building):
            continue
        
        bedrooms_list = group['bedrooms'].tolist()
        sizes_sqft = group['size_sqft'].tolist()
        
        most_common_beds = max(set(bedrooms_list), key=bedrooms_list.count)
        avg_size = sum(sizes_sqft) / len(sizes_sqft)
        count = len(group)
        
        conf = 'High' if count >= 3 else 'Medium' if count >= 2 else 'Low'
        
        key = (str(building).lower(), pattern)
        unit_pattern_table[key] = {
            'bedrooms': int(most_common_beds),
            'avg_sqft': round(avg_size, 0),
            'avg_sqm': round(avg_size * SQFT_TO_SQM, 1),
            'sample_count': count,
            'confidence': conf
        }
    
    # Family-level patterns
    for (family, pattern), group in valid_refs.groupby(['building_family', 'unit_pattern']):
        if pd.isna(pattern) or pattern == '' or pd.isna(family):
            continue
        
        bedrooms_list = group['bedrooms'].tolist()
        sizes_sqft = group['size_sqft'].tolist()
        
        most_common_beds = max(set(bedrooms_list), key=bedrooms_list.count)
        avg_size = sum(sizes_sqft) / len(sizes_sqft)
        count = len(group)
        
        conf = 'High' if count >= 5 else 'Medium' if count >= 3 else 'Low'
        
        key = (str(family).lower() + '_family', pattern)
        unit_pattern_table[key] = {
            'bedrooms': int(most_common_beds),
            'avg_sqft': round(avg_size, 0),
            'avg_sqm': round(avg_size * SQFT_TO_SQM, 1),
            'sample_count': count,
            'confidence': conf
        }
    
    pattern_count = len([k for k in unit_pattern_table.keys() if '_family' not in k[0]])
    print(f"[OK] Unit pattern table built with {pattern_count} building patterns")
    return unit_pattern_table


def infer_from_unit_pattern(building: str, unit_number: str, 
                            unit_pattern_table: Dict) -> Optional[Dict]:
    """Infer bedrooms and size from unit pattern."""
    if not building or not unit_number or not unit_pattern_table:
        return None
    
    pattern = extract_unit_pattern(unit_number)
    if not pattern:
        return None
    
    building_lower = str(building).lower()
    family = get_building_family(building).lower()
    
    # Try exact building match
    key_exact = (building_lower, pattern)
    if key_exact in unit_pattern_table:
        stats = unit_pattern_table[key_exact]
        return {
            'bedrooms': stats['bedrooms'],
            'size_sqft': stats['avg_sqft'],
            'size_sqm': stats['avg_sqm'],
            'method': 'Pattern',
            'confidence': stats['confidence']
        }
    
    # Try family match
    key_family = (family + '_family', pattern)
    if key_family in unit_pattern_table:
        stats = unit_pattern_table[key_family]
        return {
            'bedrooms': stats['bedrooms'],
            'size_sqft': stats['avg_sqft'],
            'size_sqm': stats['avg_sqm'],
            'method': 'Family Pattern',
            'confidence': 'Medium' if stats['confidence'] == 'High' else 'Low'
        }
    
    return None


# =============================================================================
# COLUMN DETECTION FOR LEAD FILES
# =============================================================================

COLUMN_PATTERNS = {
    'building_name': [
        'master project', 'masterproject', 'master_project',
        'buildingnameen', 'buildingname', 'building_name',
        'building 1', 'building 2', 'building1', 'building2',
        'project', 'building', 'development', 'community'
    ],
    'unit_number': [
        'property_number', 'propertynumber', 'property_no',
        'unitnumber', 'unit_number', 'unit_no', 'unit', 'apt', 'apartment', 'flat'
    ],
    'bedrooms': ['beds', 'bedrooms', 'bedroom', 'br', 'bed', 'no_of_beds', 'num_beds'],
    'phone': [
        'phone 1', 'phone 2', 'phone1', 'phone2', 'mobile 1', 'mobile 2',
        'mobile1', 'mobile2', 'secondary mobile', 'secondarymobile',
        'phone', 'mobile', 'contact', 'tel', 'telephone', 'cell', 'mob'
    ],
    'owner_name': [
        'owner name', 'owner_name', 'ownername', 'nameen', 'name_en', 'name en',
        'owner', 'client_name', 'client', 'customer', 'landlord', 'seller'
    ],
    'date': [
        'date', 'timestamp', 'created', 'created_at', 'createdat',
        'entry_date', 'upload_date', 'added', 'registered', 'regis'
    ]
}

EXCLUDED_COLS = {
    'countrynameen', 'countryname', 'country', 'location', 'masterlocation',
    'subtype', 'propertytype', 'completionstatus', 'usage', 'transactionamount',
    'municipalityno', 'municipalitysubno', 'landnumber', 'passport', 'procedurevalue'
}


def normalize_col_name(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def fuzzy_match(col: str, patterns: List[str], field: str = '') -> bool:
    norm = normalize_col_name(col)
    if norm in EXCLUDED_COLS:
        return False
    if field == 'owner_name' and any(k in norm for k in ['building', 'project', 'property', 'unit']):
        return False
    for p in patterns:
        pn = normalize_col_name(p)
        if pn in norm or norm in pn:
            return True
    return False


def detect_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    detected = {f: [] for f in COLUMN_PATTERNS}
    assigned = set()
    for field in ['owner_name', 'bedrooms', 'phone', 'date', 'unit_number', 'building_name']:
        for col in df.columns:
            if col in assigned:
                continue
            if fuzzy_match(str(col), COLUMN_PATTERNS[field], field):
                detected[field].append(col)
                assigned.add(col)
    return detected


# =============================================================================
# DATA CLEANING
# =============================================================================

def clean_phone(val) -> str:
    if pd.isna(val):
        return ''
    s = str(val).strip()
    if s.lower() in ['nan', 'none', 'null', '']:
        return ''
    try:
        f = float(s)
        if f == int(f):
            s = str(int(f))
    except:
        pass
    digits = re.sub(r'[^\d+]', '', s)
    return digits if len(digits) >= 7 else ''


def merge_phones(row, phone_cols: List[str]) -> str:
    phones = []
    for col in phone_cols:
        if col in row.index:
            p = clean_phone(row[col])
            if p and p not in phones:
                phones.append(p)
    return ' | '.join(phones) if phones else ''


def merge_building_names(row, bldg_cols: List[str]) -> Optional[str]:
    parts = []
    for col in bldg_cols:
        if col in row.index:
            val = row[col]
            if pd.notna(val) and str(val).strip() and str(val).strip() != '0':
                clean = str(val).strip()
                if clean not in parts:
                    parts.append(clean)
    merged = ' - '.join(parts) if parts else None
    return standardize_building_name(merged) if merged else None


def clean_bedroom(val) -> Optional[int]:
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if not s or s in ['nan', 'none', 'null']:
        return None
    if 'studio' in s or s == 's':
        return 0
    match = re.search(r'(\d+)', s)
    return int(match.group(1)) if match else None


def get_first_non_null(row, cols: List[str]) -> Optional[str]:
    for col in cols:
        if col in row.index:
            val = row[col]
            if pd.notna(val) and str(val).strip():
                return str(val).strip()
    return None


# =============================================================================
# FILE LOADING AND NORMALIZATION
# =============================================================================

def load_data_files(data_path: str = './data') -> Tuple[List[Tuple[str, pd.DataFrame]], List[str]]:
    files, errors = [], []
    data_dir = Path(data_path)
    
    if not data_dir.exists():
        return files, [f"Data folder not found: {data_path}"]
    
    csv_files = list(data_dir.glob('*.csv'))
    xlsx_files = list(data_dir.glob('*.xlsx'))
    xls_files = list(data_dir.glob('*.xls'))
    all_files = csv_files + xlsx_files + xls_files
    
    if not all_files:
        return files, [f"No CSV or Excel files in {data_path}"]
    
    for f in all_files:
        try:
            df = None
            if f.suffix.lower() == '.csv':
                for enc in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                        df = pd.read_csv(f, encoding=enc, low_memory=False)
                        break
                    except UnicodeDecodeError:
                        continue
            elif f.suffix.lower() in ['.xlsx', '.xls']:
                try:
                    excel_file = pd.ExcelFile(f)
                    sheet_dfs = []
                    for sheet_name in excel_file.sheet_names:
                        sheet_df = pd.read_excel(f, sheet_name=sheet_name)
                        if not sheet_df.empty:
                            sheet_dfs.append(sheet_df)
                    if sheet_dfs:
                        df = pd.concat(sheet_dfs, ignore_index=True)
                except Exception as e:
                    errors.append(f"Error reading Excel {f.name}: {e}")
                    continue
            
            if df is not None and not df.empty:
                files.append((f.name, df))
        except Exception as e:
            errors.append(f"Error loading {f.name}: {e}")
    
    return files, errors


def normalize_dataframe(df: pd.DataFrame, filename: str = '') -> pd.DataFrame:
    """Normalize DataFrame with size extraction."""
    if df.empty:
        return pd.DataFrame(columns=['date', 'owner_name', 'building_name', 'bedrooms', 
                                      'unit_number', 'phone', 'original_size_sqft'])
    
    col_map = detect_columns(df)
    result = pd.DataFrame(index=df.index)
    
    if col_map['date']:
        result['date'] = pd.to_datetime(df[col_map['date'][0]], errors='coerce', dayfirst=True)
    else:
        result['date'] = pd.NaT
    
    if col_map['owner_name']:
        result['owner_name'] = df.apply(
            lambda row: (get_first_non_null(row, col_map['owner_name']) or '').title() or None, axis=1
        )
    else:
        result['owner_name'] = None
    
    if col_map['building_name']:
        result['building_name'] = df.apply(
            lambda row: merge_building_names(row, col_map['building_name']), axis=1
        )
    else:
        result['building_name'] = None
    
    if col_map['bedrooms']:
        result['bedrooms'] = df[col_map['bedrooms'][0]].apply(clean_bedroom)
    else:
        result['bedrooms'] = None
    
    if col_map['unit_number']:
        result['unit_number'] = df.apply(
            lambda row: get_first_non_null(row, col_map['unit_number']), axis=1
        )
    else:
        result['unit_number'] = None
    
    if col_map['phone']:
        result['phone'] = df.apply(lambda row: merge_phones(row, col_map['phone']), axis=1)
    else:
        result['phone'] = ''
    
    # Extract size from lead files with smart unit detection
    size_col, size_unit = detect_size_column(df)
    if size_col:
        def extract_size(val):
            cleaned = clean_size_value(val)
            if cleaned is None:
                return None
            # Use smart conversion that handles unknown units
            return convert_to_sqft_if_needed(cleaned, size_unit)
        result['original_size_sqft'] = df[size_col].apply(extract_size)
        
        # Debug: show what we detected
        valid_sizes = result['original_size_sqft'].dropna()
        if len(valid_sizes) > 0:
            print(f"   Size column '{size_col}' detected as {size_unit}")
            print(f"   After conversion: min={valid_sizes.min():.0f}, max={valid_sizes.max():.0f}, median={valid_sizes.median():.0f} sqft")
    else:
        result['original_size_sqft'] = None
    
    result['_source'] = filename
    return result


# =============================================================================
# COMPREHENSIVE ENRICHMENT ENGINE
# Priority order for bedroom inference (highest authority first). Each step
# is only tried if the previous steps did not resolve a bedroom:
#   0.   Exact (building, unit) hit in DLD reference file
#   1.   Original bedroom value already in the lead file
#   1.5  Live Reidin DLD lookup (reidin_master.parquet) -- HIGH
#   2.   Unit registry lookup (multi-source, prebuilt)
#   2.3  Live PropertyFinder file lookup -- LOW (PF can misread bedrooms)
#   2.6  Bayut size-match consensus across listings (+/-75 sqft)
#   3.   Static building unit schema (manual overrides)
#   3.5  Dynamic schema learned from registry suffix patterns
#   4.   Unit pattern table from reference data
#   4.5  Size-based inference from lead file size
#   5.   Building default bedrooms
#
# Keep this comment and the `stats` counter names below in sync with the
# actual cascade. The counter names are used by the reload summary so
# each priority needs its own counter, not a shared "registry" one.
# =============================================================================

def apply_comprehensive_enrichment(lead_df: pd.DataFrame,
                                    estimation_table: Dict,
                                    prediction_table: Dict,
                                    unit_pattern_table: Dict,
                                    exact_unit_lookup: Optional[Dict] = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Apply comprehensive enrichment with priority-based bedroom inference.
    Priority 0: exact (building, unit) match from reference data overrides all.
    Ensures NO ambiguous output (no "Studio*", no "[orig]" prefixes).
    """
    if exact_unit_lookup is None:
        exact_unit_lookup = {}
    stats = {
        'beds_original': 0,
        'beds_from_exact': 0,
        'beds_from_reidin': 0,
        'beds_from_registry': 0,
        'beds_from_pf': 0,
        'beds_from_bayut_size': 0,
        'beds_from_schema': 0,
        'beds_from_pattern': 0,
        'beds_from_size': 0,
        'beds_from_default': 0,
        'beds_unresolved': 0,
        'size_original': 0,
        'size_from_exact': 0,
        'size_estimated': 0,
        'size_unresolved': 0,
        'validation_flags': 0
    }

    # Build unit registry lookup dict once (O(1) per lead instead of O(n) file reads)
    registry_lookup = {}
    dynamic_schema = {}  # {building_key: {unit_suffix: bedrooms}} — auto-learned from registry
    if UNIT_REGISTRY_AVAILABLE:
        try:
            reg_df = _load_unit_registry()
            if not reg_df.empty:
                for _, r in reg_df.iterrows():
                    if pd.isna(r.get('building_name')) or pd.isna(r.get('unit_number')):
                        continue
                    reg_b = str(r['building_name']).strip().lower().replace(' ', '').replace('-', '')
                    reg_u = str(r['unit_number']).strip().upper().replace(' ', '').replace('-', '')
                    reg_key = f"{reg_b}|{reg_u}"
                    # Only store if has bedrooms; prefer higher-confidence entries
                    if reg_key not in registry_lookup or (
                        r.get('confidence') == 'HIGH' and registry_lookup[reg_key].get('confidence') != 'HIGH'
                    ):
                        registry_lookup[reg_key] = {
                            'bedrooms': str(r['bedrooms']) if pd.notna(r.get('bedrooms')) else None,
                            'size_sqft': float(r['size_sqft']) if pd.notna(r.get('size_sqft')) else None,
                            'confidence': str(r.get('confidence', 'MEDIUM')),
                            'sources': str(r.get('sources', '')),
                        }

                # Build dynamic suffix schema: for each building, find unit suffixes where
                # 2+ known units consistently map to the same bedroom count
                try:
                    known = reg_df[reg_df['bedrooms'].notna()].copy()
                    known['bedrooms_num'] = pd.to_numeric(known['bedrooms'], errors='coerce')
                    known = known[known['bedrooms_num'].notna()]
                    known['_suffix'] = known['unit_number'].apply(
                        lambda u: (lambda d: d[-2:].zfill(2) if len(d) >= 2 else None)(
                            re.sub(r'[^0-9]', '', str(u)))
                    )
                    known = known[known['_suffix'].notna()]
                    for (bname, suffix), grp in known.groupby(['building_name', '_suffix']):
                        if len(grp) >= 2 and grp['bedrooms_num'].nunique() == 1:
                            bkey = str(bname).strip().lower().replace(' ', '').replace('-', '')
                            if bkey not in dynamic_schema:
                                dynamic_schema[bkey] = {}
                            dynamic_schema[bkey][suffix] = int(grp['bedrooms_num'].iloc[0])
                except Exception:
                    pass
        except Exception:
            pass

    # ── Live Reidin DLD lookup (HIGHEST external authority — official DLD transactions) ──────
    # Reads reidin_master directly so new uploads are effective without registry rebuild.
    # Graceful degradation: if reidin_master is missing, lookup stays {} and cascade
    # silently falls through to Priority 2 (Unit Registry) with no error.
    reidin_live_lookup = {}
    _reidin_path = Path("data/reidin_master.parquet")
    _reidin_csv_path = Path("data/reidin_master.csv")
    _rpath = _reidin_path if _reidin_path.exists() else (_reidin_csv_path if _reidin_csv_path.exists() else None)
    if _rpath:
        try:
            reidin_raw = pd.read_parquet(_rpath) if str(_rpath).endswith('.parquet') else pd.read_csv(_rpath, low_memory=False)
            _shoreline_towers = [
                "alramth", "alnabat", "almurjan", "almashraba", "alkhayali",
                "almalak", "alhabool", "alghaf", "almasalli", "alhallawi",
                "alanbara", "jashfalqa", "alshamsi", "jashhamad",
                "albasri", "alsahab", "alanbar", "aldawaar", "almsalli",
                "alsultana", "althamam", "aldas", "alkhushkar", "aljanahi",
                "almajara", "alfahad", "alfattan", "alshirawi", "alhamri",
                "alhatmi", "alseef", "shorelineapartments",
            ]
            for _, row in reidin_raw.iterrows():
                bld = str(row.get('building_name', '')).strip().lower().replace(' ', '').replace('-', '')
                unit = str(row.get('unit_number', '')).strip().upper().replace(' ', '').replace('-', '')
                if not bld or not unit or unit in ("-", "NAN", ""):
                    continue
                beds = row.get('bedrooms')
                size = row.get('size_sqft')
                data_val = {"bedrooms": beds, "size_sqft": size}
                # Shoreline: stored under every tower alias so any tower name matches by unit
                if "shoreline" in bld or bld == "shorelineapartments":
                    for tower_key in _shoreline_towers:
                        k = f"{tower_key}|{unit}"
                        if k not in reidin_live_lookup:
                            reidin_live_lookup[k] = data_val
                else:
                    key = f"{bld}|{unit}"
                    if key not in reidin_live_lookup:
                        reidin_live_lookup[key] = data_val
        except Exception as e:
            # Reidin lookup failed -- cascade continues at Priority 2 so the
            # app still loads, but log the failure instead of swallowing so
            # corruption / schema drift in reidin_master doesn't hide.
            print(f"[cascade] Priority 1.5 Reidin load failed ({_rpath.name}): {e}; falling through to registry")

    # Live PF lookup: unit+building → bedrooms (lower confidence — PF scraper can misread bedrooms)
    pf_live_lookup = {}
    _pf_path = Path("scraped_data/propertyfinder_scraped_leads.csv")
    if _pf_path.exists():
        try:
            pf_live = pd.read_csv(_pf_path, encoding="utf-8", low_memory=False)
            for _, r in pf_live.iterrows():
                if pd.isna(r.get("building_name")) or pd.isna(r.get("unit_number")):
                    continue
                room_type = r.get("room_type")
                if pd.isna(room_type):
                    continue
                br_m = re.search(r"(\d+)", str(room_type))
                if not br_m:
                    continue
                std_pf_name = standardize_building_name(str(r["building_name"])) or str(r["building_name"])
                pf_b = std_pf_name.strip().lower().replace(" ", "").replace("-", "")
                pf_u = str(r["unit_number"]).strip().upper().replace(" ", "").replace("-", "")
                pf_key = f"{pf_b}|{pf_u}"
                size_sqft = None
                if pd.notna(r.get("size_sqm")):
                    try:
                        sqm = float(str(r["size_sqm"]).replace("sqm", "").replace(",", "").strip())
                        size_sqft = round(sqm * 10.7639, 1)
                    except Exception:
                        pass
                pf_live_lookup[pf_key] = {"bedrooms": br_m.group(1), "size_sqft": size_sqft}
        except Exception as e:
            print(f"[cascade] Priority 2.3 PF load failed ({_pf_path.name}): {e}; falling through")

    # Bayut size-match lookup: {building_key: [(size_sqft, bedrooms)]}
    # Uses standardize_building_name so keys match what the enrichment loop sees
    bayut_size_lookup = {}
    _bayut_path = Path("data/bayut_palm_listings.csv")
    if _bayut_path.exists():
        try:
            bayut_raw = pd.read_csv(_bayut_path, encoding="utf-8", low_memory=False)
            bayut_valid = bayut_raw.dropna(subset=["building_name", "bedrooms", "size_sqft"])
            bayut_valid = bayut_valid[bayut_valid["size_sqft"] > 0]
            for _, r in bayut_valid.iterrows():
                # Standardize name so it matches lead/registry building names
                std_name = standardize_building_name(str(r["building_name"])) or str(r["building_name"])
                bkey = std_name.strip().lower().replace(" ", "").replace("-", "")
                try:
                    beds = int(float(r["bedrooms"]))
                    size = float(r["size_sqft"])
                    if bkey not in bayut_size_lookup:
                        bayut_size_lookup[bkey] = []
                    bayut_size_lookup[bkey].append((size, beds))
                except Exception:
                    # Per-row parse failure (e.g. 'Studio' bedrooms in a
                    # numeric-only column). Skip the row, keep the loop going.
                    continue
        except Exception as e:
            print(f"[cascade] Priority 2.6 Bayut load failed ({_bayut_path.name}): {e}; falling through")

    # Initialize clean columns
    lead_df['size_sqft'] = None
    lead_df['size_sqm'] = None
    lead_df['size_method'] = None
    lead_df['size_confidence'] = None
    lead_df['bedroom_method'] = None
    lead_df['bedroom_confidence'] = None
    lead_df['data_quality'] = 'OK'
    
    for idx in lead_df.index:
        building = lead_df.at[idx, 'building_name']
        bedrooms = lead_df.at[idx, 'bedrooms']
        unit_number = lead_df.at[idx, 'unit_number']
        original_size = lead_df.at[idx, 'original_size_sqft']
        
        bed_resolved = False
        size_resolved = False

        # PRIORITY 0: Exact (building, unit) match from reference data
        if exact_unit_lookup and building and unit_number:
            lead_b = (standardize_building_name(building) or '').strip().lower()
            lead_u = _norm_unit_for_lookup(unit_number)
            if lead_b and lead_u:
                key = (lead_b, lead_u)
                rec = exact_unit_lookup.get(key)
                if rec is None:
                    # Family-level fallback: strip trailing number (e.g. "shoreline 3" -> "shoreline")
                    base_b = re.sub(r'\s+\d+$', '', lead_b).strip()
                    if base_b != lead_b:
                        fallback_key = (base_b, lead_u)
                        rec = exact_unit_lookup.get(fallback_key)
                if rec is not None:
                    lead_df.at[idx, 'bedrooms'] = rec['bedrooms']
                    lead_df.at[idx, 'bedroom_method'] = 'Reference (Exact)'
                    lead_df.at[idx, 'bedroom_confidence'] = 'High'
                    lead_df.at[idx, 'size_sqft'] = rec['size_sqft']
                    lead_df.at[idx, 'size_sqm'] = rec['size_sqm']
                    lead_df.at[idx, 'size_method'] = 'Reference (Exact)'
                    lead_df.at[idx, 'size_confidence'] = 'High'
                    bed_resolved = True
                    size_resolved = True
                    stats['beds_from_exact'] += 1
                    stats['size_from_exact'] += 1

        # =====================================================================
        # BEDROOM RESOLUTION (Priority Order)
        # =====================================================================
        
        # PRIORITY 1: Original bedroom data from lead file
        if not bed_resolved and pd.notna(bedrooms):
            lead_df.at[idx, 'bedroom_method'] = 'Original'
            lead_df.at[idx, 'bedroom_confidence'] = 'High'
            bed_resolved = True
            stats['beds_original'] += 1

        # PRIORITY 1.5: Live Reidin DLD lookup — official DLD transactions, highest external authority
        # Reads reidin_master directly so any new upload is immediately effective.
        # Silently skipped if reidin_master is not yet uploaded (reidin_live_lookup will be {}).
        if not bed_resolved and reidin_live_lookup and building and unit_number:
            r_b = str(building).strip().lower().replace(' ', '').replace('-', '')
            r_u = str(unit_number).strip().upper().replace(' ', '').replace('-', '')
            r_key = f"{r_b}|{r_u}"
            r_rec = reidin_live_lookup.get(r_key)
            if r_rec and r_rec.get('bedrooms'):
                lead_df.at[idx, 'bedrooms'] = r_rec['bedrooms']
                lead_df.at[idx, 'bedroom_method'] = 'Reidin DLD (live)'
                lead_df.at[idx, 'bedroom_confidence'] = 'High'
                bed_resolved = True
                stats['beds_from_reidin'] += 1
                if not size_resolved and r_rec.get('size_sqft'):
                    lead_df.at[idx, 'size_sqft'] = r_rec['size_sqft']
                    lead_df.at[idx, 'size_sqm'] = round(r_rec['size_sqft'] * SQFT_TO_SQM, 0)
                    lead_df.at[idx, 'size_method'] = 'Reidin DLD (live)'
                    lead_df.at[idx, 'size_confidence'] = 'High'
                    size_resolved = True
                    stats['size_estimated'] += 1

        # PRIORITY 2: Unit registry lookup (confirmed from DLD/PM transactions + multi-source)
        if not bed_resolved and registry_lookup and building and unit_number:
            reg_b = str(building).strip().lower().replace(' ', '').replace('-', '')
            reg_u = str(unit_number).strip().upper().replace(' ', '').replace('-', '')
            reg_key = f"{reg_b}|{reg_u}"
            reg_rec = registry_lookup.get(reg_key)
            if reg_rec and reg_rec.get('bedrooms'):
                lead_df.at[idx, 'bedrooms'] = reg_rec['bedrooms']
                sources_label = reg_rec.get('sources', '')
                lead_df.at[idx, 'bedroom_method'] = f"Registry ({sources_label})"
                lead_df.at[idx, 'bedroom_confidence'] = reg_rec.get('confidence', 'MEDIUM').title()
                bed_resolved = True
                stats['beds_from_registry'] += 1
                # Also fill size from registry if not yet resolved
                if not size_resolved and reg_rec.get('size_sqft'):
                    lead_df.at[idx, 'size_sqft'] = reg_rec['size_sqft']
                    lead_df.at[idx, 'size_sqm'] = round(reg_rec['size_sqft'] * SQFT_TO_SQM, 0)
                    lead_df.at[idx, 'size_method'] = f"Registry ({sources_label})"
                    lead_df.at[idx, 'size_confidence'] = reg_rec.get('confidence', 'MEDIUM').title()
                    size_resolved = True
                    stats['size_estimated'] += 1

        # PRIORITY 2.3: Live PF file lookup (lower confidence — PF scraper can misread bedrooms)
        # Only used when PM and registry have no data for this unit
        if not bed_resolved and building and unit_number and pf_live_lookup:
            pf_b = str(building).strip().lower().replace(' ', '').replace('-', '')
            pf_u = str(unit_number).strip().upper().replace(' ', '').replace('-', '')
            pf_key = f"{pf_b}|{pf_u}"
            pf_rec = pf_live_lookup.get(pf_key)
            if pf_rec and pf_rec.get('bedrooms'):
                lead_df.at[idx, 'bedrooms'] = pf_rec['bedrooms']
                lead_df.at[idx, 'bedroom_method'] = 'PF scrape (live — verify)'
                lead_df.at[idx, 'bedroom_confidence'] = 'Low'
                bed_resolved = True
                stats['beds_from_pf'] += 1
                if not size_resolved and pf_rec.get('size_sqft'):
                    lead_df.at[idx, 'size_sqft'] = pf_rec['size_sqft']
                    lead_df.at[idx, 'size_sqm'] = round(pf_rec['size_sqft'] * SQFT_TO_SQM, 0)
                    lead_df.at[idx, 'size_method'] = 'PF scrape (live)'
                    lead_df.at[idx, 'size_confidence'] = 'Low'
                    size_resolved = True
                    stats['size_estimated'] += 1

        # PRIORITY 2.6: Bayut size-match (consensus across listings for same building+size ±75 sqft)
        # Resolves units where we know size but have no bedroom data from any unit-level source
        if not bed_resolved and building and bayut_size_lookup:
            # Use size from registry (if Priority 2 filled it) or from original lead data.
            # Read explicitly so a missing column or an all-NaN cell falls through to
            # original_size instead of hiding inside a nested ternary.
            unit_size = original_size
            if 'size_sqft' in lead_df.columns:
                registry_size = lead_df.at[idx, 'size_sqft']
                if pd.notna(registry_size):
                    unit_size = registry_size
            if pd.notna(unit_size) and unit_size > 300:
                bkey_b = str(building).strip().lower().replace(' ', '').replace('-', '')
                matches = bayut_size_lookup.get(bkey_b, [])
                nearby_beds = [beds for (sz, beds) in matches if abs(sz - unit_size) <= 75]
                if nearby_beds:
                    unique_beds = set(nearby_beds)
                    if len(unique_beds) == 1:  # Full consensus — all nearby listings agree
                        lead_df.at[idx, 'bedrooms'] = list(unique_beds)[0]
                        lead_df.at[idx, 'bedroom_method'] = f'Bayut size-match ({int(unit_size)} sqft, {len(nearby_beds)} listings)'
                        lead_df.at[idx, 'bedroom_confidence'] = 'Medium'
                        bed_resolved = True
                        stats['beds_from_bayut_size'] += 1

        # PRIORITY 3: Building-specific unit schema (manual override table)
        if not bed_resolved and building and unit_number:
            schema_result = infer_bedrooms_from_unit_schema(building, unit_number)
            if schema_result:
                lead_df.at[idx, 'bedrooms'] = schema_result['bedrooms']
                lead_df.at[idx, 'bedroom_method'] = schema_result['method']
                lead_df.at[idx, 'bedroom_confidence'] = schema_result['confidence']
                bed_resolved = True
                stats['beds_from_schema'] += 1

        # PRIORITY 3.5: Dynamic schema auto-learned from registry suffix patterns
        # (e.g. if all known S-x05 units in Ellington Beach House are 2BR → infer 2BR for unknown S-x05)
        if not bed_resolved and building and unit_number and dynamic_schema:
            b_dyn = str(building).strip().lower().replace(' ', '').replace('-', '')
            if b_dyn in dynamic_schema:
                digits_dyn = re.sub(r'[^0-9]', '', str(unit_number))
                suffix_dyn = digits_dyn[-2:].zfill(2) if len(digits_dyn) >= 2 else None
                if suffix_dyn:
                    dyn_beds = dynamic_schema[b_dyn].get(suffix_dyn)
                    if dyn_beds is not None:
                        lead_df.at[idx, 'bedrooms'] = dyn_beds
                        lead_df.at[idx, 'bedroom_method'] = f"Dynamic schema (suffix {suffix_dyn})"
                        lead_df.at[idx, 'bedroom_confidence'] = 'Medium'
                        bed_resolved = True
                        stats['beds_from_schema'] += 1

        # PRIORITY 4: Unit pattern from reference data
        if not bed_resolved and building and unit_number and unit_pattern_table:
            pattern_result = infer_from_unit_pattern(building, unit_number, unit_pattern_table)
            if pattern_result:
                lead_df.at[idx, 'bedrooms'] = pattern_result['bedrooms']
                lead_df.at[idx, 'bedroom_method'] = pattern_result['method']
                lead_df.at[idx, 'bedroom_confidence'] = pattern_result['confidence']
                bed_resolved = True
                stats['beds_from_pattern'] += 1
                
                # Also capture size from pattern if we don't have original
                if pd.isna(original_size):
                    lead_df.at[idx, 'size_sqft'] = pattern_result['size_sqft']
                    lead_df.at[idx, 'size_sqm'] = pattern_result['size_sqm']
                    lead_df.at[idx, 'size_method'] = pattern_result['method']
                    lead_df.at[idx, 'size_confidence'] = pattern_result['confidence']
                    size_resolved = True
                    stats['size_estimated'] += 1
        
        # PRIORITY 4.5: Size-based bedroom inference (lead-file size only)
        if not bed_resolved and pd.notna(original_size) and original_size > 100:
            size_result = infer_bedrooms_from_size_definitive(original_size, building)
            if size_result:
                lead_df.at[idx, 'bedrooms'] = size_result['bedrooms']
                lead_df.at[idx, 'bedroom_method'] = size_result['method']
                lead_df.at[idx, 'bedroom_confidence'] = size_result['confidence']
                bed_resolved = True
                stats['beds_from_size'] += 1
        
        # PRIORITY 5: Building default bedrooms (final fallback)
        if not bed_resolved and building:
            default_result = get_building_default_bedrooms(building)
            if default_result:
                lead_df.at[idx, 'bedrooms'] = default_result['bedrooms']
                lead_df.at[idx, 'bedroom_method'] = default_result['method']
                lead_df.at[idx, 'bedroom_confidence'] = default_result['confidence']
                bed_resolved = True
                stats['beds_from_default'] += 1
        
        # Mark unresolved bedrooms
        if not bed_resolved:
            stats['beds_unresolved'] += 1
            lead_df.at[idx, 'data_quality'] = 'Needs Review: Missing Beds'
        
        # =====================================================================
        # SIZE RESOLUTION
        # =====================================================================
        
        bedrooms_final = lead_df.at[idx, 'bedrooms']
        
        # PRIORITY 1: Original size from lead file - with validation!
        if not size_resolved and pd.notna(original_size) and original_size > 50:
            # Validate and potentially fix sqm->sqft conversion
            fixed_size, was_corrected = validate_and_fix_size(original_size, bedrooms_final)
            
            if fixed_size and fixed_size > 200:
                lead_df.at[idx, 'size_sqft'] = fixed_size
                lead_df.at[idx, 'size_sqm'] = round(fixed_size * SQFT_TO_SQM, 0)
                lead_df.at[idx, 'size_method'] = 'Original (Fixed)' if was_corrected else 'Original'
                lead_df.at[idx, 'size_confidence'] = 'Medium' if was_corrected else 'High'
                size_resolved = True
                stats['size_original'] += 1
        
        # PRIORITY 2: Estimate from bedrooms (now that beds are resolved)
        if not size_resolved and pd.notna(bedrooms_final):
            size_est = estimate_size_from_bedrooms(building, bedrooms_final, estimation_table)
            if size_est['size_sqft']:
                lead_df.at[idx, 'size_sqft'] = round(size_est['size_sqft'], 0)
                lead_df.at[idx, 'size_sqm'] = round(size_est['size_sqm'], 0)
                lead_df.at[idx, 'size_method'] = size_est['method']
                lead_df.at[idx, 'size_confidence'] = size_est['confidence']
                size_resolved = True
                stats['size_estimated'] += 1
        
        # Mark unresolved size
        if not size_resolved:
            stats['size_unresolved'] += 1
            if lead_df.at[idx, 'data_quality'] == 'OK':
                lead_df.at[idx, 'data_quality'] = 'Needs Review: Missing Size'
            else:
                lead_df.at[idx, 'data_quality'] = 'Needs Review: Missing Beds+Size'
        
        # =====================================================================
        # VALIDATION: Cross-check beds vs size
        # =====================================================================
        if bed_resolved and size_resolved:
            beds = lead_df.at[idx, 'bedrooms']
            sqft = lead_df.at[idx, 'size_sqft']
            if not validate_bedroom_size_match(beds, sqft):
                size_method = lead_df.at[idx, 'size_method']
                bed_method = lead_df.at[idx, 'bedroom_method']
                if (bed_method in ('Reference (Exact)', 'Schema', 'Pattern') and
                        size_method == 'Original' and estimation_table):
                    size_est = estimate_size_from_bedrooms(building, beds, estimation_table)
                    if size_est and size_est.get('size_sqft'):
                        lead_df.at[idx, 'size_sqft'] = round(size_est['size_sqft'], 0)
                        lead_df.at[idx, 'size_sqm'] = round(size_est['size_sqm'], 0)
                        lead_df.at[idx, 'size_method'] = 'Estimated (Auto-corrected)'
                        lead_df.at[idx, 'size_confidence'] = size_est.get('confidence', 'Medium')
                        lead_df.at[idx, 'data_quality'] = 'OK'
                        # do not set mismatch flag
                    else:
                        lead_df.at[idx, 'data_quality'] = 'Flagged: Size/Beds Mismatch'
                        stats['validation_flags'] += 1
                else:
                    lead_df.at[idx, 'data_quality'] = 'Flagged: Size/Beds Mismatch'
                    stats['validation_flags'] += 1
    
    return lead_df, stats


def validate_bedroom_size_match(bedrooms, size_sqft) -> bool:
    """Validate that bedroom count matches size range."""
    if pd.isna(bedrooms) or pd.isna(size_sqft):
        return True  # Can't validate
    
    try:
        beds = int(bedrooms)
        sqft = float(size_sqft)
    except:
        return True
    
    # Tolerance ranges (broader than typical for validation)
    ranges = {
        0: (200, 900),
        1: (400, 1500),
        2: (750, 2500),
        3: (1200, 4000),
        4: (1800, 6000),
        5: (2500, 15000),
    }
    
    beds_key = min(beds, 5)
    min_size, max_size = ranges.get(beds_key, (400, 15000))
    
    return min_size * 0.7 <= sqft <= max_size * 1.3


def validate_and_fix_size(size_sqft: float, bedrooms=None) -> Tuple[float, bool]:
    """
    Validate size value and attempt to fix if it looks like sqm.
    
    Returns: (corrected_size_sqft, was_corrected)
    
    If the size is suspiciously small for the bedroom count,
    it was likely sqm masquerading as sqft - multiply by 10.764.
    """
    if size_sqft is None or pd.isna(size_sqft):
        return None, False
    
    # Minimum and maximum expected sqft by bedroom count
    min_expected = {
        None: 300,  # Unknown beds: at least 300 sqft for any unit
        0: 250,     # Studio: at least 250 sqft
        1: 450,     # 1BR: at least 450 sqft
        2: 800,     # 2BR: at least 800 sqft
        3: 1200,    # 3BR: at least 1200 sqft
        4: 1800,    # 4BR: at least 1800 sqft
        5: 2500,    # 5BR: at least 2500 sqft
    }
    max_expected = {
        None: 15000,
        0: 900,
        1: 1500,
        2: 2500,
        3: 4000,
        4: 6000,
        5: 15000,
    }
    
    beds_key = None
    if bedrooms is not None and not pd.isna(bedrooms):
        try:
            beds_key = min(int(bedrooms), 5)
        except:
            pass
    
    min_sqft = min_expected.get(beds_key, 300)
    max_sqft = max_expected.get(beds_key, 15000)
    
    # If size is suspiciously small, it's probably sqm
    if size_sqft < min_sqft:
        corrected = size_sqft * SQM_TO_SQFT
        # Verify the corrected value is now reasonable
        if corrected >= min_sqft * 0.7:
            return round(corrected, 0), True
    
    # If size is suspiciously large, it may have been sqft inflated by 10.764x
    if size_sqft > max_sqft:
        deflated = size_sqft / SQM_TO_SQFT
        if min_sqft * 0.7 <= deflated <= max_sqft * 1.3:
            return round(deflated, 0), True
    
    return round(size_sqft, 0), False


# =============================================================================
# VALIDATION AND COMPLETENESS
# =============================================================================

def is_valid_row(row) -> bool:
    has_loc = pd.notna(row['building_name']) or pd.notna(row['unit_number'])
    phone_val = row['phone'] if pd.notna(row['phone']) else ''
    has_contact = bool(str(phone_val).strip()) or pd.notna(row['owner_name'])
    return has_loc and has_contact


def calc_completeness(row) -> float:
    fields = ['date', 'owner_name', 'building_name', 'bedrooms', 'unit_number', 'phone', 'size_sqft']
    filled = sum(1 for f in fields if f in row.index and pd.notna(row[f]) and str(row[f]).strip())
    return round(filled / len(fields) * 100, 1)


def dedup_key(row) -> str:
    def safe(val):
        return '' if pd.isna(val) else str(val).lower().strip()
    return '|'.join([safe(row.get('building_name')), safe(row.get('unit_number')), safe(row.get('owner_name'))])


# =============================================================================
# FUTURE: WEB SCRAPING SCAFFOLD
# =============================================================================

# =============================================================================
# MAIN PROCESSING PIPELINE
# =============================================================================

def format_phone_display(phone):
    """
    Format phone number with correct country code detection.
    Input: raw digits from phone_primary column.
    Output: formatted international number.
    """
    if not phone or pd.isna(phone):
        return ''
    phone = str(phone).replace('.0', '').strip()  # Fix float-to-string issue
    if not phone or phone == 'nan':
        return ''
    
    # Already has correct format
    if phone.startswith('+'):
        return phone
    
    # UAE numbers: 9 digits starting with 5
    if len(phone) == 9 and phone[0] == '5':
        return f"+971 {phone[:2]} {phone[2:5]} {phone[5:]}"
    
    # International numbers (already include country code in digits)
    # UK: starts with 44
    if phone.startswith('44') and len(phone) >= 11:
        return f"+44 {phone[2:6]} {phone[6:]}"
    # Russia/CIS: starts with 7, 10+ digits
    if phone.startswith('7') and len(phone) >= 10:
        return f"+7 {phone[1:4]} {phone[4:7]} {phone[7:]}"
    # Saudi: starts with 966
    if phone.startswith('966'):
        return f"+966 {phone[3:5]} {phone[5:8]} {phone[8:]}"
    # France: starts with 33
    if phone.startswith('33'):
        return f"+33 {phone[2:3]} {phone[3:5]} {phone[5:7]} {phone[7:]}"
    # India: starts with 91
    if phone.startswith('91') and len(phone) >= 12:
        return f"+91 {phone[2:7]} {phone[7:]}"
    # Pakistan: starts with 92
    if phone.startswith('92'):
        return f"+92 {phone[2:5]} {phone[5:]}"
    # US/Canada: starts with 1, 11 digits
    if phone.startswith('1') and len(phone) == 11:
        return f"+1 {phone[1:4]} {phone[4:7]} {phone[7:]}"
    # Australia: starts with 61
    if phone.startswith('61'):
        return f"+61 {phone[2:3]} {phone[3:7]} {phone[7:]}"
    # China: starts with 86
    if phone.startswith('86') and len(phone) >= 13:
        return f"+86 {phone[2:5]} {phone[5:9]} {phone[9:]}"
    # Iran: starts with 98
    if phone.startswith('98'):
        return f"+98 {phone[2:5]} {phone[5:]}"
    # Lebanon: starts with 961
    if phone.startswith('961'):
        return f"+961 {phone[3:4]} {phone[4:7]} {phone[7:]}"
    
    # Default: if 9 digits starting with 5, treat as UAE
    if len(phone) == 9 and phone[0] == '5':
        return f"+971 {phone[:2]} {phone[2:5]} {phone[5:]}"
    
    # Fallback: just add + prefix for long numbers
    if len(phone) > 9:
        return f"+{phone}"
    
    # Short numbers — likely UAE without detection
    return f"+971 {phone}"


def _is_master_csv_v3(df: pd.DataFrame) -> bool:
    """Detect if a DataFrame came from the pre-cleaned leads_master_v3.csv."""
    v3_columns = {'owner_name', 'building_name', 'unit_number', 'phone_primary', 'phone_display'}
    return v3_columns.issubset(set(df.columns))


def _load_master_csv_v3(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    """
    Fast-path loader for the pre-cleaned leads_master_v3.csv.
    
    Skips: normalization, dedup, building name cleaning, phone cleaning.
    Keeps: column mapping, bedroom parsing (Studio->0), date parsing.
    The enrichment engine still runs on nulls afterward.
    """
    result = pd.DataFrame(index=df.index)
    
    # Date -- already YYYY-MM-DD format
    result['date'] = pd.to_datetime(df['date'], errors='coerce')
    
    # Owner name -- already clean
    result['owner_name'] = df['owner_name']
    
    # Building name -- already normalized, DO NOT re-run standardize_building_name
    result['building_name'] = df['building_name']
    
    # Unit number -- already clean
    result['unit_number'] = df['unit_number'].astype(str).replace('nan', None)
    
    # Bedrooms -- need to parse "Studio"->0, "1"->1, etc. for numeric operations
    result['bedrooms'] = df['bedrooms'].apply(clean_bedroom)
    
    # Phone -- read phone_primary as string, apply country code detection
    # The rest of the app expects a 'phone' column with formatted display
    if 'phone_primary' in df.columns:
        # Read as string, strip .0 suffix if present
        phone_raw = df['phone_primary'].astype(str).str.replace('.0', '', regex=False)
        result['phone'] = phone_raw.apply(format_phone_display)
        result['phone_raw'] = phone_raw  # Keep raw for later processing if needed
    elif 'phone_display' in df.columns:
        result['phone'] = df['phone_display'].fillna('')
    else:
        result['phone'] = ''
    
    # Store all phones for the AI tools that split on pipe
    if 'phone_all' in df.columns:
        # Process each pipe-separated phone
        def format_all_phones(phones_str):
            if pd.isna(phones_str) or not str(phones_str).strip():
                return ''
            phones = str(phones_str).split('|')
            formatted = [format_phone_display(p.strip()) for p in phones if p.strip()]
            return ' | '.join(formatted)
        result['phone_all'] = df['phone_all'].apply(format_all_phones)
    
    # Size -- already in sqft, no conversion needed
    result['original_size_sqft'] = pd.to_numeric(df['size_sqft'], errors='coerce')
    
    # Extra columns from v3 that are useful downstream
    if 'nationality' in df.columns:
        result['nationality'] = df['nationality']
    if 'email' in df.columns:
        result['email'] = df['email']
    if 'last_transaction_amount' in df.columns:
        result['last_transaction_amount'] = pd.to_numeric(df['last_transaction_amount'], errors='coerce')
    if 'sources' in df.columns:
        result['_source'] = df['sources']
    else:
        result['_source'] = filename
    
    print(f"   [V3] Loaded {len(result):,} leads from pre-cleaned master list")
    print(f"   [V3] Bedrooms populated: {result['bedrooms'].notna().sum():,}/{len(result):,}")
    print(f"   [V3] Sizes populated: {result['original_size_sqft'].notna().sum():,}/{len(result):,}")
    print(f"   [V3] Phones populated: {(result['phone'] != '').sum():,}/{len(result):,}")
    
    return result


def validate_dataframe(df: pd.DataFrame, source_name: str = "Data") -> bool:
    """
    Validate that dataframe has required columns and data.
    Raises ValueError if validation fails.
    """
    try:
        from logger_config import data_logger
    except ImportError:
        data_logger = None
    
    REQUIRED_COLUMNS = ['owner_name', 'building_name']
    RECOMMENDED_COLUMNS = ['unit_number', 'phone', 'bedrooms', 'size_sqft']
    
    if df is None or len(df) == 0:
        error_msg = f"{source_name}: Dataframe is empty"
        if data_logger:
            data_logger.error(error_msg)
        raise ValueError(error_msg)
    
    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        error_msg = f"{source_name}: Missing required columns: {missing_required}"
        if data_logger:
            data_logger.error(error_msg)
        raise ValueError(error_msg)
    
    missing_recommended = [c for c in RECOMMENDED_COLUMNS if c not in df.columns]
    if missing_recommended:
        warning_msg = f"{source_name}: Missing recommended columns: {missing_recommended}"
        if data_logger:
            data_logger.warning(warning_msg)
        print(f"⚠️  {warning_msg}")
    
    null_counts = df[REQUIRED_COLUMNS].isnull().sum()
    for col, null_count in null_counts.items():
        if null_count > 0:
            pct = (null_count / len(df)) * 100
            if pct > 50 and data_logger:
                data_logger.warning(f"{source_name}: {col} is {pct:.1f}% null")
    
    if data_logger:
        data_logger.info(f"{source_name} validation passed: {len(df):,} records, {len(df.columns)} columns")
    return True


def process_and_clean_data(data_path: str = './data') -> Tuple[pd.DataFrame, Dict]:
    """
    Main data processing pipeline with comprehensive enrichment.
    
    Detects if the data folder contains the pre-cleaned leads_master_v3.csv
    (fast path: skip normalization/dedup) or legacy fragmented CSVs
    (full pipeline: normalize, merge, dedup).
    
    In both cases, bedroom/size enrichment still runs on null values,
    and reference data is still loaded for cross-referencing.
    """
    diag = {
        'files_loaded': [], 'file_row_counts': {}, 'raw_rows': 0,
        'rows_after_cleaning': 0, 'duplicates_removed': 0,
        'invalid_rows_removed': 0, 'errors': [],
        'ref_stats': {'loaded': False},
        'enrichment_stats': {
            'beds_original': 0, 'beds_from_schema': 0, 'beds_from_pattern': 0,
            'beds_from_size': 0, 'beds_from_default': 0, 'beds_unresolved': 0,
            'size_original': 0, 'size_estimated': 0, 'size_unresolved': 0,
            'validation_flags': 0
        },
        'unit_patterns_learned': 0,
        'schema_buildings': len(BUILDING_UNIT_SCHEMA),
        'default_buildings': len(BUILDING_DEFAULT_BEDROOMS)
    }
    
    # 1. Load reference data (always needed for enrichment + cross-referencing)
    ref_df, ref_stats = load_reference_data()
    diag['ref_stats'] = ref_stats
    
    # 2. Build estimation tables (for bedroom/size enrichment of nulls)
    estimation_table = {}
    prediction_table = {}
    unit_pattern_table = {}
    
    exact_unit_lookup = {}
    if ref_df is not None:
        estimation_table = build_size_estimation_table(ref_df)
        prediction_table = build_bedroom_prediction_table(ref_df)
        unit_pattern_table = build_unit_pattern_table(ref_df)
        exact_unit_lookup = build_exact_unit_lookup(ref_df)
        diag['unit_patterns_learned'] = len([k for k in unit_pattern_table.keys() if '_family' not in k[0]])
    
    # 3. Load lead files
    files, errors = load_data_files(data_path)
    diag['errors'] = errors
    
    if not files:
        empty_df = pd.DataFrame(columns=['date', 'owner_name', 'building_name', 'bedrooms', 
                                         'unit_number', 'phone', 'size_sqft', 'size_sqm',
                                         'size_method', 'size_confidence', 'bedroom_method',
                                         'bedroom_confidence', 'completeness', 'data_quality'])
        return empty_df, diag
    
    # =========================================================================
    # DETECT: Is this the pre-cleaned master v3 CSV?
    # =========================================================================
    is_v3 = False
    if len(files) == 1:
        fname, raw_df = files[0]
        if _is_master_csv_v3(raw_df):
            is_v3 = True
            print(f"\n[INFO] Detected pre-cleaned master CSV v3: {fname}")
            combined = _load_master_csv_v3(raw_df, fname)
            diag['files_loaded'].append(fname)
            diag['file_row_counts'][fname] = len(raw_df)
            diag['raw_rows'] = len(raw_df)
            # No dedup or invalid-row removal needed -- data is pre-cleaned
            diag['duplicates_removed'] = 0
            diag['invalid_rows_removed'] = 0
    
    if not is_v3:
        # Legacy path: multiple CSVs that need normalization + merge + dedup
        all_dfs = []
        for fname, df in files:
            diag['files_loaded'].append(fname)
            diag['file_row_counts'][fname] = len(df)
            diag['raw_rows'] += len(df)
            all_dfs.append(normalize_dataframe(df, fname))
        
        combined = pd.concat(all_dfs, ignore_index=True)
        
        # 4. Remove invalid rows
        valid_mask = combined.apply(is_valid_row, axis=1)
        diag['invalid_rows_removed'] = int((~valid_mask).sum())
        combined = combined[valid_mask]
        
        # 5. Remove duplicates
        combined['_key'] = combined.apply(dedup_key, axis=1)
        before = len(combined)
        combined = combined.drop_duplicates(subset=['_key'], keep='first')
        diag['duplicates_removed'] = before - len(combined)
        combined = combined.drop(columns=['_key'])
    
    # 5b. Add optional columns and merge PropertyFinder scraped leads
    for col in ['listing_price', 'listing_type', 'listing_url', 'furnished', 'pf_listing_count', 'source']:
        if col not in combined.columns:
            combined[col] = 0 if col == 'pf_listing_count' else ('' if col == 'source' else pd.NA)
    if 'source' in combined.columns and '_source' in combined.columns:
        combined['source'] = combined['source'].fillna(combined['_source'].fillna('')).astype(str)
        combined.loc[combined['source'] == '', 'source'] = 'crm'
    elif 'source' in combined.columns:
        combined['source'] = combined['source'].fillna('crm')
    pf_csv_path = Path(data_path).resolve().parent / 'scraped_data' / 'propertyfinder_scraped_leads.csv'
    if pf_csv_path.exists():
        try:
            try:
                pf_df = pd.read_csv(pf_csv_path, encoding='utf-8', low_memory=False, on_bad_lines='skip')
            except TypeError:
                pf_df = pd.read_csv(pf_csv_path, encoding='utf-8', low_memory=False, engine='python')
            if not pf_df.empty and 'owner_name' in pf_df.columns:
                # Count PF listings per (building, unit) — repeated listings = higher priority (e.g. N-605)
                _b = (pf_df['building_name'].fillna('').astype(str).str.strip().str.lower())
                _u = (pf_df['unit_number'].fillna('').astype(str).str.strip().str.lower())
                _counts = pf_df.groupby([_b, _u]).size()
                def _pf_listing_count(building: str, unit: str) -> int:
                    b, u = (str(building or '').strip().lower(), str(unit or '').strip().lower())
                    return int(_counts.get((b, u), 0))

                def _pf_key(r):
                    return (
                        str(r.get('owner_name') or '').strip().lower(),
                        str(r.get('building_name') or '').strip().lower(),
                        str(r.get('unit_number') or '').strip().lower()
                    )
                def _phone_from_lead_list(owner: str, building: str, unit: str) -> str:
                    """Look up phone from lead list by owner + building + unit. Returns non-empty string or ''."""
                    if not owner and not building and not unit:
                        return ''
                    o = str(owner or '').strip().lower()
                    b = str(building or '').strip().lower()
                    u = str(unit or '').strip().lower()
                    if not {'owner_name', 'building_name', 'unit_number', 'phone'}.issubset(combined.columns):
                        return ''
                    for _, r in combined.iterrows():
                        ro = str(r.get('owner_name') or '').strip().lower()
                        rb = str(r.get('building_name') or '').strip().lower()
                        ru = str(r.get('unit_number') or '').strip().lower()
                        rp = str(r.get('phone') or '').strip()
                        if rp and rp.lower() != 'nan' and (o == ro and b == rb and u == ru):
                            return rp
                    return ''
                def _parse_room_type(rt):
                    if pd.isna(rt) or not str(rt).strip():
                        return pd.NA
                    s = str(rt).strip().lower()
                    if 'studio' in s:
                        return 0
                    m = re.search(r'(\d+)\s*(?:b/?r|bed)', s, re.I)
                    return int(m.group(1)) if m else pd.NA
                combined['_merge_key'] = combined.apply(
                    lambda r: (str(r.get('owner_name') or '').strip().lower(),
                               str(r.get('building_name') or '').strip().lower(),
                               str(r.get('unit_number') or '').strip().lower()), axis=1
                )
                appended = []
                for _, pr in pf_df.iterrows():
                    try:
                        key = _pf_key(pr)
                        match_idx = combined[combined['_merge_key'] == key]
                        if not match_idx.empty:
                            idx = match_idx.index[0]
                            combined.at[idx, 'listing_price'] = pr.get('listing_price') or ''
                            combined.at[idx, 'listing_type'] = pr.get('listing_type') or ''
                            combined.at[idx, 'listing_url'] = pr.get('listing_url') or ''
                            if 'furnished' in combined.columns:
                                combined.at[idx, 'furnished'] = pr.get('furnished') or ''
                            combined.at[idx, 'pf_listing_count'] = _pf_listing_count(pr.get('building_name'), pr.get('unit_number'))
                            cur = str(combined.at[idx, 'source'] or '')
                            if 'propertyfinder' not in cur.lower():
                                combined.at[idx, 'source'] = (cur + ',propertyfinder').lstrip(',')
                            _matched += 1
                        else:
                            scraped_phone = str(pr.get('phone') or '').strip()
                            if scraped_phone.lower() in ('nan', 'n/a', 'none', '') or not scraped_phone:
                                scraped_phone = _phone_from_lead_list(
                                    pr.get('owner_name'), pr.get('building_name'), pr.get('unit_number')
                                )
                            if not scraped_phone or str(scraped_phone).lower() in ('nan', 'n/a', 'none'):
                                scraped_phone = ''
                            dt = pd.to_datetime(pr.get('scraped_at'), errors='coerce')
                            size_sqm = pd.to_numeric(pr.get('size_sqm'), errors='coerce')
                            size_sqft = size_sqm * 10.7639 if pd.notna(size_sqm) else pd.NA
                            new_row = {
                                'date': dt, 'owner_name': (pr.get('owner_name') or '').strip() or None,
                                'building_name': (pr.get('building_name') or '').strip() or None,
                                'unit_number': str(pr.get('unit_number') or '').strip() or None,
                                'bedrooms': _parse_room_type(pr.get('room_type')),
                                'phone': scraped_phone,
                                'original_size_sqft': size_sqft,
                                'listing_price': pr.get('listing_price') or '',
                                'listing_type': pr.get('listing_type') or '',
                                'listing_url': pr.get('listing_url') or '',
                                'furnished': pr.get('furnished') or '',
                                'pf_listing_count': _pf_listing_count(pr.get('building_name'), pr.get('unit_number')),
                                'source': 'propertyfinder',
                            }
                            for c in combined.columns:
                                if c not in new_row and c != '_merge_key':
                                    new_row[c] = pd.NA if c not in ['phone', 'listing_price', 'listing_type', 'listing_url', 'furnished', 'pf_listing_count', 'source'] else (0 if c == 'pf_listing_count' else '')
                            new_row['_merge_key'] = key
                            appended.append(new_row)
                    except Exception:
                        pass
                combined = combined.drop(columns=['_merge_key'])
                if appended:
                    extra = pd.DataFrame(appended)
                    for c in combined.columns:
                        if c not in extra.columns:
                            extra[c] = pd.NA
                    extra = extra[[c for c in combined.columns if c in extra.columns]]
                    extra = extra.drop(columns=['_merge_key'], errors='ignore')
                    combined = pd.concat([combined, extra], ignore_index=True)
                    diag['files_loaded'].append('propertyfinder_scraped_leads.csv')
                    diag['file_row_counts']['propertyfinder_scraped_leads.csv'] = len(appended)
            else:
                if '_merge_key' in combined.columns:
                    combined = combined.drop(columns=['_merge_key'])
        except Exception as e:
            if '_merge_key' in combined.columns:
                combined = combined.drop(columns=['_merge_key'])
            diag['errors'].append(f"PropertyFinder merge: {e}")
    
    # 6. Apply comprehensive enrichment (fills null bedrooms and sizes)
    combined, enrichment_stats = apply_comprehensive_enrichment(
        combined, estimation_table, prediction_table, unit_pattern_table,
        exact_unit_lookup=exact_unit_lookup
    )
    diag['enrichment_stats'] = enrichment_stats
    
    # 7. Calculate completeness
    combined['completeness'] = combined.apply(calc_completeness, axis=1)

    # 8. Sort (prioritize PF repeated listings first, then completeness, then date)
    sort_cols = ['pf_listing_count', 'completeness', 'date'] if 'pf_listing_count' in combined.columns else ['completeness', 'date']
    combined = combined.sort_values(sort_cols, ascending=[False, False, False] if 'pf_listing_count' in combined.columns else [False, False], na_position='last')
    combined = combined.reset_index(drop=True)
    
    # Drop helper columns
    if 'original_size_sqft' in combined.columns:
        combined = combined.drop(columns=['original_size_sqft'])
    
    diag['rows_after_cleaning'] = len(combined)
    
    # Debug output
    print(f"\n=== Enrichment Results ===")
    print(f"  Bedrooms:")
    print(f"    From Reference (Exact): {enrichment_stats.get('beds_from_exact', 0):,}")
    print(f"    Original: {enrichment_stats['beds_original']:,}")
    print(f"    From Schema: {enrichment_stats['beds_from_schema']:,}")
    print(f"    From Pattern: {enrichment_stats['beds_from_pattern']:,}")
    print(f"    From Size: {enrichment_stats['beds_from_size']:,}")
    print(f"    From Default: {enrichment_stats['beds_from_default']:,}")
    print(f"    Unresolved: {enrichment_stats['beds_unresolved']:,}")
    print(f"  Size:")
    print(f"    From Reference (Exact): {enrichment_stats.get('size_from_exact', 0):,}")
    print(f"    Original: {enrichment_stats['size_original']:,}")
    print(f"    Estimated: {enrichment_stats['size_estimated']:,}")
    print(f"    Unresolved: {enrichment_stats['size_unresolved']:,}")
    print(f"  Validation Flags: {enrichment_stats['validation_flags']:,}")
    
    # Coverage
    with_size = combined['size_sqft'].notna().sum()
    with_beds = combined['bedrooms'].notna().sum()
    total = len(combined)
    print(f"\n=== Coverage ===")
    print(f"   With size: {with_size:,} / {total:,} ({with_size/total*100:.1f}%)")
    print(f"   With bedrooms: {with_beds:,} / {total:,} ({with_beds/total*100:.1f}%)")
    
    try:
        validate_dataframe(combined, "Lead Database")
    except ValueError as e:
        print(f"\n❌ Data Validation Failed: {e}")
        empty_df = pd.DataFrame(columns=['date', 'owner_name', 'building_name', 'bedrooms',
                                         'unit_number', 'phone', 'size_sqft', 'size_sqm',
                                         'size_method', 'size_confidence', 'bedroom_method',
                                         'bedroom_confidence', 'completeness', 'data_quality'])
        diag['errors'].append(str(e))
        return empty_df, diag
    
    return combined, diag


# =============================================================================
# FILTERING AND SEARCH
# =============================================================================

def apply_filters(df: pd.DataFrame, date_start=None, date_end=None, owner_name=None,
                  building_search=None, bedrooms=None, unit_number=None, phone=None,
                  phone_required=False, min_completeness=0,
                  min_size_sqft=None, max_size_sqft=None, hide_flagged=False,
                  source_filter=None) -> pd.DataFrame:
    """Apply all filters. source_filter: None/'all', 'crm', 'propertyfinder'."""
    if df.empty:
        return df
    f = df.copy()
    
    if date_start:
        f = f[f['date'].isna() | (f['date'] >= date_start)]
    if date_end:
        f = f[f['date'].isna() | (f['date'] <= date_end)]
    
    if owner_name and owner_name.strip():
        f = f[f['owner_name'].fillna('').str.lower().str.contains(owner_name.lower(), regex=False)]
    
    if building_search and building_search.strip():
        search_buildings = parse_building_search(building_search)
        if search_buildings:
            # Word-boundary regex so "Shoreline 1" does not match "Shoreline 14"
            pattern = r'\b(' + '|'.join(re.escape(b.lower()) for b in search_buildings) + r')\b'
            mask = f['building_name'].fillna('').str.lower().str.contains(
                pattern, regex=True, na=False
            )
            f = f[mask]
    
    if bedrooms and bedrooms != 'All':
        if bedrooms == 'Studio':
            f = f[f['bedrooms'] == 0]
        else:
            try:
                f = f[f['bedrooms'] == int(bedrooms)]
            except:
                pass
    
    if unit_number and unit_number.strip():
        f = f[f['unit_number'].fillna('').str.lower().str.contains(unit_number.lower(), regex=False)]
    
    if phone and phone.strip():
        digits = re.sub(r'[^0-9]', '', phone)
        if digits:
            f = f[f['phone'].fillna('').apply(lambda x: digits in re.sub(r'[^0-9]', '', x))]
    
    if phone_required:
        f = f[f['phone'].fillna('').str.strip() != '']
    
    if min_completeness > 0:
        f = f[f['completeness'] >= min_completeness]
    
    if min_size_sqft is not None and min_size_sqft > 0:
        f = f[f['size_sqft'].isna() | (f['size_sqft'] >= min_size_sqft)]
    
    if max_size_sqft is not None and max_size_sqft > 0:
        f = f[f['size_sqft'].isna() | (f['size_sqft'] <= max_size_sqft)]
    
    if hide_flagged:
        f = f[f['data_quality'] == 'OK']
    
    if source_filter and source_filter.lower() not in ('all', ''):
        if 'source' not in f.columns:
            pass
        elif source_filter.lower() == 'crm':
            f = f[f['source'].fillna('').astype(str).str.lower().str.contains('propertyfinder', regex=False) == False]
        elif source_filter.lower() == 'propertyfinder':
            f = f[f['source'].fillna('').astype(str).str.lower().str.contains('propertyfinder', regex=False)]
    
    return f


def get_recent_transaction_lead_mask(
    leads_df: pd.DataFrame,
    ref_df: Optional[pd.DataFrame],
    since_days: int = 90,
    title_deed_only: bool = True,
    resale_only: bool = True
) -> pd.Series:
    """
    Return a boolean Series (index aligned to leads_df): True for leads whose
    building+unit appears in reference data as a sale in the last since_days.
    Uses standardized building name (exact match) and normalized unit numbers
    to avoid false positives (e.g. Shoreline family collision).
    ref_df should be the DataFrame returned by load_reference_data() (has building_std, unit_no, sale_date).
    When reference has trans_group_en/sales_recurrence, title_deed_only and resale_only filter to
    Title Deed + Resale only (actual owner-to-owner sales).
    """
    if leads_df.empty:
        return pd.Series(dtype=bool)
    if ref_df is None or ref_df.empty or 'sale_date' not in ref_df.columns:
        return pd.Series(False, index=leads_df.index)
    cutoff = datetime.now() - pd.Timedelta(days=since_days)
    if 'building_std' not in ref_df.columns or 'unit_no' not in ref_df.columns:
        return pd.Series(False, index=leads_df.index)
    ref_recent = ref_df[
        ref_df['sale_date'].notna() & (pd.to_datetime(ref_df['sale_date'], errors='coerce') >= cutoff)
    ].copy()
    if ref_recent.empty:
        return pd.Series(False, index=leads_df.index)
    if title_deed_only and 'trans_group_en' in ref_recent.columns:
        ref_recent = ref_recent[ref_recent['trans_group_en'].fillna('').str.strip().str.lower() == 'title deed']
    if resale_only and 'sales_recurrence' in ref_recent.columns:
        ref_recent = ref_recent[ref_recent['sales_recurrence'].fillna('').str.strip().str.lower() == 'resale']
    if ref_recent.empty:
        return pd.Series(False, index=leads_df.index)
    # Normalized keys: exact building match (no family substring), normalized unit
    def _norm_unit(x):
        if BUILDING_INTELLIGENCE_AVAILABLE and normalize_unit_number is not None:
            return normalize_unit_number(x) if x is not None and (pd.notna(x) and str(x).strip()) else 'N/A'
        return str(x).strip().upper() if x is not None and pd.notna(x) else 'N/A'
    ref_recent['_b'] = ref_recent['building_std'].fillna('').astype(str).str.strip().str.lower()
    ref_recent['_u'] = ref_recent['unit_no'].apply(_norm_unit)
    ref_recent = ref_recent[ref_recent['_u'].fillna('') != 'N/A']
    ref_keys = ref_recent[['_b', '_u']].drop_duplicates()

    # Vectorized: build lead keys and merge
    lead_b = leads_df['building_name'].apply(lambda x: (standardize_building_name(x) or '').lower())
    lead_u = leads_df['unit_number'].apply(_norm_unit)
    lead_keys = pd.DataFrame({'_idx': leads_df.index, '_b': lead_b, '_u': lead_u})
    lead_keys = lead_keys[(lead_keys['_b'] != '') & (lead_keys['_u'] != 'N/A')]
    merged = lead_keys.merge(ref_keys, on=['_b', '_u'], how='inner')
    matched_idx = merged['_idx'].unique()
    mask = pd.Series(False, index=leads_df.index)
    mask.loc[leads_df.index.isin(matched_idx)] = True
    return mask


def get_recent_transaction_dates(
    leads_df: pd.DataFrame,
    ref_df: Optional[pd.DataFrame],
    since_days: int = 90,
    title_deed_only: bool = True,
    resale_only: bool = True
) -> pd.Series:
    """
    Return a Series (index aligned to leads_df) of sale_date for the latest matching
    reference transaction per lead, or pd.NaT when no match.
    Uses same standardized building + normalized unit logic as get_recent_transaction_lead_mask.
    """
    if leads_df.empty:
        return pd.Series(dtype='datetime64[ns]')
    if ref_df is None or ref_df.empty or 'sale_date' not in ref_df.columns:
        return pd.Series(pd.NaT, index=leads_df.index)
    if 'building_std' not in ref_df.columns or 'unit_no' not in ref_df.columns:
        return pd.Series(pd.NaT, index=leads_df.index)
    cutoff = datetime.now() - pd.Timedelta(days=since_days)
    ref_recent = ref_df[
        ref_df['sale_date'].notna() & (pd.to_datetime(ref_df['sale_date'], errors='coerce') >= cutoff)
    ].copy()
    if ref_recent.empty:
        return pd.Series(pd.NaT, index=leads_df.index)
    if title_deed_only and 'trans_group_en' in ref_recent.columns:
        ref_recent = ref_recent[ref_recent['trans_group_en'].fillna('').str.strip().str.lower() == 'title deed']
    if resale_only and 'sales_recurrence' in ref_recent.columns:
        ref_recent = ref_recent[ref_recent['sales_recurrence'].fillna('').str.strip().str.lower() == 'resale']
    if ref_recent.empty:
        return pd.Series(pd.NaT, index=leads_df.index)
    def _norm_unit(x):
        if BUILDING_INTELLIGENCE_AVAILABLE and normalize_unit_number is not None:
            return normalize_unit_number(x) if x is not None and (pd.notna(x) and str(x).strip()) else 'N/A'
        return str(x).strip().upper() if x is not None and pd.notna(x) else 'N/A'
    ref_recent['_b'] = ref_recent['building_std'].fillna('').astype(str).str.strip().str.lower()
    ref_recent['_u'] = ref_recent['unit_no'].apply(_norm_unit)
    ref_recent['_dt'] = pd.to_datetime(ref_recent['sale_date'], errors='coerce')
    ref_recent = ref_recent[ref_recent['_u'] != 'N/A']
    ref_max = ref_recent.groupby(['_b', '_u'])['_dt'].max().reset_index()

    lead_b = leads_df['building_name'].apply(lambda x: (standardize_building_name(x) or '').lower())
    lead_u = leads_df['unit_number'].apply(_norm_unit)
    lead_keys = pd.DataFrame({'_idx': leads_df.index, '_b': lead_b, '_u': lead_u})
    lead_keys = lead_keys[(lead_keys['_b'] != '') & (lead_keys['_u'] != 'N/A')]
    merged = lead_keys.merge(ref_max, on=['_b', '_u'], how='left')
    # One row per lead that matched; take max date per _idx in case of multiple ref rows
    date_series = merged.groupby('_idx')['_dt'].max()
    result = pd.Series(pd.NaT, index=leads_df.index)
    result.loc[date_series.index] = date_series.values
    return result


def get_recent_transaction_details(
    leads_df: pd.DataFrame,
    ref_df: Optional[pd.DataFrame],
    since_days: int = 90,
    title_deed_only: bool = True,
    resale_only: bool = True
) -> pd.DataFrame:
    """
    Return a DataFrame (index aligned to leads_df) with columns display_date, trans_type, sale_type, sale_price_aed
    for the latest matching reference transaction per lead. Used to show transaction details in UI.
    """
    if leads_df.empty:
        return pd.DataFrame(index=leads_df.index, columns=['display_date', 'trans_type', 'sale_type', 'sale_price_aed'])
    if ref_df is None or ref_df.empty or 'sale_date' not in ref_df.columns:
        return pd.DataFrame(index=leads_df.index, columns=['display_date', 'trans_type', 'sale_type', 'sale_price_aed'])
    if 'building_std' not in ref_df.columns or 'unit_no' not in ref_df.columns:
        return pd.DataFrame(index=leads_df.index, columns=['display_date', 'trans_type', 'sale_type', 'sale_price_aed'])
    cutoff = datetime.now() - pd.Timedelta(days=since_days)
    ref_recent = ref_df[
        ref_df['sale_date'].notna() & (pd.to_datetime(ref_df['sale_date'], errors='coerce') >= cutoff)
    ].copy()
    if ref_recent.empty:
        return pd.DataFrame(index=leads_df.index, columns=['display_date', 'trans_type', 'sale_type', 'sale_price_aed'])
    if title_deed_only and 'trans_group_en' in ref_recent.columns:
        ref_recent = ref_recent[ref_recent['trans_group_en'].fillna('').str.strip().str.lower() == 'title deed']
    if resale_only and 'sales_recurrence' in ref_recent.columns:
        ref_recent = ref_recent[ref_recent['sales_recurrence'].fillna('').str.strip().str.lower() == 'resale']
    if ref_recent.empty:
        return pd.DataFrame(index=leads_df.index, columns=['display_date', 'trans_type', 'sale_type', 'sale_price_aed'])
    def _norm_unit(x):
        if BUILDING_INTELLIGENCE_AVAILABLE and normalize_unit_number is not None:
            return normalize_unit_number(x) if x is not None and (pd.notna(x) and str(x).strip()) else 'N/A'
        return str(x).strip().upper() if x is not None and pd.notna(x) else 'N/A'
    ref_recent['_b'] = ref_recent['building_std'].fillna('').astype(str).str.strip().str.lower()
    ref_recent['_u'] = ref_recent['unit_no'].apply(_norm_unit)
    ref_recent['_dt'] = pd.to_datetime(ref_recent['sale_date'], errors='coerce')
    ref_recent = ref_recent[ref_recent['_u'] != 'N/A']
    idxmax = ref_recent.groupby(['_b', '_u'])['_dt'].idxmax()
    best = ref_recent.loc[idxmax].copy()
    best = best.rename(columns={'_dt': 'display_date'})
    if 'trans_group_en' not in best.columns:
        best['trans_type'] = ''
    else:
        best['trans_type'] = best['trans_group_en'].fillna('')
    if 'sales_recurrence' not in best.columns:
        best['sale_type'] = ''
    else:
        best['sale_type'] = best['sales_recurrence'].fillna('')
    if 'sale_price_aed' not in best.columns:
        best['sale_price_aed'] = float('nan')
    best = best[['_b', '_u', 'display_date', 'trans_type', 'sale_type', 'sale_price_aed']]

    lead_b = leads_df['building_name'].apply(lambda x: (standardize_building_name(x) or '').lower())
    lead_u = leads_df['unit_number'].apply(_norm_unit)
    lead_keys = pd.DataFrame({'_idx': leads_df.index, '_b': lead_b, '_u': lead_u})
    lead_keys = lead_keys[(lead_keys['_b'] != '') & (lead_keys['_u'] != 'N/A')]
    merged = lead_keys.merge(best, on=['_b', '_u'], how='left')
    merged = merged.groupby('_idx').first().reset_index()
    result = pd.DataFrame(index=leads_df.index, columns=['display_date', 'trans_type', 'sale_type', 'sale_price_aed'])
    result.loc[merged['_idx'], 'display_date'] = merged['display_date'].values
    result.loc[merged['_idx'], 'trans_type'] = merged['trans_type'].values
    result.loc[merged['_idx'], 'sale_type'] = merged['sale_type'].values
    result.loc[merged['_idx'], 'sale_price_aed'] = merged['sale_price_aed'].values
    return result


def get_last_sale_per_units(units_df: pd.DataFrame, ref_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """
    For each row in units_df (columns building_name, unit_number; optional 'date' for lead/record date),
    return the latest sale from ref_df (no date filter). Same building/unit normalization as
    get_recent_transaction_details. Result columns: last_sale_date, trans_type, sale_type, sale_price_aed, likely_sold.
    likely_sold is True when last_sale_date is after the row's 'date' and sale_type is Resale.
    """
    out_cols = ['last_sale_date', 'trans_type', 'sale_type', 'sale_price_aed', 'likely_sold']
    if units_df.empty:
        return pd.DataFrame(index=units_df.index, columns=out_cols)
    if ref_df is None or ref_df.empty or 'sale_date' not in ref_df.columns:
        return pd.DataFrame(index=units_df.index, columns=out_cols)
    if 'building_std' not in ref_df.columns or 'unit_no' not in ref_df.columns:
        return pd.DataFrame(index=units_df.index, columns=out_cols)

    def _norm_unit(x):
        if BUILDING_INTELLIGENCE_AVAILABLE and normalize_unit_number is not None:
            return normalize_unit_number(x) if x is not None and (pd.notna(x) and str(x).strip()) else 'N/A'
        return str(x).strip().upper() if x is not None and pd.notna(x) else 'N/A'

    ref = ref_df[ref_df['sale_date'].notna()].copy()
    if ref.empty:
        return pd.DataFrame(index=units_df.index, columns=out_cols)
    ref['_b'] = ref['building_std'].fillna('').astype(str).str.strip().str.lower()
    ref['_u'] = ref['unit_no'].apply(_norm_unit)
    ref['_dt'] = pd.to_datetime(ref['sale_date'], errors='coerce')
    ref = ref[ref['_u'] != 'N/A']
    idxmax = ref.groupby(['_b', '_u'])['_dt'].idxmax()
    best = ref.loc[idxmax].copy()
    best = best.rename(columns={'_dt': 'last_sale_date'})
    best['trans_type'] = best['trans_group_en'].fillna('') if 'trans_group_en' in best.columns else ''
    best['sale_type'] = best['sales_recurrence'].fillna('') if 'sales_recurrence' in best.columns else ''
    best['sale_price_aed'] = best['sale_price_aed'] if 'sale_price_aed' in best.columns else float('nan')
    best = best[['_b', '_u', 'last_sale_date', 'trans_type', 'sale_type', 'sale_price_aed']]

    unit_b = units_df['building_name'].apply(lambda x: (standardize_building_name(x) or '').lower())
    unit_u = units_df['unit_number'].apply(_norm_unit)
    unit_keys = pd.DataFrame({'_idx': units_df.index, '_b': unit_b, '_u': unit_u})
    unit_keys = unit_keys[(unit_keys['_b'] != '') & (unit_keys['_u'] != 'N/A')]
    merged = unit_keys.merge(best, on=['_b', '_u'], how='left')
    merged = merged.groupby('_idx').first().reset_index()

    result = pd.DataFrame(index=units_df.index, columns=out_cols)
    result.loc[merged['_idx'], 'last_sale_date'] = merged['last_sale_date'].values
    result.loc[merged['_idx'], 'trans_type'] = merged['trans_type'].values
    result.loc[merged['_idx'], 'sale_type'] = merged['sale_type'].values
    result.loc[merged['_idx'], 'sale_price_aed'] = merged['sale_price_aed'].values

    lead_dates = pd.to_datetime(units_df['date'], errors='coerce') if 'date' in units_df.columns else pd.Series(index=units_df.index)
    sale_type_resale = merged['sale_type'].fillna('').str.strip().str.lower() == 'resale'
    last_dt = pd.to_datetime(merged['last_sale_date'], errors='coerce')
    lead_dt_merged = lead_dates.reindex(merged['_idx']).values
    likely = (last_dt.values > lead_dt_merged) & sale_type_resale.values
    result.loc[merged['_idx'], 'likely_sold'] = likely
    result['likely_sold'] = result['likely_sold'].fillna(False)
    return result


# =============================================================================
# PORTFOLIO AGGREGATION
# =============================================================================

EXCLUDED_OWNERS = {
    'buyer', 'seller', 'unknown', 'n/a', 'na', 'none', 'null',
    'owner', 'landlord', 'tenant', 'client', 'customer',
    'not available', 'not specified', 'unspecified', 'tbc', 'tba'
}


def aggregate_portfolios(df: pd.DataFrame, min_properties: int = 2) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    
    df_with_owners = df[df['owner_name'].notna() & (df['owner_name'].str.strip() != '')]
    df_with_owners = df_with_owners[~df_with_owners['owner_name'].str.lower().str.strip().isin(EXCLUDED_OWNERS)]
    
    if df_with_owners.empty:
        return pd.DataFrame()
    
    portfolios = []
    for owner, group in df_with_owners.groupby('owner_name'):
        group = group.copy()
        group['_prop_key'] = group['building_name'].fillna('') + '|' + group['unit_number'].fillna('')
        unique_props = group['_prop_key'].nunique()
        
        if unique_props < min_properties:
            continue
        
        buildings = [b for b in group['building_name'].dropna().unique() if b]
        units = [str(u) for u in group['unit_number'].dropna().unique() if u]
        total_beds = group['bedrooms'].dropna().sum()
        
        all_phones = set()
        for phones in group['phone'].dropna():
            if phones:
                for p in str(phones).split('|'):
                    if p.strip():
                        all_phones.add(p.strip())
        
        total_sqft = group['size_sqft'].dropna().sum()
        total_sqm = group['size_sqm'].dropna().sum()
        size_count = group['size_sqft'].notna().sum()
        avg_completeness = group['completeness'].mean()
        
        portfolios.append({
            'owner_name': owner,
            'properties_count': unique_props,
            'buildings': buildings,
            'units': units,
            'total_bedrooms': int(total_beds) if pd.notna(total_beds) else 0,
            'phones': list(all_phones),
            'total_size_sqft': total_sqft if pd.notna(total_sqft) else 0,
            'total_size_sqm': total_sqm if pd.notna(total_sqm) else 0,
            'units_with_size': int(size_count),
            'avg_completeness': round(avg_completeness, 1),
        })
    
    if not portfolios:
        return pd.DataFrame()
    
    portfolio_df = pd.DataFrame(portfolios)
    portfolio_df = portfolio_df.sort_values(
        ['properties_count', 'avg_completeness'], 
        ascending=[False, False]
    ).reset_index(drop=True)
    
    return portfolio_df


def format_portfolio_for_display(portfolio_df: pd.DataFrame) -> pd.DataFrame:
    if portfolio_df.empty:
        return pd.DataFrame(columns=['#', 'Owner Name', 'Properties', 'Buildings', 'Units', 'Total Beds', 'Total Size', 'Phone Numbers', 'Completeness %'])
    
    d = portfolio_df.copy().reset_index(drop=True)
    
    def fmt_buildings(blist):
        if not blist:
            return ''
        return ', '.join(blist[:3]) + ('...' if len(blist) > 3 else '')
    
    def fmt_units(ulist):
        if not ulist:
            return ''
        return ', '.join(ulist[:4]) + ('...' if len(ulist) > 4 else '')
    
    def fmt_phones(plist):
        if not plist:
            return ''
        return ' | '.join(plist[:3]) + ('...' if len(plist) > 3 else '')
    
    def fmt_size(row):
        sqft = row['total_size_sqft']
        count = row['units_with_size']
        if sqft == 0 or pd.isna(sqft):
            return 'N/A'
        return f"{int(sqft):,} sqft / {count} units"
    
    return pd.DataFrame({
        '#': d.index + 1,
        'Owner Name': d['owner_name'],
        'Properties': d['properties_count'],
        'Buildings': d['buildings'].apply(fmt_buildings),
        'Units': d['units'].apply(fmt_units),
        'Total Beds': d['total_bedrooms'],
        'Total Size': d.apply(fmt_size, axis=1),
        'Phone Numbers': d['phones'].apply(fmt_phones),
        'Completeness %': d['avg_completeness'].apply(lambda x: f"{x}%")
    })


# =============================================================================
# DISPLAY FORMATTING - CLEAN OUTPUT (No markers)
# =============================================================================

def get_unique_buildings(df: pd.DataFrame) -> List[str]:
    if df.empty or 'building_name' not in df.columns:
        return []
    return sorted([b for b in df['building_name'].dropna().unique() if b])


def get_unique_bedrooms(df: pd.DataFrame) -> List[str]:
    if df.empty or 'bedrooms' not in df.columns:
        return []
    vals = df['bedrooms'].dropna().unique()
    result = []
    for v in vals:
        if pd.isna(v):
            continue
        result.append('Studio' if v == 0 else str(int(v)))
    return sorted(set(result), key=lambda x: -1 if x == 'Studio' else int(x))


def format_for_display(df: pd.DataFrame, date_column: Optional[str] = None) -> pd.DataFrame:
    """Format for display with CLEAN output - no markers. Use date_column for Date when provided."""
    if df.empty:
        return pd.DataFrame(columns=['#', 'Date', 'Owner Name', 'Building Name', 'Bedrooms', 
                                      'Unit Number', 'Size (sqft)', 'Size (sqm)', 'Phone Number', 
                                      'Completeness %', 'Quality'])
    
    d = df.copy().reset_index(drop=True)
    date_series = d[date_column] if date_column and date_column in d.columns else d['date']
    
    def fmt_bed(row):
        beds = row.get('bedrooms')
        if pd.isna(beds):
            return ''
        return 'Studio' if int(beds) == 0 else str(int(beds))
    
    def fmt_sqft(row):
        sqft = row.get('size_sqft')
        if pd.isna(sqft):
            return ''
        return f"{int(sqft):,}"
    
    def fmt_sqm(row):
        sqm = row.get('size_sqm')
        if pd.isna(sqm):
            return ''
        try:
            return f"{int(float(str(sqm).split()[0].replace(',', ''))):,}"
        except (ValueError, TypeError):
            return str(sqm)
    
    def fmt_quality(x):
        if pd.isna(x) or x == 'OK':
            return 'OK'
        return x.replace('Needs Review: ', '').replace('Flagged: ', '')

    def fmt_date(x):
        """Format date for display; handles numpy.datetime64 and pd.Timestamp."""
        if pd.isna(x):
            return ''
        try:
            ts = pd.Timestamp(x)
            if pd.isna(ts):
                return ''
            return ts.strftime('%Y-%m-%d')
        except Exception:
            return ''

    out = {
        '#': d.index + 1,
        'Date': date_series.apply(fmt_date),
        'Owner Name': d['owner_name'].fillna(''),
        'Building Name': d['building_name'].fillna(''),
        'Bedrooms': d.apply(fmt_bed, axis=1),
        'Unit Number': d['unit_number'].fillna(''),
        'Size (sqft)': d.apply(fmt_sqft, axis=1),
        'Size (sqm)': d.apply(fmt_sqm, axis=1),
        'Phone Number': d['phone'].fillna(''),
        'Completeness %': d['completeness'].apply(lambda x: f"{x}%"),
        'Quality': d['data_quality'].apply(fmt_quality)
    }
    if 'lead_age_warning' in d.columns:
        out['Lead Age'] = d['lead_age_warning'].fillna('')
    if 'trans_type' in d.columns:
        out['Trans Type'] = d['trans_type'].fillna('')
    if 'sale_type' in d.columns:
        out['Sale Type'] = d['sale_type'].fillna('')
    if 'sale_price_aed' in d.columns:
        out['Sale Price (AED)'] = d['sale_price_aed'].apply(
            lambda x: f"{int(x):,}" if pd.notna(x) and str(x) != 'nan' and x != '' else ''
        )
    if 'listing_price' in d.columns:
        out['Listing Price'] = d['listing_price'].fillna('').astype(str)
    if 'listing_type' in d.columns:
        out['Listing Type'] = d['listing_type'].fillna('').astype(str)
    if 'listing_url' in d.columns:
        out['Listing URL'] = d['listing_url'].fillna('').astype(str)
    if 'source' in d.columns:
        out['Source'] = d['source'].fillna('').astype(str)
    if 'pf_listing_count' in d.columns:
        out['PF Listings'] = d['pf_listing_count'].fillna(0).astype(int).astype(str).replace('0', '')
    return pd.DataFrame(out)


def export_to_csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False)

# =============================================================================
# BACKWARDS-COMPAT RE-EXPORTS (PR 9)
# These functions were moved to ai_queries.py so this monolith could shrink.
# They're re-exported lazily via PEP 562 module __getattr__: nothing happens
# at import time (which would cause a circular import because ai_queries
# imports from data_processor), but the first `data_processor.get_..._for_ai`
# access loads ai_queries on demand and caches the resolved attribute.
# =============================================================================

_AI_QUERY_NAMES = frozenset({
    "search_leads_for_ai",
    "get_building_info_for_ai",
    "get_market_stats_for_ai",
    "get_listings_below_market_for_ai",
    "get_portfolio_summary_for_ai",
    "find_potential_owners_for_ai",
    "cross_reference_sale_with_leads_for_ai",
    "get_building_units_for_ai",
    "get_complete_building_intel_for_ai",
    "search_building_names_for_ai",
    "list_all_buildings_for_ai",
    "get_propertyfinder_listings_for_ai",
})


def __getattr__(name):
    if name in _AI_QUERY_NAMES:
        import ai_queries  # local import -- avoids circular at module load
        value = getattr(ai_queries, name)
        globals()[name] = value  # cache so subsequent accesses skip __getattr__
        return value
    raise AttributeError(f"module 'data_processor' has no attribute {name!r}")

