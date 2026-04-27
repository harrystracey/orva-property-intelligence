"""
Database Module - SQLite Connection Management & Schema
Palm Jumeirah Real Estate Intelligence System

Provides:
- get_connection()  -- returns a SQLite connection (WAL mode, foreign keys on)
- init_database()   -- creates all tables and indexes if they don't exist
- table_has_data()  -- check if a table contains any rows
- get_db_path()     -- returns the path to the database file
"""

import sqlite3
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Database location
# ---------------------------------------------------------------------------

DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)

DB_PATH = DB_DIR / "palm_intelligence.db"


def get_db_path() -> Path:
    """Return the path to the SQLite database file."""
    return DB_PATH


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def get_connection(readonly: bool = False) -> sqlite3.Connection:
    """
    Return a SQLite connection with sensible defaults.

    - WAL journal mode for concurrent readers / single writer
    - Foreign keys enforced
    - Row factory set to sqlite3.Row for dict-like access

    Parameters:
        readonly: If True, opens the database in read-only mode (uri).
    """
    # We deliberately do NOT use the `?mode=ro` URI here even when readonly
    # is requested. SQLite in WAL mode (which we use) needs to update the
    # .db-shm shared-memory file on every read, and ?mode=ro forbids that
    # update -- so plain SELECTs raise "attempt to write a readonly database".
    # Instead we open writable and use PRAGMA query_only=1 to refuse INSERT/
    # UPDATE/DELETE at the SQL level, which is compatible with WAL.
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    if readonly:
        conn.execute("PRAGMA query_only = 1")
    else:
        conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Schema definition (matches CURSOR_PRODUCTION_HARDENING_PLAN.md exactly)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- =========================================================================
-- Lead contacts (from uploaded CSV files)
-- =========================================================================
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_name TEXT,
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    unit_number_normalized TEXT,
    phone TEXT,
    phone_formatted TEXT,
    email TEXT,
    date TEXT,
    bedrooms TEXT,
    bedrooms_estimated BOOLEAN DEFAULT FALSE,
    bedrooms_source TEXT,
    size_sqft REAL,
    size_estimated BOOLEAN DEFAULT FALSE,
    size_source TEXT,
    completeness_score REAL,
    source_file TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_name, building_name_normalized, unit_number_normalized)
);

-- =========================================================================
-- Title deed reference transactions (from PropertyMonitor)
-- =========================================================================
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    unit_number_normalized TEXT,
    transaction_date TEXT,
    price_aed REAL,
    price_per_sqft REAL,
    size_sqft REAL,
    bedrooms TEXT,
    floor_level TEXT,
    property_type TEXT,
    transaction_type TEXT,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(building_name_normalized, unit_number_normalized, transaction_date, price_aed)
);

-- =========================================================================
-- Cross-reference matches (precomputed joins between leads and transactions)
-- =========================================================================
CREATE TABLE IF NOT EXISTS cross_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    transaction_id INTEGER REFERENCES transactions(id),
    match_confidence REAL,
    match_method TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lead_id, transaction_id)
);

-- =========================================================================
-- Scraped unit numbers
-- =========================================================================
CREATE TABLE IF NOT EXISTS scraped_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    unit_number_normalized TEXT,
    scraped_date TIMESTAMP,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- Client notes (migrated from JSON)
-- =========================================================================
CREATE TABLE IF NOT EXISTS client_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT,
    owner_name TEXT,
    building_name TEXT,
    unit_number TEXT,
    note_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- Client reminders (migrated from JSON)
-- =========================================================================
CREATE TABLE IF NOT EXISTS client_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT,
    owner_name TEXT,
    building_name TEXT,
    unit_number TEXT,
    phone TEXT,
    reminder_text TEXT,
    due_date TIMESTAMP,
    status TEXT DEFAULT 'pending',
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- Contacts (standalone or linked to leads)
-- =========================================================================
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT,
    phone TEXT,
    email TEXT,
    contact_type TEXT,
    source TEXT,
    budget_min REAL,
    budget_max REAL,
    agent_assigned TEXT,
    last_contact_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(phone, full_name)
);

-- =========================================================================
-- Contact properties (multiple per contact)
-- =========================================================================
CREATE TABLE IF NOT EXISTS contact_properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    building_name TEXT,
    unit_number TEXT,
    bedrooms TEXT,
    bathrooms TEXT,
    price_aed REAL,
    intent TEXT,
    view_type TEXT,
    notes TEXT,
    lead_id INTEGER REFERENCES leads(id),
    is_scraped_listing INTEGER DEFAULT 0,
    scraped_listing_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- Link contacts to leads (portfolio / auto-link)
-- =========================================================================
CREATE TABLE IF NOT EXISTS contact_lead_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    lead_id INTEGER REFERENCES leads(id),
    match_confidence REAL,
    match_method TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contact_id, lead_id)
);

-- =========================================================================
-- Rental contracts (Ejari -- historical from PropertyMonitor)
-- Live PM scraper has been removed; this table holds the frozen historical
-- rentals data. Used for market-rent intelligence ("comparable units rent
-- for X") and lease-expiry pages.
-- =========================================================================
CREATE TABLE IF NOT EXISTS rentals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    unit_number_normalized TEXT,
    bedrooms TEXT,
    size_sqft REAL,
    annual_rent_aed REAL,
    contract_start_date TEXT,
    contract_end_date TEXT,
    floor_level TEXT,
    view_type TEXT,
    source TEXT DEFAULT 'property_monitor_historical',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(building_name_normalized, unit_number_normalized, contract_start_date, annual_rent_aed)
);

-- =========================================================================
-- Bayut active listings (public scraper -- refreshed on demand)
-- This table is regenerated each time bayut_scraper runs; uniqueness is
-- enforced on listing_url so re-scrapes overwrite cleanly.
-- =========================================================================
CREATE TABLE IF NOT EXISTS bayut_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_url TEXT UNIQUE,
    listing_type TEXT,            -- 'sale' | 'rent'
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    unit_type TEXT,               -- 'apartment' | 'villa' | 'penthouse' | etc.
    bedrooms TEXT,
    bathrooms TEXT,
    size_sqft REAL,
    price_aed REAL,
    rent_period TEXT,             -- 'yearly' | 'monthly' (rent only)
    view_type TEXT,
    agent_name TEXT,
    agency TEXT,
    listed_date TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- PropertyFinder public listings (public scraper)
-- Same shape as bayut_listings; separate table because the scrapers run
-- independently and we want to know which source a listing came from.
-- =========================================================================
CREATE TABLE IF NOT EXISTS pf_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_url TEXT UNIQUE,
    listing_type TEXT,            -- 'sale' | 'rent'
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    bedrooms TEXT,
    bathrooms TEXT,
    size_sqft REAL,
    price_aed REAL,
    rent_period TEXT,
    view_type TEXT,
    permit_number TEXT,
    owner_name TEXT,              -- if resolved via Replit/permit lookup
    owner_phone TEXT,
    agent_name TEXT,
    agency TEXT,
    listed_date TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- Call log (was client_data/call_log.json)
-- =========================================================================
CREATE TABLE IF NOT EXISTS call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT,
    client_name TEXT,
    building_name TEXT,
    unit_number TEXT,
    phone TEXT,
    outcome TEXT,                 -- voicemail | no_answer | not_interested | interested | callback
    notes TEXT,
    called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    follow_up_reminder_id INTEGER REFERENCES client_reminders(id)
);

-- =========================================================================
-- WhatsApp message log (was whatsapp_bot/message_log.csv)
-- One row per send attempt -- success or failure. Drives the daily
-- rate-limit (36/day cap).
-- =========================================================================
CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT,
    phone_normalized TEXT,
    owner_name TEXT,
    building_name TEXT,
    unit_number TEXT,
    message_template TEXT,
    message_body TEXT,
    status TEXT,                  -- sent | failed | skipped_duplicate | skipped_excluded
    failure_reason TEXT,
    campaign_id TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- Unit registry (derived: leads + sales + rentals + listings merged by
-- (building, unit_number)). Rebuild this from the source tables; do not
-- hand-edit. Mirrors what build_unit_registry.py produces today.
-- =========================================================================
CREATE TABLE IF NOT EXISTS unit_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_name TEXT,
    building_name_normalized TEXT,
    unit_number TEXT,
    unit_number_normalized TEXT,
    bedrooms TEXT,
    bedrooms_confidence TEXT,     -- HIGH (PM/sales DLD) | MEDIUM (PF/leads/rentals) | LOW
    bedrooms_source TEXT,
    size_sqft REAL,
    floor_level TEXT,
    view_type TEXT,
    last_sale_date TEXT,
    last_sale_price_aed REAL,
    last_annual_rent_aed REAL,
    last_rent_date TEXT,
    sources TEXT,                 -- comma-separated list of contributing sources
    rebuilt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(building_name_normalized, unit_number_normalized)
);
"""

# Indexes are created separately so each can use IF NOT EXISTS
INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_leads_building ON leads(building_name_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_leads_unit ON leads(unit_number_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone)",
    "CREATE INDEX IF NOT EXISTS idx_leads_bedrooms ON leads(bedrooms)",
    "CREATE INDEX IF NOT EXISTS idx_leads_owner ON leads(owner_name)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_building ON transactions(building_name_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_unit ON transactions(unit_number_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_price ON transactions(price_aed)",
    "CREATE INDEX IF NOT EXISTS idx_cross_refs_lead ON cross_references(lead_id)",
    "CREATE INDEX IF NOT EXISTS idx_cross_refs_transaction ON cross_references(transaction_id)",
    "CREATE INDEX IF NOT EXISTS idx_client_notes_client ON client_notes(client_id)",
    "CREATE INDEX IF NOT EXISTS idx_client_reminders_status ON client_reminders(status, due_date)",
    "CREATE INDEX IF NOT EXISTS idx_client_reminders_client ON client_reminders(client_id)",
    "CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone)",
    "CREATE INDEX IF NOT EXISTS idx_contacts_full_name ON contacts(full_name)",
    "CREATE INDEX IF NOT EXISTS idx_contacts_agent ON contacts(agent_assigned)",
    "CREATE INDEX IF NOT EXISTS idx_contact_properties_contact ON contact_properties(contact_id)",
    "CREATE INDEX IF NOT EXISTS idx_contact_properties_lead ON contact_properties(lead_id)",
    "CREATE INDEX IF NOT EXISTS idx_contact_lead_links_contact ON contact_lead_links(contact_id)",
    "CREATE INDEX IF NOT EXISTS idx_contact_lead_links_lead ON contact_lead_links(lead_id)",

    # Rentals
    "CREATE INDEX IF NOT EXISTS idx_rentals_building ON rentals(building_name_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_rentals_unit ON rentals(unit_number_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_rentals_end_date ON rentals(contract_end_date)",
    "CREATE INDEX IF NOT EXISTS idx_rentals_bedrooms ON rentals(bedrooms)",

    # Bayut listings
    "CREATE INDEX IF NOT EXISTS idx_bayut_building ON bayut_listings(building_name_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_bayut_type ON bayut_listings(listing_type)",
    "CREATE INDEX IF NOT EXISTS idx_bayut_bedrooms ON bayut_listings(bedrooms)",
    "CREATE INDEX IF NOT EXISTS idx_bayut_scraped ON bayut_listings(scraped_at)",

    # PF listings
    "CREATE INDEX IF NOT EXISTS idx_pf_building ON pf_listings(building_name_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_pf_type ON pf_listings(listing_type)",
    "CREATE INDEX IF NOT EXISTS idx_pf_bedrooms ON pf_listings(bedrooms)",
    "CREATE INDEX IF NOT EXISTS idx_pf_permit ON pf_listings(permit_number)",
    "CREATE INDEX IF NOT EXISTS idx_pf_owner_phone ON pf_listings(owner_phone)",

    # Call log
    "CREATE INDEX IF NOT EXISTS idx_call_log_client ON call_log(client_id)",
    "CREATE INDEX IF NOT EXISTS idx_call_log_phone ON call_log(phone)",
    "CREATE INDEX IF NOT EXISTS idx_call_log_called ON call_log(called_at)",

    # WhatsApp
    "CREATE INDEX IF NOT EXISTS idx_wa_phone ON whatsapp_messages(phone_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_wa_status ON whatsapp_messages(status)",
    "CREATE INDEX IF NOT EXISTS idx_wa_sent ON whatsapp_messages(sent_at)",
    "CREATE INDEX IF NOT EXISTS idx_wa_campaign ON whatsapp_messages(campaign_id)",

    # Unit registry
    "CREATE INDEX IF NOT EXISTS idx_registry_building ON unit_registry(building_name_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_registry_unit ON unit_registry(unit_number_normalized)",
    "CREATE INDEX IF NOT EXISTS idx_registry_bedrooms ON unit_registry(bedrooms)",
]


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

# Tables that should carry a tenant_id column for multi-tenant SaaS use.
# Default value is 'orva' so single-tenant deployments (the current state)
# keep working without any code changes.
_TENANT_TABLES = (
    "leads", "transactions", "cross_references",
    "scraped_units", "client_notes", "client_reminders",
    "contacts", "contact_properties", "contact_lead_links",
    "rentals", "bayut_listings", "pf_listings",
    "call_log", "whatsapp_messages", "unit_registry",
)


def ensure_tenant_columns(conn) -> int:
    """
    Add a `tenant_id` column to every multi-tenant table that doesn't
    already have one, defaulting to 'orva'.

    SQLite's ALTER TABLE ADD COLUMN doesn't support IF NOT EXISTS, so
    we check pragma table_info first. Returns the number of columns
    actually added (zero on a re-run).
    """
    added = 0
    for table in _TENANT_TABLES:
        try:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            continue
        if not cols:
            # Table doesn't exist (shouldn't happen after init_database, but
            # we don't want this to be the failure mode).
            continue
        if "tenant_id" in cols:
            continue
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'orva'"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant ON {table}(tenant_id)"
        )
        added += 1
    return added


def init_database() -> None:
    """
    Create all tables and indexes if they don't already exist.
    Safe to call multiple times (uses IF NOT EXISTS throughout).
    """
    conn = get_connection()
    try:
        # Create tables
        conn.executescript(SCHEMA_SQL)

        # Create indexes
        for idx_sql in INDEXES_SQL:
            conn.execute(idx_sql)

        # Phase 6: ensure every multi-tenant table has a tenant_id column.
        # This is run AFTER the CREATE TABLE pass so it can ALTER any
        # tables that pre-date the multi-tenant migration.
        added = ensure_tenant_columns(conn)
        if added:
            print(f"[database] Added tenant_id to {added} table(s)")

        conn.commit()
        print(f"[database] Initialized database at {DB_PATH}")
    except Exception as e:
        print(f"[database] Error initializing database: {e}")
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def table_has_data(table_name: str) -> bool:
    """Check whether a table exists and contains at least one row."""
    if not DB_PATH.exists():
        return False
    try:
        conn = get_connection(readonly=True)
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM {table_name} LIMIT 1"
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def get_table_counts() -> dict:
    """Return row counts for all tables. Useful for migration verification."""
    tables = [
        "leads", "transactions", "cross_references",
        "scraped_units", "client_notes", "client_reminders",
        "contacts", "contact_properties", "contact_lead_links",
        # Phase 5A SaaS-conversion tables
        "rentals", "bayut_listings", "pf_listings",
        "call_log", "whatsapp_messages", "unit_registry",
    ]
    counts = {}
    if not DB_PATH.exists():
        return {t: 0 for t in tables}
    try:
        conn = get_connection(readonly=True)
        for table in tables:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]
            except Exception:
                counts[table] = 0
        conn.close()
    except Exception:
        counts = {t: 0 for t in tables}
    return counts


def database_exists() -> bool:
    """Check if the database file exists and has been initialized."""
    return DB_PATH.exists() and DB_PATH.stat().st_size > 0


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Initializing database...")
    init_database()
    print(f"Database path: {DB_PATH}")
    print(f"Database exists: {database_exists()}")
    print(f"Table counts: {get_table_counts()}")
    print("Done.")
