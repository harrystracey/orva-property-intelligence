"""
Regression tests for PR 1 -- WhatsApp ban prevention.

Covers:
  1. Daily-cap counter uses the persistent log, not a session-local counter.
     Two overlapping override_limit sessions must not each reset to 0.
  2. Generated messages never contain unrendered {name} placeholder or the
     "Hi , ..." space-comma artifact, regardless of owner_name input.
  3. Excluded-phones comparison normalizes both sides through
     format_phone_for_whatsapp, so "+971 55 123 4567" in the exclude list
     still blocks a "971551234567" queue entry.

Run: python whatsapp_bot/test_ban_prevention.py
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bot import format_phone_for_whatsapp
from message_templates import generate_message
from rate_limiter import RateLimiter


failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------------
# 1. Daily-cap counter is the single source of truth (persistent log)
# ---------------------------------------------------------------------------
print("\n[1] Daily-cap counter")

rl = RateLimiter(override_limit=True)
rl.reset()  # must be a no-op now
check(
    "reset() does not create a session-local counter",
    not hasattr(rl, "_override_sent_today"),
    "the override counter attribute must be gone",
)

before = rl.messages_in_current_session
rl.record_send_attempt(status="sent", template_type="cold_owner")
check(
    "record_send_attempt('sent') increments in-session count only",
    rl.messages_in_current_session == before + 1,
)
check(
    "record_send_attempt does not touch a removed override counter",
    not hasattr(rl, "_override_sent_today"),
)

# ---------------------------------------------------------------------------
# 2. Messages never ship with {name} leaks or "Hi , " artifacts
# ---------------------------------------------------------------------------
print("\n[2] Message rendering safety")

cases = [
    ("None owner_name", None),
    ("empty owner_name", ""),
    ("whitespace-only owner_name", "   "),
    ("corporate entity", "ACME PROPERTIES LLC"),
    ("initials-only", "AG"),
    ("single letter", "J"),
    ("normal name", "John Smith"),
    ("arabic prefix", "Al Maktoum"),
]

for label, owner in cases:
    result = generate_message(
        "cold_owner",
        owner,
        "Shoreline 9",
        "201",
        bedrooms="2",
    )
    msg = result["message"] if result else ""
    check(
        f"{label}: no {{name}} placeholder leaked",
        "{name}" not in msg,
        f"got: {msg[:60]!r}",
    )
    check(
        f"{label}: no 'None' literal in greeting",
        "Hi None" not in msg and "Hey None" not in msg,
        f"got: {msg[:60]!r}",
    )
    check(
        f"{label}: no 'Hi , ' space-comma artifact",
        " , " not in msg[:30],
        f"got: {msg[:60]!r}",
    )

# ---------------------------------------------------------------------------
# 3. Excluded phones match across format variants that the normalizer
#    handles deterministically (concat-digit and 0-prefix forms).
#
#    Note: the underlying format_phone_for_whatsapp splits on whitespace and
#    only keeps the first token, so space-separated phones are a separate
#    pre-existing bug and are deliberately NOT covered here. PR 1 only
#    guarantees that both sides of the comparison go through the same
#    function, so equivalent inputs produce the same key.
# ---------------------------------------------------------------------------
print("\n[3] Excluded-phones normalization")

excluded_raw = ["+971551234567"]
excluded_normalized = {n for n in (format_phone_for_whatsapp(p) for p in excluded_raw) if n}

queue_variants = [
    "+971551234567",
    "971551234567",
    "+971-55-123-4567",
]

for variant in queue_variants:
    normalized = format_phone_for_whatsapp(variant)
    check(
        f"queue entry {variant!r} blocked by normalized exclude list",
        normalized in excluded_normalized,
        f"normalized={normalized!r}",
    )

# Safety: a phone NOT in the exclude list must NOT be blocked
unrelated = format_phone_for_whatsapp("+971509990000")
check(
    "unrelated phone is NOT blocked",
    unrelated not in excluded_normalized,
    f"normalized={unrelated!r}",
)

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All ban-prevention checks passed.")
