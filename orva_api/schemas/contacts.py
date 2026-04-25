"""Pydantic models for the contacts feature.

Mirrors the SQLite schema in database.py (`contacts`, `contact_properties`,
`contact_lead_links`) and the helper functions in contact_manager.py.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------

CONTACT_TYPES = ("Owner", "Buyer", "Investor", "Broker", "Tenant", "Other")
INTENT_VALUES = ("selling", "renting", "buying", "renting_looking")


class ContactRecord(BaseModel):
    """A single contact row."""
    id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_type: Optional[str] = None
    source: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    agent_assigned: Optional[str] = None
    last_contact_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateContactRequest(BaseModel):
    """Payload for POST /api/contacts."""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_type: Optional[str] = None
    source: Optional[str] = None
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    agent_assigned: Optional[str] = None


class UpdateContactRequest(BaseModel):
    """Payload for PUT /api/contacts/{id}. All fields optional --
    None means 'don't change'."""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_type: Optional[str] = None
    source: Optional[str] = None
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    agent_assigned: Optional[str] = None


# ---------------------------------------------------------------------------
# Contact properties
# ---------------------------------------------------------------------------

class ContactProperty(BaseModel):
    id: int
    contact_id: int
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    price_aed: Optional[float] = None
    intent: Optional[str] = None
    view_type: Optional[str] = None
    notes: Optional[str] = None
    lead_id: Optional[int] = None
    is_scraped_listing: bool = False
    scraped_listing_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AddPropertyRequest(BaseModel):
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    price_aed: Optional[float] = Field(None, ge=0)
    intent: Optional[str] = None
    view_type: Optional[str] = None
    notes: Optional[str] = None
    lead_id: Optional[int] = None


class UpdatePropertyRequest(BaseModel):
    """All fields optional -- None means 'don't change'."""
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    price_aed: Optional[float] = Field(None, ge=0)
    intent: Optional[str] = None
    view_type: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Linked leads (portfolio from the lead database, matched by phone/name)
# ---------------------------------------------------------------------------

class LinkedLead(BaseModel):
    """A lead row linked to a contact via contact_lead_links."""
    link_id: int
    lead_id: int
    match_confidence: Optional[float] = None
    match_method: Optional[str] = None
    # Embedded lead row (None if the lead has been deleted)
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[str] = None
    phone: Optional[str] = None


# ---------------------------------------------------------------------------
# Full contact detail (used by GET /api/contacts/{id})
# ---------------------------------------------------------------------------

class ContactDetail(ContactRecord):
    properties: list[ContactProperty] = Field(default_factory=list)
    linked_leads: list[LinkedLead] = Field(default_factory=list)


class ContactListResponse(BaseModel):
    """Paginated list of contacts."""
    contacts: list[ContactRecord]
    total: int


class ResolveUnitSpecsResponse(BaseModel):
    """Response from POST /api/contacts/{id}/resolve-unit-specs."""
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    view_type: Optional[str] = None
