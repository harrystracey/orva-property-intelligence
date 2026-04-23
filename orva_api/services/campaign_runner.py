"""
Campaign runner -- executes WhatsApp campaigns as asyncio background tasks.
Replaces the subprocess approach (run_campaign.py) with in-process execution.
Imports existing whatsapp_bot modules directly.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure project root and whatsapp_bot are importable
_root = Path(__file__).resolve().parent.parent.parent
_wa = _root / "whatsapp_bot"
for p in [str(_root), str(_wa)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from whatsapp_bot.campaign_manager import (
    build_landlord_lease_expiry_queue,
    build_cold_owner_queue,
    build_recent_sale_queue,
    build_portfolio_owner_queue,
    build_active_seller_queue,
    build_active_renter_queue,
    build_propspace_leads_queue,
    apply_dedup_to_queue,
    shuffle_queue,
    generate_messages_for_queue,
)
from whatsapp_bot.bot import send_message, format_phone_for_whatsapp
from whatsapp_bot.message_log import log_message, get_today_send_count, was_ever_messaged
from whatsapp_bot.rate_limiter import RateLimiter, mark_restriction_now
from whatsapp_bot.message_templates import format_first_name

from ..schemas.whatsapp import (
    CampaignProgress,
    CampaignStartRequest,
    CampaignPreviewRequest,
    QueueContact,
)


class CampaignState:
    """Singleton tracking the active campaign. Only one campaign runs at a time."""

    def __init__(self):
        self.task: Optional[asyncio.Task] = None
        self.stop_requested: bool = False
        self.progress: CampaignProgress = CampaignProgress(status="idle")

    @property
    def is_running(self) -> bool:
        return self.task is not None and not self.task.done()

    def request_stop(self):
        self.stop_requested = True


# Module-level singleton
campaign_state = CampaignState()


def build_queue(params) -> list[dict]:
    """Build the message queue using existing campaign_manager functions.
    Mirrors run_campaign.py lines 72-124."""

    ct = params.campaign_type
    building = params.building or None
    bedrooms = params.bedrooms or None
    area = params.area or None
    days_ahead = params.days_ahead
    limit = params.limit or None

    if ct == "landlord_lease_expiry":
        return build_landlord_lease_expiry_queue(
            days_ahead=days_ahead,
            building_filter=building,
            bedrooms_filter=bedrooms,
            area_filter=area,
        )
    elif ct == "cold_owner":
        return build_cold_owner_queue(
            building_filter=building,
            bedrooms_filter=bedrooms,
            portfolio_only=getattr(params, "portfolio_only", False),
            limit=limit,
            area_filter=area,
        )
    elif ct == "recent_sale":
        return build_recent_sale_queue(
            since_days=days_ahead,
            building_filter=building,
            limit=limit,
            area_filter=area,
        )
    elif ct == "portfolio_owner":
        return build_portfolio_owner_queue(
            min_units=getattr(params, "min_units", 3),
            building_filter=building,
            bedrooms_filter=bedrooms,
            limit=limit,
            area_filter=area,
        )
    elif ct == "active_seller":
        return build_active_seller_queue(
            building_filter=building,
            limit=limit,
            area_filter=area,
        )
    elif ct == "active_renter":
        return build_active_renter_queue(
            building_filter=building,
            limit=limit,
            area_filter=area,
        )
    elif ct == "propspace_leads":
        return build_propspace_leads_queue(
            location=building or None,
            lead_type=getattr(params, "lead_type", None),
            beds=None,
            sub_status_filter="new" if getattr(params, "not_yet_contacted", False) else "all",
            limit=limit,
        )
    else:
        return []


def _apply_custom_message(queue: list[dict], custom_message: str):
    """Apply a single custom message to all contacts in queue."""
    msg = custom_message.strip()
    for item in queue:
        fn = format_first_name(item.get("owner_name", "")) or "there"
        item["message"] = (
            msg
            .replace("{name}", fn)
            .replace("{unit}", str(item.get("unit", "") or ""))
            .replace("{building}", str(item.get("building", "") or ""))
            .replace("{phone}", str(item.get("phone", "") or ""))
        )
        item["template_type"] = "custom"


def _queue_to_contacts(queue: list[dict]) -> list[QueueContact]:
    """Convert raw queue dicts to QueueContact models."""
    return [
        QueueContact(
            phone=q.get("phone", ""),
            owner_name=q.get("owner_name"),
            building=q.get("building"),
            unit=q.get("unit"),
            bedrooms=str(q.get("bedrooms", "")) if q.get("bedrooms") else None,
            message_preview=(q.get("message", "") or "")[:120],
            template_type=q.get("template_type"),
            is_portfolio=bool(q.get("is_portfolio")),
        )
        for q in queue
    ]


async def preview_campaign(params: CampaignPreviewRequest) -> tuple[list[dict], int]:
    """Build and return the queue for preview (no sending)."""
    queue = await asyncio.to_thread(build_queue, params)
    if not queue:
        return [], 0

    queue = await asyncio.to_thread(
        apply_dedup_to_queue, queue, 30, params.account
    )
    if not queue:
        return [], 0

    if params.custom_message and params.custom_message.strip():
        _apply_custom_message(queue, params.custom_message)
    else:
        queue = await asyncio.to_thread(generate_messages_for_queue, queue)

    return queue or [], len(queue or [])


async def run_campaign_task(params: CampaignStartRequest):
    """Main campaign loop -- runs as an asyncio.Task.
    Faithfully mirrors run_campaign.py lines 198-364."""

    state = campaign_state
    state.stop_requested = False
    state.progress = CampaignProgress(status="building", total=0)

    try:
        # 1. Build queue
        queue = await asyncio.to_thread(build_queue, params)
        if not queue:
            state.progress = CampaignProgress(status="error", error="Queue is empty after filters")
            return

        # 2. Dedup
        queue = await asyncio.to_thread(
            apply_dedup_to_queue, queue, 30, params.account
        )
        if not queue:
            state.progress = CampaignProgress(status="error", error="Queue is empty after dedup")
            return

        # 3. Messages
        if params.custom_message and params.custom_message.strip():
            _apply_custom_message(queue, params.custom_message)
        else:
            queue = await asyncio.to_thread(generate_messages_for_queue, queue)
            if not queue:
                state.progress = CampaignProgress(
                    status="error", error="Queue is empty after message generation"
                )
                return

        # 4. Exclusions -- normalize both sides through format_phone_for_whatsapp
        # so a phone excluded in raw "+971 55 ..." form still matches a
        # "971551234567" queue entry. Unparseable entries drop to None and
        # therefore never match.
        if params.excluded_phones:
            excl = {n for n in (format_phone_for_whatsapp(p) for p in params.excluded_phones) if n}
            queue = [q for q in queue if format_phone_for_whatsapp(q.get("phone")) not in excl]

        # 5. Shuffle
        queue = shuffle_queue(queue)

        # 6. Rate limiter -- override_limit skips ramp-up but daily cap still
        # enforced via persistent message log (see rate_limiter.reset docstring).
        rate_limiter = RateLimiter(override_limit=params.override_limit)

        state.progress = CampaignProgress(
            status="running",
            total=len(queue),
            daily_cap=rate_limiter.get_daily_cap(),
            messages_today=await asyncio.to_thread(get_today_send_count),
        )

        # DRY RUN -- just mark done, queue was already shown in preview
        if params.dry_run:
            state.progress.status = "done"
            return

        # 7. Send loop
        campaign_id = f"{params.campaign_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        start_time = datetime.now()

        for idx, item in enumerate(queue):
            # Check stop
            if state.stop_requested:
                state.progress.status = "stopped"
                break

            # Rate limiter: daily cap
            if not params.no_limits:
                can_send, reason = rate_limiter.can_send_today()
                if not can_send:
                    state.progress.status = "stopped"
                    state.progress.error = reason
                    break

                should_stop, stop_reason = rate_limiter.should_stop_session()
                if should_stop:
                    state.progress.status = "stopped"
                    state.progress.error = stop_reason
                    break

            # Format phone
            phone_formatted = format_phone_for_whatsapp(item.get("phone", ""))
            if not phone_formatted:
                state.progress.skipped += 1
                continue

            # Skip if already messaged
            if await asyncio.to_thread(was_ever_messaged, phone_formatted, params.account):
                state.progress.skipped += 1
                continue

            # Update current contact
            state.progress.current_contact = QueueContact(
                phone=phone_formatted,
                owner_name=item.get("owner_name"),
                building=item.get("building"),
                unit=item.get("unit"),
            )

            # Send message via bot.py (sync requests.post, run in thread)
            result = await asyncio.to_thread(
                _sync_send, phone_formatted, item.get("message", ""), params.account
            )

            # Log result
            await asyncio.to_thread(
                log_message,
                campaign_id=campaign_id,
                phone=phone_formatted,
                owner_name=item.get("owner_name", ""),
                building=item.get("building", ""),
                unit=item.get("unit", ""),
                template_type=item.get("template_type", ""),
                message=item.get("message", ""),
                status=result.get("status", "failed"),
                error=result.get("error", ""),
                wa_account=params.account,
            )

            # Update progress
            status = result.get("status", "failed")
            if status == "sent":
                state.progress.sent += 1
            elif status == "failed":
                state.progress.failed += 1
            elif status == "not_on_whatsapp":
                state.progress.not_on_wa += 1

            rate_limiter.record_send_attempt(status, item.get("template_type", ""))
            state.progress.messages_today = await asyncio.to_thread(get_today_send_count)
            state.progress.elapsed_seconds = int(
                (datetime.now() - start_time).total_seconds()
            )

            # Delays
            if not params.no_limits and status == "sent":
                paused = await rate_limiter.check_mandatory_pause()
                if paused:
                    state.progress.status = "paused"
                await rate_limiter.wait_between_messages()
                state.progress.status = "running"
            elif params.no_limits and status == "sent":
                await asyncio.sleep(3)

        if state.progress.status == "running":
            state.progress.status = "done"

    except asyncio.CancelledError:
        state.progress.status = "stopped"
    except Exception as e:
        state.progress.status = "error"
        state.progress.error = str(e)[:300]


def _sync_send(phone: str, message: str, account: str) -> dict:
    """Synchronous wrapper around bot.py's send_message (which uses requests.post).
    Called via asyncio.to_thread to avoid blocking the event loop."""
    import requests
    from whatsapp_bot.bot import get_baileys_url

    baileys_url = get_baileys_url(account)
    try:
        r = requests.post(
            f"{baileys_url}/send/text",
            json={"phone": phone, "message": message},
            timeout=30,
        )
        if r.status_code == 503:
            return {"status": "failed", "phone": phone, "error": "Server not connected"}
        data = r.json()
        if data.get("success"):
            return {"status": "sent", "phone": phone}
        err = data.get("error", "")
        if "not registered" in err:
            return {"status": "not_on_whatsapp", "phone": phone}
        return {"status": "failed", "phone": phone, "error": err}
    except Exception as e:
        return {"status": "failed", "phone": phone, "error": str(e)[:200]}
