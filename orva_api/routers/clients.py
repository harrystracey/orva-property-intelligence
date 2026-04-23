"""Client data API — notes, reminders, call log, profile."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from .. import _sys_paths  # noqa: F401 -- puts project root on sys.path

from client_data_manager import (  # noqa: E402
    make_client_id,
    get_notes, add_note, edit_note, delete_note,
    get_all_reminders, get_reminders_for_client, get_pending_reminder_count,
    add_reminder, mark_reminder_done, delete_reminder, update_reminder,
    get_call_log, log_call, get_call_count,
)

from ..auth import get_current_user
from ..deps import DataStore, get_data_store
from ..schemas.clients import (
    NoteRecord, AddNoteRequest, EditNoteRequest,
    ReminderRecord, AddReminderRequest, UpdateReminderRequest,
    CallRecord, LogCallRequest,
    ClientProfileResponse,
)

import pandas as pd

router = APIRouter(prefix="/api/clients", tags=["clients"])


def _make_id(owner_name: str, building_name: str, unit_number: str) -> str:
    return make_client_id(name=owner_name, building=building_name, unit=unit_number)


# ══════════════════════════════════════════════════════════════════════════════
# FIXED PATHS FIRST (must come before /{client_id} to avoid conflicts)
# ══════════════════════════════════════════════════════════════════════════════

# ─── Lookup ───

@router.get("/lookup/id")
def lookup_client_id(
    owner_name: str = "",
    building_name: str = "",
    unit_number: str = "",
    user: dict = Depends(get_current_user),
):
    """Generate client_id from owner_name + building + unit."""
    cid = _make_id(owner_name, building_name, unit_number)
    return {"client_id": cid}


# ─── Global Reminders ───

@router.get("/reminders/all", response_model=list[ReminderRecord])
def list_all_reminders(user: dict = Depends(get_current_user)):
    return [ReminderRecord(**r) for r in get_all_reminders()]


@router.get("/reminders/count")
def reminder_count(user: dict = Depends(get_current_user)):
    return {"count": get_pending_reminder_count()}


@router.put("/reminders/{reminder_id}")
def edit_reminder(
    reminder_id: str,
    req: UpdateReminderRequest,
    user: dict = Depends(get_current_user),
):
    dt = None
    if req.datetime:
        try:
            dt = datetime.fromisoformat(req.datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format")

    ok = update_reminder(reminder_id, reminder_dt=dt, note=req.note)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"status": "ok"}


@router.post("/reminders/{reminder_id}/done")
def complete_reminder(
    reminder_id: str,
    user: dict = Depends(get_current_user),
):
    ok = mark_reminder_done(reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"status": "ok"}


@router.delete("/reminders/{reminder_id}")
def remove_reminder(
    reminder_id: str,
    user: dict = Depends(get_current_user),
):
    ok = delete_reminder(reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"status": "ok"}


# ─── Global Call Log ───

@router.get("/calls/all", response_model=list[CallRecord])
def list_all_calls(
    user: dict = Depends(get_current_user),
):
    return [CallRecord(**c) for c in get_call_log()]


# ══════════════════════════════════════════════════════════════════════════════
# PARAMETRIC PATHS (/{client_id}/...)
# ══════════════════════════════════════════════════════════════════════════════

# ─── Client Profile ───

@router.get("/{client_id}", response_model=ClientProfileResponse)
def get_client_profile(
    client_id: str,
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    """Get full client profile: lead info + notes + reminders + calls + portfolio."""
    df = store.leads_df

    # O(1) lookup via the index precomputed in DataStore.load()
    match = store.find_client_row(client_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Client not found")
    owner_name_val = match.get("owner_name") if pd.notna(match.get("owner_name")) else None

    # Portfolio: all properties by this owner
    portfolio = []
    if owner_name_val:
        owner_rows = df[
            df["owner_name"].fillna("").str.strip().str.lower()
            == str(owner_name_val).strip().lower()
        ]
        for _, prow in owner_rows.iterrows():
            portfolio.append({
                "building_name": prow.get("building_name") if pd.notna(prow.get("building_name")) else None,
                "unit_number": prow.get("unit_number") if pd.notna(prow.get("unit_number")) else None,
                "bedrooms": float(prow["bedrooms"]) if pd.notna(prow.get("bedrooms")) else None,
                "size_sqft": float(prow["size_sqft"]) if pd.notna(prow.get("size_sqft")) else None,
                "date": str(prow["date"])[:10] if pd.notna(prow.get("date")) else None,
                "transaction_value": float(prow["transaction_value"]) if pd.notna(prow.get("transaction_value")) else None,
            })

    # Get notes, reminders, calls
    notes_raw = get_notes(client_id)
    reminders_raw = get_reminders_for_client(client_id)
    calls_raw = get_call_log(client_id=client_id)

    date_val = match.get("date")
    date_str = str(date_val)[:10] if pd.notna(date_val) else None

    return ClientProfileResponse(
        client_id=client_id,
        owner_name=owner_name_val,
        building_name=match.get("building_name") if pd.notna(match.get("building_name")) else None,
        unit_number=match.get("unit_number") if pd.notna(match.get("unit_number")) else None,
        bedrooms=float(match["bedrooms"]) if pd.notna(match.get("bedrooms")) else None,
        size_sqft=float(match["size_sqft"]) if pd.notna(match.get("size_sqft")) else None,
        phone=match.get("phone") if pd.notna(match.get("phone")) else None,
        date=date_str,
        completeness=float(match["completeness"]) if pd.notna(match.get("completeness")) else None,
        notes=[NoteRecord(**n) for n in notes_raw],
        reminders=[ReminderRecord(**r) for r in reminders_raw],
        calls=[CallRecord(**c) for c in calls_raw],
        portfolio=portfolio,
    )


# ─── Notes ───

@router.get("/{client_id}/notes", response_model=list[NoteRecord])
def list_notes(
    client_id: str,
    user: dict = Depends(get_current_user),
):
    return [NoteRecord(**n) for n in get_notes(client_id)]


@router.post("/{client_id}/notes")
def create_note(
    client_id: str,
    req: AddNoteRequest,
    user: dict = Depends(get_current_user),
):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Note text required")
    ok = add_note(client_id, req.text.strip())
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save note")
    return {"status": "ok"}


@router.put("/{client_id}/notes/{note_id}")
def update_note(
    client_id: str,
    note_id: str,
    req: EditNoteRequest,
    user: dict = Depends(get_current_user),
):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Note text required")
    ok = edit_note(client_id, note_id, req.text.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "ok"}


@router.delete("/{client_id}/notes/{note_id}")
def remove_note(
    client_id: str,
    note_id: str,
    user: dict = Depends(get_current_user),
):
    ok = delete_note(client_id, note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "ok"}


# ─── Client Reminders ───

@router.get("/{client_id}/reminders", response_model=list[ReminderRecord])
def list_client_reminders(
    client_id: str,
    user: dict = Depends(get_current_user),
):
    return [ReminderRecord(**r) for r in get_reminders_for_client(client_id)]


@router.post("/{client_id}/reminders")
def create_reminder(
    client_id: str,
    req: AddReminderRequest,
    user: dict = Depends(get_current_user),
):
    try:
        dt = datetime.fromisoformat(req.datetime)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    ok = add_reminder(
        client_id=client_id,
        client_name=req.client_name,
        building=req.building,
        unit=req.unit,
        phone=req.phone,
        reminder_dt=dt,
        note=req.note,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save reminder")
    return {"status": "ok"}


# ─── Client Calls ───

@router.get("/{client_id}/calls", response_model=list[CallRecord])
def list_client_calls(
    client_id: str,
    user: dict = Depends(get_current_user),
):
    return [CallRecord(**c) for c in get_call_log(client_id=client_id)]


@router.post("/{client_id}/calls")
def create_call(
    client_id: str,
    req: LogCallRequest,
    user: dict = Depends(get_current_user),
):
    reminder_dt = None
    if req.reminder_dt:
        try:
            reminder_dt = datetime.fromisoformat(req.reminder_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid reminder datetime")

    ok = log_call(
        client_id=client_id,
        client_name=req.client_name,
        building=req.building,
        unit=req.unit,
        phone=req.phone,
        outcome=req.outcome,
        notes=req.notes,
        reminder_dt=reminder_dt,
        reminder_note=req.reminder_note,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to log call")
    return {"status": "ok"}
