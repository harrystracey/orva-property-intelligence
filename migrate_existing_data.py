"""
One-Time Migration Script - CSV + JSON -> SQLite
Palm Jumeirah Real Estate Intelligence System

Run this ONCE to migrate all existing data into the SQLite database.
Safe to re-run (uses INSERT OR IGNORE and clears tables first).

Usage:
    python migrate_existing_data.py
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from database import init_database, get_connection, get_table_counts, DB_PATH
from data_ingestion import reingest_all


# ---------------------------------------------------------------------------
# Client data migration (JSON -> SQLite)
# ---------------------------------------------------------------------------

NOTES_FILE = Path("client_data/notes.json")
REMINDERS_FILE = Path("client_data/reminders.json")


def migrate_client_notes() -> int:
    """
    Migrate notes.json into the client_notes table.

    notes.json format:
    {
        "client_id_hash": [
            {"id": "abc123", "text": "...", "timestamp": "2026-...", "edited_at": "..."},
            ...
        ],
        ...
    }

    Returns:
        Number of notes migrated.
    """
    if not NOTES_FILE.exists():
        print("  No notes.json found -- skipping.")
        return 0

    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            all_notes = json.load(f)
    except Exception as e:
        print(f"  [ERR] Could not read notes.json: {e}")
        return 0

    if not all_notes:
        print("  notes.json is empty -- skipping.")
        return 0

    conn = get_connection()
    count = 0

    for client_id, notes_list in all_notes.items():
        for note in notes_list:
            try:
                created_at = note.get("timestamp", datetime.now().isoformat())
                updated_at = note.get("edited_at", created_at)

                conn.execute(
                    """INSERT OR IGNORE INTO client_notes
                       (client_id, note_text, created_at, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (client_id, note.get("text", ""), created_at, updated_at),
                )
                count += 1
            except Exception as e:
                print(f"  [WARN] Note migration error for {client_id}: {e}")

    conn.commit()
    conn.close()
    return count


def migrate_client_reminders() -> int:
    """
    Migrate reminders.json into the client_reminders table.

    reminders.json format:
    [
        {
            "id": "abc123",
            "client_id": "hash",
            "client_name": "...",
            "building": "...",
            "unit": "...",
            "phone": "...",
            "datetime": "2026-...",
            "note": "...",
            "status": "pending" | "done",
            "created_at": "...",
            "completed_at": null | "..."
        },
        ...
    ]

    Returns:
        Number of reminders migrated.
    """
    if not REMINDERS_FILE.exists():
        print("  No reminders.json found -- skipping.")
        return 0

    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            reminders = json.load(f)
    except Exception as e:
        print(f"  [ERR] Could not read reminders.json: {e}")
        return 0

    if not reminders:
        print("  reminders.json is empty -- skipping.")
        return 0

    conn = get_connection()
    count = 0

    for r in reminders:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO client_reminders
                   (client_id, owner_name, building_name, unit_number, phone,
                    reminder_text, due_date, status, completed_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.get("client_id"),
                    r.get("client_name"),
                    r.get("building"),
                    r.get("unit"),
                    r.get("phone"),
                    r.get("note", ""),
                    r.get("datetime"),
                    r.get("status", "pending"),
                    r.get("completed_at"),
                    r.get("created_at", datetime.now().isoformat()),
                ),
            )
            count += 1
        except Exception as e:
            print(f"  [WARN] Reminder migration error: {e}")

    conn.commit()
    conn.close()
    return count


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_migration() -> bool:
    """
    Run basic sanity checks after migration.
    Returns True if all checks pass.
    """
    print("\n--- Verification ---")
    conn = get_connection(readonly=True)
    ok = True

    # Check leads have building_name_normalized
    null_buildings = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE building_name_normalized IS NULL AND building_name IS NOT NULL"
    ).fetchone()[0]
    total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    print(f"  Leads: {total_leads:,} total, {null_buildings} with un-normalized building name")

    # Check transactions
    total_txn = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    with_units = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE unit_number IS NOT NULL AND unit_number != ''"
    ).fetchone()[0]
    print(f"  Transactions: {total_txn:,} total, {with_units:,} with unit numbers ({with_units/max(total_txn,1)*100:.1f}%)")

    # Check cross-references
    total_xref = conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
    exact = conn.execute(
        "SELECT COUNT(*) FROM cross_references WHERE match_method = 'exact_unit'"
    ).fetchone()[0]
    building = conn.execute(
        "SELECT COUNT(*) FROM cross_references WHERE match_method = 'building_only'"
    ).fetchone()[0]
    print(f"  Cross-references: {total_xref:,} total ({exact:,} exact, {building:,} building-only)")

    # Sample: top buildings by lead count
    top_buildings = conn.execute("""
        SELECT building_name_normalized, COUNT(*) as cnt
        FROM leads
        WHERE building_name_normalized IS NOT NULL
        GROUP BY building_name_normalized
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    if top_buildings:
        print("\n  Top 10 buildings by lead count:")
        for row in top_buildings:
            print(f"    {row[0]:40s} {row[1]:,}")

    # Sample: top buildings by transaction count
    top_txn_buildings = conn.execute("""
        SELECT building_name_normalized, COUNT(*) as cnt
        FROM transactions
        WHERE building_name_normalized IS NOT NULL
        GROUP BY building_name_normalized
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    if top_txn_buildings:
        print("\n  Top 10 buildings by transaction count:")
        for row in top_txn_buildings:
            print(f"    {row[0]:40s} {row[1]:,}")

    conn.close()
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(" FULL DATA MIGRATION: CSV + JSON -> SQLite")
    print("=" * 60)
    print(f"  Database: {DB_PATH}")
    print(f"  Time: {datetime.now().isoformat()}")
    print()

    # Step 1: CSV ingestion (leads + transactions + cross-refs)
    print("Phase 1: Ingesting CSV data...")
    print("-" * 40)
    results = reingest_all(clear_existing=True)

    # Step 2: Client data migration
    print("\nPhase 2: Migrating client data (JSON -> SQLite)...")
    print("-" * 40)
    notes_count = migrate_client_notes()
    print(f"  Notes migrated: {notes_count}")

    reminders_count = migrate_client_reminders()
    print(f"  Reminders migrated: {reminders_count}")

    # Step 3: Verification
    verify_migration()

    # Final summary
    counts = get_table_counts()
    db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print(" MIGRATION COMPLETE")
    print("=" * 60)
    print(f"  Database size: {db_size_mb:.2f} MB")
    for table, count in counts.items():
        print(f"  {table:25s} {count:,}")
    print("=" * 60)
    print("\nThe JSON files in client_data/ are preserved as backup.")
    print("You can delete them once you've confirmed everything works.\n")


if __name__ == "__main__":
    main()
