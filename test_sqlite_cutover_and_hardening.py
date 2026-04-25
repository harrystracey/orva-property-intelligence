"""
Regression tests for Phase 5B (SQLite cutover) + Phase 6 (hardening).

Phase 5B
  1. orva_api.deps._load_leads_from_sqlite returns None when no DB exists.
  2. With a synthetic SQLite leads table populated, the loader returns a
     DataFrame with all columns the platform expects.
  3. _load_leads_df prefers SQLite when available, falls back to parquet
     when not (we test the missing-parquet path raises FileNotFoundError
     after the SQLite path returns None).

Phase 6
  4. ensure_tenant_columns adds tenant_id to every multi-tenant table on
     a fresh database, and is idempotent on re-run.
  5. /api/admin/db-counts returns a sane payload.
  6. /api/admin/backup returns 404 when no DB; returns a file when DB exists.
  7. Both admin endpoints require auth.

Subprocess isolation: anything that touches database.DB_PATH runs in a
tempdir so the user's real DB is never mutated.

Run:
    python test_sqlite_cutover_and_hardening.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent
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
    return subprocess.run(
        [PY, "-c", script],
        env=env, capture_output=True, text=True, timeout=60,
    ).__dict__["returncode"], *(
        subprocess.run(
            [PY, "-c", script],
            env=env, capture_output=True, text=True, timeout=60,
        ).__dict__[k] for k in ("stdout", "stderr")
    )


def _run(script: str) -> tuple[int, str, str]:
    env = {
        **os.environ,
        "JWT_SECRET": "a" * 48,
        "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    r = subprocess.run([PY, "-c", script], env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------------------
# 1 + 2 + 3. SQLite-first loader
# ---------------------------------------------------------------------------
print("\n[1+2+3] orva_api.deps SQLite-first lead loader")

with tempfile.TemporaryDirectory() as tmp:
    rc, out, err = _run(dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        os.environ['JWT_SECRET'] = 'a' * 48
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from orva_api.deps import _load_leads_from_sqlite
        # No data/palm_intelligence.db in tempdir -> should return None
        out = _load_leads_from_sqlite()
        assert out is None, f'expected None, got {{out}}'
        print('OK_NO_DB')
    """))
    check("returns None when no DB exists", rc == 0 and "OK_NO_DB" in out, f"stderr={err[:200]!r}")

with tempfile.TemporaryDirectory() as tmp:
    rc, out, err = _run(dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        os.environ['JWT_SECRET'] = 'a' * 48
        sys.path.insert(0, {str(REPO_ROOT)!r})

        import database
        database.init_database()

        # Populate the leads table directly
        conn = database.get_connection()
        conn.execute(
            \"\"\"INSERT INTO leads (
                owner_name, building_name, building_name_normalized,
                unit_number, unit_number_normalized, phone, phone_formatted,
                email, date, bedrooms, size_sqft, completeness_score, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\"\"\",
            ('Alice Owner', 'Shoreline 9', 'shoreline9', '201', 'S-201',
             '+971501234567', '+971501234567', 'a@example.com',
             '2025-01-15', '2', 1450.0, 85.0, 'test'),
        )
        conn.commit()
        conn.close()

        from orva_api.deps import _load_leads_from_sqlite, _load_leads_df
        df = _load_leads_from_sqlite()
        assert df is not None and len(df) == 1, f'got {{df}}'
        # Columns the platform downstream expects
        for col in ('owner_name','building_name','unit_number','phone','email',
                    'date','bedrooms','size_sqft','completeness','source'):
            assert col in df.columns, f'missing column: {{col}}'
        # Expect 'source' marked as 'sqlite'
        assert df['source'].iloc[0] == 'sqlite', df['source'].iloc[0]

        # _load_leads_df should also pick the SQLite path (no parquet exists)
        df2 = _load_leads_df()
        assert len(df2) == 1
        assert df2['source'].iloc[0] == 'sqlite'

        print('OK_SQLITE_PATH')
    """))
    check(
        "loads synthetic leads from SQLite + sets source='sqlite'",
        rc == 0 and "OK_SQLITE_PATH" in out,
        f"stderr={err[-300:]!r}",
    )

with tempfile.TemporaryDirectory() as tmp:
    rc, out, err = _run(dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        os.environ['JWT_SECRET'] = 'a' * 48
        sys.path.insert(0, {str(REPO_ROOT)!r})
        # No SQLite DB, no parquet -> _load_leads_df should raise FileNotFoundError
        from orva_api.deps import _load_leads_df
        try:
            _load_leads_df()
            print('UNEXPECTED_OK')
        except FileNotFoundError as e:
            print(f'OK_FALLBACK_RAISED:{{e}}')
    """))
    check(
        "_load_leads_df falls through to parquet when SQLite missing (raises if parquet also missing)",
        rc == 0 and "OK_FALLBACK_RAISED" in out,
        f"stderr={err[-200:]!r}",
    )


# ---------------------------------------------------------------------------
# 4. ensure_tenant_columns
# ---------------------------------------------------------------------------
print("\n[4] Phase 6: ensure_tenant_columns")

with tempfile.TemporaryDirectory() as tmp:
    rc, out, err = _run(dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        sys.path.insert(0, {str(REPO_ROOT)!r})
        import database

        database.init_database()  # this also calls ensure_tenant_columns
        conn = database.get_connection(readonly=True)

        # Every multi-tenant table should have tenant_id
        from database import _TENANT_TABLES
        for table in _TENANT_TABLES:
            cols = {{r[1] for r in conn.execute(f'PRAGMA table_info({{table}})').fetchall()}}
            assert 'tenant_id' in cols, f'{{table}} missing tenant_id (cols: {{cols}})'

        # Default value is 'orva' on insert with no tenant_id
        conn.close()
        conn = database.get_connection()
        conn.execute("INSERT INTO contacts (full_name, phone) VALUES (?, ?)", ('X', '999'))
        conn.commit()
        row = conn.execute("SELECT tenant_id FROM contacts WHERE full_name='X'").fetchone()
        assert row['tenant_id'] == 'orva', row['tenant_id']
        conn.close()

        # Idempotent re-run -- ensure_tenant_columns returns 0 second time
        from database import ensure_tenant_columns
        c2 = database.get_connection()
        added2 = ensure_tenant_columns(c2)
        assert added2 == 0, f'expected 0, got {{added2}}'
        c2.close()

        # Index exists
        c3 = database.get_connection(readonly=True)
        idx_names = {{r[0] for r in c3.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}}
        assert 'idx_contacts_tenant' in idx_names
        c3.close()

        print('OK_TENANT')
    """))
    check(
        "every multi-tenant table has tenant_id + default 'orva' + idempotent + index",
        rc == 0 and "OK_TENANT" in out,
        f"stderr={err[-300:]!r}",
    )


# ---------------------------------------------------------------------------
# 5 + 6 + 7. Admin router
# ---------------------------------------------------------------------------
print("\n[5+6+7] Phase 6: admin router")

with tempfile.TemporaryDirectory() as tmp:
    rc, out, err = _run(dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        os.environ['JWT_SECRET'] = 'a' * 48
        sys.path.insert(0, {str(REPO_ROOT)!r})

        from orva_api.deps import data_store
        import pandas as pd
        data_store.leads_df = pd.DataFrame()
        data_store.ref_df = pd.DataFrame()
        data_store.ref_stats = {{}}
        data_store._client_index = {{}}
        data_store._loaded = True

        from orva_api import auth
        from orva_api.main import app
        from fastapi.testclient import TestClient

        # Auth NOT overridden -- should 401
        c0 = TestClient(app)
        r = c0.get('/api/admin/db-counts')
        assert r.status_code == 401, ('counts unauth', r.status_code)
        r = c0.get('/api/admin/backup')
        assert r.status_code == 401, ('backup unauth', r.status_code)

        app.dependency_overrides[auth.get_current_user] = lambda: {{
            "username": "test", "name": "Test"
        }}
        c = TestClient(app)

        # No DB yet -> db-counts says not initialized; backup is 404
        r = c.get('/api/admin/db-counts')
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get('database_initialized') is False, body
        assert body.get('counts') == {{}}, body

        r = c.get('/api/admin/backup')
        assert r.status_code == 404, r.status_code

        # Now init the DB and try again
        import database
        database.init_database()

        r = c.get('/api/admin/db-counts')
        assert r.status_code == 200
        body = r.json()
        assert body.get('database_initialized') is True
        # All known tables should appear, even if empty
        for tbl in ('leads', 'contacts', 'rentals', 'bayut_listings', 'unit_registry'):
            assert tbl in body['counts'], f'missing {{tbl}} in counts: {{body}}'

        r = c.get('/api/admin/backup')
        assert r.status_code == 200, r.text
        # Body should be a SQLite file -- starts with magic header bytes
        assert r.content.startswith(b'SQLite format 3'), r.content[:32]
        # Filename in Content-Disposition header
        assert 'orva_backup_' in r.headers.get('content-disposition', '')

        print('OK_ADMIN')
    """))
    check(
        "admin endpoints: 401 unauth, db-counts works, backup returns valid sqlite file",
        rc == 0 and "OK_ADMIN" in out,
        f"stderr={err[-400:]!r}",
    )


# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All Phase 5B + 6 checks passed.")
