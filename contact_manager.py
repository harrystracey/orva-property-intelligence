"""
Contact Manager Module - Contacts, Properties, Lead Linking
Palm Jumeirah Real Estate Intelligence System

Handles:
- CRUD for contacts and contact_properties
- Auto-linking contacts to leads (by phone / name)
- PropertyFinder scraped listing merge (selling/renting intent)
- client_id format for notes/reminders/calls: CONTACT:{contact_id}
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
except ImportError:
    pd = None

from database import get_connection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTACT_CLIENT_ID_PREFIX = "CONTACT:"
INTENT_VALUES = ("selling", "renting", "buying", "renting_looking")
PF_LEADS_CSV = Path(__file__).resolve().parent / "scraped_data" / "propertyfinder_scraped_leads.csv"

# Default tenant for legacy callers that don't pass `tenant_id`. Mirrors
# the DEFAULT value on the `tenant_id` column added in Phase 6 -- so a
# single-tenant deployment keeps behaving exactly as before.
DEFAULT_TENANT_ID = "orva"


def resolve_unit_specs(building_name: Optional[str], unit_number: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Resolve BR, Bath, and View from building + unit number.
    Uses: unit registry (best), then building unit schema, then building default bedrooms.
    Bathrooms derived from bedrooms when not in registry.
    Returns: {'bedrooms': str|None, 'bathrooms': str|None, 'view_type': str|None}.
    """
    out = {"bedrooms": None, "bathrooms": None, "view_type": None}
    if not (building_name and str(building_name).strip()) or not (unit_number and str(unit_number).strip()):
        return out
    building = str(building_name).strip()
    unit = str(unit_number).strip()
    try:
        from unit_registry import get_unit_info as get_registry_unit_info
        info = get_registry_unit_info(building, unit)
        if info:
            if info.get("bedrooms") is not None:
                out["bedrooms"] = str(int(info["bedrooms"])) if info["bedrooms"] != "" else None
            if info.get("view") is not None and str(info.get("view")).strip():
                out["view_type"] = str(info["view"]).strip()
    except Exception:
        pass
    if out["bedrooms"] is None:
        try:
            from data_processor import infer_bedrooms_from_unit_schema, get_building_default_bedrooms
            res = infer_bedrooms_from_unit_schema(building, unit)
            if res and res.get("bedrooms") is not None:
                out["bedrooms"] = str(int(res["bedrooms"]))
            if out["bedrooms"] is None:
                def_res = get_building_default_bedrooms(building)
                if def_res and def_res.get("bedrooms") is not None:
                    out["bedrooms"] = str(int(def_res["bedrooms"]))
        except Exception:
            pass
    # Derive bathrooms from bedrooms (1:1 typical; 3+ BR often have 2+ baths)
    if out["bedrooms"] is not None:
        try:
            br = int(out["bedrooms"])
            out["bathrooms"] = str(max(1, br)) if br <= 2 else str(max(2, br - 1))
        except (ValueError, TypeError):
            out["bathrooms"] = out["bedrooms"]
    return out


def contact_client_id(contact_id: int) -> str:
    """Return client_id string for notes/reminders/call log (contact-scoped)."""
    return f"{CONTACT_CLIENT_ID_PREFIX}{contact_id}"


def is_contact_client_id(client_id: str) -> bool:
    """Return True if client_id refers to a contact."""
    return isinstance(client_id, str) and client_id.startswith(CONTACT_CLIENT_ID_PREFIX)


def contact_id_from_client_id(client_id: str) -> Optional[int]:
    """Extract contact_id from CONTACT:123 client_id, else None."""
    if not is_contact_client_id(client_id):
        return None
    try:
        return int(client_id[len(CONTACT_CLIENT_ID_PREFIX):])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Contact CRUD
# ---------------------------------------------------------------------------

def create_contact(
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    contact_type: Optional[str] = None,
    source: Optional[str] = None,
    budget_min: Optional[float] = None,
    budget_max: Optional[float] = None,
    agent_assigned: Optional[str] = None,
    properties: Optional[List[Dict[str, Any]]] = None,
    leads_df: Optional[Any] = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Create a contact under `tenant_id`. Optionally link to leads by phone.
    properties: list of dicts with keys building_name, unit_number, bedrooms,
                bathrooms, price_aed, intent, view_type, notes (all optional).
    Returns (contact_id, error_message). error_message is set on duplicate
    (phone+full_name).

    NOTE on multi-tenant: the `contacts.UNIQUE(phone, full_name)` constraint
    is global (not per-tenant). Two tenants storing the same phone+name will
    collide. Recreating the table with UNIQUE(tenant_id, phone, full_name)
    is a follow-up migration; it doesn't matter while ORVA is single-tenant.
    """
    conn = get_connection()
    try:
        full_name = (full_name or "").strip() or None
        phone = (phone or "").strip() or None
        email = (email or "").strip() or None
        name_for_unique = full_name or None
        phone_for_unique = phone or None

        cur = conn.execute(
            """INSERT INTO contacts (
                full_name, phone, email, contact_type, source,
                budget_min, budget_max, agent_assigned, last_contact_date,
                tenant_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name_for_unique,
                phone_for_unique,
                email,
                contact_type,
                source,
                budget_min,
                budget_max,
                agent_assigned,
                None,
                tenant_id,
            ),
        )
        contact_id = cur.lastrowid
        conn.commit()
    except Exception as e:
        err = str(e).lower()
        if "unique" in err or "constraint" in err:
            return (None, "A contact with this phone and name already exists.")
        raise
    finally:
        conn.close()

    # Add initial properties (use separate connections)
    if properties:
        for prop in properties:
            add_property_to_contact(
                contact_id,
                building_name=prop.get("building_name"),
                unit_number=prop.get("unit_number"),
                bedrooms=prop.get("bedrooms"),
                bathrooms=prop.get("bathrooms"),
                price_aed=prop.get("price_aed"),
                intent=prop.get("intent"),
                view_type=prop.get("view_type"),
                notes=prop.get("notes"),
                lead_id=prop.get("lead_id"),
                tenant_id=tenant_id,
            )

    # Auto-link to leads by phone (and optionally merge portfolio from leads_df or DB)
    link_contact_to_leads(contact_id, leads_df=leads_df, tenant_id=tenant_id)

    return (contact_id, None)


def get_contact(
    contact_id: int,
    include_properties: bool = True,
    include_linked_leads: bool = True,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> Optional[Dict[str, Any]]:
    """Fetch contact by ID, scoped to `tenant_id`. Optionally include
    properties and linked leads."""
    conn = get_connection(readonly=True)
    try:
        row = conn.execute(
            "SELECT * FROM contacts WHERE id = ? AND tenant_id = ?",
            (contact_id, tenant_id),
        ).fetchone()
        if not row:
            return None
        contact = dict(row)
        if include_properties:
            contact["properties"] = get_contact_properties(contact_id, tenant_id=tenant_id)
        if include_linked_leads:
            contact["linked_leads"] = get_linked_leads(contact_id, tenant_id=tenant_id)
        return contact
    finally:
        conn.close()


def get_contact_properties(
    contact_id: int,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> List[Dict[str, Any]]:
    """Return all contact_properties for a contact, scoped to tenant."""
    conn = get_connection(readonly=True)
    try:
        rows = conn.execute(
            """SELECT cp.* FROM contact_properties cp
               JOIN contacts c ON c.id = cp.contact_id
               WHERE cp.contact_id = ? AND c.tenant_id = ?
               ORDER BY cp.id""",
            (contact_id, tenant_id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_linked_leads(
    contact_id: int,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> List[Dict[str, Any]]:
    """Return linked lead records (id, lead_id, match_confidence, match_method).
    Scoped to tenant via the contacts table -- a contact owned by another
    tenant can't have its links exposed."""
    conn = get_connection(readonly=True)
    try:
        # Verify the contact belongs to this tenant first
        owner_row = conn.execute(
            "SELECT 1 FROM contacts WHERE id = ? AND tenant_id = ?",
            (contact_id, tenant_id),
        ).fetchone()
        if not owner_row:
            return []
        links = conn.execute(
            "SELECT id, lead_id, match_confidence, match_method FROM contact_lead_links WHERE contact_id = ?",
            (contact_id,),
        ).fetchall()
        result = []
        for link in links:
            d = dict(link)
            lead_row = conn.execute("SELECT * FROM leads WHERE id = ?", (d["lead_id"],)).fetchone()
            d["lead"] = dict(lead_row) if lead_row else None
            result.append(d)
        return result
    finally:
        conn.close()


def update_contact(
    contact_id: int,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    contact_type: Optional[str] = None,
    source: Optional[str] = None,
    budget_min: Optional[float] = None,
    budget_max: Optional[float] = None,
    agent_assigned: Optional[str] = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> bool:
    """Update contact fields, scoped to tenant. Pass None to leave unchanged.
    Returns False if no contact with that id exists in this tenant."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM contacts WHERE id = ? AND tenant_id = ?",
            (contact_id, tenant_id),
        ).fetchone()
        if not row:
            return False
        updates = []
        values: list = []
        if full_name is not None:
            updates.append("full_name = ?")
            values.append((full_name or "").strip() or None)
        if phone is not None:
            updates.append("phone = ?")
            values.append((phone or "").strip() or None)
        if email is not None:
            updates.append("email = ?")
            values.append((email or "").strip() or None)
        if contact_type is not None:
            updates.append("contact_type = ?")
            values.append((contact_type or "").strip() or None)
        if source is not None:
            updates.append("source = ?")
            values.append((source or "").strip() or None)
        if budget_min is not None:
            updates.append("budget_min = ?")
            values.append(budget_min)
        if budget_max is not None:
            updates.append("budget_max = ?")
            values.append(budget_max)
        if agent_assigned is not None:
            updates.append("agent_assigned = ?")
            values.append((agent_assigned or "").strip() or None)
        if not updates:
            return True
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.extend([contact_id, tenant_id])
        conn.execute(
            f"UPDATE contacts SET {', '.join(updates)} WHERE id = ? AND tenant_id = ?",
            values,
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_contact(contact_id: int, tenant_id: str = DEFAULT_TENANT_ID) -> bool:
    """Delete contact (and its properties + lead links) scoped to tenant."""
    conn = get_connection()
    try:
        # Verify ownership first so we don't accidentally cascade-delete a
        # different tenant's lead links via the contact_id alone.
        row = conn.execute(
            "SELECT id FROM contacts WHERE id = ? AND tenant_id = ?",
            (contact_id, tenant_id),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM contact_lead_links WHERE contact_id = ?", (contact_id,))
        conn.execute("DELETE FROM contact_properties WHERE contact_id = ?", (contact_id,))
        conn.execute(
            "DELETE FROM contacts WHERE id = ? AND tenant_id = ?",
            (contact_id, tenant_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_contact_by_phone(
    phone: str,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> Optional[Dict[str, Any]]:
    """Find contact by phone within a tenant (normalized: digits only)."""
    if not phone or not str(phone).strip():
        return None
    digits = re.sub(r"\D", "", str(phone))
    if not digits:
        return None
    conn = get_connection(readonly=True)
    try:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE phone IS NOT NULL AND phone != '' AND tenant_id = ?",
            (tenant_id,),
        ).fetchall()
        for row in rows:
            row_digits = re.sub(r"\D", "", str(row["phone"] or ""))
            if row_digits and row_digits == digits:
                return dict(row)
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Contact properties
# ---------------------------------------------------------------------------

def add_property_to_contact(
    contact_id: int,
    building_name: Optional[str] = None,
    unit_number: Optional[str] = None,
    bedrooms: Optional[str] = None,
    bathrooms: Optional[str] = None,
    price_aed: Optional[float] = None,
    intent: Optional[str] = None,
    view_type: Optional[str] = None,
    notes: Optional[str] = None,
    lead_id: Optional[int] = None,
    is_scraped_listing: bool = False,
    scraped_listing_url: Optional[str] = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> Optional[int]:
    """Add a property to a contact (must belong to `tenant_id`). Runs
    merge_scraped_listing if building+unit given. Returns
    contact_properties.id, or None if the contact doesn't belong to
    this tenant."""
    # Verify ownership before mutating
    _conn = get_connection(readonly=True)
    try:
        row = _conn.execute(
            "SELECT 1 FROM contacts WHERE id = ? AND tenant_id = ?",
            (contact_id, tenant_id),
        ).fetchone()
        if not row:
            return None
    finally:
        _conn.close()
    if building_name or unit_number:
        scraped = merge_scraped_listing(building_name or "", unit_number or "")
        if scraped:
            is_scraped_listing = True
            scraped_listing_url = scraped.get("listing_url") or scraped_listing_url
            if not intent and scraped.get("listing_type"):
                lt = (scraped.get("listing_type") or "").lower()
                if "rent" in lt:
                    intent = "renting"
                else:
                    intent = "selling"

    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO contact_properties (
                contact_id, building_name, unit_number, bedrooms, bathrooms,
                price_aed, intent, view_type, notes, lead_id,
                is_scraped_listing, scraped_listing_url, tenant_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                contact_id,
                (building_name or "").strip() or None,
                (unit_number or "").strip() or None,
                (bedrooms or "").strip() if bedrooms is not None else None,
                (bathrooms or "").strip() if bathrooms is not None else None,
                price_aed,
                (intent or "").strip() or None,
                (view_type or "").strip() or None,
                (notes or "").strip() or None,
                lead_id,
                1 if is_scraped_listing else 0,
                (scraped_listing_url or "").strip() or None,
                tenant_id,
            ),
        )
        pid = cur.lastrowid
        conn.commit()
        return pid
    finally:
        conn.close()


def update_contact_property(
    property_id: int,
    building_name: Optional[str] = None,
    unit_number: Optional[str] = None,
    bedrooms: Optional[str] = None,
    bathrooms: Optional[str] = None,
    price_aed: Optional[float] = None,
    intent: Optional[str] = None,
    view_type: Optional[str] = None,
    notes: Optional[str] = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> bool:
    """Update a contact_property by id, scoped to tenant."""
    conn = get_connection()
    try:
        # Verify the property belongs to a contact owned by this tenant
        row = conn.execute(
            """SELECT cp.id FROM contact_properties cp
               JOIN contacts c ON c.id = cp.contact_id
               WHERE cp.id = ? AND c.tenant_id = ?""",
            (property_id, tenant_id),
        ).fetchone()
        if not row:
            return False
        updates = []
        values: list = []
        for col, val in (
            ("building_name", building_name),
            ("unit_number", unit_number),
            ("bedrooms", bedrooms),
            ("bathrooms", bathrooms),
            ("price_aed", price_aed),
            ("intent", intent),
            ("view_type", view_type),
            ("notes", notes),
        ):
            if val is not None:
                updates.append(f"{col} = ?")
                values.append((val.strip() if isinstance(val, str) else val) or None)
        if not updates:
            return True
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(property_id)
        conn.execute(
            f"UPDATE contact_properties SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        conn.commit()
        return True
    finally:
        conn.close()


def remove_property_from_contact(
    property_id: int,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> bool:
    """Remove a contact_property by id, scoped to tenant."""
    conn = get_connection()
    try:
        # Verify ownership via the contact
        row = conn.execute(
            """SELECT cp.id FROM contact_properties cp
               JOIN contacts c ON c.id = cp.contact_id
               WHERE cp.id = ? AND c.tenant_id = ?""",
            (property_id, tenant_id),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM contact_properties WHERE id = ?", (property_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_contact_portfolio(
    contact_id: int,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> List[Dict[str, Any]]:
    """All properties for contact (contact_properties + linked lead properties
    as summary), scoped to tenant."""
    props = get_contact_properties(contact_id, tenant_id=tenant_id)
    linked = get_linked_leads(contact_id, tenant_id=tenant_id)
    for link in linked:
        lead = link.get("lead")
        if not lead:
            continue
        # Add lead as property if not already in props (by lead_id)
        already = any(p.get("lead_id") == lead["id"] for p in props)
        if not already:
            props.append({
                "id": None,
                "contact_id": contact_id,
                "building_name": lead.get("building_name"),
                "unit_number": lead.get("unit_number"),
                "bedrooms": lead.get("bedrooms"),
                "bathrooms": None,
                "price_aed": None,
                "intent": None,
                "view_type": None,
                "notes": None,
                "lead_id": lead["id"],
                "is_scraped_listing": 0,
                "scraped_listing_url": None,
                "from_lead": True,
            })
    return props


# ---------------------------------------------------------------------------
# Lead linking
# ---------------------------------------------------------------------------

def link_contact_to_leads(
    contact_id: int,
    leads_df: Optional[Any] = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> List[int]:
    """
    Link contact to leads by phone (and optionally by name). Uses leads_df if provided,
    else queries DB leads table. Scoped to tenant -- only the caller's contact is
    linked, and only to leads in the same tenant. Returns list of lead_ids linked.
    """
    contact = get_contact(
        contact_id,
        include_properties=False,
        include_linked_leads=True,
        tenant_id=tenant_id,
    )
    if not contact:
        return []
    phone = (contact.get("phone") or "").strip()
    full_name = (contact.get("full_name") or "").strip().lower()
    already_linked = {link["lead_id"] for link in contact.get("linked_leads", [])}
    linked_ids = []

    def normalize_phone(p):
        return re.sub(r"\D", "", str(p or ""))

    phone_digits = normalize_phone(phone)

    if leads_df is not None and pd is not None and not leads_df.empty:
        # Match by phone in DataFrame
        for idx, row in leads_df.iterrows():
            lead_phone = row.get("phone") or row.get("phone_formatted") or ""
            if normalize_phone(lead_phone) == phone_digits and phone_digits:
                lead_id = row.get("id")
                if lead_id is not None and lead_id not in already_linked:
                    _link_one_lead(contact_id, int(lead_id), 1.0, "phone_match", tenant_id=tenant_id)
                    linked_ids.append(int(lead_id))
                    already_linked.add(int(lead_id))
        # Match by owner_name if we have name
        if full_name:
            for idx, row in leads_df.iterrows():
                owner = (row.get("owner_name") or "").strip().lower()
                if owner == full_name:
                    lead_id = row.get("id")
                    if lead_id is not None and lead_id not in already_linked:
                        _link_one_lead(contact_id, int(lead_id), 0.8, "name_match", tenant_id=tenant_id)
                        linked_ids.append(int(lead_id))
                        already_linked.add(int(lead_id))
    else:
        # Query DB leads (scoped to tenant)
        conn = get_connection()
        try:
            if phone_digits:
                rows = conn.execute(
                    "SELECT id, phone, phone_formatted, owner_name FROM leads WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchall()
                for row in rows:
                    if normalize_phone(row["phone"] or row["phone_formatted"] or "") == phone_digits:
                        lid = row["id"]
                        if lid not in already_linked:
                            _link_one_lead(contact_id, lid, 1.0, "phone_match", tenant_id=tenant_id)
                            linked_ids.append(lid)
                            already_linked.add(lid)
            if full_name:
                rows = conn.execute(
                    "SELECT id, owner_name FROM leads WHERE LOWER(TRIM(owner_name)) = ? AND tenant_id = ?",
                    (full_name, tenant_id),
                ).fetchall()
                for row in rows:
                    lid = row["id"]
                    if lid not in already_linked:
                        _link_one_lead(contact_id, lid, 0.8, "name_match", tenant_id=tenant_id)
                        linked_ids.append(lid)
                        already_linked.add(lid)
        finally:
            conn.close()

    return linked_ids


def _link_one_lead(
    contact_id: int,
    lead_id: int,
    confidence: float,
    method: str,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO contact_lead_links
               (contact_id, lead_id, match_confidence, match_method, tenant_id)
               VALUES (?, ?, ?, ?, ?)""",
            (contact_id, lead_id, confidence, method, tenant_id),
        )
        conn.commit()
    finally:
        conn.close()


def link_contact_to_lead_manual(
    contact_id: int,
    lead_id: int,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> bool:
    """Manually link contact to one lead, scoped to tenant."""
    # Verify both belong to this tenant before linking
    conn = get_connection()
    try:
        c = conn.execute(
            "SELECT 1 FROM contacts WHERE id = ? AND tenant_id = ?",
            (contact_id, tenant_id),
        ).fetchone()
        l = conn.execute(
            "SELECT 1 FROM leads WHERE id = ? AND tenant_id = ?",
            (lead_id, tenant_id),
        ).fetchone()
        if not c or not l:
            return False
        conn.execute(
            """INSERT OR IGNORE INTO contact_lead_links
               (contact_id, lead_id, match_confidence, match_method, tenant_id)
               VALUES (?, ?, 1.0, 'manual', ?)""",
            (contact_id, lead_id, tenant_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def unlink_lead(
    contact_id: int,
    lead_id: int,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> bool:
    """Remove link between contact and lead, scoped to tenant."""
    conn = get_connection()
    try:
        # Only delete if the contact belongs to this tenant
        owner = conn.execute(
            "SELECT 1 FROM contacts WHERE id = ? AND tenant_id = ?",
            (contact_id, tenant_id),
        ).fetchone()
        if not owner:
            return False
        conn.execute(
            "DELETE FROM contact_lead_links WHERE contact_id = ? AND lead_id = ?",
            (contact_id, lead_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scraped listing merge
# ---------------------------------------------------------------------------

def merge_scraped_listing(building_name: str, unit_number: str) -> Optional[Dict[str, Any]]:
    """
    Check if (building, unit) exists in PropertyFinder scraped CSV.
    Returns dict with listing_url, listing_type (rent/sale), listing_price if found.
    """
    if not PF_LEADS_CSV.exists():
        return None
    building_name = (building_name or "").strip().lower()
    unit_number = (str(unit_number or "").strip().lower()).replace(" ", "")
    if not building_name and not unit_number:
        return None
    try:
        if pd is None:
            import csv
            with open(PF_LEADS_CSV, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    b = (row.get("building_name") or "").strip().lower()
                    u = (str(row.get("unit_number") or "").strip().lower()).replace(" ", "")
                    if (b == building_name or (building_name and building_name in b)) and (u == unit_number or (unit_number and unit_number in u)):
                        return {
                            "listing_url": (row.get("listing_url") or "").strip() or None,
                            "listing_type": (row.get("listing_type") or "").strip() or None,
                            "listing_price": (row.get("listing_price") or "").strip() or None,
                        }
            return None
        df = pd.read_csv(PF_LEADS_CSV, encoding="utf-8", on_bad_lines="skip", low_memory=False)
        if df.empty:
            return None
        if "building_name" not in df.columns:
            return None
        bn = df["building_name"].fillna("").astype(str).str.strip().str.lower()
        un = df["unit_number"].fillna("").astype(str).str.strip().str.lower().str.replace(" ", "", regex=False)
        if building_name:
            mask_b = bn.str.contains(building_name, na=False, regex=False)
        else:
            mask_b = True
        if unit_number:
            mask_u = un == unit_number
        else:
            mask_u = True
        match = df.loc[mask_b & mask_u]
        if match.empty:
            return None
        row = match.iloc[0]
        return {
            "listing_url": (row.get("listing_url") or "").strip() or None if "listing_url" in row else None,
            "listing_type": (row.get("listing_type") or "").strip() or None if "listing_type" in row else None,
            "listing_price": (row.get("listing_price") or "").strip() or None if "listing_price" in row else None,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_contacts(
    query: Optional[str] = None,
    contact_type: Optional[str] = None,
    agent_assigned: Optional[str] = None,
    limit: int = 500,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> List[Dict[str, Any]]:
    """Search contacts by name/phone, optionally filter by type and agent.
    Always scoped to tenant."""
    conn = get_connection(readonly=True)
    try:
        sql = "SELECT * FROM contacts WHERE tenant_id = ?"
        params: list = [tenant_id]
        if query and query.strip():
            q = f"%{query.strip()}%"
            sql += " AND (full_name LIKE ? OR phone LIKE ? OR email LIKE ?)"
            params.extend([q, q, q])
        if contact_type and contact_type.strip():
            sql += " AND contact_type = ?"
            params.append(contact_type.strip())
        if agent_assigned and agent_assigned.strip():
            sql += " AND agent_assigned = ?"
            params.append(agent_assigned.strip())
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_contact_count(tenant_id: str = DEFAULT_TENANT_ID) -> int:
    """Total number of contacts for `tenant_id`."""
    conn = get_connection(readonly=True)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def update_last_contact_date(
    contact_id: int,
    when: Optional[datetime] = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> bool:
    """Set last_contact_date for contact (e.g. after logging a call), scoped
    to tenant."""
    conn = get_connection()
    try:
        ts = (when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "UPDATE contacts SET last_contact_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND tenant_id = ?",
            (ts, contact_id, tenant_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
