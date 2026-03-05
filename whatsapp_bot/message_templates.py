"""
WhatsApp Message Templates
All templates follow rules: no opening with name+company, always include building+unit,
personalize with first name only, use emoji sparingly, no links in first message.
Custom overrides loaded from custom_templates.json if present.
"""

import re
import random
import json
from pathlib import Path
from typing import Optional, Dict, List

CUSTOM_TEMPLATES_PATH = Path(__file__).parent / "custom_templates.json"
TEMPLATE_KEYS = ['landlord_lease_expiry', 'cold_owner_single', 'cold_owner_portfolio', 'recent_sale', 'portfolio_owner', 'active_seller', 'active_renter']


def format_building_for_message(building: str) -> str:
    """Normalize building name for message display: never full caps. Use title case."""
    if not building or not isinstance(building, str):
        return building or ''
    s = building.strip()
    if not s:
        return s
    if s.isupper():
        return s.title()
    return s


def format_first_name(full_name: str) -> Optional[str]:
    """
    Extract and format first name from ALL CAPS full name.
    Returns None for corporate entities.
    """
    if not full_name or not isinstance(full_name, str):
        return None
    
    name = full_name.strip()
    
    # Skip corporate entities (management companies, etc.) — message will use "Hi" only, no name
    corporate_indicators = [
        'LLC', 'LTD', 'L.L.C', 'CORP', 'INC', 'FZCO', 'FZE', 'FZ',
        'M/S', 'PROPERTIES', 'LIMITED', 'COMPANY', 'SERVICES',
        'HOLDINGS', 'INVESTMENT', 'REAL ESTATE', 'GROUP',
        'MANAGEMENT', 'ESTATE', 'DEVELOPMENT', 'BROKERS', 'AGENCY',
    ]
    if any(ind in name.upper() for ind in corporate_indicators):
        return None
    
    # Strip prefixes
    name = re.sub(
        r'^(MR\.?\s+|MRS\.?\s+|MS\.?\s+|DR\.?\s+|H\.E\.?\s+|SHEIKH\s+|SHAIKH\s+)', 
        '', name, flags=re.IGNORECASE
    ).strip()
    
    # Get first name
    parts = name.split()
    if not parts:
        return None
    
    first = parts[0].strip().title()
    
    # If first part is "Al" or "El", include next part (Arabic naming)
    if first.lower() in ('al', 'el', 'abu', 'bin', 'bint') and len(parts) > 1:
        first = f"{first} {parts[1].strip().title()}"
    
    return first


# =============================================================================
# COLD OWNER TEMPLATES
# =============================================================================

COLD_OWNER_SINGLE = [
    "Hi {name}, hope you are well.\n\n"
    "I'm reaching out to owners in {building} (Unit {unit}) as I have a family office "
    "looking to acquire in the building. If you've ever considered your options, I'd be "
    "happy to share what your property could achieve in today's market.\n\n"
    "Many thanks, Harry.",
    "Hi {name}, hope you're well.\n\n"
    "I have a client who was interested in buying in {building}, I checked and noticed some strong movement in "
    "it recently. Your unit ({unit}) sits in a size bracket that's seeing real demand right now.\n\n"
    "Would you be interested in a quick market update?\n\n"
    "Thanks, Harry.",
    "Good morning {name}. I work on Palm Jumeirah and have a buyer actively looking in {building}.\n\n"
    "Your unit ({unit}) fits what they're after. If you've ever thought about selling, "
    "I'd be happy to share what similar units have achieved lately.\n\n"
    "Harry.",
    "Hey {name}, hope all is good.\n\n"
    "Quick one — I'm reaching out to a few owners in {building} (Unit {unit}) because a family office "
    "is building a position in the building. If that's of interest, I can run some numbers for you.\n\n"
    "Cheers, Harry.",
    "Morning {name}. I noticed your unit ({unit}) in {building} — we've had strong interest in that building "
    "recently from a cash buyer. If you'd like a no-obligation market snapshot, just say the word.\n\n"
    "Best, Harry.",
    "Hi {name}. I have a client who specifically asked about {building}. Your unit ({unit}) is in a size "
    "bracket that's been moving well. Would you consider a quick chat about what the market might offer?\n\n"
    "Many thanks, Harry.",
    "Hi {name}, hope you're well.\n\n"
    "I'm touching base with owners in {building} as I have an investor looking to acquire there. "
    "Unit {unit} is the type of asset they're after. Happy to share recent comparables if useful.\n\n"
    "Thanks, Harry.",
]


COLD_OWNER_PORTFOLIO = [
    "Good morning {name}. I tried giving you a call last week but couldn't get hold of you. "
    "I see you have invested multiple times in {building} and wanted to check if they're all "
    "rented out or if any are for sale. I have a client interested.\n\n"
    "Harry.",
    "Hi {name}, hope you are well. I can see you hold multiple units in {building} — impressive portfolio.\n\n"
    "I have a family office actively looking in the building and wanted to check if you'd "
    "consider selling any of your positions? Happy to share what the current market would offer.\n\n"
    "Many thanks, Harry.",
    "Hi {name}, hope you're well.\n\n"
    "I have a family office actively looking in {building}. I can see you hold multiple units — "
    "would you be interested in a quick portfolio review?\n\n"
    "Thanks, Harry.",
    "Hey {name}. I work exclusively on Palm and noticed you have several units in {building}.\n\n"
    "A buyer is building a position in that building. If you'd ever consider selling one or more, "
    "I'd be happy to run the numbers.\n\n"
    "Cheers, Harry.",
    "Morning {name}. I have an investor looking to acquire in {building}. Given your multiple holdings there, "
    "I thought I'd reach out — are any of your units potentially for sale or might you be open to a conversation?\n\n"
    "Best, Harry.",
    "Hi {name}. I can see you've built a solid position in {building}. I have a family office client "
    "interested in the building and wanted to check if you'd consider selling any of your units. "
    "Happy to share current market view.\n\n"
    "Harry.",
]


# =============================================================================
# PORTFOLIO OWNER (DEDICATED CAMPAIGN: 3+ UNITS)
# Portfolio review, bulk acquisition, market intelligence angles.
# Placeholders: {name}, {unit_count}, {buildings}
# =============================================================================

PORTFOLIO_OWNER = [
    # Portfolio review
    "Hi {name}, hope you are well.\n\n"
    "I'd love to offer you a quick portfolio review — I see you hold {unit_count} units across {buildings}. "
    "I track Palm closely and can share a market update on your holdings if that's useful.\n\n"
    "Many thanks, Harry.",
    "Hi {name}, hope you're well.\n\n"
    "I work exclusively on Palm and noticed your portfolio across {buildings} ({unit_count} units). "
    "If you'd like a no-obligation market update on how your positions are performing, I'm happy to run the numbers.\n\n"
    "Thanks, Harry.",
    # Bulk acquisition
    "Good morning {name}. I have a buyer actively looking to acquire multiple units on Palm in bulk.\n\n"
    "Given your {unit_count} units in {buildings}, I thought I'd reach out — would you be open to a conversation about what they might offer?\n\n"
    "Harry.",
    "Hi {name}, hope all is good.\n\n"
    "A family office is building a position on Palm and is interested in portfolio-level deals. "
    "I see you hold {unit_count} units across {buildings}. If you'd ever consider selling one or more, I'd be happy to connect you.\n\n"
    "Cheers, Harry.",
    # Market intelligence
    "Morning {name}. I track Palm Jumeirah closely and have been following activity in {buildings}.\n\n"
    "You've built a solid position there ({unit_count} units). I'd be happy to share what I'm seeing in terms of demand and pricing — no obligation.\n\n"
    "Best, Harry.",
    "Hey {name}. I work on Palm and keep a close eye on your buildings — {buildings}. "
    "With {unit_count} units you're a meaningful holder. If you'd like a quick market intelligence update, I can run through recent comparables and trends.\n\n"
    "Harry.",
]


# =============================================================================
# LANDLORD LEASE EXPIRY TEMPLATES
# =============================================================================

LANDLORD_LEASE_EXPIRY = [
    "Hi {name}, hope you are well.\n\n"
    "I understand you may have a tenancy period coming to an end on your property in {building} (Unit {unit}). "
    "If you're exploring options for your next move, I'd love to help — I have a client looking for something similar.\n\n"
    "Many thanks, Harry.",
    "Hi {name}, I work exclusively on Palm Jumeirah and noticed your property in {building} (Unit {unit}) "
    "may have a lease transition coming up.\n\n"
    "Whether you're looking to re-let or considering a sale, I'd be happy to share what the market looks like for your unit right now.\n\n"
    "Harry.",
    "Hi {name}, your {bedrooms_display} in {building} (Unit {unit}) is in a bracket that's been moving well recently.\n\n"
    "With a potential lease change coming up, it might be worth knowing your options. Happy to share some recent comparables if useful.\n\n"
    "Thanks, Harry.",
    "Good morning {name}. I see a lease may be ending soon on your unit ({unit}) in {building}.\n\n"
    "If you're weighing up re-letting vs selling, I have a buyer interested in that building. Happy to give you a quick market view.\n\n"
    "Best, Harry.",
    "Hey {name}, hope you're well. Your property in {building} (Unit {unit}) may be coming up to a lease change.\n\n"
    "I have a client looking in that building — if you'd like to know what your unit could achieve or how the rental market looks, I can help.\n\n"
    "Cheers, Harry.",
    "Morning {name}. I work on Palm and noticed your unit ({unit}) in {building} might have a tenancy ending soon.\n\n"
    "Whether you're thinking re-let or sale, I'd be happy to share what the market is doing. No obligation.\n\n"
    "Harry.",
]


# =============================================================================
# RECENT SALE FOLLOW-UP TEMPLATES
# =============================================================================

RECENT_SALE_FOLLOW_UP = [
    "Hi {name}, hope you are well.\n\n"
    "I noticed your recent sale in {building} (Unit {unit}) and wanted to reach out. "
    "If you're looking to reinvest on Palm or have other properties to discuss, I'd be happy to help.\n\n"
    "Many thanks, Harry.",
    "Hi {name}, congratulations on your recent transaction in {building} (Unit {unit}).\n\n"
    "I work exclusively on Palm Jumeirah and am here if you'd like a quick view of what's available or if you're considering another purchase in the area.\n\n"
    "Harry.",
    "Good morning {name}. I saw your sale in {building} (Unit {unit}) — congrats.\n\n"
    "If you're looking to reinvest on Palm or want to see what's on the market, I'm happy to help.\n\n"
    "Thanks, Harry.",
    "Hey {name}. I noticed you recently sold in {building} (Unit {unit}). "
    "If you're thinking about another purchase or want a market update, give me a shout.\n\n"
    "Cheers, Harry.",
    "Hi {name}, hope you're well. I work on Palm and saw your recent sale in {building} (Unit {unit}).\n\n"
    "If you're looking to reinvest or have other units to discuss, I'd be glad to assist.\n\n"
    "Best, Harry.",
    "Morning {name}. Congratulations on the sale in {building} (Unit {unit}). "
    "I'm here if you'd like to see what's available for a reinvestment or have any questions about the area.\n\n"
    "Harry.",
]


# =============================================================================
# ACTIVE SELLER (PropertyFinder listings - currently selling)
# 2 drafts only; each explicitly mentions "I have a client interested in buying their unit".
# Hook-first: lead with relevance so they read and reply.
# =============================================================================

ACTIVE_SELLER = [
    "Hi {name}, I have a client interested in buying your unit in {building} (Unit {unit}).\n\n"
    "They're serious and looking in that building. Would you be open to a quick call so I can share their interest?\n\n"
    "Thanks, Harry.",
    "Hi {name}, I saw your listing for Unit {unit} in {building}. I have a client interested in buying it.\n\n"
    "If you're still selling, I'd be happy to connect you — no obligation. Quick chat?\n\n"
    "Harry.",
]

# =============================================================================
# ACTIVE RENTER (PropertyFinder listings - currently listing for rent)
# 2 drafts only; each explicitly mentions "I have a client interested in renting their unit".
# =============================================================================

ACTIVE_RENTER = [
    "Hi {name}, I have a client interested in renting your unit in {building} (Unit {unit}).\n\n"
    "They're looking in that building right now. Would you be open to a quick call so I can share their details?\n\n"
    "Thanks, Harry.",
    "Hi {name}, I noticed your unit ({unit}) in {building} is listed for rent. I have a client interested in renting it.\n\n"
    "If you're still looking for a tenant, I'm happy to connect you. Quick chat?\n\n"
    "Harry.",
]


def randomize_message(text: str) -> str:
    """
    Apply micro-randomization so the same template rarely produces identical output.
    Swaps greeting, closing, and optionally trailing emoji / hope-phrase variants.
    """
    if not text or not isinstance(text, str):
        return text
    # Greeting swap at start (Hi / Hey / Hello / Morning - only if one of these starts the message)
    greeting_subs = [('Hi ', 'Hey '), ('Hi ', 'Hello '), ('Hi ', 'Morning '), ('Hey ', 'Hi '), ('Hey ', 'Morning '), ('Good morning ', 'Morning '), ('Good morning ', 'Hi ')]
    for a, b in greeting_subs:
        if text.strip().startswith(a):
            if random.random() < 0.35:
                text = text.replace(a, b, 1)
            break
    # Hope-phrase variant swap
    hope_variants = [
        ("hope you are well", "hope you're well"),
        ("hope you're well", "hope you are well"),
        ("hope you are well", "hope all is good"),
        ("hope you're well", "hope all is good"),
    ]
    for old, new in hope_variants:
        if old in text and random.random() < 0.4:
            text = text.replace(old, new, 1)
            break
    # Closing swap: replace trailing closing with another variant.
    # Try longest first so we strip "Many thanks,\n\nHarry." not just "Harry." (avoids double sign-off).
    closings = [
        "Many thanks,\n\nHarry.", "Many thanks,\nHarry.", "Many thanks, Harry.",
        "Thanks,\n\nHarry.", "Thanks,\nHarry.", "Thanks, Harry.",
        "Cheers,\n\nHarry.", "Cheers,\nHarry.", "Cheers, Harry.",
        "Best,\n\nHarry.", "Best,\nHarry.", "Best, Harry.",
        "Harry.",
    ]
    for c in closings:
        if text.rstrip().endswith(c):
            if random.random() < 0.4:
                single_closings = ["Harry.", "Many thanks, Harry.", "Thanks, Harry.", "Cheers, Harry.", "Best, Harry."]
                other = random.choice(single_closings)
                text = text.rstrip()[: -len(c)].rstrip() + "\n\n" + other
            break
    # Trailing emoji: 50% remove if present (single emoji at end)
    stripped = text.rstrip()
    if len(stripped) >= 1 and stripped[-1] in "\u2600-\u27bf\U0001f300-\U0001f9ff":
        if random.random() < 0.5:
            text = stripped[:-1].rstrip()
    return text


def generate_message(
    campaign_type: str,
    owner_name: str,
    building: str,
    unit: str,
    bedrooms: Optional[str] = None,
    is_portfolio: bool = False,
    unit_count: Optional[int] = None,
    buildings: Optional[str] = None,
    listing_price: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """
    Generate a personalized message for a lead.
    
    Returns dict with 'message' and 'template_type', or None if owner should be skipped.
    For portfolio_owner campaign, pass unit_count and buildings (comma-joined building names).
    When owner is a management company, first_name is empty and greeting becomes "Hi," not "Hi Company Name,".
    """
    first_name = format_first_name(owner_name) or ""
    is_corporate = not first_name and owner_name and isinstance(owner_name, str) and owner_name.strip()

    # Select template pool (custom overrides from JSON if present)
    if campaign_type == 'landlord_lease_expiry':
        template_type = 'landlord_lease_expiry'
        templates = _get_templates_for_type(template_type, LANDLORD_LEASE_EXPIRY)
    elif campaign_type == 'cold_owner':
        if is_portfolio:
            template_type = 'cold_owner_portfolio'
            templates = _get_templates_for_type(template_type, COLD_OWNER_PORTFOLIO)
        else:
            template_type = 'cold_owner_single'
            templates = _get_templates_for_type(template_type, COLD_OWNER_SINGLE)
    elif campaign_type == 'recent_sale':
        template_type = 'recent_sale'
        templates = _get_templates_for_type(template_type, RECENT_SALE_FOLLOW_UP)
    elif campaign_type == 'portfolio_owner':
        template_type = 'portfolio_owner'
        templates = _get_templates_for_type(template_type, PORTFOLIO_OWNER)
    elif campaign_type == 'active_seller':
        template_type = 'active_seller'
        templates = _get_templates_for_type(template_type, ACTIVE_SELLER)
    elif campaign_type == 'active_renter':
        template_type = 'active_renter'
        templates = _get_templates_for_type(template_type, ACTIVE_RENTER)
    else:
        raise ValueError(f"Unknown campaign_type: {campaign_type}")
    
    if not templates:
        raise ValueError(f"No templates for {template_type}")
    
    # Pick random template
    template = random.choice(templates)
    building_display = format_building_for_message(building or '')
    buildings_display = format_building_for_message(buildings or '') if buildings else (building_display or 'Palm Jumeirah')

    if campaign_type == 'portfolio_owner':
        message = template.format(
            name=first_name,
            unit_count=unit_count or 0,
            buildings=buildings_display or building_display or 'Palm Jumeirah'
        )
    elif campaign_type in ('active_seller', 'active_renter'):
        bedrooms_display = f"{bedrooms}-bed " if bedrooms is not None and str(bedrooms).strip() != '' else ''
        message = template.format(
            name=first_name,
            building=building_display,
            unit=unit,
            bedrooms=bedrooms or '',
            bedrooms_display=bedrooms_display
        )
    else:
        # Format message (bedrooms_display avoids "-bed" when bedrooms is None)
        bedrooms_display = f"{bedrooms}-bed" if bedrooms is not None and str(bedrooms).strip() != '' else ''
        message = template.format(
            name=first_name,
            building=building_display,
            unit=unit,
            bedrooms=bedrooms or '',
            bedrooms_display=bedrooms_display
        )
    # Corporate/management company: use "Hi" only (no name) so it doesn't look bot-written
    if is_corporate:
        message = (
            message.replace("Hi , ", "Hi ")
            .replace("Hi ,\n", "Hi,\n")
            .replace("Hi ,", "Hi,")
            .replace("Hi . ", "Hi. ")
            .replace("Good morning , ", "Good morning. ")
            .replace("Good morning . ", "Good morning. ")
            .replace("Good morning ,\n", "Good morning.\n")
            .replace("Good morning .\n", "Good morning.\n")
            .replace("Hey , ", "Hey ")
            .replace("Hey ,\n", "Hey,\n")
            .replace("Hey . ", "Hey. ")
            .replace("Morning , ", "Morning. ")
            .replace("Morning . ", "Morning. ")
            .replace("Morning ,\n", "Morning.\n")
            .replace("Morning .\n", "Morning.\n")
        )
    message = randomize_message(message)

    return {
        'message': message,
        'template_type': template_type
    }


def _get_templates_for_type(key: str, default_list: List[str]) -> List[str]:
    """Return active custom templates for key if present, else all custom, else default list."""
    custom = load_custom_templates()
    if custom:
        # Prefer _active subset (user-selected variants); fall back to full list
        active_key = f"{key}_active"
        if active_key in custom and custom[active_key]:
            return custom[active_key]
        if key in custom and custom[key]:
            return custom[key]
    return list(default_list)


def load_custom_templates() -> Optional[Dict[str, List[str]]]:
    """Load custom template overrides from JSON. Returns None if file missing or invalid."""
    if not CUSTOM_TEMPLATES_PATH.exists():
        return None
    try:
        with open(CUSTOM_TEMPLATES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        _all_keys = set(TEMPLATE_KEYS) | {f"{k}_active" for k in TEMPLATE_KEYS}
        return {k: v for k, v in data.items() if k in _all_keys and isinstance(v, list) and v} or None
    except Exception:
        return None


def save_custom_templates(data: Dict[str, List[str]]) -> bool:
    """Save all variant + active-subset data to JSON."""
    try:
        _all_keys = set(TEMPLATE_KEYS) | {f"{k}_active" for k in TEMPLATE_KEYS}
        out = {k: [t.strip() for t in v if isinstance(t, str) and t.strip()] for k, v in data.items() if k in _all_keys}
        with open(CUSTOM_TEMPLATES_PATH, 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def get_editable_templates() -> Dict[str, List[str]]:
    """Return all variants for editing (base keys only, no _active keys)."""
    custom = load_custom_templates() or {}
    defaults = {
        'landlord_lease_expiry': list(LANDLORD_LEASE_EXPIRY),
        'cold_owner_single': list(COLD_OWNER_SINGLE),
        'cold_owner_portfolio': list(COLD_OWNER_PORTFOLIO),
        'recent_sale': list(RECENT_SALE_FOLLOW_UP),
        'portfolio_owner': list(PORTFOLIO_OWNER),
        'active_seller': list(ACTIVE_SELLER),
        'active_renter': list(ACTIVE_RENTER),
    }
    # Merge: custom overrides defaults for base keys only
    result = dict(defaults)
    for k in TEMPLATE_KEYS:
        if k in custom:
            result[k] = custom[k]
    return result


def get_active_template_sets() -> Dict[str, List[str]]:
    """Return the _active subsets so the UI knows which variants are currently enabled."""
    custom = load_custom_templates() or {}
    return {k: custom[f"{k}_active"] for k in TEMPLATE_KEYS if f"{k}_active" in custom}
