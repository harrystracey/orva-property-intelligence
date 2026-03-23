"""
Message Log - CSV-based sent/failed/pending tracking
Provides dedup: never message same phone within 30 days, never retry not_on_whatsapp.
"""

import csv
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict

LOG_FILE = Path(__file__).parent / "message_log.csv"
REPLY_LOG_FILE = Path(__file__).parent / "reply_log.csv"
LOG_HEADERS = [
    'timestamp', 'campaign_id', 'wa_account', 'phone', 'owner_name', 'building',
    'unit', 'template_type', 'message', 'status', 'error'
]
REPLY_LOG_HEADERS = ['phone', 'detected_at']


def initialize_log():
    """Create log file if it doesn't exist."""
    if not LOG_FILE.exists():
        with open(LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
            writer.writeheader()
        print(f"[LOG] Created message log: {LOG_FILE}")


def log_message(
    campaign_id: str,
    phone: str,
    owner_name: str,
    building: str,
    unit: str,
    template_type: str,
    message: str,
    status: str,  # 'sent', 'failed', 'not_on_whatsapp'
    error: str = '',
    wa_account: str = '1',
):
    """Append a message send attempt to the log."""
    initialize_log()

    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
        writer.writerow({
            'timestamp': datetime.now().isoformat(),
            'campaign_id': campaign_id,
            'wa_account': wa_account,
            'phone': phone,
            'owner_name': owner_name,
            'building': building,
            'unit': unit,
            'template_type': template_type,
            'message': message,
            'status': status,
            'error': error
        })


def was_messaged_recently(phone: str, days: int = 30) -> bool:
    """
    Check if a phone was messaged within the last N days.
    Returns True if phone should be SKIPPED (already messaged recently).
    """
    if not LOG_FILE.exists():
        return False
    
    cutoff = datetime.now() - timedelta(days=days)
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['phone'] == phone:
                try:
                    ts = datetime.fromisoformat(row['timestamp'])
                    if ts >= cutoff:
                        return True
                except Exception:
                    pass
    
    return False


def was_ever_messaged(phone: str, wa_account: str = '1') -> bool:
    """
    Check if a phone was ever messaged by this WA account.
    Returns True if phone should be SKIPPED (we have any prior conversation).
    Old rows without wa_account default to account '1' for backward compat.
    """
    if not LOG_FILE.exists():
        return False
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['phone'] == phone and row.get('wa_account', '1') == wa_account:
                return True
    return False


def is_not_on_whatsapp(phone: str) -> bool:
    """
    Check if phone was marked as not_on_whatsapp in any previous attempt.
    Returns True if phone should be SKIPPED (not on WhatsApp).
    """
    if not LOG_FILE.exists():
        return False
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['phone'] == phone and row['status'] == 'not_on_whatsapp':
                return True
    
    return False


def should_skip_phone(phone: str, days_window: int = 30, wa_account: str = '1') -> tuple[bool, str]:
    """
    Check if phone should be skipped (dedup logic).
    Returns (should_skip: bool, reason: str).
    Skips if ever messaged by this account, or not on WhatsApp (global).
    """
    if is_not_on_whatsapp(phone):
        return (True, 'not_on_whatsapp')

    if was_ever_messaged(phone, wa_account=wa_account):
        return (True, 'ever_messaged')

    return (False, '')


def get_send_stats(days: Optional[int] = None) -> Dict:
    """
    Get send statistics from the log.
    If days is specified, only count messages sent in last N days.
    """
    if not LOG_FILE.exists():
        return {
            'total': 0,
            'sent': 0,
            'failed': 0,
            'not_on_whatsapp': 0
        }
    
    cutoff = None
    if days:
        cutoff = datetime.now() - timedelta(days=days)
    
    stats = {
        'total': 0,
        'sent': 0,
        'failed': 0,
        'not_on_whatsapp': 0
    }
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if cutoff:
                try:
                    ts = datetime.fromisoformat(row['timestamp'])
                    if ts < cutoff:
                        continue
                except:
                    continue
            
            stats['total'] += 1
            status = row['status']
            if status in stats:
                stats[status] += 1
    
    return stats


def _init_reply_log():
    """Create reply log file if it doesn't exist."""
    if not REPLY_LOG_FILE.exists():
        with open(REPLY_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=REPLY_LOG_HEADERS)
            writer.writeheader()


def record_reply(phone: str) -> None:
    """Record that we detected a reply from this phone (best-effort tracking)."""
    _init_reply_log()
    with open(REPLY_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=REPLY_LOG_HEADERS)
        writer.writerow({'phone': phone, 'detected_at': datetime.now().isoformat()})


def get_reply_stats(days: Optional[int] = None) -> Dict:
    """
    Get reply statistics (distinct phones we detected as having replied).
    If days is specified, only count replies detected in last N days.
    """
    if not REPLY_LOG_FILE.exists():
        return {'replied': 0}
    cutoff = None
    if days:
        cutoff = datetime.now() - timedelta(days=days)
    seen = set()
    with open(REPLY_LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if cutoff:
                try:
                    ts = datetime.fromisoformat(row['detected_at'])
                    if ts < cutoff:
                        continue
                except Exception:
                    continue
            seen.add(row['phone'])
    return {'replied': len(seen)}


def get_sent_entries_for_reply_check(days: int = 90, limit: int = 5000) -> List[Dict]:
    """
    Get list of sent messages (phone, timestamp) for reply-checking.
    Returns most recent first, up to limit, only status=='sent'.
    """
    if not LOG_FILE.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    entries = []
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('status') != 'sent':
                continue
            try:
                ts = datetime.fromisoformat(row['timestamp'])
                if ts < cutoff:
                    continue
            except Exception:
                continue
            entries.append({
                'phone': row['phone'],
                'timestamp': row['timestamp'],
                'owner_name': row.get('owner_name', ''),
                'template_type': row.get('template_type', ''),
                'building': row.get('building', ''),
                'unit': row.get('unit', ''),
            })
    # Dedupe by phone (keep most recent per phone)
    by_phone = {}
    for e in entries:
        by_phone[e['phone']] = e
    out = sorted(by_phone.values(), key=lambda x: x['timestamp'], reverse=True)
    return out[:limit]


def get_today_send_count() -> int:
    """Get count of successfully sent messages today (for daily cap check)."""
    if not LOG_FILE.exists():
        return 0
    
    today = datetime.now().date()
    count = 0
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['status'] == 'sent':
                try:
                    ts = datetime.fromisoformat(row['timestamp'])
                    if ts.date() == today:
                        count += 1
                except:
                    pass
    
    return count


def get_recent_messages(limit: int = 100) -> List[Dict]:
    """Get the most recent N messages from the log."""
    if not LOG_FILE.exists():
        return []
    
    messages = []
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        messages = list(reader)
    
    # Reverse to get most recent first
    return messages[-limit:][::-1] if messages else []
