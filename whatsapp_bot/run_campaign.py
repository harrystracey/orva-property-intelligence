"""
CLI Entry Point for WhatsApp Campaigns
Usage:
  python whatsapp_bot/run_campaign.py --type landlord_lease_expiry --days 90 --dry-run
  python whatsapp_bot/run_campaign.py --type cold_owner --building "Shoreline 12" --dry-run
  python whatsapp_bot/run_campaign.py --type cold_owner --portfolio-only
"""

import asyncio
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from bot import connect_to_whatsapp, reconnect_to_whatsapp, send_message, format_phone_for_whatsapp, verify_whatsapp_ready
from campaign_manager import (
    build_landlord_lease_expiry_queue,
    build_cold_owner_queue,
    build_recent_sale_queue,
    build_portfolio_owner_queue,
    build_active_seller_queue,
    build_active_renter_queue,
    build_propspace_leads_queue,
    apply_dedup_to_queue,
    shuffle_queue,
    generate_messages_for_queue
)
from rate_limiter import RateLimiter, mark_restriction_now
from message_log import log_message, get_today_send_count, was_ever_messaged


async def run_campaign(
    campaign_type: str,
    building: Optional[str] = None,
    bedrooms: Optional[str] = None,
    area: Optional[str] = None,
    days_ahead: int = 90,
    portfolio_only: bool = False,
    min_units: int = 3,
    limit: Optional[int] = None,
    dry_run: bool = False,
    override_limit: bool = False,
    custom_message: Optional[str] = None,
    lead_type: Optional[str] = None,
    beds: Optional[int] = None,
    not_yet_contacted: bool = False,
    exclude_file=None,
    no_limits: bool = False,
    account: str = '1',
):
    """Execute a WhatsApp campaign."""
    campaign_id = f"{campaign_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print("=" * 70)
    print(f"  WHATSAPP CAMPAIGN: {campaign_type.upper()}")
    print("=" * 70)
    print(f"  Campaign ID: {campaign_id}")
    print(f"  Mode: {'DRY RUN (no messages sent)' if dry_run else 'LIVE'}")
    print()
    
    # Build queue
    print("[QUEUE] Building message queue...")
    
    if campaign_type == 'landlord_lease_expiry':
        queue = build_landlord_lease_expiry_queue(
            days_ahead=days_ahead,
            building_filter=building,
            bedrooms_filter=bedrooms,
            area_filter=area
        )
    elif campaign_type == 'cold_owner':
        queue = build_cold_owner_queue(
            building_filter=building,
            bedrooms_filter=bedrooms,
            portfolio_only=portfolio_only,
            limit=limit,
            area_filter=area
        )
    elif campaign_type == 'recent_sale':
        queue = build_recent_sale_queue(
            since_days=days_ahead,
            building_filter=building,
            limit=limit,
            area_filter=area
        )
    elif campaign_type == 'portfolio_owner':
        queue = build_portfolio_owner_queue(
            min_units=min_units,
            building_filter=building,
            bedrooms_filter=bedrooms,
            limit=limit,
            area_filter=area
        )
    elif campaign_type == 'active_seller':
        queue = build_active_seller_queue(
            building_filter=building,
            limit=limit,
            area_filter=area
        )
    elif campaign_type == 'active_renter':
        queue = build_active_renter_queue(
            building_filter=building,
            limit=limit,
            area_filter=area
        )
    elif campaign_type == 'propspace_leads':
        queue = build_propspace_leads_queue(
            location=building or None,
            lead_type=lead_type,
            beds=beds,
            sub_status_filter='new' if not_yet_contacted else 'all',
            limit=limit,
        )
    else:
        print(f"[ERROR] Unknown campaign type: {campaign_type}")
        return
    
    if not queue:
        print("[ERROR] Queue is empty after filters")
        return
    
    # Apply dedup
    queue = apply_dedup_to_queue(queue, days_window=30, wa_account=account)
    
    if not queue:
        print("[ERROR] Queue is empty after dedup (all phones messaged recently)")
        return
    
    # Apply manual exclusions from app queue preview.
    # Normalize both sides via format_phone_for_whatsapp so "+971 55 ..."
    # in the exclude list still matches a "971551234567" queue entry.
    if exclude_file:
        import json as _json
        from bot import format_phone_for_whatsapp as _fpw
        _excl_path = Path(exclude_file) if Path(exclude_file).is_absolute() else Path(__file__).parent / exclude_file
        if _excl_path.exists():
            _raw_excl = _json.loads(_excl_path.read_text(encoding="utf-8"))
            _excl_normalized = {n for n in (_fpw(p) for p in _raw_excl) if n}
            _before = len(queue)
            queue = [item for item in queue if _fpw(item.get("phone")) not in _excl_normalized]
            print(f"[EXCLUDE] Removed {_before - len(queue)} manually excluded contacts ({len(queue)} remaining)")
    
    # Generate messages (or use single custom message for all)
    if custom_message and custom_message.strip():
        print("\n[MESSAGES] Using single custom message for all contacts")
        msg = custom_message.strip()
        for item in queue:
            from message_templates import format_first_name as _ffn
            _first = _ffn(item.get('owner_name', '')) or 'there'
            item['message'] = (msg
                .replace('{name}', _first)
                .replace('{unit}', str(item.get('unit', '') or ''))
                .replace('{building}', str(item.get('building', '') or ''))
                .replace('{phone}', str(item.get('phone', '') or ''))
            )
            item['template_type'] = 'custom'
    else:
        print("\n[MESSAGES] Generating personalized messages...")
        queue = generate_messages_for_queue(queue)
        if not queue:
            print("[ERROR] Queue is empty after message generation (all corporate entities?)")
            return
    
    # Shuffle to avoid consecutive same-building messages
    queue = shuffle_queue(queue)
    print(f"[OK] Queue shuffled: {len(queue)} messages ready")
    
    # DRY RUN: Preview only
    if dry_run:
        print()
        print("=" * 70)
        print(f"  DRY RUN PREVIEW ({len(queue)} messages)")
        print("=" * 70)
        
        preview_count = min(10, len(queue))
        for i, item in enumerate(queue[:preview_count], 1):
            print(f"\n[{i}] {item['owner_name']}")
            print(f"    Building: {item['building']}, Unit: {item['unit']}")
            print(f"    Phone: {format_phone_for_whatsapp(item['phone'])}")
            print(f"    Template: {item['template_type']}")
            print(f"    Message preview:")
            print("    " + item['message'].replace('\n', '\n    '))
        
        if len(queue) > preview_count:
            print(f"\n  ... and {len(queue) - preview_count} more messages")
        
        print()
        print("=" * 70)
        print(f"  Total: {len(queue)} messages would be sent")
        print(f"  To run for real, remove --dry-run")
        print("=" * 70)
        return
    
    # LIVE SEND
    print()
    print("=" * 70)
    print(f"  STARTING LIVE CAMPAIGN ({len(queue)} messages)")
    print("=" * 70)
    print()
    
    # Check daily cap
    rate_limiter = RateLimiter(override_limit=override_limit)
    if override_limit:
        print(f"[CAP] Override: skipping ramp-up (daily cap still enforced via message log)")
    daily_cap = rate_limiter.get_daily_cap()
    today_count = get_today_send_count()
    print(f"[CAP] Today's sent: {today_count} / {daily_cap}")
    can_send, reason = rate_limiter.can_send_today()
    if not can_send and not no_limits:
        print(f"[STOP] {reason}")
        return
    
    # Connect to WhatsApp
    playwright, browser, page = None, None, None
    print("\n[CONNECT] Connecting to WhatsApp Web...")
    try:
        playwright, browser, page = await connect_to_whatsapp()
    except Exception as e:
        print(f"[ERROR] Could not connect: {e}")
        print("\nSTEPS TO FIX:")
        print("1. Launch WhatsApp Chrome: powershell -File whatsapp_bot/start_whatsapp_chrome.ps1")
        print("   (First time: log in in that window. Next times: already logged in.)")
        print("2. Run this script again")
        return

    try:
        # Verify WhatsApp is ready
        ready = await verify_whatsapp_ready(page)
        if not ready:
            print("[WARN] WhatsApp Web may not be ready. Continuing anyway...")

        print()
        print(f"[START] Sending {len(queue)} messages...")
        print(f"[START] Estimated duration: {len(queue) * 60 / 60:.1f} minutes")
        print()

        # Send loop
        sent_count = 0
        failed_count = 0
        not_on_wa_count = 0
        existing_chat_count = 0
        skipped_already_messaged = 0

        _stop_flag = Path(__file__).resolve().parent / "stop_campaign.flag"

        for idx, item in enumerate(queue, 1):
            # Check for manual stop from app UI
            if _stop_flag.exists():
                try:
                    _stop_flag.unlink()
                except Exception:
                    pass
                print("\n[STOP] Campaign stopped by user.")
                break

            # Check if should stop
            if not no_limits:
                should_stop, stop_reason = rate_limiter.should_stop_session()
                if should_stop:
                    print(f"\n[STOP] {stop_reason}")
                    break

            # Check daily cap again
            if not no_limits:
                can_send, reason = rate_limiter.can_send_today()
                if not can_send:
                    print(f"\n[STOP] {reason}")
                    break

            # Format phone
            phone_formatted = format_phone_for_whatsapp(item['phone'])
            if not phone_formatted:
                print(f"[{idx}/{len(queue)}] SKIP: Invalid phone for {item['owner_name']}")
                continue

            if was_ever_messaged(phone_formatted, wa_account=account):
                print(f"[{idx}/{len(queue)}] [SKIP] Already conversed: {item['owner_name']}")
                skipped_already_messaged += 1
                continue

            print(f"[{idx}/{len(queue)}] {item['owner_name']} - {item['building']} Unit {item['unit']}")

            # Send message
            result = await send_message(page, phone_formatted, item['message'], account=account)
            # Log result
            log_message(
                campaign_id=campaign_id,
                phone=phone_formatted,
                owner_name=item['owner_name'],
                building=item['building'],
                unit=item['unit'],
                template_type=item['template_type'],
                message=item['message'],
                status=result['status'],
                error=result.get('error', ''),
                wa_account=account,
            )

            # Update counters
            if result['status'] == 'sent':
                sent_count += 1
            elif result['status'] == 'failed':
                failed_count += 1
            elif result['status'] == 'not_on_whatsapp':
                not_on_wa_count += 1
            elif result['status'] == 'existing_chat':
                existing_chat_count += 1

            rate_limiter.record_send_attempt(result['status'], item['template_type'])

            # Check if should stop due to failures
            if not no_limits:
                should_stop, stop_reason = rate_limiter.should_stop_session()
                if should_stop:
                    print(f"\n[STOP] {stop_reason}")
                    break

            # Only delay when a message was actually sent (skip delay for not_on_whatsapp, failed, etc.)
            if result['status'] == 'sent':
                if no_limits:
                    if idx < len(queue):
                        await asyncio.sleep(3)
                else:
                    did_pause = await rate_limiter.check_mandatory_pause()
                    if did_pause:
                        print("\n[RECONNECT] Reconnecting to Chrome after long pause...")
                        try:
                            playwright, browser, page = await reconnect_to_whatsapp(playwright, browser)
                            rate_limiter.consecutive_failures = 0
                            print("[OK] Reconnected.")
                            ready = await verify_whatsapp_ready(page)
                            if not ready:
                                print("[WARN] WhatsApp tab may still be loading (white screen). Waiting 10s...")
                                await asyncio.sleep(10)
                            print()
                        except Exception as e:
                            print(f"[ERROR] Reconnect failed: {e}")
                            print("[STOP] Cannot continue without WhatsApp connection.")
                            break
                    if idx < len(queue):
                        await rate_limiter.wait_between_messages()

        # Summary
        print()
        print("=" * 70)
        print("  CAMPAIGN COMPLETE")
        print("=" * 70)
        print(f"  Sent: {sent_count}")
        print(f"  Failed: {failed_count}")
        print(f"  Not on WhatsApp: {not_on_wa_count}")
        print(f"  Skipped (existing chat): {existing_chat_count}")
        print(f"  Skipped (already conversed): {skipped_already_messaged}")
        print(f"  Total today: {get_today_send_count()}")
        print("=" * 70)
    finally:
        # Always close browser and stop Playwright so Windows doesn't raise "I/O operation on closed pipe"
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await asyncio.sleep(0.25)
                await playwright.stop()
            except Exception:
                pass


async def run_test_message(phone: str):
    """Send a single test message to verify WhatsApp connection and message delivery."""
    print("=" * 70)
    print("  WHATSAPP TEST MODE")
    print("=" * 70)
    print(f"  Test phone: {phone}")
    print()
    
    # Generate a sample test message
    test_message = (
        "Hi there! This is a test message from Harry's Palm Jumeirah outreach system.\n\n"
        "I'm testing the WhatsApp integration. If you're seeing this, it means the bot is "
        "working correctly 😊\n\n"
        "Sample property intel: Shoreline 12 (Unit 505) has been seeing strong activity recently.\n\n"
        "Harry."
    )
    
    print("[TEST] Sample message:")
    print("=" * 70)
    print(test_message)
    print("=" * 70)
    print()
    
    # Format phone
    formatted_phone = format_phone_for_whatsapp(phone)
    if not formatted_phone:
        print(f"[ERROR] Invalid phone number: {phone}")
        return
    
    print(f"[TEST] Formatted phone: {formatted_phone}")
    print()
    
    # Connect to WhatsApp
    playwright, browser, page = None, None, None
    print("[CONNECT] Connecting to WhatsApp Web...")
    try:
        playwright, browser, page = await connect_to_whatsapp()
    except Exception as e:
        print(f"[ERROR] Could not connect: {e}")
        print("\nSTEPS TO FIX:")
        print("1. Launch WhatsApp Chrome: powershell -File whatsapp_bot/start_whatsapp_chrome.ps1")
        print("   (First time: log in in that window. Next times: already logged in.)")
        print("2. Run this test again")
        return

    try:
        # Verify WhatsApp is ready
        ready = await verify_whatsapp_ready(page)
        if not ready:
            print("[WARN] WhatsApp Web may not be ready. Continuing anyway...")

        print()
        print("[SEND] Sending test message...")
        print()

        # Send message
        result = await send_message(page, formatted_phone, test_message)

        # Show result
        print()
        print("=" * 70)
        if result['status'] == 'sent':
            print("  ✅ TEST SUCCESSFUL")
            print(f"  Message sent to {formatted_phone}")
        elif result['status'] == 'not_on_whatsapp':
            print("  ⚠️  TEST RESULT: Not on WhatsApp")
            print(f"  {formatted_phone} is not registered on WhatsApp")
        else:
            print("  ❌ TEST FAILED")
            print(f"  Status: {result['status']}")
            print(f"  Error: {result.get('error', 'Unknown')}")
        print("=" * 70)
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await asyncio.sleep(0.25)
                await playwright.stop()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="WhatsApp Campaign Runner")
    
    parser.add_argument(
        '--type',
        choices=['landlord_lease_expiry', 'cold_owner', 'recent_sale', 'portfolio_owner', 'active_seller', 'active_renter'],
        help='Campaign type'
    )
    
    parser.add_argument('--building', type=str, help='Building filter (e.g. "Shoreline 12")')
    parser.add_argument('--area', type=str, help='Area filter: Palm Jumeirah, Dubai Marina, JBR, or All')
    parser.add_argument('--bedrooms', type=str, help='Bedroom filter (e.g. "2")')
    parser.add_argument('--days', type=int, default=90, help='Days ahead for lease expiry (default: 90)')
    parser.add_argument('--portfolio-only', action='store_true', help='Only message portfolio investors (2+ units)')
    parser.add_argument('--min-units', type=int, default=3, help='Portfolio owner campaign: min units per owner (default: 3)')
    parser.add_argument('--limit', type=int, help='Limit queue size (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, do not send messages')
    parser.add_argument('--override-limit', action='store_true', dest='override_limit', help='Use full daily cap, skip ramp-up')
    parser.add_argument('--mark-restricted', action='store_true', help='Record today as restriction date; cooldown will apply when you run campaigns again')
    parser.add_argument('--test', type=str, metavar='PHONE', help='Test mode: send one message to specified phone (e.g. YOUR_PHONE_NUMBER)')
    parser.add_argument('--custom-message-file', type=str, metavar='PATH', help='Path to file containing a single message to send to all contacts (overrides templates)')
    parser.add_argument('--lead-type', type=str, choices=['tenant', 'buyer', 'both'], default=None,
                        help='PropSpace leads: filter by lead type')
    parser.add_argument('--beds', type=int, default=None,
                        help='PropSpace leads: filter by beds_min')
    parser.add_argument('--not-yet-contacted', action='store_true', dest='not_yet_contacted',
                        help='PropSpace leads: only not-yet-contacted sub_status')
    parser.add_argument('--exclude-file', type=str, metavar='PATH', dest='exclude_file',
                        help='JSON file with phone numbers to skip (written by app queue preview)')
    parser.add_argument('--no-limits', action='store_true', dest='no_limits',
                        help='Skip all delays, caps and pauses. Send continuously until done or Ctrl+C.')
    parser.add_argument('--account', type=str, default='1', choices=['1', '2'],
                        help='WhatsApp account to use (1=port 3001, 2=port 3002). Default: 1')

    args = parser.parse_args()
    
    if args.mark_restricted:
        mark_restriction_now()
        print("Restriction date recorded. Cooldown (reduced caps + doubled delays for 2 days) will apply for the next 7 days.")
        return
    
    # Test mode
    if args.test:
        asyncio.run(run_test_message(args.test))
        return
    
    # Campaign mode requires --type
    if not args.type:
        parser.error("--type is required for campaign mode (or use --test for test mode)")
    
    custom_message = None
    if getattr(args, 'custom_message_file', None):
        p = Path(args.custom_message_file)
        if p.exists():
            custom_message = p.read_text(encoding='utf-8')
        else:
            print(f"[WARN] Custom message file not found: {p}")
    
    asyncio.run(run_campaign(
        campaign_type=args.type,
        building=args.building,
        bedrooms=args.bedrooms,
        area=args.area,
        days_ahead=args.days,
        portfolio_only=args.portfolio_only,
        min_units=args.min_units,
        limit=args.limit,
        dry_run=args.dry_run,
        override_limit=args.override_limit,
        custom_message=custom_message,
        lead_type=getattr(args, "lead_type", None),
        beds=getattr(args, "beds", None),
        not_yet_contacted=getattr(args, "not_yet_contacted", False),
        exclude_file=getattr(args, "exclude_file", None),
        no_limits=getattr(args, "no_limits", False),
        account=getattr(args, "account", "1"),
    ))


if __name__ == "__main__":
    main()
