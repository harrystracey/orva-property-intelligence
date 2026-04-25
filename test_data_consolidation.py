"""
Regression tests for Phase 1 + 5A -- data snapshot + SQLite consolidation.

Covers:
  1. scripts/freeze_snapshot.py freezes a synthetic project tree, writes a
     valid MANIFEST.json, and survives missing files without erroring.
  2. database.py exposes every new SaaS table (rentals, bayut_listings,
     pf_listings, call_log, whatsapp_messages, unit_registry) and creates
     them with the documented columns + indexes.
  3. data_ingestion.py exposes importers for each new table.
  4. End-to-end: synthesize tiny rentals/bayut/pf/call-log/wa-log inputs,
     run the full ingestion pipeline against a temp SQLite DB, assert
     each row landed in the right table.

Run from repo root:
    python test_data_consolidation.py

Why subprocess isolation: ingest_* mutates a process-global DB path
defined in database.py (DB_PATH). We chdir into a temp directory and
reload the modules so the live ./data/palm_intelligence.db is never
touched.
"""

import importlib
import json
import os
import sqlite3
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


def run_in_subprocess(script: str, *, env_extra: dict | None = None) -> tuple[int, str, str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [PY, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# 1. Snapshot script behaviour
# ---------------------------------------------------------------------------
print("\n[1] scripts/freeze_snapshot.py")

from scripts.freeze_snapshot import freeze_snapshot  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    tmp_root = Path(tmp)
    # Synthetic project tree
    (tmp_root / "lead_database").mkdir()
    (tmp_root / "lead_database" / "leads_master.csv").write_text(
        "owner_name,phone\nAlice,971501234567\nBob,971502345678\n", encoding="utf-8"
    )
    (tmp_root / "scraped_data").mkdir()
    (tmp_root / "scraped_data" / "palm_jumeirah_rentals.csv").write_text(
        "building,unit,rent\nShoreline 9,201,180000\n", encoding="utf-8"
    )
    out = tmp_root / "snap"
    record = freeze_snapshot(project_root=tmp_root, out_dir=out, verbose=False)

    check("MANIFEST.json was written", (out / "MANIFEST.json").exists())
    check(
        "leads_master.csv was copied",
        (out / "lead_database" / "leads_master.csv").exists(),
    )
    check(
        "rentals CSV was copied",
        (out / "scraped_data" / "palm_jumeirah_rentals.csv").exists(),
    )
    check(
        "manifest counts present files (>=2)",
        record["totals"]["present"] >= 2,
        f"got {record['totals']['present']}",
    )
    check(
        "manifest counts missing files (>0, real CSVs we know are absent)",
        record["totals"]["missing"] > 0,
    )
    # Hash should be a 64-hex-char sha256
    leads_entry = next(
        e for e in record["groups"]["leads"]
        if e.get("path") == "lead_database/leads_master.csv"
    )
    check(
        "frozen entry has valid sha256",
        len(leads_entry.get("sha256", "")) == 64,
    )
    check(
        "frozen entry records row count for CSV",
        leads_entry.get("rows") == 2,
        f"rows={leads_entry.get('rows')}",
    )


# ---------------------------------------------------------------------------
# 2 + 3. Schema additions and importer registrations
# ---------------------------------------------------------------------------
print("\n[2] database.py SaaS-conversion tables exist")

with tempfile.TemporaryDirectory() as tmp:
    # Run schema init in a subprocess against a temp DB so we don't mutate
    # the user's real database.
    script = dedent(f"""
        import os, sys
        os.chdir({tmp!r})
        sys.path.insert(0, {str(REPO_ROOT)!r})
        import database
        database.init_database()

        conn = database.get_connection()
        tables = {{r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}}
        indexes = {{r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}}
        print("TABLES:", sorted(tables))
        print("INDEX_COUNT:", len(indexes))
        # Check rentals columns
        rcols = [r[1] for r in conn.execute("PRAGMA table_info(rentals)").fetchall()]
        print("RENTAL_COLS:", rcols)
        bcols = [r[1] for r in conn.execute("PRAGMA table_info(bayut_listings)").fetchall()]
        print("BAYUT_COLS:", bcols)
        ucols = [r[1] for r in conn.execute("PRAGMA table_info(unit_registry)").fetchall()]
        print("REGISTRY_COLS:", ucols)
        conn.close()
    """)
    rc, out, err = run_in_subprocess(script)
    check("schema init runs cleanly", rc == 0, f"stderr={err[:200]!r}")

    expected_new_tables = {
        "rentals", "bayut_listings", "pf_listings",
        "call_log", "whatsapp_messages", "unit_registry",
    }
    for tbl in expected_new_tables:
        check(f"table `{tbl}` was created", tbl in out)

    expected_rental_cols = {
        "building_name_normalized", "unit_number_normalized",
        "annual_rent_aed", "contract_start_date", "contract_end_date",
    }
    for col in expected_rental_cols:
        check(f"rentals.{col} column present", f"'{col}'" in out)

    expected_bayut_cols = {"listing_url", "listing_type", "scraped_at", "price_aed"}
    for col in expected_bayut_cols:
        check(f"bayut_listings.{col} column present", f"'{col}'" in out)

    expected_registry_cols = {
        "bedrooms_confidence", "last_sale_date", "last_annual_rent_aed",
    }
    for col in expected_registry_cols:
        check(f"unit_registry.{col} column present", f"'{col}'" in out)


print("\n[3] data_ingestion.py importers registered")

import data_ingestion  # noqa: E402
for name in (
    "ingest_rentals",
    "ingest_bayut_listings",
    "ingest_pf_listings",
    "ingest_call_log",
    "ingest_whatsapp_log",
):
    check(f"data_ingestion.{name} is callable", callable(getattr(data_ingestion, name, None)))


# ---------------------------------------------------------------------------
# 4. End-to-end: ingest tiny synthetic CSVs and verify rows land
# ---------------------------------------------------------------------------
print("\n[4] End-to-end ingestion against a temp DB")

with tempfile.TemporaryDirectory() as tmp:
    script = dedent(f"""
        import os, sys, json
        os.chdir({tmp!r})
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from pathlib import Path

        # Build the synthetic source files in the directory layout the
        # importers expect.
        Path("scraped_data").mkdir()
        Path("scraped_data/palm_jumeirah_rentals.csv").write_text(
            "building_name,unit_number,bedrooms,size_sqft,annual_rent,contract_start,contract_end\\n"
            "Shoreline 9,201,2,1450,180000,2025-03-01,2026-03-01\\n"
            "Oceana,1501,3,2200,260000,2025-04-15,2026-04-15\\n",
            encoding="utf-8",
        )

        Path("data").mkdir()
        Path("data/bayut_palm_listings.csv").write_text(
            "listing_url,listing_type,building_name,unit_number,bedrooms,size_sqft,price_aed\\n"
            "https://example.com/bayut/1,sale,Shoreline 9,201,2,1450,5500000\\n"
            "https://example.com/bayut/2,rent,Tiara,805,1,890,150000\\n",
            encoding="utf-8",
        )

        Path("scraped_data/propertyfinder_scraped_leads.csv").write_text(
            "listing_url,listing_type,building_name,bedrooms,price_aed,permit_number\\n"
            "https://example.com/pf/1,sale,Five Palm,40903,2,5050000\\n",
            encoding="utf-8",
        )

        Path("client_data").mkdir()
        Path("client_data/call_log.json").write_text(json.dumps([
            {{"client_id": "abc123", "client_name": "Test", "phone": "971501234567",
              "outcome": "voicemail", "notes": "left vm", "called_at": "2026-04-25T10:00:00"}}
        ]), encoding="utf-8")

        Path("whatsapp_bot").mkdir()
        Path("whatsapp_bot/message_log.csv").write_text(
            "phone,phone_normalized,owner_name,status,sent_at\\n"
            "+971501234567,971501234567,Alice,sent,2026-04-25T11:00:00\\n",
            encoding="utf-8",
        )

        # Now run the importers
        import database
        database.init_database()
        import data_ingestion as di

        rent_stats   = di.ingest_rentals()
        bayut_stats  = di.ingest_bayut_listings()
        pf_stats     = di.ingest_pf_listings()
        call_stats   = di.ingest_call_log()
        wa_stats     = di.ingest_whatsapp_log()

        conn = database.get_connection(readonly=True)
        rentals_n = conn.execute("SELECT COUNT(*) FROM rentals").fetchone()[0]
        bayut_n   = conn.execute("SELECT COUNT(*) FROM bayut_listings").fetchone()[0]
        pf_n      = conn.execute("SELECT COUNT(*) FROM pf_listings").fetchone()[0]
        call_n    = conn.execute("SELECT COUNT(*) FROM call_log").fetchone()[0]
        wa_n      = conn.execute("SELECT COUNT(*) FROM whatsapp_messages").fetchone()[0]

        # Confirm building name normalization actually ran
        norm_row = conn.execute(
            "SELECT building_name_normalized FROM rentals WHERE unit_number = '201'"
        ).fetchone()
        building_norm = norm_row[0] if norm_row else None

        print(f"COUNTS rentals={{rentals_n}} bayut={{bayut_n}} pf={{pf_n}} call={{call_n}} wa={{wa_n}}")
        print(f"NORM={{building_norm!r}}")
        conn.close()
    """)
    rc, out, err = run_in_subprocess(script)
    check("end-to-end ingestion runs cleanly", rc == 0, f"stderr={err[-300:]!r}")
    check("2 rentals ingested", "rentals=2" in out, f"out={out[-200:]!r}")
    check("2 Bayut listings ingested", "bayut=2" in out)
    check("1 PF listing ingested", "pf=1" in out)
    check("1 call log entry migrated", "call=1" in out)
    check("1 WA message migrated", "wa=1" in out)
    check(
        "rental building_name_normalized populated by standardize_building_name",
        "NORM=" in out and "NORM=None" not in out,
        f"normalized value: {out.split('NORM=', 1)[1] if 'NORM=' in out else '?'}",
    )


# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All data-consolidation checks passed.")
