"""baseline: initial schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-25 19:00:00 UTC

This is the baseline migration. It re-runs database.init_database()
which is idempotent (CREATE TABLE IF NOT EXISTS) -- so on a fresh
database it builds everything; on an existing database it's a no-op.

From this revision forward, every schema change should be a new
revision file generated with:

    alembic revision -m "short description"

and edited by hand (we don't use SQLAlchemy MetaData -- the schema
is raw SQL).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply database.SCHEMA_SQL + INDEXES_SQL + ensure_tenant_columns."""
    # Import here so the migration file stays portable -- the operator
    # might be running this with sys.path set up by alembic/env.py only.
    from database import SCHEMA_SQL, INDEXES_SQL, ensure_tenant_columns

    bind = op.get_bind()

    # Tables
    raw = bind.connection.connection if hasattr(bind, "connection") else bind
    # SQLAlchemy connection -> use exec_driver_sql to run multiple statements
    for statement in SCHEMA_SQL.split(";\n"):
        s = statement.strip()
        if s:
            bind.exec_driver_sql(s + ";")

    # Indexes
    for idx_sql in INDEXES_SQL:
        bind.exec_driver_sql(idx_sql)

    # Multi-tenant columns (idempotent -- ensure_tenant_columns checks
    # before adding). It expects a dbapi connection so we unwrap.
    dbapi_conn = bind.connection.connection if hasattr(bind, "connection") else bind
    ensure_tenant_columns(dbapi_conn)


def downgrade() -> None:
    """
    Drop all platform tables. This is the only revision that's
    irreversible in practice -- downgrade past baseline = empty DB.
    """
    tables = [
        "contact_lead_links", "contact_properties", "contacts",
        "client_reminders", "client_notes",
        "scraped_units", "cross_references",
        "rentals", "bayut_listings", "pf_listings",
        "call_log", "whatsapp_messages", "unit_registry",
        "transactions", "leads",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t}")
