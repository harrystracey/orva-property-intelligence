"""Contacts API -- CRUD for contacts, contact_properties, and linked leads.

Wraps contact_manager.py (the Python module that owns the SQLite tables)
behind a typed REST surface for orva-web.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import _sys_paths  # noqa: F401 -- puts project root on sys.path

import contact_manager as cm  # noqa: E402

from ..auth import get_current_user
from ..tenant_context import current_tenant_id
from ..schemas.contacts import (
    ContactRecord, ContactDetail, ContactListResponse,
    CreateContactRequest, UpdateContactRequest,
    ContactProperty, AddPropertyRequest, UpdatePropertyRequest,
    LinkedLead, ResolveUnitSpecsResponse,
    CONTACT_TYPES, INTENT_VALUES,
)


router = APIRouter(prefix="/api/contacts", tags=["contacts"])


# ---------------------------------------------------------------------------
# Helpers -- shape SQLite rows into API response objects
# ---------------------------------------------------------------------------

def _row_to_contact(row: dict) -> ContactRecord:
    """contacts table row -> ContactRecord."""
    return ContactRecord(
        id=int(row["id"]),
        full_name=row.get("full_name"),
        phone=row.get("phone"),
        email=row.get("email"),
        contact_type=row.get("contact_type"),
        source=row.get("source"),
        budget_min=row.get("budget_min"),
        budget_max=row.get("budget_max"),
        agent_assigned=row.get("agent_assigned"),
        last_contact_date=str(row["last_contact_date"]) if row.get("last_contact_date") else None,
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


def _row_to_property(row: dict) -> ContactProperty:
    return ContactProperty(
        id=int(row["id"]),
        contact_id=int(row["contact_id"]),
        building_name=row.get("building_name"),
        unit_number=row.get("unit_number"),
        bedrooms=row.get("bedrooms"),
        bathrooms=row.get("bathrooms"),
        price_aed=row.get("price_aed"),
        intent=row.get("intent"),
        view_type=row.get("view_type"),
        notes=row.get("notes"),
        lead_id=row.get("lead_id"),
        is_scraped_listing=bool(row.get("is_scraped_listing")),
        scraped_listing_url=row.get("scraped_listing_url"),
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


def _link_to_linked_lead(link: dict) -> LinkedLead:
    """contact_lead_links row + embedded `lead` dict -> LinkedLead."""
    lead = link.get("lead") or {}
    return LinkedLead(
        link_id=int(link["id"]),
        lead_id=int(link["lead_id"]),
        match_confidence=link.get("match_confidence"),
        match_method=link.get("match_method"),
        building_name=lead.get("building_name"),
        unit_number=lead.get("unit_number"),
        bedrooms=lead.get("bedrooms"),
        phone=lead.get("phone"),
    )


def _validate_contact_type(ct: Optional[str]) -> Optional[str]:
    """Coerce empty string to None; reject unknown values with 422."""
    if ct is None:
        return None
    ct = ct.strip()
    if not ct:
        return None
    if ct not in CONTACT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"contact_type must be one of: {', '.join(CONTACT_TYPES)}",
        )
    return ct


def _validate_intent(intent: Optional[str]) -> Optional[str]:
    if intent is None:
        return None
    intent = intent.strip()
    if not intent:
        return None
    if intent not in INTENT_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"intent must be one of: {', '.join(INTENT_VALUES)}",
        )
    return intent


# ---------------------------------------------------------------------------
# Collection endpoints (GET / POST on /api/contacts)
# ---------------------------------------------------------------------------

@router.get("", response_model=ContactListResponse)
def list_contacts(
    query: Optional[str] = Query(None, description="Substring search on name/phone/email"),
    contact_type: Optional[str] = None,
    agent_assigned: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    user: dict = Depends(get_current_user),
) -> ContactListResponse:
    """Search contacts. Scoped to the caller's tenant."""
    tid = current_tenant_id(user)
    rows = cm.search_contacts(
        query=query,
        contact_type=contact_type,
        agent_assigned=agent_assigned,
        limit=limit,
        tenant_id=tid,
    )
    total = cm.get_contact_count(tenant_id=tid)
    return ContactListResponse(
        contacts=[_row_to_contact(r) for r in rows],
        total=total,
    )


@router.post("", response_model=ContactRecord, status_code=201)
def create_contact(
    req: CreateContactRequest,
    user: dict = Depends(get_current_user),
) -> ContactRecord:
    """Create a new contact under the caller's tenant. Auto-links to leads."""
    tid = current_tenant_id(user)
    contact_id, error = cm.create_contact(
        full_name=req.full_name,
        phone=req.phone,
        email=req.email,
        contact_type=_validate_contact_type(req.contact_type),
        source=req.source,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
        agent_assigned=req.agent_assigned,
        tenant_id=tid,
    )
    if error or not contact_id:
        raise HTTPException(status_code=409, detail=error or "Failed to create contact")
    contact = cm.get_contact(
        contact_id, include_properties=False, include_linked_leads=False, tenant_id=tid,
    )
    if not contact:
        raise HTTPException(status_code=500, detail="Created contact but could not load it back")
    return _row_to_contact(contact)


# ---------------------------------------------------------------------------
# Single-contact endpoints
# ---------------------------------------------------------------------------

@router.get("/{contact_id}", response_model=ContactDetail)
def get_contact(
    contact_id: int,
    user: dict = Depends(get_current_user),
) -> ContactDetail:
    """Full contact view: row + properties + linked leads. Tenant-scoped."""
    tid = current_tenant_id(user)
    contact = cm.get_contact(
        contact_id, include_properties=True, include_linked_leads=True, tenant_id=tid,
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    base = _row_to_contact(contact).model_dump()
    return ContactDetail(
        **base,
        properties=[_row_to_property(p) for p in contact.get("properties", [])],
        linked_leads=[_link_to_linked_lead(l) for l in contact.get("linked_leads", [])],
    )


@router.put("/{contact_id}", response_model=ContactRecord)
def update_contact(
    contact_id: int,
    req: UpdateContactRequest,
    user: dict = Depends(get_current_user),
) -> ContactRecord:
    """Partial update; only fields explicitly provided are changed."""
    tid = current_tenant_id(user)
    if not cm.get_contact(
        contact_id, include_properties=False, include_linked_leads=False, tenant_id=tid,
    ):
        raise HTTPException(status_code=404, detail="Contact not found")

    cm.update_contact(
        contact_id,
        full_name=req.full_name,
        phone=req.phone,
        email=req.email,
        contact_type=_validate_contact_type(req.contact_type),
        source=req.source,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
        agent_assigned=req.agent_assigned,
        tenant_id=tid,
    )
    updated = cm.get_contact(
        contact_id, include_properties=False, include_linked_leads=False, tenant_id=tid,
    )
    return _row_to_contact(updated)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(
    contact_id: int,
    user: dict = Depends(get_current_user),
):
    """Hard delete: removes the contact + properties + lead-links."""
    tid = current_tenant_id(user)
    if not cm.get_contact(
        contact_id, include_properties=False, include_linked_leads=False, tenant_id=tid,
    ):
        raise HTTPException(status_code=404, detail="Contact not found")
    cm.delete_contact(contact_id, tenant_id=tid)
    return None


# ---------------------------------------------------------------------------
# Contact properties (sub-resource)
# ---------------------------------------------------------------------------

@router.post("/{contact_id}/properties", response_model=ContactProperty, status_code=201)
def add_property(
    contact_id: int,
    req: AddPropertyRequest,
    user: dict = Depends(get_current_user),
) -> ContactProperty:
    """Add a property to a contact. Auto-merges scraped listings if matched."""
    tid = current_tenant_id(user)
    if not cm.get_contact(
        contact_id, include_properties=False, include_linked_leads=False, tenant_id=tid,
    ):
        raise HTTPException(status_code=404, detail="Contact not found")

    prop_id = cm.add_property_to_contact(
        contact_id,
        building_name=req.building_name,
        unit_number=req.unit_number,
        bedrooms=req.bedrooms,
        bathrooms=req.bathrooms,
        price_aed=req.price_aed,
        intent=_validate_intent(req.intent),
        view_type=req.view_type,
        notes=req.notes,
        lead_id=req.lead_id,
        tenant_id=tid,
    )
    if not prop_id:
        raise HTTPException(status_code=500, detail="Failed to add property")

    rows = cm.get_contact_properties(contact_id, tenant_id=tid)
    new_row = next((r for r in rows if r["id"] == prop_id), None)
    if not new_row:
        raise HTTPException(status_code=500, detail="Created property but could not reload it")
    return _row_to_property(new_row)


@router.put("/{contact_id}/properties/{property_id}", response_model=ContactProperty)
def update_property(
    contact_id: int,
    property_id: int,
    req: UpdatePropertyRequest,
    user: dict = Depends(get_current_user),
) -> ContactProperty:
    """Partial update of a contact property."""
    tid = current_tenant_id(user)
    rows = cm.get_contact_properties(contact_id, tenant_id=tid)
    target = next((r for r in rows if r["id"] == property_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Property not found on this contact")

    cm.update_contact_property(
        property_id,
        building_name=req.building_name,
        unit_number=req.unit_number,
        bedrooms=req.bedrooms,
        bathrooms=req.bathrooms,
        price_aed=req.price_aed,
        intent=_validate_intent(req.intent),
        view_type=req.view_type,
        notes=req.notes,
        tenant_id=tid,
    )
    rows = cm.get_contact_properties(contact_id, tenant_id=tid)
    updated = next((r for r in rows if r["id"] == property_id), None)
    return _row_to_property(updated)


@router.delete("/{contact_id}/properties/{property_id}", status_code=204)
def delete_property(
    contact_id: int,
    property_id: int,
    user: dict = Depends(get_current_user),
):
    tid = current_tenant_id(user)
    rows = cm.get_contact_properties(contact_id, tenant_id=tid)
    if not any(r["id"] == property_id for r in rows):
        raise HTTPException(status_code=404, detail="Property not found on this contact")
    cm.remove_property_from_contact(property_id, tenant_id=tid)
    return None


# ---------------------------------------------------------------------------
# Helpers used by the UI
# ---------------------------------------------------------------------------

@router.get("/{contact_id}/resolve-unit-specs", response_model=ResolveUnitSpecsResponse)
def resolve_unit_specs(
    contact_id: int,
    building_name: str = Query(...),
    unit_number: str = Query(...),
    user: dict = Depends(get_current_user),
) -> ResolveUnitSpecsResponse:
    """
    Look up bedrooms/bathrooms/view from the unit registry + building schema
    so the UI can pre-fill 'Add property' forms.
    """
    tid = current_tenant_id(user)
    if not cm.get_contact(
        contact_id, include_properties=False, include_linked_leads=False, tenant_id=tid,
    ):
        raise HTTPException(status_code=404, detail="Contact not found")
    specs = cm.resolve_unit_specs(building_name, unit_number)
    return ResolveUnitSpecsResponse(**specs)
