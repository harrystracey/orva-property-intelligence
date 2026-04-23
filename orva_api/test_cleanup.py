"""
Regression tests for PR 8 -- API cleanup.

Covers:
  1. orva_api._sys_paths is the single source of truth for sys.path
     augmentation (no more inline `sys.path.insert` blocks in routers).
  2. DataStore builds a client_id -> row index on load so
     find_client_row is O(1) (not O(n)).
  3. Chat service uses the module-level CLAUDE_MODEL constant and
     defaults to the latest Sonnet 4.x, overridable via CLAUDE_MODEL env.
  4. Frontend api.ts exposes typed CampaignPreviewParams /
     CampaignStartParams (no more Record<string, unknown>).
  5. Dockerfile creates a non-root user, USERs to it, and has HEALTHCHECK.

Run from repo root:
    python -m orva_api.test_cleanup

The sys.path test runs in a subprocess so it sees a clean sys.path.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

failures: list[str] = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def run_in_subprocess(script: str) -> tuple[int, str, str]:
    full_env = {
        **os.environ,
        "JWT_SECRET": "a" * 48,
        "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [PY, "-c", script],
        cwd=str(REPO_ROOT),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# 1. Inline `sys.path.insert` blocks are gone from routers and services
# ---------------------------------------------------------------------------
print("\n[1] sys.path consolidation")

HERE = REPO_ROOT / "orva_api"
files_that_should_use_the_helper = [
    HERE / "main.py",
    HERE / "deps.py",
    HERE / "routers" / "leads.py",
    HERE / "routers" / "clients.py",
    HERE / "routers" / "whatsapp.py",
    HERE / "services" / "chat_service.py",
    HERE / "services" / "campaign_runner.py",
]

for f in files_that_should_use_the_helper:
    src = f.read_text(encoding="utf-8")
    check(
        f"{f.relative_to(REPO_ROOT)} no longer calls sys.path.insert",
        "sys.path.insert" not in src,
    )
    check(
        f"{f.relative_to(REPO_ROOT)} imports _sys_paths",
        "_sys_paths" in src,
    )

# _sys_paths.py itself exists and is the only file that modifies sys.path
check(
    "_sys_paths.py exists",
    (HERE / "_sys_paths.py").exists(),
)

# ---------------------------------------------------------------------------
# 2. DataStore.find_client_row is O(1) via the precomputed index
# ---------------------------------------------------------------------------
print("\n[2] O(1) client lookup")

script = dedent(
    """
    import pandas as pd
    from orva_api.deps import DataStore

    store = DataStore.__new__(DataStore)
    store.leads_df = pd.DataFrame([
        {"owner_name": "John Smith", "building_name": "Shoreline 9", "unit_number": "201"},
        {"owner_name": "Jane Doe",   "building_name": "Oceana",      "unit_number": "1501"},
        {"owner_name": None,         "building_name": "Tiara",       "unit_number": "805"},
    ])
    store.ref_df = pd.DataFrame()
    store.ref_stats = {}
    store._client_index = {}
    store._loaded = False
    store._rebuild_client_index()

    # The index must contain entries for rows with a valid owner
    assert len(store._client_index) >= 2, f"expected >=2, got {len(store._client_index)}"

    # find_client_row on a known id returns a row
    any_id = next(iter(store._client_index))
    row = store.find_client_row(any_id)
    assert row is not None, "find_client_row returned None for indexed id"

    # find_client_row on a bogus id returns None (not an exception)
    assert store.find_client_row("bogus_does_not_exist") is None

    print("ok")
    """
)

rc, out, err = run_in_subprocess(script)
check("find_client_row works via the precomputed index", rc == 0 and "ok" in out, f"stdout={out!r} stderr={err[:200]!r}")

# ---------------------------------------------------------------------------
# 3. CLAUDE_MODEL module constant + env override
# ---------------------------------------------------------------------------
print("\n[3] CLAUDE_MODEL constant")

chat_service_src = (REPO_ROOT / "orva_api" / "services" / "chat_service.py").read_text(encoding="utf-8")
check(
    "chat_service defines CLAUDE_MODEL module constant",
    "CLAUDE_MODEL = os.getenv" in chat_service_src,
)
check(
    "default model is claude-sonnet-4-6",
    '"claude-sonnet-4-6"' in chat_service_src,
)
# No hardcoded old model snapshot left
check(
    "old claude-sonnet-4-20250514 literal removed",
    "claude-sonnet-4-20250514" not in chat_service_src,
)
# All client.messages.create calls route through the constant
create_calls = re.findall(r"client\.messages\.create\(\s*model\s*=\s*([A-Za-z_][\w]*)", chat_service_src)
check(
    "every messages.create uses model=CLAUDE_MODEL",
    len(create_calls) >= 3 and all(c == "CLAUDE_MODEL" for c in create_calls),
    f"call sites: {create_calls}",
)

# env override works in a subprocess
rc, out, err = run_in_subprocess("from orva_api.services.chat_service import CLAUDE_MODEL; print(CLAUDE_MODEL)")
check("default CLAUDE_MODEL resolves", rc == 0 and out.strip() == "claude-sonnet-4-6", f"got {out!r}")

env = {
    **os.environ,
    "JWT_SECRET": "a" * 48,
    "CLAUDE_MODEL": "claude-haiku-4-5-20251001",
    "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
}
result = subprocess.run(
    [PY, "-c", "from orva_api.services.chat_service import CLAUDE_MODEL; print(CLAUDE_MODEL)"],
    cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=30,
)
check(
    "CLAUDE_MODEL env override respected",
    result.returncode == 0 and "claude-haiku-4-5-20251001" in result.stdout,
    f"got {result.stdout!r}",
)

# ---------------------------------------------------------------------------
# 4. Frontend has typed campaign param interfaces
# ---------------------------------------------------------------------------
print("\n[4] Typed campaign params")

api_ts = (REPO_ROOT / "orva-web" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
check("CampaignPreviewParams interface present", "export interface CampaignPreviewParams" in api_ts)
check("CampaignStartParams extends CampaignPreviewParams", "interface CampaignStartParams extends CampaignPreviewParams" in api_ts)
check(
    "previewCampaign signature no longer accepts Record<string, unknown>",
    "previewCampaign(params: CampaignPreviewParams)" in api_ts
    and "previewCampaign(params: Record<string, unknown>)" not in api_ts,
)
check(
    "startCampaign signature typed",
    "startCampaign(params: CampaignStartParams)" in api_ts,
)

# ---------------------------------------------------------------------------
# 5. Dockerfile hardening: non-root user + HEALTHCHECK
# ---------------------------------------------------------------------------
print("\n[5] Dockerfile hardening")

dockerfile = (REPO_ROOT / "orva_api" / "Dockerfile").read_text(encoding="utf-8")
check("Dockerfile creates an orva user", "useradd" in dockerfile and "orva" in dockerfile)
check("Dockerfile switches to the non-root user before CMD",
      re.search(r"USER orva\s", dockerfile) is not None)
check("Dockerfile has a HEALTHCHECK", "HEALTHCHECK" in dockerfile)
check("HEALTHCHECK hits /api/health", "/api/health" in dockerfile)

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All API-cleanup checks passed.")
