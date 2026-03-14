"""
Chat Scans -- stores WhatsApp chat scan results per contact.
Data file: whatsapp_bot/chat_scans.csv
One row per phone number (upsert on re-scan).
"""

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

CHAT_SCANS_PATH = Path(__file__).parent / "chat_scans.csv"

HEADERS = [
    "phone", "owner_name", "scanned_at",
    "incoming_count", "outgoing_count",
    "last_reply_text", "last_reply_at", "last_sent_at",
    "contact_type", "building", "unit",
]

_TEMPLATE_TYPE_MAP = {
    "propspace_buyer": "Buyer",
    "propspace_tenant": "Tenant",
    "landlord_lease_expiry": "Landlord",
    "cold_owner": "Landlord",
    "recent_sale": "Landlord",
    "portfolio_owner": "Landlord",
    "active_seller": "Landlord",
    "active_renter": "Landlord",
}


def _infer_contact_type(template_type: str) -> str:
    if not template_type:
        return ""
    for prefix, ctype in _TEMPLATE_TYPE_MAP.items():
        if template_type.startswith(prefix):
            return ctype
    return ""


def _load_existing() -> dict:
    if not CHAT_SCANS_PATH.exists():
        return {}
    try:
        df = pd.read_csv(CHAT_SCANS_PATH, dtype=str).fillna("")
        return {row["phone"]: row.to_dict() for _, row in df.iterrows()}
    except Exception:
        return {}


def save_scan(phone: str, owner_name: str, scan_result: dict,
              template_type: str = "", building: str = "", unit: str = "") -> None:
    """Upsert a scan result for a phone number. Preserves user-set contact_type."""
    existing = _load_existing()
    existing_row = existing.get(phone, {})

    contact_type = existing_row.get("contact_type", "")
    if not contact_type:
        contact_type = _infer_contact_type(template_type)

    row = {
        "phone": phone,
        "owner_name": owner_name or existing_row.get("owner_name", ""),
        "scanned_at": datetime.now().isoformat(),
        "incoming_count": scan_result.get("incoming_count", 0),
        "outgoing_count": scan_result.get("outgoing_count", 0),
        "last_reply_text": scan_result.get("last_reply_text", ""),
        "last_reply_at": scan_result.get("last_reply_at", ""),
        "last_sent_at": scan_result.get("last_sent_at", ""),
        "contact_type": contact_type,
        "building": building or existing_row.get("building", ""),
        "unit": unit or existing_row.get("unit", ""),
    }
    existing[phone] = row

    with open(CHAT_SCANS_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing.values())


def load_scans() -> pd.DataFrame:
    """Load all scan rows as a DataFrame."""
    if not CHAT_SCANS_PATH.exists():
        return pd.DataFrame(columns=HEADERS)
    try:
        return pd.read_csv(CHAT_SCANS_PATH, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=HEADERS)


def update_contact_type(phone: str, contact_type: str) -> None:
    """Set the contact_type for a phone number."""
    existing = _load_existing()
    if phone not in existing:
        return
    existing[phone]["contact_type"] = contact_type
    with open(CHAT_SCANS_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing.values())
