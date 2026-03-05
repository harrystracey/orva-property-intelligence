"""
Building Intelligence System for Palm Jumeirah
Handles fuzzy matching, Shoreline tower mapping, and unit validation.
"""

try:
    from fuzzywuzzy import fuzz
except ImportError:
    # Fallback if fuzzywuzzy not installed
    class fuzz:
        @staticmethod
        def partial_ratio(s1, s2):
            s1, s2 = s1.lower(), s2.lower()
            if s1 in s2 or s2 in s1:
                return 90
            return 50

import re
import pandas as pd

# =============================================================================
# SHORELINE TOWER MAPPING - Correct Arabic Names to Tower Numbers
# =============================================================================

SHORELINE_TOWER_MAPPING = {
    "Al Ramth": (1, ["Shoreline 1", "S1", "Tower 1"]),
    "Al Nabat": (2, ["Shoreline 2", "S2", "Tower 2"]),
    "Al Murjan": (3, ["Shoreline 3", "S3", "Tower 3"]),
    "Al Mashraba": (4, ["Shoreline 4", "S4", "Tower 4"]),
    "Al Khayali": (5, ["Shoreline 5", "S5", "Tower 5"]),
    "Al Malak": (6, ["Shoreline 6", "S6", "Tower 6"]),
    "Al Habool": (7, ["Shoreline 7", "S7", "Tower 7"]),
    "Al Ghaf": (8, ["Shoreline 8", "S8", "Tower 8"]),
    "Al Masalli": (9, ["Shoreline 9", "S9", "Tower 9"]),
    "Al Hallawi": (10, ["Shoreline 10", "S10", "Tower 10"]),
    "Al Anbara": (11, ["Shoreline 11", "S11", "Tower 11"]),
    "Jash Falqa": (12, ["Shoreline 12", "S12", "Tower 12"]),
    "Al Shamsi": (13, ["Shoreline 13", "S13", "Tower 13"]),
    "Jash Hamad": (14, ["Shoreline 14", "S14", "Tower 14"]),
    # Additional towers
    "Al Basri": (1, ["Shoreline 1"]),
    "Al Sahab": (2, ["Shoreline 2"]),
    "Al Anbar": (3, ["Shoreline 3"]),
    "Al Dawaar": (4, ["Shoreline 4"]),
    "Al Msalli": (6, ["Shoreline 6"]),  # Alternate spelling
    "Al Sultana": (8, ["Shoreline 8"]),
    "Al Thamam": (9, ["Shoreline 9"]),
    "Al Das": (10, ["Shoreline 10"]),
    "Al Khushkar": (11, ["Shoreline 11"]),
    "Al Janahi": (12, ["Shoreline 12"]),
    "Al Majara": (13, ["Shoreline 13"]),
    "Al Fahad": (14, ["Shoreline 14"]),
    "Al Fattan": (15, ["Shoreline 15"]),
    "Al Shirawi": (16, ["Shoreline 16"]),
    "Al Hamri": (18, ["Shoreline 18"]),
    "Al Hatmi": (19, ["Shoreline 19"]),
    "Al Seef": (20, ["Shoreline 20"]),
}

# Reverse mapping: number to all names
SHORELINE_NUMBER_TO_NAMES = {}
for name, (num, aliases) in SHORELINE_TOWER_MAPPING.items():
    if num not in SHORELINE_NUMBER_TO_NAMES:
        SHORELINE_NUMBER_TO_NAMES[num] = {"arabic": [], "aliases": aliases}
    SHORELINE_NUMBER_TO_NAMES[num]["arabic"].append(name)

# =============================================================================
# BUILDING ALIASES - Common variations for each building
# =============================================================================

BUILDING_ALIASES = {
    "The Fairmont Palm Residences": [
        "Fairmont", "Fairmont Residences", "Fairmont Palm",
        "The Fairmont", "Fairmont Palm Residence South",
        "Fairmont Palm Residence North", "Fairmont North", "Fairmont South"
    ],
    "Ellington Beach House": [
        "Ellington", "Beach House", "Ellington Properties",
        "Ellington Beach", "EBH"
    ],
    "Oceana": [
        "Oceana Residences", "Oceana Baltic",
        "Oceana 1", "Oceana 2", "Oceana 3", "Oceana 4",
        "Oceana 5", "Oceana 6", "Oceana 7",
        "Oceana Caribbean", "Oceana Atlantic", "Oceana Pacific",
        "Oceana Southern", "Dukes Oceana"
    ],
    "Marina Residences": [
        "Marina", "Marina Residence",
        "Marina Residences 1", "Marina Residences 2",
        "Marina Residences 3", "Marina Residences 4",
        "Marina Residences 5", "Marina Residences 6",
        "Palm Marina"
    ],
    "Seven Palm": ["Seven", "Seven Palms", "7 Palm", "Seven Hotel"],
    "Palm Beach Towers": [
        "Palm Beach", "Palm Beach Tower 1",
        "Palm Beach Tower 2", "Palm Beach Tower 3", "PBT"
    ],
    "Tiara Residences": [
        "Tiara", "Tiara Ruby", "Tiara Emerald",
        "Tiara Diamond", "Tiara Sapphire", "Tiara Aquamarine",
        "Tiara United"
    ],
    "Anantara Residences": [
        "Anantara", "Anantara North", "Anantara South",
        "Anantara Palm"
    ],
    "Kempinski Residences": [
        "Kempinski", "Kempinski Palm", "Kempinski Emerald Palace"
    ],
    "Serenia Residences": [
        "Serenia", "Serenia Living"
    ],
    "Balqis Residences": [
        "Balqis", "Balqis Residence"
    ],
    "Golden Mile": [
        "Golden Mile Residences", "Golden Mile Palms"
    ],
    "The 8": [
        "The Eight", "8", "IFA Hotels"
    ],
    "Palm Tower": [
        "The Palm Tower", "St Regis Palm"
    ],
    "Viceroy": [
        "Viceroy Palm", "Viceroy Hotel", "Viceroy Residences"
    ],
    "Azizi Mina": [
        "Azizi", "Mina Azizi"
    ],
    "Club Vista Mare": [
        "Vista Mare", "CVM"
    ],
    "Royal Atlantis": [
        "Atlantis Residences", "Atlantis Royal"
    ],
}

# =============================================================================
# BUILDING SPECIFICATIONS - For validation
# =============================================================================

BUILDING_SPECS = {
    "Ellington Beach House": {
        "unit_types": ["1-bed", "2-bed", "3-bed"],  # NO STUDIOS!
        "towers": ["North (N)", "South (S)"],
        "notes": "No studio apartments in this building"
    },
    "The Fairmont Palm Residences": {
        "unit_types": ["Studio", "1-bed", "2-bed", "3-bed"],
        "towers": ["North", "South"]
    },
    "Seven Palm": {
        "unit_types": ["Studio", "1-bed", "2-bed"],  # Mostly studios/1-beds
        "notes": "Hotel-style apartments, 57% studios"
    },
    "Palm Tower": {
        "unit_types": ["Studio", "1-bed", "2-bed"],
        "notes": "St Regis managed, 48% studios"
    },
    "Oceana": {
        "unit_types": ["Studio", "1-bed", "2-bed", "3-bed"],
        "towers": ["Caribbean", "Atlantic", "Pacific", "Southern", "Baltic"]
    },
}

# =============================================================================
# BUILDING NAME RESOLUTION
# =============================================================================

def resolve_building_name(search_term):
    """
    Fuzzy building name resolution with Shoreline tower support.
    
    Returns: (canonical_name, display_name, confidence)
    - canonical_name: The standard name to use for database lookups
    - display_name: User-friendly name with tower number if applicable
    - confidence: 'high', 'medium', or 'low'
    """
    if not search_term:
        return (None, None, None)
    
    search_lower = search_term.lower().strip()
    
    # Direct Shoreline number match: "Shoreline 9", "S9"
    shoreline_match = re.search(r'(?:shoreline|s)\s*(\d+)', search_lower)
    if shoreline_match:
        num = int(shoreline_match.group(1))
        if num in SHORELINE_NUMBER_TO_NAMES:
            arabic_names = SHORELINE_NUMBER_TO_NAMES[num]["arabic"]
            primary_name = arabic_names[0] if arabic_names else f"Shoreline {num}"
            return (primary_name, f"{primary_name} (Shoreline Tower {num})", "high")
    
    # Check Shoreline Arabic names
    for tower, (num, aliases) in SHORELINE_TOWER_MAPPING.items():
        tower_lower = tower.lower()
        if search_lower == tower_lower or tower_lower in search_lower:
            return (tower, f"{tower} (Shoreline Tower {num})", "high")
        # Check aliases
        for alias in aliases:
            if alias.lower() in search_lower:
                return (tower, f"{tower} (Shoreline Tower {num})", "high")
    
    # Check general building aliases
    for canonical, aliases in BUILDING_ALIASES.items():
        canonical_lower = canonical.lower()
        if search_lower == canonical_lower or canonical_lower in search_lower:
            return (canonical, canonical, "high")
        for alias in aliases:
            alias_lower = alias.lower()
            if search_lower == alias_lower or alias_lower in search_lower:
                return (canonical, canonical, "medium")
    
    # Fuzzy matching fallback
    best_match = None
    best_score = 0
    
    # Check buildings
    all_buildings = list(BUILDING_ALIASES.keys()) + list(SHORELINE_TOWER_MAPPING.keys())
    
    for building in all_buildings:
        score = fuzz.partial_ratio(search_lower, building.lower())
        if score > best_score and score >= 70:
            best_score = score
            best_match = building
    
    if best_match:
        confidence = "high" if best_score >= 90 else "medium" if best_score >= 80 else "low"
        
        # If it's a Shoreline tower, include the number
        if best_match in SHORELINE_TOWER_MAPPING:
            num = SHORELINE_TOWER_MAPPING[best_match][0]
            return (best_match, f"{best_match} (Shoreline Tower {num})", confidence)
        
        return (best_match, best_match, confidence)
    
    return (None, None, None)


def get_shoreline_info(tower_identifier):
    """
    Get detailed info about a Shoreline tower.
    Accepts: "Shoreline 9", "S9", "Al Masalli", "9", etc.
    
    Returns dict with all tower information or None.
    """
    search = str(tower_identifier).lower().strip()
    
    # Extract number if present
    num_match = re.search(r'(\d+)', search)
    if num_match:
        num = int(num_match.group(1))
        if 1 <= num <= 20 and num in SHORELINE_NUMBER_TO_NAMES:
            info = SHORELINE_NUMBER_TO_NAMES[num]
            return {
                "tower_number": num,
                "arabic_names": info["arabic"],
                "aliases": info["aliases"],
                "display_name": f"{info['arabic'][0]} (Shoreline Tower {num})"
            }
    
    # Check Arabic names
    for tower, (num, aliases) in SHORELINE_TOWER_MAPPING.items():
        if tower.lower() in search or search in tower.lower():
            return {
                "tower_number": num,
                "arabic_names": [tower],
                "aliases": aliases,
                "display_name": f"{tower} (Shoreline Tower {num})"
            }
    
    return None

# =============================================================================
# UNIT TYPE VALIDATION
# =============================================================================

def validate_unit_type(building_name, unit_type):
    """
    Validate unit type against building specifications.
    
    Returns: (is_valid, message)
    """
    if not building_name:
        return (True, "Unknown building - cannot validate")
    
    # Resolve building name first
    canonical, _, _ = resolve_building_name(building_name)
    if canonical:
        building_name = canonical
    
    if building_name not in BUILDING_SPECS:
        return (True, "Building not in validation database")
    
    valid_types = BUILDING_SPECS[building_name]["unit_types"]
    
    # Normalize unit type
    unit_str = str(unit_type).lower().strip()
    if unit_str in ['0', 'studio', 's']:
        unit_check = "Studio"
    elif unit_str.isdigit():
        unit_check = f"{unit_str}-bed"
    elif '-bed' in unit_str or 'bed' in unit_str:
        # Extract number
        num_match = re.search(r'(\d+)', unit_str)
        if num_match:
            unit_check = f"{num_match.group(1)}-bed"
        else:
            unit_check = unit_str
    else:
        unit_check = unit_str
    
    if unit_check in valid_types:
        return (True, f"Valid - {building_name} has {unit_check} units")
    else:
        notes = BUILDING_SPECS[building_name].get("notes", "")
        return (
            False, 
            f"⚠️ INVALID: {building_name} only has {', '.join(valid_types)}. "
            f"'{unit_type}' is likely a data error. {notes}"
        )

# =============================================================================
# UNIT NUMBER NORMALIZATION
# =============================================================================

def normalize_unit_number(unit_num):
    """
    Standardize unit numbers for consistent matching.
    
    Examples:
    - "S607" → "S-607"
    - "N410" → "N-410"
    - "Unit 101" → "101"
    - "Apt 2B" → "2B"
    - "1203" → "1203"
    """
    if not unit_num or pd.isna(unit_num) or str(unit_num).strip() in ['nan', '', 'N/A', 'None']:
        return 'N/A'
    
    unit_str = str(unit_num).strip().upper()
    
    # Remove common prefixes
    unit_str = re.sub(r'^(UNIT|APT|APARTMENT|FLAT|NO\.?|#)\s*', '', unit_str, flags=re.IGNORECASE)
    
    # Add hyphen after letter prefix: S607 → S-607, N410 → N-410
    match = re.match(r'^([A-Z]{1,2})(\d+)$', unit_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    
    # Handle floor-unit format: 12-03 → 1203
    floor_unit = re.match(r'^(\d{1,2})-(\d{2,3})$', unit_str)
    if floor_unit:
        return f"{floor_unit.group(1)}{floor_unit.group(2)}"
    
    return unit_str


def extract_floor_from_unit(unit_num):
    """
    Extract floor number from unit number.
    
    Examples:
    - "S-607" → 6
    - "1203" → 12
    - "N-410" → 4
    - "2B" → None (can't determine)
    """
    if not unit_num or unit_num == 'N/A':
        return None
    
    unit_str = str(unit_num).upper()
    
    # Format: S-607 or N-410 (letter prefix with hyphen)
    match = re.match(r'^[A-Z]-?(\d)(\d{2})$', unit_str)
    if match:
        return int(match.group(1))
    
    # Format: 1203 (4 digits - first 2 are floor)
    match = re.match(r'^(\d{2})(\d{2})$', unit_str)
    if match:
        return int(match.group(1))
    
    # Format: 607 (3 digits - first 1 is floor)
    match = re.match(r'^(\d)(\d{2})$', unit_str)
    if match:
        return int(match.group(1))
    
    return None

# =============================================================================
# DATA QUALITY HELPERS
# =============================================================================

def calculate_data_age(date_val):
    """
    Calculate data age and return indicator.
    
    Returns: emoji + text description
    """
    try:
        if pd.isna(date_val):
            return "❓ Unknown age"
        
        date = pd.to_datetime(date_val)
        age_days = (pd.Timestamp.now() - date).days
        
        if age_days < 0:
            return "🆕 Fresh (future date)"
        elif age_days < 30:
            return "🆕 Fresh (<1 month)"
        elif age_days < 90:
            return "✅ Recent (<3 months)"
        elif age_days < 365:
            return "⚠️ Moderate (<1 year)"
        elif age_days < 730:
            return f"🕐 Aging ({age_days//365} year)"
        else:
            return f"🕐 Stale ({age_days//365}+ years)"
    except Exception:
        return "❓ Unknown age"


def validate_phone_number(phone):
    """
    Validate phone number quality.
    
    Returns dict with status, quality emoji, and message.
    """
    if pd.isna(phone) or str(phone).strip() in ['No phone', 'nan', '', 'None', 'N/A']:
        return {"status": "missing", "quality": "❌", "message": "No phone number"}
    
    phone_clean = str(phone).replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
    
    if not phone_clean.replace('.', '').isdigit():
        return {"status": "invalid", "quality": "❌", "message": "Invalid format (non-numeric)"}
    
    # UAE format: 971XXXXXXXXX (12 digits)
    if phone_clean.startswith('971'):
        if len(phone_clean) == 12:
            return {"status": "valid", "quality": "✅", "message": "Valid UAE mobile"}
        else:
            return {"status": "questionable", "quality": "⚠️", "message": f"UAE code but wrong length ({len(phone_clean)} digits)"}
    
    # UAE without country code: 05XXXXXXXX (10 digits)
    if phone_clean.startswith('05') and len(phone_clean) == 10:
        return {"status": "valid", "quality": "✅", "message": "Valid UAE mobile (local format)"}
    
    # International numbers
    if 10 <= len(phone_clean) <= 15:
        return {"status": "valid", "quality": "✅", "message": "Valid international format"}
    
    if len(phone_clean) < 10:
        return {"status": "invalid", "quality": "❌", "message": "Too short to be valid"}
    
    return {"status": "questionable", "quality": "⚠️", "message": f"Unusual format ({len(phone_clean)} digits)"}


def format_phone_number(phone):
    """
    Format phone number for display.
    
    Examples:
    - "971501234567" → "+971 50 123 4567"
    - "0501234567" → "+971 50 123 4567"
    """
    if pd.isna(phone) or str(phone).strip() in ['No phone', 'nan', '', 'None', 'N/A']:
        return "No phone"
    
    phone_clean = str(phone).replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
    
    # Format UAE: +971 XX XXX XXXX
    if phone_clean.startswith('971') and len(phone_clean) == 12:
        return f"+971 {phone_clean[3:5]} {phone_clean[5:8]} {phone_clean[8:]}"
    
    # Local UAE without country code
    if phone_clean.startswith('05') and len(phone_clean) == 10:
        return f"+971 {phone_clean[1:3]} {phone_clean[3:6]} {phone_clean[6:]}"
    
    # Russian format
    if phone_clean.startswith('7') and len(phone_clean) == 11:
        return f"+7 {phone_clean[1:4]} {phone_clean[4:7]} {phone_clean[7:]}"
    
    # UK format
    if phone_clean.startswith('44') and len(phone_clean) >= 12:
        return f"+44 {phone_clean[2:6]} {phone_clean[6:]}"
    
    # Return as-is with + prefix if looks international
    if len(phone_clean) >= 10:
        return f"+{phone_clean}"
    
    return str(phone).strip()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_all_shoreline_towers():
    """Return list of all Shoreline towers with their info."""
    towers = []
    for num in range(1, 21):
        if num in SHORELINE_NUMBER_TO_NAMES:
            info = SHORELINE_NUMBER_TO_NAMES[num]
            towers.append({
                "number": num,
                "arabic_names": info["arabic"],
                "display": f"Shoreline {num} ({', '.join(info['arabic'])})"
            })
    return towers


def search_buildings(query, limit=10):
    """
    Search for buildings matching a query.
    Returns list of matching buildings with scores.
    """
    if not query:
        return []
    
    query_lower = query.lower().strip()
    results = []
    
    # Check all buildings
    all_buildings = list(BUILDING_ALIASES.keys()) + list(SHORELINE_TOWER_MAPPING.keys())
    
    for building in all_buildings:
        score = fuzz.partial_ratio(query_lower, building.lower())
        if score >= 50:
            display = building
            if building in SHORELINE_TOWER_MAPPING:
                num = SHORELINE_TOWER_MAPPING[building][0]
                display = f"{building} (Shoreline Tower {num})"
            
            results.append({
                "name": building,
                "display": display,
                "score": score
            })
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
