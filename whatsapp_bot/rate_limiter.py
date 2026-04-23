"""
Rate Limiter - Delay logic, daily caps, pause intervals
Enforces safety rules to avoid WhatsApp ban.
"""

import json
import random
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Tuple

from message_log import get_today_send_count

# Cooldown after a restriction: reduced caps for 7 days
COOLDOWN_FILE = Path(__file__).resolve().parent.parent / "client_data" / "last_restriction.json"
COOLDOWN_DAYS = 7
COOLDOWN_CAPS = {1: 5, 2: 5, 3: 10, 4: 10, 5: 20, 6: 20, 7: 20}  # days since restriction -> cap

# Persisted campaign start date for ramp-up (Day 1 = first run ever)
CAMPAIGN_START_FILE = Path(__file__).resolve().parent.parent / "client_data" / "campaign_start.json"


# =============================================================================
# SAFETY CONSTANTS (NON-OVERRIDABLE)
# =============================================================================

DAILY_CAP = 36
MIN_DELAY_SECONDS = 45
MAX_DELAY_SECONDS = 180
EXTENDED_PAUSE_CHANCE = 0.15  # 15% chance of extended pause
EXTENDED_PAUSE_MIN = 60
EXTENDED_PAUSE_MAX = 240  # up to 4 min
# Batch: send 3-6 messages then long pause 20-50 min
BATCH_SIZE_MIN = 3
BATCH_SIZE_MAX = 6
LONG_PAUSE_MIN = 20 * 60   # 20 minutes
LONG_PAUSE_MAX = 50 * 60   # 50 minutes
DAILY_CAP_MIN = 36
DAILY_CAP_MAX = 36
MAX_CONSECUTIVE_FAILURES = 999999  # Disabled: no stop on consecutive failures
SESSION_TIME_LIMIT_HOURS = 3

# Gradual ramp-up (first 7 days)
RAMP_UP_SCHEDULE = {
    1: 5,
    2: 10,
    3: 15,
    4: 25,
    5: 30,
    6: 35,
    7: 36,  # From day 7 onward
}


def get_last_restriction_date() -> Optional[datetime]:
    """Return date of last restriction from cooldown file, or None."""
    if not COOLDOWN_FILE.exists():
        return None
    try:
        with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        s = data.get("date")
        if s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass
    return None


def mark_restriction_now() -> bool:
    """Record current date as last restriction. Call when you get restricted."""
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump({"date": datetime.now().date().isoformat()}, f, indent=2)
        return True
    except Exception:
        return False


def _cooldown_days_since_restriction() -> Optional[int]:
    """Days since last restriction (1-7), or None if not in cooldown."""
    d = get_last_restriction_date()
    if not d:
        return None
    ref_date = d.date() if hasattr(d, "date") else d
    days = (datetime.now().date() - ref_date).days
    if days < 0 or days > COOLDOWN_DAYS - 1:
        return None
    return days + 1  # 1-indexed for COOLDOWN_CAPS


def get_campaign_start_date() -> datetime:
    """Return persisted campaign start date; if missing, write today and return it."""
    if CAMPAIGN_START_FILE.exists():
        try:
            with open(CAMPAIGN_START_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            s = data.get("date")
            if s:
                return datetime.fromisoformat(s).replace(tzinfo=None)
        except Exception:
            pass
    CAMPAIGN_START_FILE.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now().date().isoformat()
    with open(CAMPAIGN_START_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": today}, f, indent=2)
    return datetime.fromisoformat(today)


class RateLimiter:
    """Enforces rate limits, delays, and safety pauses."""

    def __init__(self, campaign_start_date: Optional[datetime] = None, override_limit: bool = False):
        self.consecutive_failures = 0
        self.messages_in_current_session = 0
        self.session_start_time = datetime.now()
        self.campaign_start_date = campaign_start_date if campaign_start_date is not None else get_campaign_start_date()
        self.last_message_time = None
        self.last_template_type = None
        self.template_repeat_count = 0
        self.override_limit = override_limit
        self._cooldown_day: Optional[int] = _cooldown_days_since_restriction()
        self._cooldown_double_delays: bool = self._cooldown_day is not None and self._cooldown_day <= 2
        self._random_daily_cap: int = random.randint(DAILY_CAP_MIN, DAILY_CAP_MAX)
        self._batch_size: int = random.randint(BATCH_SIZE_MIN, BATCH_SIZE_MAX)
        self._messages_since_pause: int = 0

    def reset(self) -> None:
        """
        Deprecated. Retained as a no-op for backwards compatibility.

        Why: previously this zeroed a session-local counter that overrode the
        persistent CSV count. Two overlapping override_limit sessions could each
        start at 0 and together exceed the daily cap -> ban risk. The persistent
        CSV is now the single source of truth; override_limit still skips ramp-up.
        """
        return

    def get_daily_cap(self) -> int:
        """Get daily cap. Cooldown/ramp-up override; mature schedule uses 32-38 random."""
        if self._cooldown_day is not None:
            cap = COOLDOWN_CAPS.get(self._cooldown_day, DAILY_CAP)
            return min(cap, DAILY_CAP)
        days_since_start = (datetime.now().date() - self.campaign_start_date.date()).days + 1
        if days_since_start <= 0:
            days_since_start = 1
        if self.override_limit or days_since_start >= 8:
            return self._random_daily_cap
        return RAMP_UP_SCHEDULE.get(days_since_start, DAILY_CAP)
    
    def can_send_today(self) -> tuple[bool, str]:
        """
        Check if we can send another message today.
        Returns (can_send: bool, reason: str)
        Reads the persistent CSV as the single source of truth so concurrent
        sessions cannot each start from 0 and double the cap.
        """
        today_count = get_today_send_count()
        daily_cap = self.get_daily_cap()
        
        if today_count >= daily_cap:
            return (False, f"Daily cap reached ({today_count}/{daily_cap})")
        
        return (True, '')
    
    def should_stop_session(self) -> tuple[bool, str]:
        """Check if session should be stopped (time limit). Consecutive-failure stop disabled."""
        # Check session time limit
        elapsed_hours = (datetime.now() - self.session_start_time).total_seconds() / 3600
        if elapsed_hours >= SESSION_TIME_LIMIT_HOURS:
            return (True, f"Session time limit reached ({elapsed_hours:.1f}h)")
        
        return (False, '')
    
    async def wait_between_messages(self):
        """Apply random delay between messages with occasional extended pauses."""
        delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        if random.random() < EXTENDED_PAUSE_CHANCE:
            delay = random.uniform(EXTENDED_PAUSE_MIN, EXTENDED_PAUSE_MAX)
            print(f"  [PAUSE] Extended pause: {delay:.0f}s (human distraction simulation)")
        else:
            print(f"  [WAIT] {delay:.0f}s until next message...")
        if self._cooldown_double_delays:
            delay = delay * 2
            print(f"  [COOLDOWN] Delays doubled: {delay:.0f}s")
        await asyncio.sleep(delay)
    
    async def check_mandatory_pause(self) -> bool:
        """After each batch (3-6 messages), take a long pause (20-50 min). Returns True if a pause occurred."""
        if self.messages_in_current_session > 0 and self._messages_since_pause >= self._batch_size:
            pause_duration = random.uniform(LONG_PAUSE_MIN, LONG_PAUSE_MAX)
            mins = int(pause_duration / 60)
            print()
            print("=" * 70)
            print(f"  BATCH COMPLETE: {self._messages_since_pause} messages — pausing {mins} minutes")
            print("=" * 70)
            print()
            await asyncio.sleep(pause_duration)
            self._messages_since_pause = 0
            self._batch_size = random.randint(BATCH_SIZE_MIN, BATCH_SIZE_MAX)
            print(f"  [RESUME] Next batch size: {self._batch_size} messages")
            return True
        return False
    
    def record_send_attempt(self, status: str, template_type: str):
        """Update session state after a send attempt."""
        if status == 'sent':
            self.consecutive_failures = 0
            self.messages_in_current_session += 1
            self._messages_since_pause += 1
        elif status in ('failed', 'not_on_whatsapp'):
            self.consecutive_failures += 1
        
        # Track template rotation (avoid same template 3x in a row)
        if template_type == self.last_template_type:
            self.template_repeat_count += 1
        else:
            self.template_repeat_count = 1
            self.last_template_type = template_type
        
        self.last_message_time = datetime.now()
    
    def should_rotate_template(self) -> bool:
        """Check if we should force-rotate template (same message 3x in a row)."""
        return self.template_repeat_count >= 3
    
    def get_session_stats(self) -> Dict:
        """Get current session statistics."""
        elapsed = datetime.now() - self.session_start_time
        return {
            'messages_sent': self.messages_in_current_session,
            'consecutive_failures': self.consecutive_failures,
            'session_duration_mins': int(elapsed.total_seconds() / 60),
            'daily_cap': self.get_daily_cap(),
            'today_total': get_today_send_count()
        }
