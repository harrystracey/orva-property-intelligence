"""
Regression tests for Phase 2 -- restricted scrapers removed.

Covers:
  1. Deleted modules/dirs no longer exist on disk.
  2. No remaining .py file imports them.
  3. Public scrapers (Bayut, PropertyFinder) still on disk.
  4. reidin_processor.py still importable + process_reidin_export still works
     (CSV ingestion path is the only Reidin entry point now).
  5. orva-web /tools/reidin stub is gone, /tools/pf-scraper still present
     (PF scraper is public -- user wants it kept even though UI is a stub).
  6. app.py itself has been deleted (Streamlit removed in Phase 4).

Run: python test_restricted_scrapers_removed.py
"""

import ast
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

failures: list[str] = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------------
# 1. Deleted paths are gone
# ---------------------------------------------------------------------------
print("\n[1] Restricted scraper paths deleted")

deleted_paths = [
    "archive_propertymonitor",
    "propspace_scraper",
    "reidin_extractor.py",
    "reidin_debug.py",
    "orva-web/src/app/tools/reidin",
]
for rel in deleted_paths:
    p = HERE / rel
    check(f"{rel} no longer exists", not p.exists())


# ---------------------------------------------------------------------------
# 2. No .py file imports the deleted modules
# ---------------------------------------------------------------------------
print("\n[2] No code imports the deleted modules")

forbidden_imports = [
    "reidin_extractor",
    "reidin_debug",
    "propspace_scraper",
    "scraper_agent",   # was inside archive_propertymonitor/
]

py_files = [
    p for p in HERE.rglob("*.py")
    if "node_modules" not in p.parts
    and ".venv" not in p.parts
    and "__pycache__" not in p.parts
]

for forbidden in forbidden_imports:
    offenders = []
    for f in py_files:
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        # Look for actual import statements (not comments / docstrings)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == forbidden:
                        offenders.append(str(f.relative_to(HERE)))
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod == forbidden:
                    offenders.append(str(f.relative_to(HERE)))
    check(
        f"no Python file imports `{forbidden}`",
        not offenders,
        f"offenders: {offenders}" if offenders else "",
    )


# ---------------------------------------------------------------------------
# 3. Public scrapers still on disk
# ---------------------------------------------------------------------------
print("\n[3] Public scrapers preserved")

kept_paths = [
    "bayut_scraper",
    "propertyfinder_scraper",
    "propertyfinder_scraper/scraper.py",
    "reidin_processor.py",  # CSV-only ingestion still useful
]
for rel in kept_paths:
    p = HERE / rel
    check(f"{rel} still present", p.exists())


# ---------------------------------------------------------------------------
# 4. reidin_processor still importable + CSV path intact
# ---------------------------------------------------------------------------
print("\n[4] reidin_processor.py still works for CSV ingestion")

import reidin_processor  # noqa: E402

check(
    "process_reidin_export is callable",
    callable(getattr(reidin_processor, "process_reidin_export", None)),
)
check(
    "process_reidin_raw was removed (live extractor gone)",
    not hasattr(reidin_processor, "process_reidin_raw"),
)


# ---------------------------------------------------------------------------
# 5. orva-web stubs
# ---------------------------------------------------------------------------
print("\n[5] orva-web tool stubs")

check(
    "orva-web/src/app/tools/reidin is gone",
    not (HERE / "orva-web/src/app/tools/reidin").exists(),
)
# /tools/pf-scraper is left in place because PF scraper itself is kept.
# We don't assert its UI state here -- it's a stub either way.


# ---------------------------------------------------------------------------
# 6. app.py is gone (Streamlit removed in Phase 4)
# ---------------------------------------------------------------------------
print("\n[6] Streamlit (app.py) has been deleted")

check(
    "app.py no longer exists at repo root",
    not (HERE / "app.py").exists(),
)
check(
    "start_app.ps1 launcher is gone",
    not (HERE / "start_app.ps1").exists(),
)
_req_lines = [
    L.strip()
    for L in (HERE / "requirements.txt").read_text(encoding="utf-8").splitlines()
    if L.strip() and not L.strip().startswith("#")
]
_pkg_names = {L.split("=")[0].split(">")[0].split("<")[0].strip().lower() for L in _req_lines}
check(
    "streamlit no longer in requirements.txt",
    not any(p.startswith("streamlit") for p in _pkg_names),
    f"packages: {sorted(_pkg_names)}",
)


# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All restricted-scraper-removal checks passed.")
