"""Contacts API router."""

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ..auth import get_current_user

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


def _import_cm():
    import contact_manager as cm
    return cm


@router.get("")
def list_contacts(
    q: str = Query(""),
    contact_type: str = Query(""),
    limit: int = Query(200, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    cm = _import_cm()
    results = cm.search_contacts(
        query=q or None,
        contact_type=contact_type or None,
        limit=limit,
    )
    total = cm.get_contact_count()
    return {"contacts": results, "total": total}


@router.get("/{contact_id}")
def get_contact(
    contact_id: int,
    user: dict = Depends(get_current_user),
):
    cm = _import_cm()
    contact = cm.get_contact(contact_id, include_properties=True, include_linked_leads=True)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.post("")
def create_contact(
    body: dict,
    user: dict = Depends(get_current_user),
):
    cm = _import_cm()
    contact_id, err = cm.create_contact(
        full_name=body.get("full_name"),
        phone=body.get("phone"),
        email=body.get("email"),
        contact_type=body.get("contact_type"),
        source=body.get("source"),
        budget_min=body.get("budget_min"),
        budget_max=body.get("budget_max"),
        agent_assigned=body.get("agent_assigned"),
        properties=body.get("properties"),
    )
    if err:
        raise HTTPException(status_code=409, detail=err)
    return {"contact_id": contact_id}


@router.put("/{contact_id}")
def update_contact(
    contact_id: int,
    body: dict,
    user: dict = Depends(get_current_user),
):
    cm = _import_cm()
    ok = cm.update_contact(contact_id, **{k: v for k, v in body.items()})
    if not ok:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True}


@router.delete("/{contact_id}")
def delete_contact(
    contact_id: int,
    user: dict = Depends(get_current_user),
):
    cm = _import_cm()
    ok = cm.delete_contact(contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True}


@router.post("/{contact_id}/properties")
def add_property(
    contact_id: int,
    body: dict,
    user: dict = Depends(get_current_user),
):
    cm = _import_cm()
    prop_id = cm.add_property_to_contact(
        contact_id,
        building_name=body.get("building_name"),
        unit_number=body.get("unit_number"),
        bedrooms=body.get("bedrooms"),
        bathrooms=body.get("bathrooms"),
        price_aed=body.get("price_aed"),
        intent=body.get("intent"),
        view_type=body.get("view_type"),
        notes=body.get("notes"),
    )
    if not prop_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"property_id": prop_id}


@router.delete("/{contact_id}/properties/{property_id}")
def remove_property(
    contact_id: int,
    property_id: int,
    user: dict = Depends(get_current_user),
):
    cm = _import_cm()
    ok = cm.remove_property_from_contact(property_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Property not found")
    return {"ok": True}
