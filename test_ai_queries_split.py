"""
Regression tests for PR 9 -- ai_queries.py split from data_processor.py.

Covers:
  1. ai_queries.py exists and exposes every AI-tool function.
  2. data_processor.py re-exports every AI-tool function (back-compat)
     -- old callers that do `from data_processor import ..._for_ai`
     keep working without code changes.
  3. Both import paths resolve to the SAME function object (not a copy)
     so behaviour is guaranteed identical.
  4. data_processor.py itself no longer defines the AI functions as
     top-level defs -- they only live in ai_queries.py.
  5. One sample function actually runs end-to-end on an empty DataFrame
     and returns a safe empty result (no import-time side effects).

Run: python test_ai_queries_split.py
"""

import ast
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

AI_FN_NAMES = [
    "search_leads_for_ai",
    "get_building_info_for_ai",
    "get_market_stats_for_ai",
    "get_listings_below_market_for_ai",
    "get_portfolio_summary_for_ai",
    "find_potential_owners_for_ai",
    "cross_reference_sale_with_leads_for_ai",
    "get_building_units_for_ai",
    "get_complete_building_intel_for_ai",
    "search_building_names_for_ai",
    "list_all_buildings_for_ai",
    "get_propertyfinder_listings_for_ai",
]

failures: list[str] = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------------
# 1. ai_queries.py exists and has every AI function
# ---------------------------------------------------------------------------
print("\n[1] ai_queries.py exposes all AI tool functions")

import ai_queries  # noqa: E402

for name in AI_FN_NAMES:
    check(f"ai_queries.{name} exists", hasattr(ai_queries, name))

# ---------------------------------------------------------------------------
# 2. data_processor still re-exports them (back-compat)
# ---------------------------------------------------------------------------
print("\n[2] data_processor re-exports (back-compat)")

import data_processor  # noqa: E402

for name in AI_FN_NAMES:
    check(f"data_processor.{name} still importable", hasattr(data_processor, name))

# ---------------------------------------------------------------------------
# 3. Both paths point to the same function object
# ---------------------------------------------------------------------------
print("\n[3] Back-compat re-exports are identity-equal (not copies)")

for name in AI_FN_NAMES:
    a = getattr(ai_queries, name)
    b = getattr(data_processor, name)
    check(f"{name} is the same object via both imports", a is b)

# ---------------------------------------------------------------------------
# 4. data_processor does not DEFINE the AI functions as top-level defs
#    (they're only re-exported via `from ai_queries import ...`)
# ---------------------------------------------------------------------------
print("\n[4] data_processor no longer defines AI functions locally")

dp_src = (HERE / "data_processor.py").read_text(encoding="utf-8")
tree = ast.parse(dp_src)
local_defs = {
    node.name for node in tree.body
    if isinstance(node, ast.FunctionDef)
}
for name in AI_FN_NAMES:
    check(
        f"{name} is no longer a top-level def in data_processor.py",
        name not in local_defs,
    )

# private helpers moved with the AI functions should also be gone
for helper in ("_get_median_market_price", "_parse_listing_price_to_aed"):
    check(
        f"{helper} moved out of data_processor.py",
        helper not in local_defs,
    )

# ---------------------------------------------------------------------------
# 5. One function runs end-to-end on empty inputs without blowing up
# ---------------------------------------------------------------------------
print("\n[5] Sample function runs on empty data")

empty_leads = pd.DataFrame(
    columns=["owner_name", "building_name", "unit_number", "bedrooms", "size_sqft", "phone"]
)
try:
    result = ai_queries.search_leads_for_ai(empty_leads, building="Shoreline 9")
    check("search_leads_for_ai returns an empty list on empty data", result == [])
except Exception as e:
    check("search_leads_for_ai runs without raising on empty input", False, f"raised: {e}")

try:
    result = ai_queries.list_all_buildings_for_ai(pd.DataFrame())
    check("list_all_buildings_for_ai runs on empty ref_df", isinstance(result, dict))
except Exception as e:
    check("list_all_buildings_for_ai runs without raising", False, f"raised: {e}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All AI-queries-split checks passed.")
