"""
alerts.py — STUB for Phase 3

Phase 3: Push matched listing alerts to Telegram channel or console.

Planned triggers:
- New listing appears on Bayut/PF that matches a known owner
- Owner's unit price drops below market median
- Owner's unit relisted after being delisted

TODO Phase 3 implementation:
- python-telegram-bot or httpx POST to Telegram Bot API
- Configurable channel IDs per agent / building
- Deduplication: don't alert twice for the same listing+owner pair
"""

from typing import Optional


def send_telegram_alert(
    match_result: dict,
    channel_id: Optional[str] = None,
) -> bool:
    """TODO Phase 3 — post a match alert to a Telegram channel."""
    raise NotImplementedError("Phase 3: Telegram alerts not yet implemented.")


def print_alert(match_result: dict) -> None:
    """Console fallback alert — available now."""
    conf = match_result.get("confidence", 0)
    emoji = "✅" if conf >= 0.9 else "⚠️" if conf >= 0.6 else "❓"
    print(
        f"\n{emoji} LISTING MATCH — {conf * 100:.0f}% confidence\n"
        f"   Building : {match_result.get('building')}\n"
        f"   Unit     : {match_result.get('unit')}\n"
        f"   Owner    : {match_result.get('owner_name')}\n"
        f"   Phone    : {match_result.get('phone_display')}\n"
        f"   Match    : {match_result.get('match_type')}\n"
    )
