"""Pydantic models for the listings router (lease-expiry, matcher, bayut, client-match)."""

from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Lease expiry
# ---------------------------------------------------------------------------

class ExpiringLease(BaseModel):
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[str] = None
    size_sqft: Optional[float] = None
    contract_end: Optional[str] = None
    days_remaining: Optional[int] = None
    annual_rent: Optional[float] = None
    has_owner_contact: bool = False
    owner_name: Optional[str] = None
    owner_phone: Optional[str] = None
    owner_email: Optional[str] = None


class LeaseExpiryResponse(BaseModel):
    leases: list[ExpiringLease]
    total: int
    with_contact: int
    active_rentals_total: int
    unique_buildings: int
    expiry_window_days: int


# ---------------------------------------------------------------------------
# Listing matcher
# ---------------------------------------------------------------------------

class MatchListingRequest(BaseModel):
    building_name: str
    unit_number: Optional[str] = None
    size_sqft: Optional[float] = Field(None, gt=0)
    bedrooms: Optional[str] = None


class MatchedOwner(BaseModel):
    building: str
    unit: str
    size_sqft: Optional[float] = None
    beds: Optional[str] = None
    owner_name: str
    phone: str
    phone_display: str
    email: Optional[str] = None
    transaction_date: Optional[str] = None
    transaction_value: Optional[float] = None
    confidence: float
    match_type: str


class MatchListingResponse(BaseModel):
    matches: list[MatchedOwner]
    coverage: dict


# ---------------------------------------------------------------------------
# Bayut listings
# ---------------------------------------------------------------------------

class BayutListing(BaseModel):
    listing_url: Optional[str] = None
    listing_type: Optional[str] = None        # 'sale' | 'rent'
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    size_sqft: Optional[float] = None
    price_aed: Optional[float] = None
    rent_period: Optional[str] = None
    view_type: Optional[str] = None
    agent_name: Optional[str] = None
    agency: Optional[str] = None
    listed_date: Optional[str] = None
    scraped_at: Optional[str] = None


class BuildingSummary(BaseModel):
    building_name: str
    listings: int
    avg_beds: Optional[float] = None
    avg_size: Optional[float] = None
    avg_price: Optional[float] = None
    types: str


class BayutListingsResponse(BaseModel):
    listings: list[BayutListing]
    total: int
    sale_count: int
    rent_count: int
    unique_buildings: int
    building_summary: list[BuildingSummary]
    last_scraped: Optional[str] = None


# ---------------------------------------------------------------------------
# Client match (find owners for a buyer/tenant client)
# ---------------------------------------------------------------------------

class ClientMatchRequest(BaseModel):
    transaction_type: str = Field(..., description="'sale' or 'rent'")
    bedrooms: Optional[str] = None  # 'Studio', '1', '2', '3', '4', '5+', or None for any
    buildings: list[str] = Field(default_factory=list)  # empty = all buildings
    sea_view_only: bool = False
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    limit: int = Field(100, ge=1, le=500)


class OwnerMatchResult(BaseModel):
    """A ranked owner match for a client's requirements."""
    client_id: str
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[str] = None
    size_sqft: Optional[float] = None
    last_sale_price: Optional[float] = None
    last_sale_date: Optional[str] = None
    last_annual_rent: Optional[float] = None
    has_active_listing: bool = False
    active_listing_url: Optional[str] = None
    active_listing_price: Optional[float] = None
    score: float
    score_factors: list[str] = Field(default_factory=list)


class ClientMatchResponse(BaseModel):
    matches: list[OwnerMatchResult]
    total: int
