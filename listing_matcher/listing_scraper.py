"""
listing_scraper.py — STUB for Phase 2

Phase 2: Automated Bayut / PropertyFinder scraper.
Will use Playwright with stealth mode to scrape Palm Jumeirah listings daily.

For now, listings are entered manually or via CSV upload in the Streamlit UI.

Future implementation plan:
- Scheduled daily scrape of Palm Jumeirah listings on Bayut + PF
- Extract per listing: building, beds, size, price, agent, permit number, URL
- Diff against previous day → new / price-changed / delisted events
- Auto-match new listings against lead database
- Push matched results to Telegram channel
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Listing:
    building_name: str
    bedrooms: Optional[str] = None
    size_sqft: Optional[float] = None
    price: Optional[float] = None
    listing_url: Optional[str] = None
    agent_name: Optional[str] = None
    permit_number: Optional[str] = None
    floor: Optional[int] = None
    unit_number: Optional[str] = None
    source: str = "manual"
    extra: dict = field(default_factory=dict)


def scrape_bayut_palm_jumeirah() -> list[Listing]:
    """TODO Phase 2 — scrape live Bayut listings for Palm Jumeirah."""
    raise NotImplementedError("Phase 2: use manual entry or CSV upload for now.")


def scrape_propertyfinder_palm_jumeirah() -> list[Listing]:
    """TODO Phase 2 — scrape live PropertyFinder listings for Palm Jumeirah."""
    raise NotImplementedError("Phase 2: use manual entry or CSV upload for now.")


def parse_listing_from_url(url: str) -> Optional[Listing]:
    """
    TODO Phase 2 — extract listing data from a Bayut or PF URL.
    Planned approach: headless Playwright, extract JSON-LD or structured data.
    """
    raise NotImplementedError("Phase 2: URL parsing not yet implemented.")
