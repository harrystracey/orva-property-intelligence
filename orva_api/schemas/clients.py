"""Pydantic models for client data: notes, reminders, call log."""

from pydantic import BaseModel
from typing import Optional


# --- Notes ---

class NoteRecord(BaseModel):
    id: str
    text: str
    timestamp: str
    edited_at: Optional[str] = None


class AddNoteRequest(BaseModel):
    text: str


class EditNoteRequest(BaseModel):
    text: str


# --- Reminders ---

class ReminderRecord(BaseModel):
    id: str
    client_id: str
    client_name: str
    building: str
    unit: str
    phone: str
    datetime: str
    note: str
    status: str
    created_at: str
    completed_at: Optional[str] = None


class AddReminderRequest(BaseModel):
    client_name: str
    building: str = ""
    unit: str = ""
    phone: str = ""
    datetime: str  # ISO format
    note: str


class UpdateReminderRequest(BaseModel):
    datetime: Optional[str] = None
    note: Optional[str] = None


# --- Call Log ---

class CallRecord(BaseModel):
    id: str
    client_id: str
    client_name: str
    building: str
    unit: str
    phone: str
    called_at: str
    outcome: str
    notes: str
    reminder_dt: Optional[str] = None
    reminder_note: Optional[str] = None


class LogCallRequest(BaseModel):
    client_name: str
    building: str = ""
    unit: str = ""
    phone: str = ""
    outcome: str  # voicemail, no_answer, not_interested, interested, callback
    notes: str = ""
    reminder_dt: Optional[str] = None
    reminder_note: Optional[str] = None


# --- Client Profile ---

class ClientProfileResponse(BaseModel):
    client_id: str
    owner_name: Optional[str] = None
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[float] = None
    size_sqft: Optional[float] = None
    phone: Optional[str] = None
    date: Optional[str] = None
    completeness: Optional[float] = None
    notes: list[NoteRecord]
    reminders: list[ReminderRecord]
    calls: list[CallRecord]
    portfolio: list[dict]  # other properties by same owner
