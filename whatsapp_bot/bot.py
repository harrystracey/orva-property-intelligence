"""
WhatsApp Bot - Baileys HTTP bridge
Sends messages via the local Baileys Node.js server (http://127.0.0.1:3001).
Playwright/CDP functions retained for chat scanning (local Windows use only).
"""

import asyncio
import re
import random
import requests
from playwright.async_api import async_playwright, Page, Browser
from typing import Optional, Dict


BAILEYS_ACCOUNTS = {
    "1": "http://127.0.0.1:3001",
    "2": "http://127.0.0.1:3002",
}
BAILEYS_URL = BAILEYS_ACCOUNTS["1"]  # default


def get_baileys_url(account: str = "1") -> str:
    return BAILEYS_ACCOUNTS.get(str(account), BAILEYS_ACCOUNTS["1"])


async def connect_to_whatsapp(account: str = "1") -> tuple:
    """
    Check that the Baileys server is running and WhatsApp is connected.
    Returns (None, None, None) — page param kept for run_campaign.py compatibility.
    """
    url = get_baileys_url(account)
    port = url.split(":")[-1]
    try:
        r = requests.get(f"{url}/status", timeout=5)
        data = r.json()
        if data.get("connected"):
            print(f"[OK] Baileys account {account} connected — phone: {data.get('phone')}")
            return None, None, None
        elif data.get("qr_available"):
            raise Exception(f"WhatsApp account {account} not connected. Open ORVA → WhatsApp page → scan QR.")
        else:
            raise Exception(f"WhatsApp account {account} not connected and no QR yet. Wait a moment and retry.")
    except requests.exceptions.ConnectionError:
        raise Exception(
            f"Baileys server not running on port {port}. SSH to server and run: pm2 start baileys-wa-{account}"
        )


async def reconnect_to_whatsapp(playwright, browser, account: str = "1") -> tuple:
    """
    Baileys auto-reconnects on its own. Just re-verify status.
    playwright/browser params kept for run_campaign.py compatibility — ignored.
    """
    return await connect_to_whatsapp(account)


def format_phone_for_whatsapp(phone_primary: str) -> Optional[str]:
    """
    Format phone number for WhatsApp (international format).
    UAE numbers: 971 + 9 digits (starting with 5).
    If multiple numbers are in the string (e.g. "971...; 971..."), use only the first.
    """
    if not phone_primary:
        return None

    raw = str(phone_primary).replace('.0', '').strip()
    if not raw or raw.lower() == 'nan':
        return None

    # Take first number only (CSV often has "971xxx; 971yyy" or "971xxx, 971yyy" or space-separated)
    parts = re.split(r'[;\s,|]+', raw)
    first = next((p.strip() for p in parts if p.strip()), raw)
    phone = ''.join(c for c in first if c.isdigit())
    
    if not phone:
        return None
    
    # Already has 971 country code (971 + 9 digit number = 12 digits total)
    if phone.startswith('971') and len(phone) == 12:
        return phone
    
    # UAE number (9 digits starting with 5)
    if len(phone) == 9 and phone[0] == '5':
        return f"971{phone}"
    
    # Already has country code (other lengths)
    if len(phone) >= 10:
        return phone
    
    # Assume UAE and prepend 971
    return f"971{phone}"


async def send_message(page: Page, phone_number: str, message: str, skip_chat_check: bool = False, account: str = "1") -> Dict:
    """
    Send a WhatsApp message via the Baileys HTTP server.
    page param retained for run_campaign.py compatibility — ignored.
    account: "1" or "2" — selects which Baileys instance to use.
    Returns Dict with 'status': 'sent' | 'failed' | 'not_on_whatsapp'
    """
    baileys_url = get_baileys_url(account)
    try:
        print(f"[SEND] Baileys account {account} → {phone_number}")
        r = requests.post(
            f"{baileys_url}/send/text",
            json={"phone": phone_number, "message": message},
            timeout=30,
        )
        if r.status_code == 503:
            raise Exception("Baileys server not connected")
        data = r.json()
        if data.get("success"):
            print(f"  [OK] Sent to {phone_number}")
            return {"status": "sent", "phone": phone_number}
        err = data.get("error", "")
        if "not registered" in err:
            print(f"  [SKIP] {phone_number} not on WhatsApp")
            return {"status": "not_on_whatsapp", "phone": phone_number}
        return {"status": "failed", "phone": phone_number, "error": err}
    except Exception as e:
        print(f"  [FAIL] {phone_number}: {str(e)[:100]}")
        return {"status": "failed", "phone": phone_number, "error": str(e)[:200]}


async def _send_message_playwright(page: Page, phone_number: str, message: str, skip_chat_check: bool = False) -> Dict:
    """
    Legacy Playwright-based send (local Windows use only — kept for reference).
    """
    try:
        url = f"https://web.whatsapp.com/send?phone={phone_number}"
        print(f"[SEND] Opening chat: {phone_number}")
        
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)

        # Wait for WhatsApp to finish rendering (avoid white screen). Poll for chat input OR "not on WhatsApp" popup.
        async def _wait_for_chat_ready(max_sec: int) -> bool:
            for _ in range(max_sec):
                await asyncio.sleep(1)
                page_text = await page.evaluate('() => document.body.innerText')
                if "isn't on WhatsApp" in page_text or "is not on WhatsApp" in page_text or "isn\u2019t on WhatsApp" in page_text or "number shared via url is invalid" in page_text:
                    return True
                try:
                    inp = await page.query_selector('div[contenteditable="true"][data-tab="10"]')
                    if inp:
                        return True
                except Exception:
                    pass
            return False

        print(f"  [WAIT] Waiting for page to load...")
        ready = await _wait_for_chat_ready(30)
        if not ready:
            print(f"  [RELOAD] White screen detected; reloading page...")
            await page.reload(wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)
            ready = await _wait_for_chat_ready(25)
        if not ready:
            print(f"  [WARN] Page may still be loading (white screen); continuing anyway...")

        # Check if number is not on WhatsApp (popup/dialog appears)
        # Use JS body text check so curly apostrophe (U+2019) in "isn't" is detected
        print(f"  [CHECK] Looking for 'not on WhatsApp' popup...")
        page_text = await page.evaluate('() => document.body.innerText')
        not_on_wa = (
            "isn\u2019t on WhatsApp" in page_text or   # curly apostrophe (what WhatsApp uses)
            "isn't on WhatsApp" in page_text or       # straight apostrophe (fallback)
            "is not on WhatsApp" in page_text or
            "number shared via url is invalid" in page_text
        )
        
        if not_on_wa:
            print(f"  [POPUP] Detected 'not on WhatsApp' message")
            print(f"  [SKIP] {phone_number} not on WhatsApp")
            
            # Click OK button via JavaScript (robust across DOM changes)
            clicked = await page.evaluate('''() => {
                const btns = document.querySelectorAll('button, div[role="button"]');
                for (const btn of btns) {
                    if (btn.textContent.trim() === "OK") {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            if clicked:
                await asyncio.sleep(0.5)
                print(f"  [OK] Dismissed popup")
            
            return {'status': 'not_on_whatsapp', 'phone': phone_number}
        
        # Find chat input box (data-tab="10" = conversation input only, NOT search bar)
        try:
            input_box = await page.wait_for_selector(
                'div[contenteditable="true"][data-tab="10"]',
                timeout=10000
            )
        except Exception:
            # Input box not found -- check for popup again (may have appeared late)
            page_text_late = await page.evaluate('() => document.body.innerText')
            not_on_wa_late = (
                "isn\u2019t on WhatsApp" in page_text_late or
                "isn't on WhatsApp" in page_text_late or
                "is not on WhatsApp" in page_text_late or
                "number shared via url is invalid" in page_text_late
            )
            if not_on_wa_late:
                print(f"  [POPUP] Detected on retry")
                print(f"  [SKIP] {phone_number} not on WhatsApp")
                clicked = await page.evaluate('''() => {
                    const btns = document.querySelectorAll('button, div[role="button"]');
                    for (const btn of btns) {
                        if (btn.textContent.trim() === "OK") {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                if clicked:
                    await asyncio.sleep(0.5)
                return {'status': 'not_on_whatsapp', 'phone': phone_number}
            print(f"  [FAIL] Could not find input box for {phone_number}")
            return {
                'status': 'failed',
                'phone': phone_number,
                'error': 'Input box not found (selectors may have changed)'
            }
        
        # Wait 3s for messages to fully render, then check for existing chat.
        await asyncio.sleep(3)
        has_messages = await page.evaluate('''() => {
            // Require >= 2 [data-id] so we don't treat one stray UI element as "has messages"
            // (empty/new chats can have a single data-id on placeholder or input area)
            if (document.querySelectorAll('[data-id]').length >= 2) return true;
            // Timestamp spans = real message bubbles
            if (document.querySelectorAll('span[data-testid="msg-time"]').length > 0) return true;
            // Legacy class names (older WA Web builds)
            const legacy = ['[data-testid="msg-container"]','div.message-in','div.message-out','[data-testid="conv-msg-true"]'];
            for (const sel of legacy) {
                if (document.querySelectorAll(sel).length > 0) return true;
            }
            return false;
        }''')
        if has_messages and not skip_chat_check:
            print(f"  [SKIP] {phone_number} already has a chat")
            return {'status': 'existing_chat', 'phone': phone_number}
        elif has_messages:
            print(f"  [FOLLOWUP] {phone_number} has existing chat - sending follow-up")
        
        # Human-like typing: 30-120ms per char, word-level pauses every 4-8 words
        print(f"  [TYPE] Typing message ({len(message)} chars)...")
        word_count = 0
        next_word_pause_at = random.randint(4, 8)
        for char in message:
            if char == '\n':
                await page.keyboard.down('Shift')
                await page.keyboard.press('Enter')
                await page.keyboard.up('Shift')
                await asyncio.sleep(random.uniform(0.05, 0.15))
            else:
                await input_box.type(char, delay=random.randint(30, 120))
                if char == ' ':
                    word_count += 1
                    if word_count >= next_word_pause_at:
                        await asyncio.sleep(random.uniform(0.1, 0.4))
                        next_word_pause_at = word_count + random.randint(4, 8)
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Brief pause before sending
        await asyncio.sleep(random.uniform(1.0, 3.0))
        
        # Send entire message with Enter (only pressed ONCE at the end)
        print(f"  [SEND] Pressing Enter to send...")
        await page.keyboard.press('Enter')
        
        # Wait for message to appear in chat
        await asyncio.sleep(2)
        
        print(f"  [OK] Message sent to {phone_number}")
        return {'status': 'sent', 'phone': phone_number}
    
    except Exception as e:
        print(f"  [FAIL] Error sending to {phone_number}: {str(e)[:100]}")
        return {
            'status': 'failed',
            'phone': phone_number,
            'error': str(e)[:200]
        }


async def verify_whatsapp_ready(page: Page) -> bool:
    """Check if WhatsApp Web is logged in and ready (not stuck on white screen). Reloads once if stuck."""
    selector = 'div[contenteditable="true"][data-tab="3"]'  # Search box
    for attempt in range(2):
        try:
            await page.wait_for_selector(selector, timeout=20000)
            print("[OK] WhatsApp Web is ready")
            return True
        except Exception:
            if attempt == 0:
                print("[WARN] White screen? Reloading WhatsApp tab...")
                try:
                    await page.goto("https://web.whatsapp.com", wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(3)
                except Exception:
                    pass
            else:
                print("[WARN] WhatsApp Web may not be fully loaded or logged in (white screen?)")
                return False
    return False


async def check_replies_for_sent_messages(
    page: Page,
    sent_entries: list,
    record_reply_callback,
    delay_between_chats: float = 2.0,
) -> Dict:
    """
    Open each chat we've sent to and detect if there's at least one incoming message.
    Best-effort: WhatsApp Web DOM may change. Calls record_reply_callback(phone) for each reply detected.
    sent_entries: list of dicts with 'phone' key.
    Returns dict with 'checked': N, 'replied': M, 'errors': list of error strings.
    """
    results = {'checked': 0, 'replied': 0, 'errors': []}
    for entry in sent_entries:
        phone = entry.get('phone')
        if not phone:
            continue
        results['checked'] += 1
        try:
            url = f"https://web.whatsapp.com/send?phone={phone}"
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)
            # Check for "not on WhatsApp" so we don't count as reply
            page_text = await page.evaluate('() => document.body.innerText')
            if "isn't on WhatsApp" in page_text or "is not on WhatsApp" in page_text:
                await asyncio.sleep(delay_between_chats)
                continue
            # Detect incoming messages: WhatsApp Web uses message-in (their) vs message-out (ours)
            has_incoming = await page.evaluate('''() => {
                const incoming = document.querySelectorAll('[data-id*="false_"]');
                return incoming && incoming.length > 0;
            }''')
            if has_incoming:
                try:
                    record_reply_callback(phone)
                    results['replied'] += 1
                except Exception:
                    pass
        except Exception as e:
            results['errors'].append(f"{phone}: {str(e)[:80]}")
        await asyncio.sleep(delay_between_chats)
    return results

async def scan_chat_messages(page, phone: str) -> dict:
    """
    Open a WhatsApp chat and read all visible messages (both sent and received).
    WhatsApp Web virtualises the list so only ~50-100 recent messages are rendered.
    Returns dict with incoming/outgoing lists and summary fields.
    """
    url = f"https://web.whatsapp.com/send?phone={phone}"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)

    # Wait for at least one message element to render
    try:
        await page.wait_for_selector("[data-id]", timeout=10000)
    except Exception:
        pass  # No messages rendered � proceed anyway

    # Check not-on-WhatsApp
    page_text = await page.evaluate("() => document.body.innerText")
    if ("isn’t on WhatsApp" in page_text or
            "isn't on WhatsApp" in page_text or
            "is not on WhatsApp" in page_text or
            "number shared via url is invalid" in page_text):
        return {"messages": [], "incoming": [], "outgoing": [],
                "incoming_count": 0, "outgoing_count": 0,
                "last_reply_text": "", "last_reply_at": "",
                "last_sent_at": "", "not_on_whatsapp": True}

    js = """
(function() {
    var msgs = [];
    var els = document.querySelectorAll('[data-id]');
    els.forEach(function(el) {
        var id = el.getAttribute('data-id') || '';
        var dir = id.startsWith('true_') ? 'out' : (id.startsWith('false_') ? 'in' : null);
        if (!dir) return;
        var textEl = el.querySelector('span.selectable-text');
        var text = textEl ? textEl.innerText.trim() : '';
        if (!text) return;
        var timeEl = el.querySelector('span[data-testid="msg-time"]');
        var time = timeEl ? timeEl.innerText.trim() : '';
        msgs.push({dir: dir, text: text, time: time});
    });
    return JSON.stringify(msgs);
})()
"""
    import json as _json
    raw = await page.evaluate(js)
    messages = _json.loads(raw) if raw else []

    if not messages:
        import sys as _sys
        print(f"WARN: 0 messages for {phone}", file=_sys.stderr, flush=True)

    incoming = [m for m in messages if m["dir"] == "in"]
    outgoing = [m for m in messages if m["dir"] == "out"]

    return {
        "messages": messages,
        "incoming": incoming,
        "outgoing": outgoing,
        "incoming_count": len(incoming),
        "outgoing_count": len(outgoing),
        "last_reply_text": incoming[-1]["text"] if incoming else "",
        "last_reply_at": incoming[-1]["time"] if incoming else "",
        "last_sent_at": outgoing[-1]["time"] if outgoing else "",
        "not_on_whatsapp": False,
    }


async def scan_all_bot_chats(page, phones: list, delay: float = 2.5,
                              progress_callback=None) -> list:
    """
    Scan all bot-messaged chats and return a list of scan result dicts.
    phones: list of dicts with at least 'phone' and optionally 'owner_name'.
    progress_callback(done, total): called after each chat for UI updates.
    """
    results = []
    total = len(phones)
    for i, entry in enumerate(phones):
        phone = entry.get("phone", "")
        if not phone:
            continue
        try:
            scan = await scan_chat_messages(page, phone)
            scan["phone"] = phone
            scan["owner_name"] = entry.get("owner_name", "")
            results.append(scan)
        except Exception as e:
            results.append({
                "phone": phone,
                "owner_name": entry.get("owner_name", ""),
                "messages": [], "incoming": [], "outgoing": [],
                "incoming_count": 0, "outgoing_count": 0,
                "last_reply_text": "", "last_reply_at": "",
                "last_sent_at": "", "not_on_whatsapp": False,
                "error": str(e)[:120],
            })
        if progress_callback:
            progress_callback(i + 1, total)
        await asyncio.sleep(delay)
    return results
