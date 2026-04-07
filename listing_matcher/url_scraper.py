"""
URL scraper for Bayut and PropertyFinder listing pages.
Paste a listing URL → extract building, bedrooms, size, price, etc.

Bayut: Uses WhatsApp user-agent to get server-rendered meta tags (no JS needed).
PF: Uses httpx with standard headers (server-rendered).
"""

import re
from typing import Optional

import httpx

_WHATSAPP_UA = "WhatsApp/2.23.20.0"
_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_VIEW_PATTERNS = [
    (r"full sea view", "Full Sea View"),
    (r"sea view", "Sea View"),
    (r"marina view", "Marina View"),
    (r"garden view", "Garden View"),
    (r"palm view", "Palm View"),
    (r"burj view", "Burj View"),
    (r"atlantis view", "Atlantis View"),
    (r"beach view", "Beach View"),
    (r"canal view", "Canal View"),
    (r"park view", "Park View"),
    (r"pool view", "Pool View"),
    (r"city view", "City View"),
    (r"community view", "Community View"),
    (r"lagoon view", "Lagoon View"),
]


def _extract_meta(html: str) -> dict[str, str]:
    """Extract all meta tags from HTML."""
    metas = {}
    for m in re.finditer(r'<meta\s+(?:property|name)="([^"]+)"\s+content="([^"]+)"', html):
        metas[m.group(1)] = m.group(2)
    return metas


def _detect_view(text: str) -> Optional[str]:
    """Detect view type from text."""
    lower = text.lower()
    for pattern, label in _VIEW_PATTERNS:
        if re.search(pattern, lower):
            return label
    return None


def _parse_bayut_description(desc: str) -> dict:
    """
    Parse Bayut meta description format:
    "1-bed, 2-bath, 640 sqft apartment for rent at Seven Palm, Palm Jumeirah for AED 150,000 yearly"
    """
    result = {
        "bedrooms": None,
        "bathrooms": None,
        "size_sqft": None,
        "listing_type": None,
        "building": None,
        "area": None,
        "price": None,
    }

    # Bedrooms: "1-bed" or "Studio"
    bed_match = re.search(r"(\d+)-bed", desc, re.I)
    if bed_match:
        result["bedrooms"] = int(bed_match.group(1))
    elif "studio" in desc.lower():
        result["bedrooms"] = 0

    # Bathrooms: "2-bath"
    bath_match = re.search(r"(\d+)-bath", desc, re.I)
    if bath_match:
        result["bathrooms"] = int(bath_match.group(1))

    # Size: "640 sqft"
    size_match = re.search(r"([\d,]+)\s*sqft", desc, re.I)
    if size_match:
        result["size_sqft"] = float(size_match.group(1).replace(",", ""))

    # Type: "for rent" or "for sale"
    if "for rent" in desc.lower():
        result["listing_type"] = "rent"
    elif "for sale" in desc.lower():
        result["listing_type"] = "sale"

    # Building + area: "at Seven Palm, Palm Jumeirah"
    loc_match = re.search(r"at\s+(.+?)(?:,\s*(.+?))?\s+for\s+AED", desc, re.I)
    if loc_match:
        result["building"] = loc_match.group(1).strip()
        result["area"] = loc_match.group(2).strip() if loc_match.group(2) else None

    # Price: "AED 150,000"
    price_match = re.search(r"AED\s*([\d,]+)", desc)
    if price_match:
        result["price"] = int(price_match.group(1).replace(",", ""))

    return result


def scrape_bayut(url: str, timeout: int = 10) -> dict:
    """Scrape a Bayut listing URL using WhatsApp user-agent (fast, no browser)."""
    result = {
        "portal": "bayut",
        "building": None,
        "bedrooms": None,
        "bathrooms": None,
        "size_sqft": None,
        "price": None,
        "listing_type": None,
        "furnished": None,
        "view": None,
        "image_url": None,
        "url": url,
    }

    r = httpx.get(url, headers={"User-Agent": _WHATSAPP_UA}, follow_redirects=True, timeout=timeout)
    if r.status_code != 200:
        return {**result, "error": f"HTTP {r.status_code}"}

    metas = _extract_meta(r.text)
    desc = metas.get("description", "") or metas.get("og:description", "")
    title = metas.get("og:title", "") or re.search(r"<title>([^<]+)</title>", r.text, re.I)

    if isinstance(title, re.Match):
        title = title.group(1)
    title = title or ""

    if not desc:
        return {**result, "error": "No description found — listing may have been removed"}

    # Parse structured data from description
    parsed = _parse_bayut_description(desc)
    result.update({k: v for k, v in parsed.items() if v is not None})

    # View from title
    result["view"] = _detect_view(title + " " + desc)

    # Furnished from title
    combined = (title + " " + desc).lower()
    if "furnished" in combined and "unfurnished" not in combined:
        result["furnished"] = True
    elif "unfurnished" in combined:
        result["furnished"] = False

    # Image
    result["image_url"] = metas.get("og:image")

    return result


def scrape_propertyfinder(url: str, timeout: int = 10) -> dict:
    """Scrape a PropertyFinder listing URL."""
    result = {
        "portal": "propertyfinder",
        "building": None,
        "bedrooms": None,
        "bathrooms": None,
        "size_sqft": None,
        "price": None,
        "listing_type": None,
        "furnished": None,
        "view": None,
        "permit_number": None,
        "url": url,
    }

    # Detect type from URL
    if "/for-rent/" in url or "/to-rent/" in url:
        result["listing_type"] = "rent"
    elif "/for-sale/" in url or "/to-buy/" in url:
        result["listing_type"] = "sale"

    r = httpx.get(url, headers={"User-Agent": _BROWSER_UA}, follow_redirects=True, timeout=timeout)
    if r.status_code != 200:
        return {**result, "error": f"HTTP {r.status_code}"}

    text = r.text
    metas = _extract_meta(text)
    desc = metas.get("description", "") or metas.get("og:description", "")

    # PF description format: "X Bedroom Apartment for Rent in Building, Area - AED X"
    bed_match = re.search(r"(\d+)\s*(?:Bed|BR|Bedroom)", desc, re.I)
    if bed_match:
        result["bedrooms"] = int(bed_match.group(1))
    elif "studio" in desc.lower():
        result["bedrooms"] = 0

    size_match = re.search(r"([\d,]+)\s*(?:sq\.?\s*ft|sqft)", desc + " " + text[:5000], re.I)
    if size_match:
        result["size_sqft"] = float(size_match.group(1).replace(",", ""))

    price_match = re.search(r"AED\s*([\d,]+)", desc)
    if price_match:
        result["price"] = int(price_match.group(1).replace(",", ""))

    # Building from OG title or breadcrumbs
    og_title = metas.get("og:title", "")
    # PF titles: "X Bed Apartment for Rent in Building Name, Area"
    bld_match = re.search(r"(?:in|at)\s+(.+?)(?:,|\s*-\s*AED|\s*\|)", og_title, re.I)
    if bld_match:
        result["building"] = bld_match.group(1).strip()

    # Permit number
    permit_match = re.search(r"(?:Permit|RERA|Trakheesi)[^\d]*(\d{5,})", text, re.I)
    if permit_match:
        result["permit_number"] = permit_match.group(1)

    result["view"] = _detect_view(desc + " " + og_title)

    combined = (desc + " " + og_title).lower()
    if "furnished" in combined and "unfurnished" not in combined:
        result["furnished"] = True
    elif "unfurnished" in combined:
        result["furnished"] = False

    result["image_url"] = metas.get("og:image")

    return result


def scrape_listing_url(url: str, timeout: int = 10) -> dict:
    """
    Scrape a Bayut or PropertyFinder listing URL.
    Returns dict with: portal, building, bedrooms, size_sqft, price, listing_type, etc.
    """
    url = url.strip()

    if "bayut.com" in url:
        return scrape_bayut(url, timeout)
    elif "propertyfinder" in url:
        return scrape_propertyfinder(url, timeout)
    else:
        return {"error": "Unsupported portal. Only Bayut and PropertyFinder URLs are supported."}


# Make it importable as async too (for FastAPI)
async def scrape_listing_url_async(url: str, timeout: int = 10) -> dict:
    """Async wrapper — the actual scraping is sync (httpx) but runs fast."""
    return scrape_listing_url(url, timeout)
