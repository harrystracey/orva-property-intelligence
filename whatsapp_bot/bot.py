"""
WhatsApp Bot - Playwright automation for WhatsApp Web
Connects to user's Chrome via CDP (same pattern as Property Monitor scraper).
"""

import asyncio
import re
import random
from playwright.async_api import async_playwright, Page, Browser
from typing import Optional, Dict


CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"


async def connect_to_whatsapp() -> tuple:
    """
    Connect to already-running Chrome and find WhatsApp Web tab.
    Returns (playwright, browser, page)
    """
    print("[CONNECT] Connecting to Chrome via CDP...")
    
    playwright = await async_playwright().start()
    
    try:
        browser = await playwright.chromium.connect_over_cdp(CDP_URL)
        print("[OK] Connected to Chrome")
    except Exception as e:
        print(f"[ERROR] Could not connect to Chrome: {e}")
        print(f"  Make sure Chrome is running with --remote-debugging-port={CDP_PORT}")
        print(f"  Command: chrome.exe --remote-debugging-port={CDP_PORT}")
        raise
    
    # Find WhatsApp Web tab
    page = None
    for context in browser.contexts:
        for p in context.pages:
            if 'web.whatsapp.com' in p.url:
                page = p
                print(f"[OK] Found WhatsApp Web tab: {p.url}")
                break
        if page:
            break
    
    if not page:
        print("[ERROR] WhatsApp Web tab not found.")
        print("  Please open web.whatsapp.com in Chrome and log in first.")
        raise Exception("WhatsApp Web tab not found")
    
    return playwright, browser, page


async def reconnect_to_whatsapp(playwright, browser) -> tuple:
    """
    Close the existing browser and stop Playwright (ignore errors), then connect fresh via CDP.
    Use after a long batch pause when the CDP connection may have died.
    Returns (playwright, browser, page) from a new connection.
    """
    try:
        await browser.close()
    except Exception:
        pass
    try:
        await asyncio.sleep(0.2)
        await playwright.stop()
    except Exception:
        pass
    return await connect_to_whatsapp()


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


async def send_message(page: Page, phone_number: str, message: str) -> Dict:
    """
    Send a WhatsApp message to a phone number.
    
    IMPORTANT: Multi-line messages are sent as ONE message using Shift+Enter for line breaks.
    Enter is only pressed ONCE at the very end to send the complete message.
    
    Returns:
        Dict with 'status' ('sent', 'failed', 'not_on_whatsapp', 'existing_chat') and optionally 'error'.
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
        if has_messages:
            print(f"  [SKIP] {phone_number} already has a chat")
            return {'status': 'existing_chat', 'phone': phone_number}
        
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
