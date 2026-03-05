"""
Client Data Manager Module - Notes & Reminders Persistence
Handles saving, loading, and managing client notes and follow-up reminders.
All data stored as JSON in client_data/ directory.
"""

import json
import os
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from dateutil import parser as dateutil_parser

CLIENT_DIR = Path("client_data")
CLIENT_DIR.mkdir(exist_ok=True)

NOTES_FILE = CLIENT_DIR / "notes.json"
REMINDERS_FILE = CLIENT_DIR / "reminders.json"
CALL_LOG_FILE = CLIENT_DIR / "call_log.json"
LEAD_OVERRIDES_FILE = CLIENT_DIR / "lead_overrides.json"

CALL_OUTCOMES = ('voicemail', 'no_answer', 'not_interested', 'interested', 'callback')


# =============================================================================
# CLIENT ID GENERATION
# =============================================================================

def make_client_id(name: str = None, building: str = None, unit: str = None, contact_id: int = None) -> str:
    """Generate a deterministic short ID from client name + building + unit, or for contacts use CONTACT:id.
    Same lead always maps to the same profile. Coerces to str so float/NaN from DataFrame do not cause AttributeError."""
    if contact_id is not None:
        return f"CONTACT:{contact_id}"
    raw = f"{str(name or '').strip().lower()}|{str(building or '').strip().lower()}|{str(unit or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# =============================================================================
# JSON FILE HELPERS
# =============================================================================

def _load_json(filepath: Path) -> dict | list:
    """Load JSON file, return empty structure if missing or corrupt."""
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[client_data_manager] Error loading {filepath}: {e}")
    # Default: dict for notes, list for reminders
    if filepath == NOTES_FILE:
        return {}
    return []


def _save_json(filepath: Path, data) -> bool:
    """Save data to JSON file."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return True
    except Exception as e:
        print(f"[client_data_manager] Error saving {filepath}: {e}")
        return False


# =============================================================================
# NOTES CRUD
# =============================================================================

def get_notes(client_id: str) -> list:
    """Get all notes for a client, newest first."""
    all_notes = _load_json(NOTES_FILE)
    notes = all_notes.get(client_id, [])
    # Sort newest first
    notes.sort(key=lambda n: n.get('timestamp', ''), reverse=True)
    return notes


def add_note(client_id: str, text: str) -> bool:
    """Add a new note for a client."""
    all_notes = _load_json(NOTES_FILE)
    if client_id not in all_notes:
        all_notes[client_id] = []

    note = {
        'id': str(uuid.uuid4())[:8],
        'text': text,
        'timestamp': datetime.now().isoformat()
    }
    all_notes[client_id].append(note)
    return _save_json(NOTES_FILE, all_notes)


def edit_note(client_id: str, note_id: str, new_text: str) -> bool:
    """Edit an existing note."""
    all_notes = _load_json(NOTES_FILE)
    notes = all_notes.get(client_id, [])

    for note in notes:
        if note['id'] == note_id:
            note['text'] = new_text
            note['edited_at'] = datetime.now().isoformat()
            return _save_json(NOTES_FILE, all_notes)
    return False


def delete_note(client_id: str, note_id: str) -> bool:
    """Delete a note."""
    all_notes = _load_json(NOTES_FILE)
    notes = all_notes.get(client_id, [])

    all_notes[client_id] = [n for n in notes if n['id'] != note_id]
    return _save_json(NOTES_FILE, all_notes)


# =============================================================================
# LEAD FIELD OVERRIDES
# =============================================================================

def get_lead_overrides(client_id: str) -> dict:
    """Return any manually saved field overrides for this lead."""
    all_overrides = _load_json(LEAD_OVERRIDES_FILE)
    if isinstance(all_overrides, dict):
        return all_overrides.get(client_id, {})
    return {}


def save_lead_overrides(client_id: str, overrides: dict) -> bool:
    """Save manual field overrides for a lead (bedrooms, size, phone, etc.)."""
    all_overrides = _load_json(LEAD_OVERRIDES_FILE)
    if not isinstance(all_overrides, dict):
        all_overrides = {}
    # Strip empty strings — treat as "cleared" (remove override)
    cleaned = {k: v for k, v in overrides.items() if v != "" and v is not None}
    all_overrides[client_id] = cleaned
    return _save_json(LEAD_OVERRIDES_FILE, all_overrides)


# =============================================================================
# DATE/TIME PARSING
# =============================================================================

def parse_reminder_datetime(text: str) -> datetime | None:
    """Parse a typed date/time string into a datetime object.
    Accepts formats like:
      08/02/2026, 2pm
      08/02/2026, 2:30pm
      8/2/2026 14:00
      2026-02-08, 2pm
      15 March 2026, 3pm
    Uses dayfirst=True (DD/MM/YYYY) since user is in Dubai."""
    if not text or not text.strip():
        return None
    try:
        return dateutil_parser.parse(text.strip(), dayfirst=True)
    except (ValueError, TypeError):
        return None


# =============================================================================
# REMINDERS CRUD
# =============================================================================

def get_all_reminders() -> list:
    """Get all reminders, sorted by actionability:
    1. Overdue pending (oldest first)
    2. Due today pending
    3. Future pending (soonest first)
    4. Completed (most recently completed first)
    """
    reminders = _load_json(REMINDERS_FILE)
    now = datetime.now()

    def sort_key(r):
        status = r.get('status', 'pending')
        try:
            dt = datetime.fromisoformat(r.get('datetime', ''))
        except (ValueError, TypeError):
            dt = datetime.max

        if status == 'done':
            # Completed reminders go to bottom, newest done first
            completed_at = r.get('completed_at', '')
            try:
                comp_dt = datetime.fromisoformat(completed_at)
            except (ValueError, TypeError):
                comp_dt = datetime.min
            # Group 3 = bottom, then reverse-sort by completed_at
            return (3, datetime.max - comp_dt)
        else:
            # Pending reminders: overdue first, then future
            if dt <= now:
                # Overdue: oldest overdue first (most urgent)
                return (1, dt)
            else:
                # Future: soonest first
                return (2, dt)

    reminders.sort(key=sort_key)
    return reminders


def get_reminders_for_client(client_id: str) -> list:
    """Get all reminders for a specific client."""
    all_reminders = get_all_reminders()
    return [r for r in all_reminders if r.get('client_id') == client_id]


def get_pending_reminder_count() -> int:
    """Get count of pending reminders that are due (overdue or due today)."""
    reminders = _load_json(REMINDERS_FILE)
    now = datetime.now()
    count = 0
    for r in reminders:
        if r.get('status', 'pending') == 'pending':
            try:
                dt = datetime.fromisoformat(r.get('datetime', ''))
                if dt <= now:
                    count += 1
            except (ValueError, TypeError):
                # If datetime is unparseable, count it as actionable
                count += 1
    return count


def add_reminder(client_id: str, client_name: str, building: str,
                 unit: str, phone: str, reminder_dt: datetime, note: str) -> bool:
    """Add a new reminder."""
    reminders = _load_json(REMINDERS_FILE)
    reminder = {
        'id': str(uuid.uuid4())[:8],
        'client_id': client_id,
        'client_name': client_name or 'Unknown',
        'building': building or '',
        'unit': unit or '',
        'phone': phone or '',
        'datetime': reminder_dt.isoformat(),
        'note': note or '',
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
        'completed_at': None
    }
    reminders.append(reminder)
    return _save_json(REMINDERS_FILE, reminders)


def mark_reminder_done(reminder_id: str) -> bool:
    """Mark a reminder as done (keeps it in the list)."""
    reminders = _load_json(REMINDERS_FILE)
    for r in reminders:
        if r['id'] == reminder_id:
            r['status'] = 'done'
            r['completed_at'] = datetime.now().isoformat()
            return _save_json(REMINDERS_FILE, reminders)
    return False


def delete_reminder(reminder_id: str) -> bool:
    """Permanently remove a reminder from the list."""
    reminders = _load_json(REMINDERS_FILE)
    reminders = [r for r in reminders if r['id'] != reminder_id]
    return _save_json(REMINDERS_FILE, reminders)


def update_reminder(reminder_id: str, reminder_dt: datetime = None, note: str = None) -> bool:
    """Update an existing reminder's date and/or note. Only provided fields are updated."""
    reminders = _load_json(REMINDERS_FILE)
    for r in reminders:
        if r['id'] == reminder_id:
            if reminder_dt is not None:
                r['datetime'] = reminder_dt.isoformat()
            if note is not None:
                r['note'] = note
            return _save_json(REMINDERS_FILE, reminders)
    return False


# =============================================================================
# CALL LOG CRUD
# =============================================================================

def get_call_log(client_id: str = None) -> list:
    """Get all call records, or filtered by client_id. Newest first."""
    calls = _load_json(CALL_LOG_FILE)
    if not isinstance(calls, list):
        calls = []
    if client_id:
        calls = [c for c in calls if c.get('client_id') == client_id]
    calls.sort(key=lambda c: c.get('called_at', ''), reverse=True)
    return calls


def log_call(client_id: str, client_name: str, building: str, unit: str, phone: str,
             outcome: str, notes: str = '', reminder_dt: datetime = None,
             reminder_note: str = None) -> bool:
    """Record a call. If reminder_dt and reminder_note are set, creates a follow-up reminder."""
    if outcome not in CALL_OUTCOMES:
        outcome = 'no_answer'
    calls = _load_json(CALL_LOG_FILE)
    if not isinstance(calls, list):
        calls = []
    record = {
        'id': str(uuid.uuid4())[:8],
        'client_id': client_id or '',
        'client_name': client_name or 'Unknown',
        'building': building or '',
        'unit': unit or '',
        'phone': phone or '',
        'called_at': datetime.now().isoformat(),
        'outcome': outcome,
        'notes': (notes or '').strip(),
        'reminder_dt': reminder_dt.isoformat() if reminder_dt else None,
        'reminder_note': (reminder_note or '').strip() or None,
    }
    calls.append(record)
    if not _save_json(CALL_LOG_FILE, calls):
        return False
    if reminder_dt and (reminder_note or '').strip():
        add_reminder(
            client_id=client_id or '',
            client_name=client_name or 'Unknown',
            building=building or '',
            unit=unit or '',
            phone=phone or '',
            reminder_dt=reminder_dt,
            note=(reminder_note or '').strip()
        )
    return True


def get_call_count(client_id: str) -> int:
    """Return number of calls logged for this client."""
    calls = get_call_log(client_id=client_id)
    return len(calls)


def get_all_called_client_ids() -> set:
    """Return set of client_ids that have at least one call logged (for lead list indicator)."""
    calls = _load_json(CALL_LOG_FILE)
    if not isinstance(calls, list):
        return set()
    return {c.get('client_id') for c in calls if c.get('client_id')}
