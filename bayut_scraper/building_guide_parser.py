"""
Bayut Building Guide Parser
Extracts unit type specifications from building guide text.
"""

import re
from typing import List, Dict, Optional


def parse_building_guide(page_text: str, building_name: str) -> List[Dict]:
    """
    Extract unit type info from Bayut building guide text.
    
    Parses natural language descriptions like:
    - "Type-F covers around 2,055 sq. ft. offering panoramic sea views"
    - "Type-D 2-bed flats are the smallest with a covered area of 1,582 sq. ft."
    - "Type E unit usually covers around 1,646 sq. ft. and offers views of the road"
    
    Returns list of dicts with:
        - building: Building name
        - unit_type: Type letter (A-H)
        - bedrooms: Bedroom count
        - size_sqft: Size in sqft
        - view: View description
        - source_text: Original sentence for audit
    """
    results = []
    
    # Pattern: "Type X" or "Type-X" followed by bedroom/size/view info
    type_pattern = r'Type[\s-]?([A-H]\d?)\b'
    
    # Split into sentences (using multiple delimiters)
    sentences = re.split(r'[.!?]\s+', page_text)
    
    for sentence in sentences:
        type_match = re.search(type_pattern, sentence, re.IGNORECASE)
        if not type_match:
            continue
        
        unit_type = type_match.group(1).upper()
        
        # Extract bedrooms
        bed_match = re.search(r'(\d)[- ]?bed', sentence, re.IGNORECASE)
        bedrooms = bed_match.group(1) if bed_match else None
        
        # Extract size (handles "sq. ft.", "sq ft", "sqft")
        size_match = re.search(r'([\d,]+)\s*sq\.?\s*\.?\s*ft', sentence, re.IGNORECASE)
        size = float(size_match.group(1).replace(',', '')) if size_match else None
        
        # Extract view keywords (ordered by specificity)
        view = None
        view_patterns = [
            (r'full\s*sea\s*and\s*burj', 'Full Sea and Burj Al Arab View'),
            (r'panoramic\s*sea', 'Panoramic Sea View'),
            (r'full\s*sea', 'Full Sea View'),
            (r'partial\s*sea', 'Partial Sea View'),
            (r'sea\s*view', 'Sea View'),
            (r'overlooks?\s*the\s*sea', 'Sea View'),
            (r'facing\s*the\s*sea', 'Sea View'),
            (r'burj\s*al\s*arab', 'Burj Al Arab View'),
            (r'burj\s*view', 'Burj Al Arab View'),
            (r'atlantis\s*view', 'Atlantis View'),
            (r'marina\s*view', 'Marina View'),
            (r'lagoon\s*view', 'Lagoon View'),
            (r'palm\s*view', 'Palm View'),
            (r'garden\s*view', 'Garden View'),
            (r'pool\s*view', 'Pool View'),
            (r'beach\s*view', 'Beach View'),
            (r'road[- ]?facing', 'Road View'),
            (r'views?\s*of\s*the\s*road', 'Road View'),
            (r'street\s*view', 'Road View'),
            (r'sister\s*blocks', 'Building View'),
            (r'facing\s*the\s*blocks', 'Building View'),
            (r'inland\s*view', 'Inland View'),
            (r'community\s*view', 'Community View'),
        ]
        for pattern, view_name in view_patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                view = view_name
                break
        
        # Skip if no useful data extracted
        if not bedrooms and not size and not view:
            continue
        
        results.append({
            'building': building_name,
            'unit_type': unit_type,
            'bedrooms': bedrooms,
            'bathrooms': None,  # Not in building guides
            'size_sqft': size,
            'view': view,
            'source': 'building_guide',
            'source_text': sentence.strip()[:200],  # Truncate long sentences
        })
    
    return results


def extract_size_range(text: str) -> Optional[float]:
    """
    Extract size from various formats:
    - "2,055 sq. ft."
    - "around 1,646 sqft"
    - "1,400 to 1,600 sq ft"
    Returns midpoint for ranges.
    """
    # Try range first: "1,400 to 1,600 sq ft"
    range_match = re.search(r'([\d,]+)\s*(?:to|-)\s*([\d,]+)\s*sq', text, re.IGNORECASE)
    if range_match:
        low = float(range_match.group(1).replace(',', ''))
        high = float(range_match.group(2).replace(',', ''))
        return (low + high) / 2
    
    # Try single value: "2,055 sq. ft."
    single_match = re.search(r'([\d,]+)\s*sq\.?\s*ft', text, re.IGNORECASE)
    if single_match:
        return float(single_match.group(1).replace(',', ''))
    
    return None


def normalize_view_description(view_text: str) -> str:
    """Normalize view descriptions to consistent format."""
    view_text = view_text.lower().strip()
    
    # Mapping of variations to standard names
    view_map = {
        'panoramic sea': 'Panoramic Sea View',
        'full sea': 'Full Sea View',
        'partial sea': 'Partial Sea View',
        'sea view': 'Sea View',
        'burj al arab': 'Burj Al Arab View',
        'burj view': 'Burj Al Arab View',
        'atlantis': 'Atlantis View',
        'marina': 'Marina View',
        'lagoon': 'Lagoon View',
        'palm': 'Palm View',
        'garden': 'Garden View',
        'pool': 'Pool View',
        'road': 'Road View',
        'building': 'Building View',
        'community': 'Community View',
        'inland': 'Inland View',
    }
    
    for keyword, standard_name in view_map.items():
        if keyword in view_text:
            return standard_name
    
    return 'Unknown View'
