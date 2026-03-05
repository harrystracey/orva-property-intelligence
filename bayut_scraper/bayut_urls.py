"""
Bayut URL Mapping for Palm Jumeirah Buildings
Maps normalized building names to Bayut slug structure.
"""

BAYUT_BUILDINGS = {
    # Shoreline Apartments (Arabic names on Bayut)
    'Shoreline 1': {'slug': 'al-ramth', 'community': 'shoreline-apartments'},
    'Shoreline 2': {'slug': 'al-nabat', 'community': 'shoreline-apartments'},
    'Shoreline 3': {'slug': 'al-sultana', 'community': 'shoreline-apartments'},
    'Shoreline 4': {'slug': 'al-tamr', 'community': 'shoreline-apartments'},
    'Shoreline 5': {'slug': 'al-jeer', 'community': 'shoreline-apartments'},
    'Shoreline 6': {'slug': 'al-shahla', 'community': 'shoreline-apartments'},
    'Shoreline 7': {'slug': 'al-khudrawi', 'community': 'shoreline-apartments'},
    'Shoreline 8': {'slug': 'al-sarrood', 'community': 'shoreline-apartments'},
    'Shoreline 9': {'slug': 'al-msalli', 'community': 'shoreline-apartments'},
    'Shoreline 10': {'slug': 'al-dabas', 'community': 'shoreline-apartments'},
    'Shoreline 11': {'slug': 'al-habool', 'community': 'shoreline-apartments'},
    'Shoreline 12': {'slug': 'al-haseer', 'community': 'shoreline-apartments'},
    'Shoreline 13': {'slug': 'al-ameera', 'community': 'shoreline-apartments'},
    'Shoreline 14': {'slug': 'al-hallawi', 'community': 'shoreline-apartments'},
    'Shoreline 15': {'slug': 'al-das', 'community': 'shoreline-apartments'},
    'Shoreline 16': {'slug': 'al-khushkar', 'community': 'shoreline-apartments'},
    'Shoreline 17': {'slug': 'al-hamri', 'community': 'shoreline-apartments'},
    'Shoreline 18': {'slug': 'al-safeena', 'community': 'shoreline-apartments'},
    'Shoreline 19': {'slug': 'al-basri', 'community': 'shoreline-apartments'},
    'Shoreline 20': {'slug': 'al-ghozlan', 'community': 'shoreline-apartments'},
    
    # Major Buildings
    'Oceana': {'slug': 'oceana', 'community': 'oceana'},
    'Fairmont': {'slug': 'the-fairmont-palm-residences', 'community': 'the-fairmont-palm-residences'},
    'Marina Residences': {'slug': 'marina-residences', 'community': 'marina-residences'},
    'Marina 1': {'slug': 'marina-residences', 'community': 'marina-residences'},
    'Marina 2': {'slug': 'marina-residences', 'community': 'marina-residences'},
    'Marina 3': {'slug': 'marina-residences', 'community': 'marina-residences'},
    'Marina 4': {'slug': 'marina-residences', 'community': 'marina-residences'},
    'Marina 5': {'slug': 'marina-residences', 'community': 'marina-residences'},
    'Marina 6': {'slug': 'marina-residences', 'community': 'marina-residences'},
    'Golden Mile': {'slug': 'golden-mile', 'community': 'golden-mile'},
    'Tiara Residences': {'slug': 'tiara-residences', 'community': 'tiara-residences'},
    'Azure Residences': {'slug': 'azure-residences', 'community': 'azure-residences'},
    'Kempinski': {'slug': 'kempinski-palm-residence', 'community': 'the-crescent'},
    'Palm Views': {'slug': 'palm-views', 'community': 'palm-views'},
    'Palm Views East': {'slug': 'palm-views', 'community': 'palm-views'},
    'Palm Views West': {'slug': 'palm-views', 'community': 'palm-views'},
    'The 8': {'slug': 'the-8', 'community': 'the-crescent'},
    'Seven Palm': {'slug': 'seven-palm', 'community': 'seven-palm'},
    'Palm Tower': {'slug': 'the-palm-tower', 'community': 'palm-jumeirah'},
    'Anantara': {'slug': 'anantara-residences', 'community': 'the-crescent'},
    'Balqis': {'slug': 'balqis-residence', 'community': 'the-crescent'},
    'Five Palm Jumeirah': {'slug': 'five-palm-jumeirah', 'community': 'palm-jumeirah'},
    'Serenia Residences': {'slug': 'serenia-residences', 'community': 'the-crescent'},
    'Grandeur': {'slug': 'grandeur-residences', 'community': 'the-crescent'},
    'Muraba': {'slug': 'muraba-residences', 'community': 'the-crescent'},
    'Atlantis The Royal': {'slug': 'atlantis-the-royal-residences', 'community': 'the-crescent'},
}


def get_building_guide_url(building_name: str) -> str:
    """Get Bayut building guide URL."""
    config = BAYUT_BUILDINGS.get(building_name)
    if not config:
        return None
    return f"https://www.bayut.com/buildings/{config['slug']}/"


def get_floor_plan_url(building_name: str) -> str:
    """Get Bayut floor plan URL."""
    config = BAYUT_BUILDINGS.get(building_name)
    if not config or not config['community']:
        return None
    return f"https://www.bayut.com/floorplans/dubai/palm-jumeirah/{config['community']}/{config['slug']}/"


def get_listings_url(building_name: str, listing_type: str = 'rent') -> str:
    """Get Bayut listings URL (rent or sale)."""
    config = BAYUT_BUILDINGS.get(building_name)
    if not config or not config['community']:
        return None
    
    if listing_type == 'rent':
        return f"https://www.bayut.com/to-rent/apartments/dubai/palm-jumeirah/{config['community']}/{config['slug']}/"
    else:
        return f"https://www.bayut.com/for-sale/apartments/dubai/palm-jumeirah/{config['community']}/{config['slug']}/"


def get_all_buildings():
    """Get list of all building names."""
    # Return unique building names (excluding Marina 1-6 which map to same slug)
    seen_slugs = set()
    unique_buildings = []
    for building, config in BAYUT_BUILDINGS.items():
        slug_key = (config['slug'], config['community'])
        if slug_key not in seen_slugs:
            seen_slugs.add(slug_key)
            unique_buildings.append(building)
    return unique_buildings
