# WhatsApp Outreach Bot

**Production-grade WhatsApp automation for Palm Jumeirah property outreach**

---

## OVERVIEW

This bot automates personalized WhatsApp outreach to property owners on Palm Jumeirah. It uses Playwright to connect to WhatsApp Web (via Chrome debug mode), sends messages with human-like typing and delays, and enforces strict safety rules to avoid detection.

**Key Features:**
- Landlord lease expiry campaigns (targets owners with expiring leases)
- Cold owner outreach (single-unit and portfolio investors)
- Personalized messages with building + unit context
- 100 msg/day cap with gradual ramp-up (10→20→30→50→100 over 5 days)
- 30-day dedup window (never message same phone twice in 30 days)
- Human-like delays: 30-90s between messages, 10-15 min pause every 20 messages
- CSV logging for tracking and compliance

**Message Sending:**
- Multi-paragraph messages sent as **ONE complete message** (not split)
- Uses **Shift+Enter** for line breaks within message
- Presses **Enter only once** at the end to send entire message
- Human-like character-by-character typing (20-80ms delay)

---

## ARCHITECTURE

```
whatsapp_bot/
├── bot.py                  # Core Playwright WhatsApp Web automation
├── campaign_manager.py     # Build queues from leads/rentals, apply filters
├── message_templates.py    # All templates with name formatting
├── rate_limiter.py         # Delays, caps, session limits
├── message_log.py          # CSV tracking (dedup source of truth)
├── run_campaign.py         # CLI entry point
└── message_log.csv         # Auto-created log file (sent/failed/not_on_whatsapp)
```

---

## SETUP

### 1. Prerequisites

- **Chrome** (for WhatsApp Web)
- **WhatsApp Web account** (logged in on your phone)
- **Python 3.9+** with Playwright installed
- **Lead data** at `data/leads_master_v3.csv`
- **Rental data** at `scraped_data/palm_jumeirah_rentals.csv`

### 2. Install Dependencies

```bash
pip install playwright pandas
playwright install chromium
```

### 3. Launch Chrome for WhatsApp (recommended)

Use the dedicated launcher so Chrome opens WhatsApp and keeps you logged in:

**From project root (PowerShell):**
```powershell
powershell -File whatsapp_bot/start_whatsapp_chrome.ps1
```

Or from inside `whatsapp_bot/`:
```powershell
.\start_whatsapp_chrome.ps1
```

- First run: Chrome opens with `web.whatsapp.com` — log in once (scan QR).
- Next runs: same command; Chrome uses the saved profile so you stay logged in.

**Alternative (manual):** Launch Chrome with debug port and open WhatsApp yourself:
```powershell
chrome.exe --remote-debugging-port=9222
# Then open web.whatsapp.com and log in
```

### 4. Open WhatsApp Web

If you use the launcher above, WhatsApp opens automatically. Otherwise in the Chrome window:
1. Navigate to `web.whatsapp.com`
2. Scan QR code with your phone (if not already logged in)
3. Wait for WhatsApp to fully load

### 5. Test with YOUR OWN Number First

Before running any campaign, send a test message to yourself:

```bash
python whatsapp_bot/run_campaign.py --test YOUR_PHONE_NUMBER
```

Replace `YOUR_PHONE_NUMBER` with your own WhatsApp number. This will:
- Connect to WhatsApp Web
- Send one test message to your number
- Verify the connection and selectors are working
- Show you exactly what recipients will see

### 6. Test with Dry Run

After verifying with your own number, preview a full campaign:

```bash
python whatsapp_bot/run_campaign.py --type cold_owner --building "Shoreline 12" --dry-run
```

This shows a preview of 10 messages without sending anything.

---

## USAGE

### CLI Commands

**Test Mode (send to your own number):**
```bash
python whatsapp_bot/run_campaign.py --test YOUR_PHONE_NUMBER
```
Replace with your WhatsApp number. Use this FIRST before any real campaign.

**Landlord Lease Expiry (90 days ahead):**
```bash
python whatsapp_bot/run_campaign.py --type landlord_lease_expiry --days 90
```

**Cold Owner Outreach (specific building):**
```bash
python whatsapp_bot/run_campaign.py --type cold_owner --building "Shoreline 12"
```

**Portfolio Investors Only:**
```bash
python whatsapp_bot/run_campaign.py --type cold_owner --portfolio-only
```

**Dry Run (preview without sending):**
```bash
python whatsapp_bot/run_campaign.py --type cold_owner --building "Shoreline 12" --dry-run
```

**Filter by Bedrooms:**
```bash
python whatsapp_bot/run_campaign.py --type landlord_lease_expiry --bedrooms 2
```

**Limit Queue (for testing):**
```bash
python whatsapp_bot/run_campaign.py --type cold_owner --limit 10
```

### Streamlit UI

**Access via app:**
1. Launch Streamlit: `streamlit run app.py`
2. Click **📱 WhatsApp** button in header
3. Build campaigns visually with filters
4. Preview queue before sending
5. View send stats and message log

**Note:** Actual sending still requires CLI (for safety — no accidental sends from UI).

---

## MESSAGE TEMPLATES

### Rules

1. **Never open with name and company.** Lead with value/context.
2. **Always include building AND unit number** so owner knows you have real data.
3. **Personalize with first name only.** Extract from full name, convert to Title Case.
4. **Use emoji sparingly.** One smiley max per message.
5. **No links in first message.** WhatsApp flags URLs to new contacts.
6. **Portfolio template ONLY for 2+ unit owners.**

### Name Formatting

- `"GALALELDIN HANY GALAL ABOELELLA"` → `"Galaleldin"`
- `"MR. AHMED AL SMITH"` → `"Ahmed Al Smith"` (keeps "Al")
- `"M/S. CARYATID PROPERTIES LIMITED"` → Skipped (corporate entity)

### Template Selection

- **Cold Owner (single unit):** 3 templates (family office, recent transaction, market update)
- **Cold Owner (portfolio):** 2 templates (multiple investments, portfolio review)
- **Landlord Lease Expiry:** 3 templates (lease ending, re-let or sell, market timing)

---

## SAFETY RULES (NON-NEGOTIABLE)

1. **100 messages/day hard cap**
2. **30-90s random delay** between messages
3. **10-15 min pause** every 20 messages
4. **No duplicate messages within 30 days**
5. **No links** in any message
6. **3 consecutive failures = STOP** (something is wrong)
7. **Rotate templates** (never same message 3x in a row)
8. **Skip companies** (LLC, Ltd, etc.)
9. **Human-like typing** (20-80ms per character)
10. **3-hour session limit** (requires manual restart)
11. **Gradual ramp-up:** Day 1: 10, Day 2: 20, Day 3: 30, Day 4: 50, Day 5+: 100

---

## DEDUP LOGIC

The bot uses `message_log.csv` as the source of truth:

- **Never message same phone within 30 days** (even if in different campaigns)
- **Never retry "not_on_whatsapp" numbers** (flagged permanently)
- **Dedup before sending** (not after — saves API calls)

To reset dedup for a specific phone (for testing):
1. Open `whatsapp_bot/message_log.csv`
2. Delete rows for that phone
3. Save

---

## CAMPAIGN BUILDING LOGIC

### Landlord Lease Expiry

1. Get expiring leases from `palm_jumeirah_rentals.csv` (next N days)
2. For each lease, match `building + unit` against lead list to find OWNER
3. If owner has phone → queue message
4. If owner has no phone → skip
5. Remove already-messaged phones (from log)
6. Shuffle queue (avoid same building consecutively)

**IMPORTANT:** Phone numbers in lead list = LANDLORDS (not tenants). We message the property OWNER about their expiring lease.

### Cold Owner

1. Filter lead list by building/bedrooms/portfolio criteria
2. Count units per owner: 2+ units → portfolio templates, 1 unit → single templates
3. Skip companies (corporate name detection)
4. Remove already-messaged phones
5. Shuffle queue

---

## LOGS

**Location:** `whatsapp_bot/message_log.csv`

**Format:**
```
timestamp, campaign_id, phone, owner_name, building, unit, template_type, message, status, error
```

**Status values:**
- `sent` — Successfully sent
- `failed` — Error during send (selector issue, timeout, etc.)
- `not_on_whatsapp` — Phone not registered on WhatsApp

**Export:** Use Streamlit UI → WhatsApp page → Message Log tab → Download CSV.

---

## TESTING CHECKLIST

Before any real campaign:

1. **Test with YOUR OWN number first (REQUIRED)**
   ```bash
   python whatsapp_bot/run_campaign.py --test YOUR_PHONE_NUMBER
   ```
   Replace with your WhatsApp number. This sends ONE test message to verify:
   - Chrome connection working
   - WhatsApp Web logged in
   - Message formatting correct
   - Selectors still valid

2. **Run dry-run for each campaign type**
   ```bash
   python whatsapp_bot/run_campaign.py --type landlord_lease_expiry --days 90 --dry-run
   python whatsapp_bot/run_campaign.py --type cold_owner --portfolio-only --dry-run
   ```

3. **Verify name formatting**
   - Check dry-run output for correct first names (Title Case, no "MR.", etc.)
   - Verify corporate entities are skipped (no "LLC", "LTD" in queue)

4. **Verify unit numbers in messages**
   - Every message preview should contain "(Unit 607)" or similar

5. **Verify portfolio detection**
   - Portfolio-only mode should show ONLY owners with 2+ units
   - Portfolio templates should say "invested multiple times" or "multiple units"

6. **Verify dedup works**
   - Run same campaign twice with dry-run → second run should show 0 messages

---

## RESTRICTIONS AND LIMITS

**24h "restricted from new chats" (WhatsApp):**
- This is enforced by WhatsApp's servers. There is **no technical workaround** in this app.
- If you are restricted, wait out the period (typically 24 hours). Do not try to bypass it.
- The built-in **rate limiter** (`rate_limiter.py`) is there to reduce the chance of being flagged: daily cap (with ramp-up over 5 days), delays between messages, and mandatory pauses. Use it.
- **Practical tips:** After a restriction, keep volume low; stay under the app's daily cap; avoid sending spikes; consider [WhatsApp Business API](https://developers.facebook.com/docs/whatsapp/cloud-api) for higher, policy-compliant volume.

---

## TROUBLESHOOTING

### "Could not connect to Chrome"

**Problem:** Bot can't connect to Chrome via CDP.

**Fix:**
1. Close all Chrome windows
2. Launch Chrome with debug flag: `chrome.exe --remote-debugging-port=9222`
3. Open `web.whatsapp.com` and log in
4. Run bot again

### "WhatsApp Web tab not found"

**Problem:** Bot connected to Chrome but couldn't find WhatsApp Web.

**Fix:**
1. Make sure `web.whatsapp.com` is open in a tab
2. Make sure you're logged in (QR code scanned)
3. Refresh the WhatsApp tab if needed

### Phone number "not on WhatsApp" detection

**How it works:**
1. Bot navigates to `web.whatsapp.com/send?phone=...`
2. Waits for any popup/dialog to appear
3. Checks for text: "isn't on WhatsApp" or "is not on WhatsApp" or "Phone number...invalid"
4. If found:
   - Clicks "OK" button to dismiss popup
   - Logs number as `not_on_whatsapp`
   - Skips to next message (does NOT attempt to type)
5. Number is permanently flagged in `message_log.csv` (never retried)

**Why this matters:**
- Avoids wasting time typing messages to invalid numbers
- Prevents rate limit penalties from failed sends
- Keeps dedup log clean (invalid numbers never retried)

### "Input box not found (selectors may have changed)"

**Problem:** WhatsApp changed their HTML structure (happens ~1x/year).

**Fix:**
1. **STOP the bot immediately** (don't keep retrying)
2. Open WhatsApp Web in Chrome
3. Right-click input box → Inspect
4. Find new selector (usually `div[contenteditable="true"]` with a data attribute)
5. Update `bot.py` → `send_message()` → input box selectors

### "Daily cap reached"

**Problem:** Already sent max messages today.

**Fix:**
- Wait until tomorrow (cap resets at midnight)
- Or manually edit `message_log.csv` to remove today's entries (NOT recommended for production)

### Messages appearing as multiple separate messages

**Problem:** Multi-paragraph message splits into multiple WhatsApp bubbles.

**Fix:**
- This should NOT happen with the current implementation
- Bot uses **Shift+Enter** for line breaks (not Enter)
- Enter is pressed **only once** at the end to send complete message
- If you see splits, check `bot.py` → `send_message()` function
- Verify line breaks use: `page.keyboard.down('Shift')` + `press('Enter')` + `keyboard.up('Shift')`

### Messages going to spam

**Problem:** Recipient reports messages as spam.

**Fix:**
- Make sure templates don't contain links
- Reduce send rate (increase delays in `rate_limiter.py`)
- Personalize messages better (use first name, building context)
- Don't send same message to multiple people in same building consecutively

---

## IMPORTANT REMINDERS

- **Phone numbers in lead list = LANDLORDS, not tenants.** Lease expiry campaigns message the property OWNER.
- **Portfolio template ONLY for 2+ unit owners.** Never send "invested multiple times" to single-unit owners.
- **Do NOT modify `leads_master_v3.csv` or rental data.** Read-only.
- **Same Chrome debug port 9222** as Property Monitor scraper.
- **Message log is the dedup source of truth.** Protect this file.
- **WhatsApp Web selectors change frequently.** If selectors break, STOP and fix — don't keep retrying.

---

## SUPPORT

For issues or questions:
1. Check this README first
2. Read error messages carefully (most are self-explanatory)
3. Test with `--dry-run` before every real campaign
4. Check `message_log.csv` for send history and errors
