"""
DLD Trakheesi Listing Validator
================================
Resolves Madmoun listing GUIDs (from Bayut/PropertyFinder QR codes) to property
details via the Dubai Land Department's Madmoun validation API.

Uses a headed Playwright browser to load the Trakheesi validation page, which
executes the reCAPTCHA v3 challenge natively and intercepts the DLD API response.
This approach is free (no 2Captcha cost), faster (~5-10s), and gets a
high-quality reCAPTCHA score that DLD's backend accepts.

Usage:
    python -m scraper.dld_validator <GUID or Madmoun URL>
"""

import re
import time
import asyncio
import logging

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

TRAKHEESI_BASE = "https://trakheesi.dubailand.gov.ae/rev/madmoun/listing/validation"
DLD_API_FRAGMENT = "ext.dubailand.gov.ae/trakheesi"

# Rate limiting for batch mode
RATE_LIMIT_DELAY = 1.5   # seconds between browser launches in batch mode


# ── Core: Playwright-based validation ─────────────────────────────────────────

async def _validate_via_browser(listing_guid: str) -> dict:
    """
    Load the Trakheesi validation page in a headed browser, intercept the DLD API
    response, and return the raw JSON data dict.

    The page automatically executes reCAPTCHA v3 and POSTs to the DLD API on load.
    A real Chrome window gets a high enough reCAPTCHA score for DLD to accept.
    """
    from playwright.async_api import async_playwright

    page_url = f"{TRAKHEESI_BASE}?khevJujtDig={listing_guid}"
    captured_response: dict = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()

        async def handle_response(response):
            if DLD_API_FRAGMENT in response.url and response.request.method == "POST":
                try:
                    body = await response.json()
                    captured_response["data"] = body
                    captured_response["status"] = response.status
                    logger.info("DLD API response intercepted — status %d", response.status)
                except Exception as exc:
                    captured_response["error"] = f"Could not parse DLD response: {exc}"
                    captured_response["status"] = response.status

        page.on("response", handle_response)
        logger.info("Loading Trakheesi validation page…")

        await page.goto(page_url, wait_until="networkidle", timeout=30_000)

        # Wait up to 15 s for the API response to arrive after page load
        deadline = 15
        waited = 0
        while "data" not in captured_response and "error" not in captured_response and waited < deadline:
            await asyncio.sleep(0.5)
            waited += 0.5

        await browser.close()

    return captured_response


def _run_browser_validation(listing_guid: str) -> dict:
    """
    Synchronous wrapper around the async Playwright function.

    Runs Playwright in a dedicated worker thread so the ProactorEventLoop it
    needs on Windows is completely isolated from Streamlit's thread-local loop
    state.  This avoids NotImplementedError from SelectorEventLoop on any call,
    not just the first.
    """
    import sys
    import concurrent.futures

    def _worker() -> dict:
        # Each call gets a fresh thread → fresh event loop with no prior state.
        # On Windows, ProactorEventLoop is required for subprocess creation
        # (Playwright launches Chrome via asyncio.create_subprocess_exec).
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_validate_via_browser(listing_guid))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            future = _pool.submit(_worker)
            return future.result(timeout=60)
    except Exception as exc:
        return {"error": f"Browser launch failed: {exc}", "status": 0}


# ── Public API ─────────────────────────────────────────────────────────────────

def validate_listing(listing_guid: str) -> dict:
    """
    Resolve a Trakheesi/Madmoun listing GUID to property details.

    Args:
        listing_guid: Madmoun GUID string, e.g.
                      "gc2hzdo7t8plgx47pfisx1h5mhuf3wfsbw3kujydscuhchrrn"

    Returns:
        dict with keys:
            success, building, building_ar, zone, size_sqm, size_sqft,
            beds, floor, value, permit_type, agency, permit_number,
            listing_number, license_number, permit_status,
            permit_start, permit_end, owner_name, owner_phone, owner_email,
            guid, raw_response, error
        All errors caught — check result['success'] and result['error'].
    """
    result: dict = {
        "success": False,
        "guid": listing_guid,
        "error": None,
        "raw_response": None,
        "building": "", "building_ar": "", "zone": "",
        "size_sqm": 0.0, "size_sqft": 0.0,
        "beds": "", "floor": None,
        "value": 0.0, "permit_type": "", "agency": "",
        "permit_number": "", "listing_number": "", "license_number": "",
        "permit_status": "", "permit_start": "", "permit_end": "",
        "owner_name": None, "owner_phone": None, "owner_email": None,
    }

    try:
        browser_result = _run_browser_validation(listing_guid)

        if "error" in browser_result and "data" not in browser_result:
            result["error"] = browser_result["error"]
            return result

        if browser_result.get("status", 0) not in (200, 0):
            result["error"] = (
                f"DLD API returned HTTP {browser_result['status']} — "
                "reCAPTCHA may have been rejected. Try again."
            )
            return result

        data = browser_result.get("data", {})
        result["raw_response"] = data

        if not data:
            result["error"] = "No response data captured from DLD API"
            return result

        if data.get("Code") != 0:
            result["error"] = (
                f"DLD API Code {data.get('Code')}: {data.get('Errors', [])}"
            )
            logger.warning(result["error"])
            return result

        resp = data.get("Response") or {}
        if not resp:
            result["error"] = "Empty Response body from DLD API"
            return result

        size_sqm = resp.get("PropertySize") or 0.0

        result.update({
            "success": True,
            "building": resp.get("BuildingNameEn") or resp.get("PropertyNameEn") or "Unknown",
            "building_ar": resp.get("BuildingNameAr") or resp.get("PropertyNameAr") or "",
            "zone": resp.get("ZoneNameEn") or "",
            "size_sqm": size_sqm,
            # DLD PropertySize is always sqm — convert for the matcher
            "size_sqft": round(size_sqm * 10.764, 2) if size_sqm else 0.0,
            "beds": resp.get("RoomTypeEn") or "",
            "floor": resp.get("FloorNumber"),
            "value": resp.get("PropertyValue") or 0.0,
            "permit_type": resp.get("PermitTypeNameEn") or "",
            "agency": resp.get("AuthorityNameEn") or "",
            "permit_number": resp.get("PermitNumber") or "",
            "listing_number": resp.get("ListingNumber") or "",
            "license_number": resp.get("LicenseNumber") or "",
            "permit_status": resp.get("PermitStatusEn") or "",
            "permit_start": resp.get("StartDate") or "",
            "permit_end": resp.get("EndDate") or "",
            # CardHolder fields almost always null — owner comes from lead DB
            "owner_name": resp.get("CardHolderNameEn"),
            "owner_phone": resp.get("CardHolderMobile"),
            "owner_email": resp.get("CardHolderEmail"),
            "error": None,
        })

        logger.info(
            "Resolved: %s | %s | %s | %.0f sqft | %s",
            result["building"], result["zone"], result["beds"],
            result["size_sqft"], result["permit_type"],
        )

    except Exception as exc:
        result["error"] = f"Unexpected error — {type(exc).__name__}: {exc}"
        logger.error(result["error"])

    return result


def batch_validate(guids: list, progress_callback=None) -> list:
    """
    Validate multiple GUIDs with rate limiting and one retry pass for failures.

    Args:
        guids: list of GUID strings
        progress_callback: optional callable(current: int, total: int, result: dict)

    Returns:
        List of result dicts (same schema as validate_listing).
    """
    results: list = []
    failed_pairs: list = []
    total = len(guids)
    logger.info("Starting batch validation of %d listings…", total)

    for i, guid in enumerate(guids):
        logger.info("[%d/%d] Validating: %s…", i + 1, total, guid[:20])
        res = validate_listing(guid)
        results.append(res)

        if not res["success"]:
            failed_pairs.append((guid, res["error"]))

        if progress_callback:
            progress_callback(i + 1, total, res)

        if i < total - 1:
            time.sleep(RATE_LIMIT_DELAY)

    if failed_pairs:
        logger.info("Retrying %d failed lookups…", len(failed_pairs))
        time.sleep(2)
        for guid, _orig_err in failed_pairs:
            retry = validate_listing(guid)
            if retry["success"]:
                for j, r in enumerate(results):
                    if r["guid"] == guid and not r["success"]:
                        results[j] = retry
                        break
            time.sleep(RATE_LIMIT_DELAY)

    success_count = sum(1 for r in results if r["success"])
    logger.info("Batch complete: %d/%d succeeded", success_count, total)
    return results


def extract_guid_from_url(url: str) -> str | None:
    """
    Extract the listing GUID from a Madmoun URL or return the raw GUID if clean.

    Supported formats:
      - https://trakheesi.dubailand.gov.ae/…?khevJujtDig=<GUID>
      - Raw GUID string (30+ alphanumeric chars)
    """
    if not url:
        return None
    url = url.strip()

    if "khevJujtDig=" in url:
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            return params.get("khevJujtDig", [None])[0]
        except Exception:
            m = re.search(r"khevJujtDig=([a-zA-Z0-9]+)", url)
            return m.group(1) if m else None

    if re.match(r"^[a-zA-Z0-9]{30,}$", url):
        return url

    return None


# ── CLI Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Windows consoles default to cp1252 which can't encode emoji — force UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m scraper.dld_validator <GUID or Madmoun URL>")
        print("Example: python -m scraper.dld_validator gc2hzdo7t8plgx47pfisx1h5mhuf3wfsbw3kujydscuhchrrn")
        sys.exit(1)

    raw_input = sys.argv[1]
    guid = extract_guid_from_url(raw_input) or raw_input

    print(f"\n🔍 Validating GUID: {guid[:30]}…")
    print("   (Opening browser, executing reCAPTCHA — ~5-10 seconds)\n")

    res = validate_listing(guid)

    if res["success"]:
        print("=" * 60)
        print("✅ PROPERTY DETAILS")
        print("=" * 60)
        print(f"  Building:    {res['building']} ({res['building_ar']})")
        print(f"  Zone:        {res['zone']}")
        print(f"  Size:        {res['size_sqm']} sqm / {res['size_sqft']} sqft")
        print(f"  Bedrooms:    {res['beds']}")
        print(f"  Floor:       {res['floor'] or 'N/A'}")
        print(f"  Value:       AED {res['value']:,.0f}")
        print(f"  Type:        {res['permit_type']}")
        print(f"  Agency:      {res['agency']}")
        print(f"  Permit:      {res['permit_number']}")
        print(f"  DLD Listing: {res['listing_number']}")
        print(f"  License:     {res['license_number']}")
        print(f"  Status:      {res['permit_status']}")
        start = res["permit_start"][:10] if res["permit_start"] else "N/A"
        end   = res["permit_end"][:10]   if res["permit_end"]   else "N/A"
        print(f"  Valid:       {start} → {end}")
        if res["owner_name"]:
            print(f"\n  🎯 OWNER IN DLD RESPONSE:")
            print(f"  Owner:  {res['owner_name']}")
            print(f"  Phone:  {res['owner_phone']}")
            print(f"  Email:  {res['owner_email']}")
        else:
            print("\n  ℹ️  Owner not in DLD response (normal)")
            print("     → Cross-reference with lead database via listing_matcher")
        print("=" * 60)
    else:
        print(f"❌ FAILED: {res['error']}")
        print("\nTroubleshooting:")
        print("  1. Ensure Chrome/Playwright is installed: playwright install chromium")
        print("  2. Verify the GUID came from a Madmoun QR code or URL")
        print("  3. Try again — reCAPTCHA occasionally scores low on first load")
