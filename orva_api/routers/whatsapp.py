"""WhatsApp campaign management API -- proxies to wa-1/wa-2, runs campaigns."""

import asyncio
import sys
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

# Ensure project root + whatsapp_bot are importable
_root = Path(__file__).resolve().parent.parent.parent
_wa = _root / "whatsapp_bot"
for p in [str(_root), str(_wa)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from whatsapp_bot.message_log import (
    get_recent_messages,
    get_send_stats,
)
from whatsapp_bot.rate_limiter import mark_restriction_now

# Lazy import to avoid circular: reply_log may not exist yet
def _get_reply_stats(days=None):
    try:
        from whatsapp_bot.message_log import get_reply_stats
        return get_reply_stats(days)
    except Exception:
        return {"replied": 0}

from ..auth import get_current_user, get_user_from_request
from ..config import WA_HOST_1, WA_HOST_2
from ..schemas.whatsapp import (
    CampaignPreviewRequest,
    CampaignPreviewResponse,
    CampaignStartRequest,
    LinkStartRequest,
    MessageLogEntry,
    MessageLogResponse,
    QueueContact,
    SendStatsResponse,
)
from ..services.campaign_runner import (
    campaign_state,
    preview_campaign,
    run_campaign_task,
    _queue_to_contacts,
)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _get_wa_url(account: str) -> str:
    if account == "2":
        return f"http://{WA_HOST_2}:3002"
    return f"http://{WA_HOST_1}:3001"


# ─── WA Server Proxy Endpoints ──────────────────────────────────────────────

@router.get("/status/{account}")
async def get_wa_status(account: str, user: dict = Depends(get_current_user)):
    """Proxy GET /status from wa-{account}."""
    url = _get_wa_url(account)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/status", timeout=5)
            return r.json()
    except httpx.ConnectError:
        return {"connected": False, "qr_available": False, "phone": None, "error": "WA server not reachable"}
    except Exception as e:
        return {"connected": False, "qr_available": False, "phone": None, "error": str(e)[:200]}


@router.get("/qr/{account}")
async def get_wa_qr(account: str, user: dict = Depends(get_current_user)):
    """Proxy QR PNG from wa-{account}."""
    url = _get_wa_url(account)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/qr", timeout=5)
            if r.status_code == 404:
                raise HTTPException(404, "No QR available")
            return Response(content=r.content, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"WA server error: {str(e)[:100]}")


@router.post("/link/start/{account}")
async def start_link(
    account: str,
    req: LinkStartRequest,
    user: dict = Depends(get_current_user),
):
    """Proxy POST /link/start to wa-{account}."""
    url = _get_wa_url(account)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{url}/link/start",
                json={"phone_number": req.phone_number},
                timeout=10,
            )
            return r.json()
    except Exception as e:
        raise HTTPException(503, f"WA server error: {str(e)[:100]}")


@router.get("/link/status/{account}")
async def link_status(account: str, user: dict = Depends(get_current_user)):
    """Proxy GET /link/status from wa-{account}."""
    url = _get_wa_url(account)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/link/status", timeout=5)
            return r.json()
    except Exception as e:
        return {"pending": False, "link_code": None, "error": str(e)[:200]}


@router.get("/telemetry/{account}")
async def get_telemetry(account: str, user: dict = Depends(get_current_user)):
    """Proxy GET /telemetry from wa-{account}."""
    url = _get_wa_url(account)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/telemetry", timeout=5)
            return r.json()
    except Exception as e:
        return {"error": str(e)[:200]}


# ─── Campaign Endpoints ─────────────────────────────────────────────────────

@router.post("/campaign/preview", response_model=CampaignPreviewResponse)
async def preview(
    req: CampaignPreviewRequest,
    user: dict = Depends(get_current_user),
):
    """Build queue without sending. Returns contact list for review."""
    queue, total = await preview_campaign(req)
    contacts = _queue_to_contacts(queue)
    return CampaignPreviewResponse(queue=contacts, total=total)


@router.post("/campaign/start")
async def start_campaign(
    req: CampaignStartRequest,
    user: dict = Depends(get_current_user),
):
    """Start campaign as background asyncio task."""
    if campaign_state.is_running:
        raise HTTPException(400, "Campaign already running")

    campaign_state.task = asyncio.create_task(run_campaign_task(req))
    return {"status": "started"}


@router.post("/campaign/stop")
async def stop_campaign(user: dict = Depends(get_current_user)):
    """Stop the running campaign."""
    if not campaign_state.is_running:
        raise HTTPException(400, "No campaign running")
    campaign_state.request_stop()
    return {"status": "stopping"}


@router.get("/campaign/progress")
async def campaign_progress_sse(
    request: Request,
    user: dict = Depends(get_user_from_request),
):
    """
    SSE stream of campaign progress. Yields JSON every 1s.

    Accepts auth via the standard Authorization: Bearer header OR via a
    `?token=...` query param, because browser EventSource cannot attach
    custom headers. New clients should prefer the header (use fetch +
    ReadableStream) -- passing the token in the URL leaks into server
    logs and Referer headers.
    """
    from sse_starlette.sse import EventSourceResponse

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            yield {"data": campaign_state.progress.model_dump_json()}
            if campaign_state.progress.status in ("done", "stopped", "error", "idle"):
                yield {"data": campaign_state.progress.model_dump_json()}
                break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/campaign/status")
async def campaign_status(user: dict = Depends(get_current_user)):
    """Get current campaign progress (non-SSE, single snapshot)."""
    return campaign_state.progress.model_dump()


# ─── Stats & Log Endpoints ──────────────────────────────────────────────────

@router.get("/stats", response_model=SendStatsResponse)
async def get_stats(user: dict = Depends(get_current_user)):
    """Send statistics: today, 7 days, all time + reply counts."""
    stats_today = await asyncio.to_thread(get_send_stats, 1)
    stats_week = await asyncio.to_thread(get_send_stats, 7)
    stats_all = await asyncio.to_thread(get_send_stats, None)
    reply_today = await asyncio.to_thread(_get_reply_stats, 1)
    reply_week = await asyncio.to_thread(_get_reply_stats, 7)
    reply_all = await asyncio.to_thread(_get_reply_stats, None)

    return SendStatsResponse(
        today={**stats_today, "replies": reply_today.get("replied", 0)},
        week={**stats_week, "replies": reply_week.get("replied", 0)},
        all_time={**stats_all, "replies": reply_all.get("replied", 0)},
    )


@router.get("/messages", response_model=MessageLogResponse)
async def get_messages(
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Get recent messages with optional search."""
    messages = await asyncio.to_thread(get_recent_messages, limit)
    if search:
        q = search.lower()
        messages = [
            m for m in messages
            if q in (m.get("owner_name", "") or "").lower()
            or q in (m.get("building", "") or "").lower()
            or q in (m.get("phone", "") or "").lower()
        ]
    entries = [MessageLogEntry(**m) for m in messages]
    return MessageLogResponse(messages=entries, total=len(entries))


@router.get("/messages/export")
async def export_messages(user: dict = Depends(get_current_user)):
    """Download full message log as CSV."""
    log_path = _root / "whatsapp_bot" / "message_log.csv"
    if not log_path.exists():
        raise HTTPException(404, "No message log found")
    content = log_path.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=whatsapp_log.csv"},
    )


@router.post("/restriction")
async def mark_restriction(user: dict = Depends(get_current_user)):
    """Record a restriction date for cooldown."""
    ok = await asyncio.to_thread(mark_restriction_now)
    return {"status": "ok" if ok else "error"}
