"""
Bayut Listing Parser
Extracts unit-level data from individual property listings.
"""

import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup


def parse_listings_page(html_content: str, building_name: str) -> List[Dict]:
    """
    Extract unit data from Bayut listings page.
    
    Listing cards contain:
    - Title: "Vacant | Full Sea And Burj View | D Type"
    - Specs: "2 Beds | 3 Baths | 1,550 sqft"
    - Unit number: Sometimes in description or reference
    - View: Often in title
    
    Returns list of dicts with:
        - building: Building name
        - unit_number: Unit number (if found)
        - unit_type: Type letter (if mentioned)
        - bedrooms: Bedroom count
        - bathrooms: Bathroom count
        - size_sqft: Size
        - view: View description
        - source: 'listing'
        - listing_url: URL to the listing
    """
    results = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all listing cards
    # Bayut uses various class names: "PropertyCard", "property-card", etc.
    listing_cards = soup.find_all(['article', 'div', 'li'], class_=re.compile(r'property|listing|card', re.I))
    
    for card in listing_cards:
        card_text = card.get_text(separator=' ', strip=True)
        
        # Extract bedrooms
        bed_match = re.search(r'(\d+)\s*(?:Bed|BR|bedroom)', card_text, re.IGNORECASE)
        bedrooms = bed_match.group(1) if bed_match else None
        
        # Extract bathrooms
        bath_match = re.search(r'(\d+)\s*(?:Bath|BA|bathroom)', card_text, re.IGNORECASE)
        bathrooms = bath_match.group(1) if bath_match else None
        
        # Extract size
        size_match = re.search(r'([\d,]+)\s*(?:sq\.?\s*ft|sqft)', card_text, re.IGNORECASE)
        size_sqft = float(size_match.group(1).replace(',', '')) if size_match else None
        
        # Extract unit type (Type A, Type B, etc.)
        type_match = re.search(r'Type[\s-]?([A-H]\d?)', card_text, re.IGNORECASE)
        unit_type = type_match.group(1).upper() if type_match else None
        
        # Extract unit number (various formats: "Unit 1203", "#S-607", etc.)
        unit_match = re.search(r'(?:Unit|#|Apt)\s*([A-Z]?-?\d+[A-Z]?)', card_text, re.IGNORECASE)
        unit_number = unit_match.group(1) if unit_match else None
        
        # Extract view from title (usually in the title/heading)
        view = None
        title_elem = card.find(['h2', 'h3', 'h4', 'a'], class_=re.compile(r'title|heading|name', re.I))
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            view = extract_view_from_text(title_text)
        
        # If view not in title, check full card text
        if not view:
            view = extract_view_from_text(card_text)
        
        # Extract listing URL
        listing_url = None
        link_elem = card.find('a', href=True)
        if link_elem:
            href = link_elem['href']
            if href.startswith('/'):
                listing_url = 'https://www.bayut.com' + href
            elif href.startswith('http'):
                listing_url = href
        
        # Require at least one identifier or spec field that the unit registry
        # cascade can actually use: bedrooms, size_sqft, or unit_type. A row with
        # only a 'view' is noise and ends up corrupting the Bayut feed into the
        # registry (Priority 2.6 size-match) with no hook to match a real unit.
        if bedrooms or size_sqft or unit_type:
            results.append({
                'building': building_name,
                'unit_number': unit_number,
                'unit_type': unit_type,
                'bedrooms': bedrooms,
                'bathrooms': bathrooms,
                'size_sqft': size_sqft,
                'view': view,
                'source': 'listing',
                'source_text': card_text[:200],
                'listing_url': listing_url,
            })
    
    return results


def extract_view_from_text(text: str) -> Optional[str]:
    """Extract view description from text using keywords."""
    text_lower = text.lower()
    
    # Ordered by specificity (most specific first)
    view_patterns = [
        ('full sea and burj', 'Full Sea and Burj Al Arab View'),
        ('sea and burj', 'Full Sea and Burj Al Arab View'),
        ('full atlantis view', 'Full Atlantis View'),
        ('panoramic sea', 'Panoramic Sea View'),
        ('full sea view', 'Full Sea View'),
        ('full sea', 'Full Sea View'),
        ('partial sea', 'Partial Sea View'),
        ('sea view', 'Sea View'),
        ('burj al arab view', 'Burj Al Arab View'),
        ('burj view', 'Burj Al Arab View'),
        ('atlantis view', 'Atlantis View'),
        ('marina view', 'Marina View'),
        ('lagoon view', 'Lagoon View'),
        ('palm view', 'Palm View'),
        ('garden view', 'Garden View'),
        ('pool view', 'Pool View'),
        ('beach view', 'Beach View'),
        ('road facing', 'Road View'),
        ('road view', 'Road View'),
        ('street view', 'Road View'),
        ('community view', 'Community View'),
        ('inland view', 'Inland View'),
    ]
    
    for keyword, view_name in view_patterns:
        if keyword in text_lower:
            return view_name
    
    return None


def parse_listing_detail_page(html_content: str, building_name: str) -> Dict:
    """
    Parse detailed listing page (when clicked into a specific listing).
    More detailed info often available on the full listing page.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract unit details from detail page
    result = {
        'building': building_name,
        'unit_number': None,
        'unit_type': None,
        'bedrooms': None,
        'bathrooms': None,
        'size_sqft': None,
        'view': None,
        'source': 'listing_detail',
        'source_text': None,
    }
    
    # Get page text
    page_text = soup.get_text(separator=' ', strip=True)
    
    # Extract details
    bed_match = re.search(r'(\d+)\s*(?:Bed|BR|bedroom)', page_text, re.IGNORECASE)
    if bed_match:
        result['bedrooms'] = bed_match.group(1)
    
    bath_match = re.search(r'(\d+)\s*(?:Bath|BA|bathroom)', page_text, re.IGNORECASE)
    if bath_match:
        result['bathrooms'] = bath_match.group(1)
    
    size_match = re.search(r'([\d,]+)\s*(?:sq\.?\s*ft|sqft)', page_text, re.IGNORECASE)
    if size_match:
        result['size_sqft'] = float(size_match.group(1).replace(',', ''))
    
    type_match = re.search(r'Type[\s-]?([A-H]\d?)', page_text, re.IGNORECASE)
    if type_match:
        result['unit_type'] = type_match.group(1).upper()
    
    unit_match = re.search(r'(?:Unit|#|Apt)\s*([A-Z]?-?\d+[A-Z]?)', page_text, re.IGNORECASE)
    if unit_match:
        result['unit_number'] = unit_match.group(1)
    
    # Extract view from title and description
    title = soup.find(['h1', 'h2'], class_=re.compile(r'title|heading', re.I))
    if title:
        result['view'] = extract_view_from_text(title.get_text(strip=True))
    
    if not result['view']:
        result['view'] = extract_view_from_text(page_text)
    
    result['source_text'] = page_text[:500]
    
    return result
