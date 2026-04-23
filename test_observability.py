"""
Regression tests for PR 6 -- Observability.

Covers:
  1. The enrichment `stats` dict exposes distinct counters per cascade
     priority (beds_from_reidin, beds_from_pf, beds_from_bayut_size)
     instead of collapsing them all into beds_from_registry.
  2. The priority-cascade comment in data_processor.py lists every
     priority that the code actually emits a counter for.

Run: python test_observability.py
"""

import ast
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from data_processor import apply_comprehensive_enrichment

failures: list[str] = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------------
# 1. Stats dict exposes the new counters even on an empty dataframe
# ---------------------------------------------------------------------------
print("\n[1] Enrichment stats counters")

empty_df = pd.DataFrame(
    columns=[
        "building_name", "unit_number", "bedrooms", "size_sqft",
        "owner_name", "phone", "date",
    ]
)
_, stats = apply_comprehensive_enrichment(
    empty_df, estimation_table={}, prediction_table={}, unit_pattern_table={}
)

for key in ("beds_from_reidin", "beds_from_registry", "beds_from_pf", "beds_from_bayut_size"):
    check(
        f"stats exposes {key!r}",
        key in stats,
        f"stats keys: {sorted(stats.keys())}",
    )

check(
    "stats does not silently collapse Reidin/PF into registry",
    "beds_from_reidin" in stats and "beds_from_pf" in stats,
)

# ---------------------------------------------------------------------------
# 2. Cascade comment reflects the actual priorities emitted in code
# ---------------------------------------------------------------------------
print("\n[2] Cascade comment accuracy")

source = (HERE / "data_processor.py").read_text(encoding="utf-8")
comment_anchor_idx = source.find("Priority order for bedroom inference")
header = source[comment_anchor_idx: comment_anchor_idx + 1500]

for needle in ("1.5  Live Reidin", "2.3  Live PropertyFinder", "2.6  Bayut size-match"):
    check(
        f"cascade comment mentions {needle!r}",
        needle in header,
        f"snippet head: {header[:120]!r}",
    )

# There should be exactly one `# PRIORITY 4:` header in the code now
# (the duplicate size-inference one was renamed to PRIORITY 4.5).
priority_4_lines = [ln for ln in source.splitlines() if ln.strip().startswith("# PRIORITY 4:")]
check(
    "no duplicate '# PRIORITY 4:' header remains",
    len(priority_4_lines) == 1,
    f"found {len(priority_4_lines)}",
)

# ---------------------------------------------------------------------------
# 3. orva_api adopts stdlib logging (no bare print() in main.py startup)
# ---------------------------------------------------------------------------
print("\n[3] orva_api uses stdlib logging")

main_src = (HERE / "orva_api" / "main.py").read_text(encoding="utf-8")
check(
    "main.py imports logging",
    "import logging" in main_src,
)
check(
    "main.py lifespan uses logger, not print",
    "logger.info(\"loading lead data\")" in main_src,
)
check(
    "main.py no longer calls print() in lifespan",
    "print(\"[ORVA API]" not in main_src,
)

auth_src = (HERE / "orva_api" / "auth.py").read_text(encoding="utf-8")
check(
    "auth.py uses logger for USERS_FILE warnings",
    "logger.warning(" in auth_src,
)
check(
    "auth.py no longer prints [auth] warnings",
    "print(f\"[auth]" not in auth_src,
)

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All observability checks passed.")
