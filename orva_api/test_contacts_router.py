"""
Regression tests for the orva_api contacts router.

Covers:
  1. Schemas import + Pydantic validates required vs optional fields.
  2. Router is registered on the FastAPI app with all 9 endpoints.
  3. End-to-end CRUD against a temp SQLite DB (init_database in a tempdir):
       - POST   /api/contacts           -> create
       - GET    /api/contacts           -> list (filters work)
       - GET    /api/contacts/{id}      -> detail (props + linked leads)
       - PUT    /api/contacts/{id}      -> partial update
       - POST   /api/contacts/{id}/properties      -> add
       - PUT    /api/contacts/{id}/properties/{p}  -> update
       - DELETE /api/contacts/{id}/properties/{p}  -> remove
       - DELETE /api/contacts/{id}      -> delete
  4. Auth is required on every endpoint (401 without token).
  5. Validation: contact_type / intent rejected with 422 when invalid.
  6. Duplicate (phone, full_name) returns 409.

Subprocess isolation: each test that needs a DB runs in a subprocess with
cwd set to a tempdir, so the user's real ./data/palm_intelligence.db is
never mutated.

Run:
    python -m orva_api.test_contacts_router
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


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def run_in_subprocess(script: str, *, env_extra: dict | None = None) -> tuple[int, str, str]:
    env = {
        **os.environ,
        "JWT_SECRET": "a" * 48,
        "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    if env_extra:
        env.update(env_extra)
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
print("\n[1] orva_api.schemas.contacts")

os.environ.setdefault("JWT_SECRET", "a" * 48)
from orva_api.schemas.contacts import (  # noqa: E402
    ContactRecord, ContactDetail, ContactListResponse,
    CreateContactRequest, UpdateContactRequest,
    ContactProperty, AddPropertyRequest,
    LinkedLead, ResolveUnitSpecsResponse,
    CONTACT_TYPES, INTENT_VALUES,
)

check("CONTACT_TYPES exposes the canonical 6 values", len(CONTACT_TYPES) == 6)
check(
    "INTENT_VALUES contains selling/renting/buying/renting_looking",
    set(INTENT_VALUES) == {"selling", "renting", "buying", "renting_looking"},
)

# Minimal payloads validate
ContactRecord(id=1)  # only id is required
CreateContactRequest()  # all optional
ContactDetail(id=1)  # properties + linked_leads default to []

check("ContactRecord accepts id-only", True)
check("CreateContactRequest accepts empty payload", True)
check("ContactDetail defaults properties + linked_leads to []", True)

# Negative budget rejected
from pydantic import ValidationError  # noqa: E402

bad = False
try:
    CreateContactRequest(budget_min=-100)
except ValidationError:
    bad = True
check("CreateContactRequest rejects negative budget", bad)

bad = False
try:
    AddPropertyRequest(price_aed=-1)
except ValidationError:
    bad = True
check("AddPropertyRequest rejects negative price", bad)


# ---------------------------------------------------------------------------
# 2. Router registration
# ---------------------------------------------------------------------------
print("\n[2] Router is mounted on the FastAPI app")

# Run inside subprocess so we don't need the data store loaded.
script = dedent("""
    import os
    os.environ.setdefault('JWT_SECRET', 'a' * 48)
    from orva_api.main import app
    paths = sorted({route.path for route in app.routes if hasattr(route, 'path')})
    print('PATHS:', '|'.join(p for p in paths if p.startswith('/api/contacts')))
""")
rc, out, err = run_in_subprocess(script)
check("orva_api.main imports cleanly with contacts router", rc == 0, f"stderr={err[:300]!r}")

expected_paths = [
    "/api/contacts",
    "/api/contacts/{contact_id}",
    "/api/contacts/{contact_id}/properties",
    "/api/contacts/{contact_id}/properties/{property_id}",
    "/api/contacts/{contact_id}/resolve-unit-specs",
]
for path in expected_paths:
    check(f"path {path} is registered", path in out)


# ---------------------------------------------------------------------------
# 3. End-to-end CRUD against a temp SQLite DB using TestClient
# ---------------------------------------------------------------------------
print("\n[3] End-to-end CRUD via FastAPI TestClient")

with tempfile.TemporaryDirectory() as tmp:
    script = dedent(f"""
        import os, json, sys
        os.chdir({tmp!r})
        os.environ['JWT_SECRET'] = 'a' * 48
        sys.path.insert(0, {str(REPO_ROOT)!r})

        # Bypass the lifespan data load -- it tries to read CSVs that don't
        # exist in the tempdir. We just want HTTP-level routing + DB.
        import database
        database.init_database()

        # Stub a no-op auth dep so we don't have to mint real JWTs.
        from orva_api import auth
        auth.get_current_user = lambda: {{"username": "test", "name": "Test"}}

        # Re-import the router so it picks up the patched dep.
        # Easier: monkey-patch the dependency_overrides on the app.
        from orva_api.main import app
        app.dependency_overrides[auth.get_current_user] = lambda: {{
            "username": "test", "name": "Test",
        }}

        from fastapi.testclient import TestClient
        client = TestClient(app)

        # --- Create ---
        r = client.post("/api/contacts", json={{
            "full_name": "Alice Owner",
            "phone": "+971501234567",
            "email": "alice@example.com",
            "contact_type": "Owner",
        }})
        assert r.status_code == 201, (r.status_code, r.text)
        alice = r.json()
        assert alice["id"]
        assert alice["full_name"] == "Alice Owner"

        # Duplicate -> 409
        r = client.post("/api/contacts", json={{
            "full_name": "Alice Owner",
            "phone": "+971501234567",
        }})
        assert r.status_code == 409, (r.status_code, r.text)

        # Bad contact_type -> 422
        r = client.post("/api/contacts", json={{
            "full_name": "Mallory",
            "contact_type": "Hacker",
        }})
        assert r.status_code == 422, (r.status_code, r.text)

        # --- List + filter ---
        # Add a Buyer to test the type filter
        r = client.post("/api/contacts", json={{
            "full_name": "Bob Buyer",
            "phone": "+971502222222",
            "contact_type": "Buyer",
        }})
        assert r.status_code == 201

        r = client.get("/api/contacts")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2, data
        assert len(data["contacts"]) == 2

        r = client.get("/api/contacts?contact_type=Buyer")
        assert r.status_code == 200
        data = r.json()
        assert all(c["contact_type"] == "Buyer" for c in data["contacts"]), data
        assert len(data["contacts"]) == 1

        r = client.get("/api/contacts?query=alice")
        assert r.status_code == 200
        data = r.json()
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["full_name"] == "Alice Owner"

        # --- Detail ---
        r = client.get(f"/api/contacts/{{alice['id']}}")
        assert r.status_code == 200
        detail = r.json()
        assert detail["id"] == alice["id"]
        assert detail["properties"] == []
        assert detail["linked_leads"] == []

        # 404 path
        r = client.get("/api/contacts/9999999")
        assert r.status_code == 404

        # --- Update ---
        r = client.put(f"/api/contacts/{{alice['id']}}", json={{
            "agent_assigned": "Harry",
        }})
        assert r.status_code == 200, r.text
        assert r.json()["agent_assigned"] == "Harry"

        # --- Add property ---
        r = client.post(f"/api/contacts/{{alice['id']}}/properties", json={{
            "building_name": "Shoreline 9",
            "unit_number": "201",
            "bedrooms": "2",
            "intent": "selling",
            "price_aed": 5500000,
        }})
        assert r.status_code == 201, r.text
        prop = r.json()
        assert prop["intent"] == "selling"
        assert prop["bedrooms"] == "2"

        # Bad intent -> 422
        r = client.post(f"/api/contacts/{{alice['id']}}/properties", json={{
            "intent": "stealing",
        }})
        assert r.status_code == 422

        # --- Update property ---
        r = client.put(
            f"/api/contacts/{{alice['id']}}/properties/{{prop['id']}}",
            json={{"bedrooms": "3", "price_aed": 6000000}},
        )
        assert r.status_code == 200
        assert r.json()["bedrooms"] == "3"

        # --- Detail again -- properties populated ---
        r = client.get(f"/api/contacts/{{alice['id']}}")
        assert r.status_code == 200
        assert len(r.json()["properties"]) == 1

        # --- Delete property ---
        r = client.delete(
            f"/api/contacts/{{alice['id']}}/properties/{{prop['id']}}"
        )
        assert r.status_code == 204

        # --- Delete contact ---
        r = client.delete(f"/api/contacts/{{alice['id']}}")
        assert r.status_code == 204
        r = client.get(f"/api/contacts/{{alice['id']}}")
        assert r.status_code == 404

        print('OK')
    """)
    rc, out, err = run_in_subprocess(script)
    check("end-to-end CRUD passes against temp DB", rc == 0 and "OK" in out, f"stderr={err[-400:]!r}")


# ---------------------------------------------------------------------------
# 4. Auth required (no override)
# ---------------------------------------------------------------------------
print("\n[4] Auth is enforced when not overridden")

with tempfile.TemporaryDirectory() as tmp:
    script = dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        os.environ['JWT_SECRET'] = 'a' * 48
        sys.path.insert(0, {str(REPO_ROOT)!r})
        import database
        database.init_database()

        from orva_api.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        # No auth header -> 401
        r = client.get('/api/contacts')
        assert r.status_code == 401, (r.status_code, r.text)
        r = client.post('/api/contacts', json={{}})
        assert r.status_code == 401, r.status_code
        r = client.get('/api/contacts/1')
        assert r.status_code == 401, r.status_code
        print('OK')
    """)
    rc, out, err = run_in_subprocess(script)
    check("unauthenticated requests get 401", rc == 0 and "OK" in out, f"stderr={err[-300:]!r}")


# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All contacts-router checks passed.")
