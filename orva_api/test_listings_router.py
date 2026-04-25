"""
Regression tests for the orva_api listings router.

Covers:
  1. Schemas import + validation (negative budget rejected, etc.)
  2. All 4 endpoints registered on the FastAPI app.
  3. Empty-data responses are well-formed (no rentals / no Bayut CSV
     should produce empty arrays + sensible totals, not 500s).
  4. Validation: invalid transaction_type / negative budget rejected
     with 422.
  5. Auth required (401 without token).

Run:
    python -m orva_api.test_listings_router
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def run_in_subprocess(script: str) -> tuple[int, str, str]:
    env = {
        **os.environ,
        "JWT_SECRET": "a" * 48,
        "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [PY, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# 1. Schemas
# ---------------------------------------------------------------------------
print("\n[1] orva_api.schemas.listings")

os.environ.setdefault("JWT_SECRET", "a" * 48)
from orva_api.schemas.listings import (  # noqa: E402
    ExpiringLease, LeaseExpiryResponse,
    MatchListingRequest, MatchedOwner, MatchListingResponse,
    BayutListing, BuildingSummary, BayutListingsResponse,
    ClientMatchRequest, OwnerMatchResult, ClientMatchResponse,
)
from pydantic import ValidationError  # noqa: E402

# ExpiringLease accepts all-None fields
ExpiringLease(has_owner_contact=False)
check("ExpiringLease accepts all defaults except has_owner_contact", True)

# MatchListingRequest requires building_name
bad = False
try:
    MatchListingRequest()  # type: ignore[call-arg]
except ValidationError:
    bad = True
check("MatchListingRequest rejects missing building_name", bad)

# size_sqft must be > 0
bad = False
try:
    MatchListingRequest(building_name="x", size_sqft=0)
except ValidationError:
    bad = True
check("MatchListingRequest rejects size_sqft<=0", bad)

# ClientMatchRequest requires transaction_type
bad = False
try:
    ClientMatchRequest()  # type: ignore[call-arg]
except ValidationError:
    bad = True
check("ClientMatchRequest rejects missing transaction_type", bad)

# Negative budget rejected
bad = False
try:
    ClientMatchRequest(transaction_type="sale", budget_min=-1)
except ValidationError:
    bad = True
check("ClientMatchRequest rejects negative budget", bad)

# Defaults are sensible
req = ClientMatchRequest(transaction_type="sale")
check("ClientMatchRequest default limit is 100", req.limit == 100)
check("ClientMatchRequest default sea_view_only is False", req.sea_view_only is False)
check("ClientMatchRequest default buildings is []", req.buildings == [])


# ---------------------------------------------------------------------------
# 2. Endpoints registered
# ---------------------------------------------------------------------------
print("\n[2] Endpoints registered on FastAPI app")

script = dedent("""
    import os
    os.environ.setdefault('JWT_SECRET', 'a' * 48)
    from orva_api.main import app
    paths = sorted({route.path for route in app.routes if hasattr(route, 'path')})
    print('\\n'.join(p for p in paths if any(s in p for s in
        ('lease-expiry', 'match/listing', 'bayut/listings', 'client-match'))))
""")
rc, out, err = run_in_subprocess(script)
check("orva_api.main imports cleanly", rc == 0, f"stderr={err[:200]!r}")

for path in [
    "/api/lease-expiry",
    "/api/match/listing",
    "/api/bayut/listings",
    "/api/client-match",
]:
    check(f"path {path} is registered", path in out)


# ---------------------------------------------------------------------------
# 3. Empty-data behaviour (no CSVs in tempdir)
# ---------------------------------------------------------------------------
print("\n[3] Empty-data responses are well-formed (no 500s)")

with tempfile.TemporaryDirectory() as tmp:
    script = dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        os.environ['JWT_SECRET'] = 'a' * 48
        sys.path.insert(0, {str(REPO_ROOT)!r})

        # Stub out the data-store load so we don't try to read missing CSVs.
        # We still need the DataStore object to expose .leads_df for client-match.
        import database
        database.init_database()

        from orva_api.deps import data_store, get_data_store
        import pandas as pd
        data_store.leads_df = pd.DataFrame()
        data_store.ref_df = pd.DataFrame()
        data_store.ref_stats = {{}}
        data_store._client_index = {{}}
        data_store._loaded = True  # bypass on-startup load

        from orva_api import auth
        from orva_api.main import app
        app.dependency_overrides[auth.get_current_user] = lambda: {{
            "username": "test", "name": "Test"
        }}
        from fastapi.testclient import TestClient
        client = TestClient(app)

        # Lease expiry
        r = client.get('/api/lease-expiry?days_ahead=90')
        assert r.status_code == 200, (r.status_code, r.text)
        body = r.json()
        assert body['leases'] == [], body
        assert body['total'] == 0
        assert body['expiry_window_days'] == 90

        # Bayut listings
        r = client.get('/api/bayut/listings')
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['listings'] == []
        assert body['total'] == 0

        # Client match (empty leads -> empty result)
        r = client.post('/api/client-match', json={{
            "transaction_type": "sale",
        }})
        assert r.status_code == 200, r.text
        assert r.json()['matches'] == []

        # Match listing -- 503 because no leads CSV exists in tempdir
        r = client.post('/api/match/listing', json={{
            "building_name": "Shoreline 9",
        }})
        assert r.status_code in (200, 503), (r.status_code, r.text)

        # Validation: bad transaction_type -> 422
        r = client.post('/api/client-match', json={{
            "transaction_type": "lease",
        }})
        assert r.status_code == 422, r.text

        # Validation: missing building_name on match -> 422
        r = client.post('/api/match/listing', json={{}})
        assert r.status_code == 422, r.text

        # Validation: negative price_min on bayut -> 422
        r = client.get('/api/bayut/listings?price_min=-1')
        assert r.status_code == 422, r.text

        # Days_ahead range check
        r = client.get('/api/lease-expiry?days_ahead=999999')
        assert r.status_code == 422, r.text

        print('OK')
    """)
    rc, out, err = run_in_subprocess(script)
    check(
        "all 4 endpoints handle empty data + validation cleanly",
        rc == 0 and "OK" in out,
        f"stderr={err[-400:]!r}",
    )


# ---------------------------------------------------------------------------
# 4. Auth required
# ---------------------------------------------------------------------------
print("\n[4] Auth enforced when not overridden")

with tempfile.TemporaryDirectory() as tmp:
    script = dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        os.environ['JWT_SECRET'] = 'a' * 48
        sys.path.insert(0, {str(REPO_ROOT)!r})
        import database
        database.init_database()

        from orva_api.deps import data_store
        import pandas as pd
        data_store.leads_df = pd.DataFrame()
        data_store.ref_df = pd.DataFrame()
        data_store.ref_stats = {{}}
        data_store._client_index = {{}}
        data_store._loaded = True

        from orva_api.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        for path, method, body in [
            ('/api/lease-expiry', 'GET', None),
            ('/api/bayut/listings', 'GET', None),
            ('/api/match/listing', 'POST', {{"building_name": "x"}}),
            ('/api/client-match', 'POST', {{"transaction_type": "sale"}}),
        ]:
            r = client.request(method, path, json=body)
            assert r.status_code == 401, (path, r.status_code, r.text)
        print('OK')
    """)
    rc, out, err = run_in_subprocess(script)
    check("all 4 endpoints return 401 when unauthenticated", rc == 0 and "OK" in out, f"stderr={err[-300:]!r}")


# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All listings-router checks passed.")
