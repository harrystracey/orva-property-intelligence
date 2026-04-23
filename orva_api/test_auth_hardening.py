"""
Regression tests for PR 3 -- Auth hardening.

Covers:
  1. config.py refuses to load when JWT_SECRET is missing, banned, or short.
  2. config.py accepts JWT_EXPIRY_HOURS and CORS_ORIGINS from env.
  3. auth.USERS loads from USERS_FILE when it exists; falls back otherwise.
  4. get_user_from_request resolves a token from Authorization header
     OR ?token= query param; missing/bogus tokens raise 401.

Run from repo root:
    python -m orva_api.test_auth_hardening

The tests set JWT_SECRET + other env vars before importing orva_api, so they
have to run in subprocesses for isolation (config.py validates at import).
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

failures: list[str] = []


def run_subprocess_test(label: str, env: dict, script: str) -> tuple[int, str, str]:
    """Run a Python snippet in a clean subprocess with the given env."""
    full_env = {**os.environ, **env}
    # Ensure repo root on PYTHONPATH so `import orva_api` works.
    full_env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + full_env.get("PYTHONPATH", "")
    result = subprocess.run(
        [PY, "-c", script],
        cwd=str(REPO_ROOT),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------------
# 1. JWT_SECRET validation at config import
# ---------------------------------------------------------------------------
print("\n[1] JWT_SECRET validation")

bad_cases = [
    ("missing",           {"JWT_SECRET": ""}),
    ("default placeholder", {"JWT_SECRET": "orva-jwt-secret-change-in-production"}),
    ("too short",         {"JWT_SECRET": "short"}),
    ("another placeholder", {"JWT_SECRET": "changeme"}),
]
for label, env in bad_cases:
    rc, out, err = run_subprocess_test(label, env, "from orva_api.config import JWT_SECRET")
    check(
        f"config refuses {label} JWT_SECRET",
        rc != 0 and "JWT_SECRET" in err,
        f"rc={rc}, stderr head: {err.splitlines()[-1] if err else '<empty>'}",
    )

good_secret = "a" * 48
rc, out, err = run_subprocess_test(
    "good secret",
    {"JWT_SECRET": good_secret},
    "from orva_api.config import JWT_SECRET; print(JWT_SECRET)",
)
check(
    "config accepts a 48-char JWT_SECRET",
    rc == 0 and good_secret in out,
    f"rc={rc}",
)

# ---------------------------------------------------------------------------
# 2. JWT_EXPIRY_HOURS + CORS_ORIGINS env overrides
# ---------------------------------------------------------------------------
print("\n[2] Configurable expiry + CORS")

rc, out, err = run_subprocess_test(
    "custom expiry",
    {"JWT_SECRET": good_secret, "JWT_EXPIRY_HOURS": "72"},
    "from orva_api.config import JWT_EXPIRY_HOURS; print(JWT_EXPIRY_HOURS)",
)
check("JWT_EXPIRY_HOURS respects env", rc == 0 and out.strip() == "72", f"got {out!r}")

rc, out, err = run_subprocess_test(
    "default expiry is 7 days",
    {"JWT_SECRET": good_secret},
    "from orva_api.config import JWT_EXPIRY_HOURS; print(JWT_EXPIRY_HOURS)",
)
check("default JWT_EXPIRY_HOURS is 168 (7 days)", rc == 0 and out.strip() == "168", f"got {out!r}")

rc, out, err = run_subprocess_test(
    "custom CORS origins",
    {
        "JWT_SECRET": good_secret,
        "CORS_ORIGINS": "https://orvauae.com, http://localhost:3000",
    },
    "from orva_api.config import CORS_ORIGINS; print(CORS_ORIGINS)",
)
check(
    "CORS_ORIGINS splits and trims",
    rc == 0 and "https://orvauae.com" in out and "http://localhost:3000" in out,
    f"got {out!r}",
)

# ---------------------------------------------------------------------------
# 3. USERS loads from JSON file when present
# ---------------------------------------------------------------------------
print("\n[3] USERS_FILE loading")

with tempfile.TemporaryDirectory() as tmp:
    users_path = Path(tmp) / "users.json"
    payload = {
        "alice": {
            "name": "Alice",
            "email": "alice@test.local",
            "password_hash": "$2b$12$placeholder_not_used_in_test",
        }
    }
    users_path.write_text(json.dumps(payload), encoding="utf-8")

    rc, out, err = run_subprocess_test(
        "users from file",
        {"JWT_SECRET": good_secret, "USERS_FILE": str(users_path)},
        "from orva_api.auth import USERS; print(sorted(USERS.keys()))",
    )
    check(
        "USERS loads from USERS_FILE",
        rc == 0 and "'alice'" in out and "'harry'" not in out,
        f"got stdout={out!r} stderr={err[:120]!r}",
    )

    rc, out, err = run_subprocess_test(
        "users fallback when file missing",
        {"JWT_SECRET": good_secret, "USERS_FILE": str(Path(tmp) / "does_not_exist.json")},
        "from orva_api.auth import USERS; print(sorted(USERS.keys()))",
    )
    check(
        "USERS falls back to legacy dict when file missing",
        rc == 0 and "'harry'" in out,
        f"got {out!r}",
    )

# ---------------------------------------------------------------------------
# 4. get_user_from_request resolves header OR query-param token
# ---------------------------------------------------------------------------
print("\n[4] SSE-friendly token extraction")

sse_script = dedent(
    """
    import sys
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from orva_api.auth import get_user_from_request, create_token

    token = create_token("harry")

    # Mock request with a token query param
    class Req:
        def __init__(self, qp): self.query_params = qp
    class QP:
        def __init__(self, d): self._d = d
        def get(self, k): return self._d.get(k)

    # Case A: Authorization header present
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    u = get_user_from_request(Req(QP({})), credentials=creds)
    assert u["username"] == "harry", f"header auth: {u}"
    print("A-ok")

    # Case B: No header, query param present
    u = get_user_from_request(Req(QP({"token": token})), credentials=None)
    assert u["username"] == "harry", f"query auth: {u}"
    print("B-ok")

    # Case C: Neither => 401
    try:
        get_user_from_request(Req(QP({})), credentials=None)
        print("C-should-have-raised")
    except HTTPException as e:
        assert e.status_code == 401, f"got {e.status_code}"
        print("C-ok")

    # Case D: Invalid token => 401
    try:
        get_user_from_request(Req(QP({"token": "garbage"})), credentials=None)
        print("D-should-have-raised")
    except HTTPException as e:
        assert e.status_code == 401, f"got {e.status_code}"
        print("D-ok")
    """
)

rc, out, err = run_subprocess_test("sse token extraction", {"JWT_SECRET": good_secret}, sse_script)
check("header auth works", "A-ok" in out, f"stdout={out!r} stderr={err[:200]!r}")
check("query-param auth works", "B-ok" in out)
check("missing token raises 401", "C-ok" in out)
check("bogus token raises 401", "D-ok" in out)


# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All auth-hardening checks passed.")
