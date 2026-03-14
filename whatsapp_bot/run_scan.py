"""
Scan WhatsApp chats for all bot-messaged contacts.
Called as a subprocess from the Streamlit app (WA Inbox tab).
Outputs PROGRESS:N/TOTAL:name lines to stdout for progress tracking.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from whatsapp_bot.bot import connect_to_whatsapp, scan_chat_messages
from whatsapp_bot.message_log import get_sent_entries_for_reply_check
import re
from whatsapp_bot.chat_scans import save_scan
from contact_manager import get_contact_by_phone, create_contact


async def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    entries = get_sent_entries_for_reply_check(days=90)
    if not entries:
        print("DONE:0", flush=True)
        return

    # Load PropSpace budget data by phone
    _ps_budget = {}
    try:
        _ps_csv = Path(__file__).parent.parent / "scraped_data" / "propspace_leads.csv"
        if _ps_csv.exists():
            import csv as _csv
            with open(_ps_csv, encoding="utf-8") as _f:
                for _pr in _csv.DictReader(_f):
                    _pn = re.sub(r"[^0-9]", "", _pr.get("phone", ""))
                    if _pn:
                        _ps_budget[_pn] = {
                            "budget_min": _pr.get("budget_min", ""),
                            "budget_max": _pr.get("budget_max", ""),
                        }
    except Exception:
        pass

    playwright, browser, page = await connect_to_whatsapp()
    try:
        for i, e in enumerate(entries):
            name = e.get("owner_name", e["phone"])[:30]
            print(f"PROGRESS:{i+1}/{len(entries)}:{name}", flush=True)
            try:
                result = await scan_chat_messages(page, e["phone"])
            except Exception as ex:
                print(f"WARN:skip {e['phone']}: {ex}", flush=True)
                result = {
                    "incoming_count": 0, "outgoing_count": 0,
                    "last_reply_text": "", "last_reply_at": "", "last_sent_at": ""
                }
            result["phone"] = e["phone"]
            save_scan(e["phone"], e.get("owner_name", ""), result, e.get("template_type", ""),
                      building=e.get("building", ""), unit=e.get("unit", ""))
            # Auto-create contact in SQLite if not already there
            try:
                if not get_contact_by_phone(e["phone"]):
                    _ctype = {"propspace_buyer": "Buyer", "propspace_tenant": "Tenant"}.get(
                        e.get("template_type", ""), "Landlord")
                    _pn_norm = re.sub(r"[^0-9]", "", e["phone"])
                    _bdata = _ps_budget.get(_pn_norm, {})
                    _bmin = float(_bdata["budget_min"]) if _bdata.get("budget_min", "") not in ("", "nan") else None
                    _bmax = float(_bdata["budget_max"]) if _bdata.get("budget_max", "") not in ("", "nan") else None
                    create_contact(
                        full_name=e.get("owner_name") or None,
                        phone=e["phone"],
                        contact_type=_ctype,
                        source="WA Scan",
                        budget_min=_bmin,
                        budget_max=_bmax,
                    )
            except Exception as _ce:
                print(f"WARN: contact create failed {e['phone']}: {_ce}", file=sys.stderr, flush=True)
            await asyncio.sleep(2.0)
        print(f"DONE:{len(entries)}", flush=True)
    finally:
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await playwright.stop()
        except Exception:
            pass


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
