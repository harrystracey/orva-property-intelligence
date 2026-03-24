"""Pydantic models for WhatsApp campaign API."""

from pydantic import BaseModel
from typing import Optional


# --- Request models ---

class CampaignPreviewRequest(BaseModel):
    campaign_type: str  # landlord_lease_expiry | cold_owner | recent_sale | portfolio_owner | active_seller | active_renter | propspace_leads
    building: Optional[str] = None
    bedrooms: Optional[str] = None
    area: Optional[str] = None
    days_ahead: int = 90
    portfolio_only: bool = False
    min_units: int = 3
    limit: Optional[int] = None
    lead_type: Optional[str] = None
    not_yet_contacted: bool = False
    custom_message: Optional[str] = None
    account: str = "1"


class CampaignStartRequest(BaseModel):
    campaign_type: str
    building: Optional[str] = None
    bedrooms: Optional[str] = None
    area: Optional[str] = None
    days_ahead: int = 90
    portfolio_only: bool = False
    min_units: int = 3
    limit: Optional[int] = None
    lead_type: Optional[str] = None
    not_yet_contacted: bool = False
    custom_message: Optional[str] = None
    account: str = "1"
    dry_run: bool = False
    override_limit: bool = False
    no_limits: bool = False
    excluded_phones: list[str] = []


class LinkStartRequest(BaseModel):
    phone_number: str


# --- Response models ---

class QueueContact(BaseModel):
    phone: str
    owner_name: Optional[str] = None
    building: Optional[str] = None
    unit: Optional[str] = None
    bedrooms: Optional[str] = None
    message_preview: Optional[str] = None
    template_type: Optional[str] = None
    is_portfolio: bool = False


class CampaignPreviewResponse(BaseModel):
    queue: list[QueueContact]
    total: int


class CampaignProgress(BaseModel):
    status: str = "idle"  # idle | building | running | paused | stopped | done | error
    sent: int = 0
    failed: int = 0
    not_on_wa: int = 0
    skipped: int = 0
    total: int = 0
    current_contact: Optional[QueueContact] = None
    daily_cap: int = 36
    messages_today: int = 0
    elapsed_seconds: int = 0
    error: Optional[str] = None


class WAStatusResponse(BaseModel):
    connected: bool
    qr_available: bool = False
    phone: Optional[str] = None
    qr_b64: Optional[str] = None


class LinkStatusResponse(BaseModel):
    link_code: Optional[str] = None
    error: Optional[str] = None
    pending: bool = False


class SendStatsResponse(BaseModel):
    today: dict
    week: dict
    all_time: dict


class MessageLogEntry(BaseModel):
    timestamp: Optional[str] = None
    campaign_id: Optional[str] = None
    wa_account: Optional[str] = None
    phone: Optional[str] = None
    owner_name: Optional[str] = None
    building: Optional[str] = None
    unit: Optional[str] = None
    template_type: Optional[str] = None
    message: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


class MessageLogResponse(BaseModel):
    messages: list[MessageLogEntry]
    total: int
