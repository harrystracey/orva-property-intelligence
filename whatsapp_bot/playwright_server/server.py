"""
ORVA Playwright WhatsApp Server
FastAPI + Playwright + Chromium on Xvfb (Linux server).
Identical HTTP API to Baileys server — bot.py requires zero changes.
Listens on http://127.0.0.1:{WA_PORT} (default 3001).

Env vars:
  WA_PORT     — HTTP port (default 3001)
  WA_DISPLAY  — X display for Xvfb (default :99)
  WA_PROFILE  — Chrome profile subdirectory name (default profile1)
  WA_DATA_DIR — Path to data/ dir for wa_status.json (default ../../data)
"""

import asyncio
import base64
import json
import logging
import os
import random
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
PORT = int(os.environ.get("WA_PORT", "3001"))
DISPLAY = os.environ.get("WA_DISPLAY", ":99")
PROFILE_NAME = os.environ.get("WA_PROFILE", "profile1")
ACCOUNT = os.environ.get("WA_ACCOUNT", "1")

_here = Path(__file__).parent
CHROME_PROFILE_DIR = _here / "chrome_profile" / PROFILE_NAME
DATA_DIR = Path(os.environ.get("WA_DATA_DIR", str(_here / ".." / ".." / "data")))
STATUS_FILE = DATA_DIR / "wa_status.json"

CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Fake microphone WAV path — must match the --use-file-for-fake-audio-capture Chromium flag.
# An empty 1-second silent placeholder is created on server deploy; each voice note overwrites
# this file with the real audio before Playwright clicks the mic button.
FAKE_MIC_PATH = "/tmp/fake_mic.wav"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("wa")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_browser_context = None
_page = None
_is_connected = False
_qr_png_bytes: bytes | None = None
_qr_last_seen_at: float = 0.0   # epoch seconds when QR was last detected on canvas
_QR_HOLD_SECS = 30              # keep QR bytes for at least this long after canvas disappears
_qr_logged: bool = False        # True after "QR code ready" has been logged for this session;
                                # reset on connect, disconnect, or after a reload click so the
                                # message fires exactly once per QR session — not on every rotation
_connected_phone: str | None = None
_messages_today = 0
_telemetry_log: list[str] = []
_last_action = "Starting up..."
_last_error: str | None = None
_poller_task = None
_page_lock: asyncio.Lock = None  # type: ignore  # initialised in _start_playwright

# Link-code flow state (non-blocking /link/start)
_link_code: str = ""
_link_code_error: str = ""
_link_code_pending: bool = False


# ---------------------------------------------------------------------------
# Telemetry helpers
# ---------------------------------------------------------------------------
def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _log_action(msg: str) -> None:
    global _last_action
    _last_action = msg
    entry = f"{_ts()} — {msg}"
    _telemetry_log.insert(0, entry)
    if len(_telemetry_log) > 100:
        _telemetry_log.pop()
    log.info(msg)
    _write_status()


def _write_status() -> None:
    try:
        payload = {
            "account": ACCOUNT,
            "connected": _is_connected,
            "phone": _connected_phone,
            "last_action": _last_action,
            "last_action_at": datetime.now(timezone.utc).isoformat(),
            "messages_today": _messages_today,
            "last_error": _last_error,
            "log": _telemetry_log[:100],
            # Embed QR as base64 so Streamlit gets it in one poll without a second request.
            # Streamlit decodes: base64.b64decode(payload["qr_b64"]) → raw PNG bytes → st.image()
            "qr_b64": base64.b64encode(_qr_png_bytes).decode() if _qr_png_bytes else None,
        }
        STATUS_FILE.write_text(json.dumps(payload, indent=2))
    except Exception as e:
        log.warning(f"Could not write status file: {e}")


# ---------------------------------------------------------------------------
# QR helpers
# ---------------------------------------------------------------------------
async def _refresh_qr_if_expired() -> bool:
    """
    Detect the WA Web 'QR expired' reload overlay and click it.
    Returns True if the overlay was found and clicked.
    Caller must await asyncio.sleep(3.5) before re-reading the canvas.

    Tries known data-testid selectors first, then falls back to any
    clickable element whose text contains 'reload' (case-insensitive).
    """
    try:
        clicked = await _page.evaluate("""
            () => {
                const known = [
                    'span[data-testid="refresh-btn-wa"]',
                    'div[data-testid="qr-code-refresh-button"]',
                    '[data-testid="refresh-btn-wa"]',
                ];
                for (const sel of known) {
                    const el = document.querySelector(sel);
                    if (el) { el.click(); return true; }
                }
                const candidates = document.querySelectorAll(
                    'button, div[role="button"], span[role="button"]'
                );
                for (const el of candidates) {
                    if (/reload/i.test(el.innerText || el.textContent)) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        return bool(clicked)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Background QR / connection poller
# ---------------------------------------------------------------------------
async def _poll_connection() -> None:
    global _is_connected, _qr_png_bytes, _qr_last_seen_at, _qr_logged, _connected_phone, _last_error

    while True:
        await asyncio.sleep(2)          # outside lock — yields to link flow while it holds lock
        if _page is None:
            continue
        try:
            async with _page_lock:
                # Check if the main chat sidebar is visible (= logged in)
                chat_visible = await _page.evaluate(
                    "() => !!document.querySelector('[data-testid=\"chat-list\"]')"
                    " || !!document.querySelector('div[data-tab=\"3\"]')"
                )
                if chat_visible and not _is_connected:
                    _is_connected = True
                    _qr_png_bytes = None   # clear QR only on confirmed login
                    _qr_last_seen_at = 0.0
                    _qr_logged = False     # reset so next QR session logs once
                    try:
                        _connected_phone = await _page.evaluate(
                            "() => {"
                            "  const el = document.querySelector('[data-testid=\"default-user\"]');"
                            "  return el ? el.textContent.trim() : null;"
                            "}"
                        )
                    except Exception:
                        pass
                    _log_action(f"Connected — phone: {_connected_phone or 'unknown'}")
                    continue

                if chat_visible and _is_connected:
                    _write_status()
                    continue

                # Not in chat — dismiss expired-QR overlay if present, then capture canvas
                reloaded = await _refresh_qr_if_expired()
                if reloaded:
                    _qr_logged = False  # reset so "QR code ready" fires once after new QR loads
                    _log_action("QR expired — clicked reload, waiting for fresh QR...")
                    await asyncio.sleep(3.5)  # cloud Xvfb + network: 3.5s guarantees canvas fully painted

                qr_b64 = await _page.evaluate(
                    "() => {"
                    "  const canvas = document.querySelector('canvas');"
                    "  return canvas ? canvas.toDataURL('image/png') : null;"
                    "}"
                )
                if qr_b64:
                    raw = base64.b64decode(qr_b64.split(",", 1)[1])
                    _qr_last_seen_at = time.monotonic()
                    _qr_png_bytes = raw
                    _is_connected = False
                    _connected_phone = None
                    if not _qr_logged:
                        # Log "QR code ready" exactly once per QR session (first appearance or after reload).
                        # Subsequent WA Web rotations (every ~20s) update bytes silently.
                        _qr_logged = True
                        _log_action("QR code ready — scan in ORVA WhatsApp page")
                    else:
                        _write_status()  # update qr_b64 in JSON silently on each rotation
                else:
                    # Canvas not visible — could be a transient gap (QR rotating, page loading).
                    # Only clear QR if it's been more than _QR_HOLD_SECS since we last saw it.
                    if _qr_png_bytes and (time.monotonic() - _qr_last_seen_at) < _QR_HOLD_SECS:
                        _write_status()  # hold bytes, no log spam
                    else:
                        if _qr_png_bytes:
                            _qr_png_bytes = None
                            _qr_last_seen_at = 0.0
                            _qr_logged = False
                        if _is_connected:
                            _is_connected = False
                            _connected_phone = None
                            _log_action("Disconnected — WhatsApp Web session lost")
                        else:
                            _write_status()

        except Exception as e:
            _last_error = str(e)[:200]
            _write_status()


# ---------------------------------------------------------------------------
# Playwright startup
# ---------------------------------------------------------------------------
async def _start_playwright() -> None:
    global _browser_context, _page, _poller_task, _page_lock
    _page_lock = asyncio.Lock()

    # Set DISPLAY so Chromium uses Xvfb
    os.environ["DISPLAY"] = DISPLAY
    log.info(f"Using DISPLAY={DISPLAY}, profile={CHROME_PROFILE_DIR}")

    # Clear Chrome's crash flag so the "Restore pages?" infobar never appears.
    # PM2 SIGKILL on restart leaves exit_type="Crashed" in Default/Preferences.
    for _prefs_file in [
        CHROME_PROFILE_DIR / "Default" / "Preferences",
        CHROME_PROFILE_DIR / "Preferences",
    ]:
        if _prefs_file.exists():
            try:
                _prefs = json.loads(_prefs_file.read_text())
                _prefs.setdefault("profile", {})["exit_type"] = "Normal"
                _prefs["profile"]["exited_cleanly"] = True
                _prefs_file.write_text(json.dumps(_prefs))
                log.info(f"Cleared Chrome crash flag in {_prefs_file.name}")
            except Exception as _e:
                log.warning(f"Could not clear Chrome crash flag: {_e}")
            break

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    _browser_context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(CHROME_PROFILE_DIR),
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-restore-session-state",   # suppress "Restore pages?" infobar
            "--disable-session-crashed-bubble",  # suppress crash recovery bubble
            # Fake microphone — auto-grant permission, use WAV file as mic input.
            # The WAV at FAKE_MIC_PATH is overwritten per-request before clicking the mic button.
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={FAKE_MIC_PATH}",
        ],
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )

    # Reuse existing page or open a new one
    pages = _browser_context.pages
    _page = pages[0] if pages else await _browser_context.new_page()

    log.info("Navigating to WhatsApp Web...")
    await _page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=30000)

    _poller_task = asyncio.create_task(_poll_connection())
    log.info(f"[START] ORVA Playwright server on http://0.0.0.0:{PORT}")


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await _start_playwright()
    yield
    if _poller_task:
        _poller_task.cancel()
    if _browser_context:
        await _browser_context.close()


app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/status")
def status():
    return JSONResponse({
        "connected": _is_connected,
        "qr_available": _qr_png_bytes is not None,
        "phone": _connected_phone,
        "action": _last_action,
        # Include QR as base64 so Streamlit can render it without a second request.
        # app.py decodes: base64.b64decode(response["qr_b64"]) → raw PNG → st.image()
        "qr_b64": base64.b64encode(_qr_png_bytes).decode() if _qr_png_bytes else None,
    })


@app.get("/qr")
def qr():
    if not _qr_png_bytes:
        return JSONResponse(
            {"error": "No QR available. Already connected, or QR not yet generated."},
            status_code=404,
        )
    return Response(content=_qr_png_bytes, media_type="image/png")


@app.post("/link/start")
async def link_start(body: dict):
    """
    Kick off 'Log in with phone number' flow non-blocking.
    Returns {"status": "started"} immediately.
    Poll GET /link/status for the result.
    """
    global _link_code, _link_code_error, _link_code_pending
    if not _page:
        return JSONResponse({"error": "Playwright not ready"}, status_code=503)
    if _is_connected:
        return JSONResponse({"error": "Already connected — no link needed"}, status_code=400)

    phone_number = body.get("phone_number", "").strip().lstrip("+")
    if not phone_number:
        return JSONResponse({"error": "phone_number required"}, status_code=400)

    if _link_code_pending:
        return JSONResponse({"status": "already_running"})

    _link_code = ""
    _link_code_error = ""
    _link_code_pending = True
    asyncio.create_task(_run_link_code_flow(phone_number))
    return JSONResponse({"status": "started"})


async def _run_link_code_flow(phone_number: str) -> None:
    global _link_code, _link_code_error, _link_code_pending
    try:
        code = await _playwright_get_link_code(phone_number)
        _link_code = code
        _log_action(f"Link code ready for ...{phone_number[-4:]}: {code}")
    except Exception as e:
        _link_code_error = str(e)[:300]
        _log_action(f"Link code failed: {_link_code_error[:80]}")
    finally:
        _link_code_pending = False


@app.get("/link/status")
def link_status():
    """Poll this after POST /link/start to get the generated code."""
    return JSONResponse({
        "pending": _link_code_pending,
        "link_code": _link_code,
        "error": _link_code_error,
    })


@app.get("/screenshot")
async def screenshot():
    """Returns current browser page as base64 PNG — for debugging selector failures."""
    if not _page:
        return JSONResponse({"error": "no page"}, status_code=503)
    try:
        async with _page_lock:
            buf = await _page.screenshot(timeout=5000)
        return JSONResponse({"png_b64": base64.b64encode(buf).decode()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


_COUNTRY_MAP = {
    "971": ("United Arab Emirates", "AE"),
    "44":  ("United Kingdom", "GB"),
    "1":   ("United States", "US"),
    "91":  ("India", "IN"),
    "92":  ("Pakistan", "PK"),
    "966": ("Saudi Arabia", "SA"),
    "965": ("Kuwait", "KW"),
    "974": ("Qatar", "QA"),
    "973": ("Bahrain", "BH"),
    "968": ("Oman", "OM"),
    "20":  ("Egypt", "EG"),
    "7":   ("Russia", "RU"),
    "49":  ("Germany", "DE"),
    "33":  ("France", "FR"),
    "86":  ("China", "CN"),
}


def _parse_phone(phone_number: str) -> tuple[str, str, str]:
    """
    Given an E.164 number without '+' (e.g. '971501234567'),
    return (country_code, local_number, country_name).
    Tries longest prefix first.
    """
    for prefix in sorted(_COUNTRY_MAP.keys(), key=len, reverse=True):
        if phone_number.startswith(prefix):
            country_name = _COUNTRY_MAP[prefix][0]
            local = phone_number[len(prefix):]
            return prefix, local, country_name
    # Unknown country — return as-is, UI may still work
    return "", phone_number, ""


async def _playwright_get_link_code(phone_number: str) -> str:
    """
    Drives the WA Web 'Log in with phone number' flow.
    Returns the 8-char pairing code (e.g. 'ABCD-EFGH').
    Acquires _page_lock for its entire run — poller is blocked while we drive the page.
    """
    async with _page_lock:
        # ── Step 0: ensure we're on WA Web ───────────────────────────────────
        # Only navigate if the page has drifted — avoids redundant goto when already there.
        try:
            if "web.whatsapp.com" not in (_page.url or ""):
                await _page.goto("https://web.whatsapp.com",
                                 wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
            else:
                await asyncio.sleep(1)  # brief settle — already on WA Web
        except Exception:
            pass

        # If the phone entry form is already open, we're stuck from a previous failed attempt.
        # Reload to get a fresh QR/login screen so Step 1 can find its button.
        try:
            _stuck = await _page.evaluate(
                "() => !!document.querySelector('input[type=\"tel\"], input[inputmode=\"tel\"]')"
            )
            if _stuck:
                log.info("[LINK] Phone form from previous attempt detected — reloading for fresh state")
                await _page.goto("https://web.whatsapp.com",
                                 wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
        except Exception:
            pass

        # ── Step 1: click "Link with phone number" ───────────────────────────
        for attempt in range(10):
            clicked = await _page.evaluate("""
                () => {
                    const testids = [
                        '[data-testid="link-device-phone-num-btn-side"]',
                        '[data-testid="login-phone-btn"]',
                    ];
                    for (const sel of testids) {
                        const el = document.querySelector(sel);
                        if (el) { el.click(); return sel; }
                    }
                    // Only search anchors and buttons — avoids clicking parent container divs
                    // whose innerText includes all child text (length < 80 is an extra guard)
                    const clickables = document.querySelectorAll('a, button, [role="button"]');
                    for (const el of clickables) {
                        const t = (el.innerText || el.textContent || '').trim();
                        if (/phone.?number/i.test(t) && t.length < 80 && el.offsetWidth > 0) {
                            el.click(); return 'link:' + t.slice(0, 50);
                        }
                    }
                    return null;
                }
            """)
            if clicked:
                log.info(f"[LINK] Clicked phone-number button via: {clicked}")
                break
            await asyncio.sleep(1)
        else:
            raise ValueError("Could not find 'Link with phone number' button — is the QR page loaded?")

        # ── Step 2: parse phone number into country + local digits ───────────
        country_code, local_number, country_name = _parse_phone(phone_number)
        log.info(f"[LINK] Parsed: +{country_code} ({country_name}) local={local_number}")

        # ── Step 3: change country dropdown ──────────────────────────────
        await asyncio.sleep(2.0)  # let the "Enter phone number" form fully render

        if country_name:
            # ── DOM dump for diagnostics ──────────────────────────────────────
            dom_info = await _page.evaluate("""
                () => {
                    const rows = [];
                    const els = document.querySelectorAll('[data-testid], [role="combobox"], button, input, select');
                    for (const el of els) {
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 && r.height === 0) continue;
                        const tid  = el.getAttribute('data-testid') || '';
                        const role = el.getAttribute('role') || '';
                        const t    = (el.innerText || el.textContent || '').trim().replace(/\\s+/g,' ').slice(0,40);
                        rows.push(`${el.tagName}[testid=${tid}][role=${role}] "${t}" ${Math.round(r.width)}x${Math.round(r.height)}`);
                        if (rows.length >= 60) break;
                    }
                    return rows.join(' | ');
                }
            """)
            log.info(f"[LINK][DOM] {dom_info}")

            # ── Strategy 0: native <select> (new WA Web UI) ───────────────────
            dropdown_opened = None
            try:
                await _page.select_option('select', label=country_name, timeout=1500)
                dropdown_opened = 'native-select'
                log.info(f"[LINK] Country set via native select: {country_name}")
            except Exception:
                pass

            if not dropdown_opened:
                # ── Strategy A: known testid selectors ────────────────────────
                dropdown_opened = await _page.evaluate("""
                    () => {
                        const ids = ['phone-number-country','country-selector',
                                     'link-device-phone-num-country-dropdown',
                                     'link-phone-number-country-select','intro-country-picker'];
                        for (const id of ids) {
                            const el = document.querySelector(`[data-testid="${id}"]`);
                            if (el) { el.click(); return 'testid:' + id; }
                        }
                        return null;
                    }
                """)

            if not dropdown_opened:
                # ── Strategy B: combobox / select element by visible text ──────
                dropdown_opened = await _page.evaluate("""
                    () => {
                        for (const sel of ['[role="combobox"]','[aria-haspopup="listbox"]',
                                           '[aria-haspopup="true"]','[aria-haspopup="dialog"]']) {
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent !== null) {
                                const r = el.getBoundingClientRect();
                                if (r.width > 20 && r.height > 10) { el.click(); return 'role:' + sel; }
                            }
                        }
                        return null;
                    }
                """)

            if not dropdown_opened:
                # ── Strategy C: first non-action button (the country button) ───
                dropdown_opened = await _page.evaluate("""
                    () => {
                        const SKIP = /^(next|back|done|cancel|ok|yes|no|close|submit|continue|confirm|search|clear|delete|edit|save|send|log in|sign in|link with phone|get link code|scan|qr|retry)$/i;
                        for (const btn of document.querySelectorAll('button')) {
                            if (!btn.offsetParent) continue;
                            const t = (btn.innerText || btn.textContent || '').trim();
                            if (!t || t.length < 2 || t.length > 40 || /\\d/.test(t) || SKIP.test(t)) continue;
                            const r = btn.getBoundingClientRect();
                            if (r.width > 80 && r.height > 20 && r.height < 100) { btn.click(); return 'button:' + t; }
                        }
                        return null;
                    }
                """)

            if dropdown_opened and dropdown_opened != 'native-select':
                log.info(f"[LINK] Country dropdown opened via: {dropdown_opened}")
                await asyncio.sleep(1.2)  # wait for search overlay to appear

                # Find the search input that appeared inside the dropdown overlay
                search_focused = await _page.evaluate("""
                    () => {
                        // Prefer a search-type input; fall back to any newly visible input
                        for (const sel of ['input[type="search"]', 'input[placeholder]', 'input[type="text"]', 'input']) {
                            const inp = document.querySelector(sel);
                            if (inp && inp.offsetParent !== null && inp.offsetWidth > 40) {
                                inp.focus();
                                return sel;
                            }
                        }
                        return null;
                    }
                """)
                log.info(f"[LINK] Search input focused: {search_focused}")

                # Type country name into search field
                await _page.keyboard.type(country_name, delay=60)
                await asyncio.sleep(1.2)

                # Click the matching list item (role=option, li, or any visible element)
                _country_clicked = await _page.evaluate(f"""
                    () => {{
                        const target = '{country_name}';
                        for (const sel of ['[role="option"]', 'li', '[data-testid*="list"]', 'div']) {{
                            for (const el of document.querySelectorAll(sel)) {{
                                if (!el.offsetParent) continue;
                                const t = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                                if (t === target || t.startsWith(target)) {{
                                    el.click();
                                    return 'clicked-list:' + t.slice(0, 30);
                                }}
                            }}
                        }}
                        return null;
                    }}
                """)

                if not _country_clicked:
                    # Fallback: press Enter to confirm first filtered result
                    await _page.keyboard.press("Enter")
                    _country_clicked = "Enter-fallback"

                log.info(f"[LINK] Country list item: {_country_clicked}")
                await asyncio.sleep(0.8)

                # Verify the country changed
                current_country = await _page.evaluate("""
                    () => {
                        for (const btn of document.querySelectorAll('button')) {
                            const t = (btn.innerText||btn.textContent||'').trim();
                            if (t.length > 2 && t.length < 40 && !/\\d/.test(t) && btn.offsetParent) return t;
                        }
                        const sel = document.querySelector('select');
                        if (sel) return sel.options[sel.selectedIndex]?.text || '';
                        return '';
                    }
                """)
                log.info(f"[LINK] Country after selection: {current_country}")

            await asyncio.sleep(0.5)

        # ── Step 4: fill the local phone number ──────────────────────────────
        fill_number = local_number if country_name else phone_number
        filled = False
        for sel in ['input[type="tel"]', 'input[inputmode="tel"]', 'input[inputmode="numeric"]', 'input[type="text"]']:
            inp = await _page.query_selector(sel)
            if inp and await inp.is_visible():
                await inp.click()
                await _page.keyboard.press("Control+A")
                await _page.keyboard.press("Delete")
                await _page.keyboard.type(fill_number, delay=80)
                filled = True
                log.info(f"[LINK] Entered number via keyboard {sel}: {fill_number}")
                break

        if not filled:
            # Last resort: find first visible wide input and type via keyboard
            clicked = await _page.evaluate("""
                () => {
                    const inputs = Array.from(document.querySelectorAll('input')).filter(
                        i => i.offsetWidth > 80 && i.offsetParent !== null
                    );
                    if (!inputs.length) return false;
                    inputs[0].focus();
                    return true;
                }
            """)
            if clicked:
                await _page.keyboard.press("Control+A")
                await _page.keyboard.press("Delete")
                await _page.keyboard.type(fill_number, delay=80)
                log.info(f"[LINK] Entered number via keyboard fallback: {fill_number}")
            filled = clicked

        await asyncio.sleep(0.5)

        # ── Step 5: click Next ───────────────────────────────────────────────
        await _page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, [role="button"]');
                for (const b of btns) {
                    const t = (b.innerText || b.textContent || '').trim();
                    if (/^next$/i.test(t) && b.offsetWidth > 0) { b.click(); return 'next'; }
                }
                const form = document.querySelector('form');
                if (form) { form.requestSubmit(); return 'form'; }
            }
        """)
        log.info("[LINK] Clicked Next, waiting for pairing code...")
        await asyncio.sleep(4.0)

        # ── Step 6: extract the pairing code ─────────────────────────────────
        for attempt in range(20):  # poll up to ~40s
            code = await _page.evaluate("""
                () => {
                    for (const sel of [
                        '[data-testid="link-with-phone-number-code"]',
                        '[data-testid="phonecode-login-code"]',
                        '[data-testid="pairing-code"]',
                    ]) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const t = el.innerText.trim().replace(/\\s+/g, '');
                            if (t.length >= 8) return t.slice(0,4) + '-' + t.slice(t.length-4);
                        }
                    }
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_TEXT, null
                    );
                    let node;
                    while ((node = walker.nextNode())) {
                        const t = (node.textContent || '').trim();
                        if (/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(t)) return t;
                        if (/^[A-Z0-9]{8}$/.test(t)) return t.slice(0,4) + '-' + t.slice(4);
                    }
                    return null;
                }
            """)
            if code:
                return code

            err = await _page.evaluate("""
                () => {
                    for (const sel of [
                        '[data-testid*="error"]', '[class*="error"]',
                        'span[style*="color: rgb(234"]',
                    ]) {
                        const el = document.querySelector(sel);
                        if (el && el.offsetWidth > 0 && el.innerText)
                            return el.innerText.trim().slice(0, 120);
                    }
                    const body = document.body.innerText || '';
                    if (/valid phone number is required/i.test(body))
                        return 'Invalid phone number — check country and digits';
                    return null;
                }
            """)
            if err:
                raise ValueError(f"WA Web: {err}")

            await asyncio.sleep(2)

        raise ValueError("Timed out waiting for pairing code — check phone number and country")


@app.get("/telemetry")
def telemetry():
    try:
        return JSONResponse(json.loads(STATUS_FILE.read_text()))
    except Exception:
        return JSONResponse({"error": "Status file not available"}, status_code=503)


@app.post("/send/text")
async def send_text(body: dict):
    if not _is_connected or not _page:
        return JSONResponse(
            {"success": False, "error": "WhatsApp not connected — scan QR first"},
            status_code=503,
        )

    phone = body.get("phone", "").strip()
    message = body.get("message", "").strip()
    skip_chat_check = body.get("skip_chat_check", False)

    if not phone or not message:
        return JSONResponse(
            {"success": False, "error": "phone and message are required"},
            status_code=400,
        )

    result = await _playwright_send_text(phone, message, skip_chat_check)

    if result["status"] == "sent":
        global _messages_today
        _messages_today += 1
        _log_action(f"Sent text to {phone}")
        return JSONResponse({"success": True})
    elif result["status"] == "not_on_whatsapp":
        _log_action(f"Not on WhatsApp: {phone}")
        return JSONResponse({"success": False, "error": "not registered"})
    else:
        err = result.get("error", "send failed")
        _last_error = err
        _log_action(f"Failed to send to {phone}: {err[:60]}")
        _write_status()
        return JSONResponse({"success": False, "error": err}, status_code=500)


@app.post("/send/voice")
async def send_voice(body: dict):
    if not _is_connected or not _page:
        return JSONResponse(
            {"success": False, "error": "WhatsApp not connected — scan QR first"},
            status_code=503,
        )

    phone = body.get("phone", "").strip()
    audio_path = body.get("audio_path", "").strip()

    if not phone or not audio_path:
        return JSONResponse(
            {"success": False, "error": "phone and audio_path are required"},
            status_code=400,
        )
    if not Path(audio_path).exists():
        return JSONResponse(
            {"success": False, "error": f"audio_path not found: {audio_path}"},
            status_code=400,
        )

    # Step 1: Convert to 16-bit PCM WAV at 48kHz mono (Chromium fake device format)
    # and overwrite FAKE_MIC_PATH so the browser streams it as the microphone input.
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path,
             "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "1",
             FAKE_MIC_PATH],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr[-300:])
    except Exception as e:
        log.error(f"[FAIL] ffmpeg WAV conversion for {phone}: {e}")
        return JSONResponse(
            {"success": False, "error": f"ffmpeg conversion failed: {str(e)[:200]}"},
            status_code=500,
        )

    # Step 2: Get audio duration via ffprobe so we know how long to hold the recording
    audio_duration = 10.0  # fallback
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", audio_path],
            capture_output=True, text=True, timeout=15,
        )
        streams = json.loads(probe.stdout).get("streams", [])
        if streams:
            audio_duration = float(streams[0].get("duration", 10.0))
    except Exception:
        pass

    # Step 3: Send via Playwright fake-mic PTT flow
    result = await _playwright_send_voice(phone, audio_duration)

    if result["status"] == "sent":
        global _messages_today
        _messages_today += 1
        _log_action(f"Sent voice note to {phone}")
        return JSONResponse({"success": True})
    elif result["status"] == "not_on_whatsapp":
        _log_action(f"Not on WhatsApp: {phone}")
        return JSONResponse({"success": False, "error": "not registered"})
    else:
        err = result.get("error", "send failed")
        _last_error = err
        _log_action(f"Failed voice send to {phone}: {err[:60]}")
        _write_status()
        return JSONResponse({"success": False, "error": err}, status_code=500)


# ---------------------------------------------------------------------------
# Playwright send helpers (ported directly from bot.py _send_message_playwright)
# ---------------------------------------------------------------------------

async def _open_chat_and_check(phone: str) -> dict | None:
    """
    Navigate to wa.me deep link, wait for chat input box.
    Returns None if chat is ready, or a result dict if 'not_on_whatsapp' / 'failed'.
    """
    url = f"https://web.whatsapp.com/send?phone={phone}"
    log.info(f"[SEND] Opening chat: {phone}")
    await _page.goto(url, wait_until="domcontentloaded", timeout=30000)

    # Poll up to 30s for chat input or "not on WhatsApp" popup
    for _ in range(30):
        await asyncio.sleep(1)
        page_text = await _page.evaluate("() => document.body.innerText")
        not_on_wa = (
            "\u2019t on WhatsApp" in page_text      # "isn't on WhatsApp" (curly apostrophe)
            or "isn't on WhatsApp" in page_text
            or "is not on WhatsApp" in page_text
            or "number shared via url is invalid" in page_text
        )
        if not_on_wa:
            await _dismiss_popup()
            return {"status": "not_on_whatsapp", "phone": phone}
        try:
            inp = await _page.query_selector('div[contenteditable="true"][data-tab="10"]')
            if inp:
                return None  # ready
        except Exception:
            pass

    # Final popup check
    page_text = await _page.evaluate("() => document.body.innerText")
    if (
        "\u2019t on WhatsApp" in page_text
        or "isn't on WhatsApp" in page_text
        or "is not on WhatsApp" in page_text
    ):
        await _dismiss_popup()
        return {"status": "not_on_whatsapp", "phone": phone}

    return {"status": "failed", "phone": phone, "error": "Input box not found after 30s"}


async def _dismiss_popup() -> None:
    try:
        await _page.evaluate(
            "() => {"
            "  const btns = document.querySelectorAll('button, div[role=\"button\"]');"
            "  for (const btn of btns) {"
            "    if (btn.textContent.trim() === 'OK') { btn.click(); return true; }"
            "  }"
            "  return false;"
            "}"
        )
        await asyncio.sleep(0.5)
    except Exception:
        pass


async def _wait_for_input_box():
    """Wait for and return the chat input box."""
    return await _page.wait_for_selector(
        'div[contenteditable="true"][data-tab="10"]',
        timeout=10000,
    )


async def _playwright_send_text(phone: str, message: str, skip_chat_check: bool) -> dict:
    try:
        result = await _open_chat_and_check(phone)
        if result is not None:
            return result

        try:
            input_box = await _wait_for_input_box()
        except Exception:
            return {"status": "failed", "phone": phone, "error": "Input box not found"}

        # Check for existing chat
        await asyncio.sleep(3)
        has_messages = await _page.evaluate(
            "() => {"
            "  if (document.querySelectorAll('[data-id]').length >= 2) return true;"
            "  if (document.querySelectorAll('span[data-testid=\"msg-time\"]').length > 0) return true;"
            "  return false;"
            "}"
        )
        if has_messages and not skip_chat_check:
            log.info(f"  [SKIP] {phone} already has a chat")
            return {"status": "existing_chat", "phone": phone}

        # Human-like typing
        log.info(f"  [TYPE] Typing message ({len(message)} chars)...")
        word_count = 0
        next_word_pause_at = random.randint(4, 8)
        for char in message:
            if char == "\n":
                await _page.keyboard.down("Shift")
                await _page.keyboard.press("Enter")
                await _page.keyboard.up("Shift")
                await asyncio.sleep(random.uniform(0.05, 0.15))
            else:
                await input_box.type(char, delay=random.randint(30, 120))
                if char == " ":
                    word_count += 1
                    if word_count >= next_word_pause_at:
                        await asyncio.sleep(random.uniform(0.1, 0.4))
                        next_word_pause_at = word_count + random.randint(4, 8)
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.5, 1.5))

        await asyncio.sleep(random.uniform(1.0, 3.0))
        log.info(f"  [SEND] Pressing Enter to send...")
        await _page.keyboard.press("Enter")
        await asyncio.sleep(2)
        log.info(f"  [OK] Message sent to {phone}")
        return {"status": "sent", "phone": phone}

    except Exception as e:
        log.error(f"  [FAIL] Error sending to {phone}: {str(e)[:100]}")
        return {"status": "failed", "phone": phone, "error": str(e)[:200]}


async def _playwright_send_voice(phone: str, audio_duration: float) -> dict:
    """
    Send a native PTT voice note using Chromium's fake microphone injection.
    FAKE_MIC_PATH must already contain the audio (written by the /send/voice endpoint).
    Chromium streams it as mic input when WhatsApp Web records PTT.
    """
    try:
        result = await _open_chat_and_check(phone)
        if result is not None:
            return result

        try:
            await _wait_for_input_box()
        except Exception:
            return {"status": "failed", "phone": phone, "error": "Input box not found"}

        # Click the microphone icon to start PTT recording.
        # Chromium immediately feeds FAKE_MIC_PATH through the fake audio device.
        log.info(f"  [VOICE] Clicking mic icon for {phone} (duration={audio_duration:.1f}s)...")
        mic_clicked = False
        for mic_sel in [
            'span[data-testid="audio-input"]',
            'button[data-testid="compose-btn-audio"]',
            '[data-testid="audio-input"]',
        ]:
            try:
                mic_btn = await _page.wait_for_selector(mic_sel, timeout=3000)
                if mic_btn:
                    await mic_btn.click()
                    mic_clicked = True
                    log.info(f"  [VOICE] Mic started via {mic_sel}")
                    break
            except Exception:
                continue

        if not mic_clicked:
            return {"status": "failed", "phone": phone, "error": "Microphone button not found"}

        # Hold the recording for the audio duration (+ 0.5s buffer so WA Web captures it all).
        # The WAV loops in Chromium — we stop before the loop point.
        await asyncio.sleep(audio_duration + 0.5)

        # Click the send checkmark to stop recording and dispatch the PTT message.
        log.info(f"  [VOICE] Clicking send to stop recording and send PTT...")
        sent = False
        for send_sel in [
            'span[data-testid="send"]',
            '[data-testid="audio-stop"]',
            'div[aria-label="Send"]',
        ]:
            try:
                send_btn = await _page.wait_for_selector(send_sel, timeout=4000)
                if send_btn:
                    await send_btn.click()
                    sent = True
                    break
            except Exception:
                continue

        if not sent:
            return {"status": "failed", "phone": phone, "error": "PTT send button not found"}

        await asyncio.sleep(2)
        log.info(f"  [OK] Voice note sent to {phone}")
        return {"status": "sent", "phone": phone}

    except Exception as e:
        log.error(f"  [FAIL] Voice send error for {phone}: {str(e)[:100]}")
        return {"status": "failed", "phone": phone, "error": str(e)[:200]}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
