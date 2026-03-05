"""
Bayut Floor Plan Parser
Extracts unit type → bedroom → bathroom mappings from floor plan pages.
"""

import re
from typing import List, Dict
from bs4 import BeautifulSoup


def parse_floor_plan_page(html_content: str, building_name: str) -> List[Dict]:
    """
    Extract unit type info from Bayut floor plan page.
    
    Floor plan pages list unit types like:
    - Type B: 1 bedroom, 2 bathrooms
    - Type D: 2 bedrooms, 3 bathrooms
    - Type F: 2 bedrooms, 4 bathrooms
    - Type A: 3 bedrooms, 4 bathrooms
    
    Returns list of dicts with:
        - building: Building name
        - unit_type: Type letter (A-H)
        - bedrooms: Bedroom count
        - bathrooms: Bathroom count
        - size_sqft: None (not on floor plan pages)
        - view: None (not on floor plan pages)
        - source: 'floor_plan'
    """
    results = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract all text
    page_text = soup.get_text()
    
    # Pattern: "Type X: Y bedroom(s), Z bathroom(s)"
    # Also handles: "Type X - Y bed, Z bath"
    pattern = r'Type\s*([A-H]\d?)[\s:,-]*(\d+)\s*(?:bed|bedroom|BR)s?[,\s]*(\d+)\s*(?:bath|bathroom|BA)s?'
    
    matches = re.finditer(pattern, page_text, re.IGNORECASE)
    
    for match in matches:
        unit_type = match.group(1).upper()
        bedrooms = match.group(2)
        bathrooms = match.group(3)
        
        results.append({
            'building': building_name,
            'unit_type': unit_type,
            'bedrooms': bedrooms,
            'bathrooms': bathrooms,
            'size_sqft': None,
            'view': None,
            'source': 'floor_plan',
            'source_text': match.group(0),
        })
    
    # Also try structured HTML elements if available
    # Floor plan pages might have cards/divs with class names like "floorplan-item"
    floor_plan_items = soup.find_all(['div', 'li', 'section'], class_=re.compile(r'floor|plan|type', re.I))
    
    for item in floor_plan_items:
        item_text = item.get_text(strip=True)
        
        # Try to extract type, beds, baths from this element
        type_match = re.search(r'Type\s*([A-H]\d?)', item_text, re.IGNORECASE)
        if not type_match:
            continue
        
        unit_type = type_match.group(1).upper()
        
        bed_match = re.search(r'(\d+)\s*(?:bed|bedroom|BR)', item_text, re.IGNORECASE)
        bath_match = re.search(r'(\d+)\s*(?:bath|bathroom|BA)', item_text, re.IGNORECASE)
        
        if bed_match or bath_match:
            results.append({
                'building': building_name,
                'unit_type': unit_type,
                'bedrooms': bed_match.group(1) if bed_match else None,
                'bathrooms': bath_match.group(1) if bath_match else None,
                'size_sqft': None,
                'view': None,
                'source': 'floor_plan',
                'source_text': item_text[:200],
            })
    
    # Remove duplicates (same type with same data)
    unique_results = []
    seen = set()
    for result in results:
        key = (result['unit_type'], result['bedrooms'], result['bathrooms'])
        if key not in seen:
            seen.add(key)
            unique_results.append(result)
    
    return unique_results


def parse_floor_plan_images(html_content: str, building_name: str) -> List[str]:
    """
    Extract floor plan image URLs from page.
    Returns list of image URLs.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all images with floor plan keywords in src or alt
    images = soup.find_all('img', src=re.compile(r'floor|plan|type', re.I))
    image_urls = [img.get('src', '') for img in images if img.get('src')]
    
    # Also check alt text
    images_alt = soup.find_all('img', alt=re.compile(r'floor|plan|type', re.I))
    image_urls.extend([img.get('src', '') for img in images_alt if img.get('src') and img.get('src') not in image_urls])
    
    # Make URLs absolute if they're relative
    full_urls = []
    for url in image_urls:
        if url.startswith('//'):
            full_urls.append('https:' + url)
        elif url.startswith('/'):
            full_urls.append('https://www.bayut.com' + url)
        elif url.startswith('http'):
            full_urls.append(url)
    
    return full_urls
