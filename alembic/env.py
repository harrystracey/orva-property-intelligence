"""
Alembic environment for ORVA.

The platform's authoritative schema lives in `database.py` (SCHEMA_SQL +
ensure_tenant_columns). Alembic is layered on top so schema changes from
this point on are versioned + reversible.

We don't autogenerate from SQLAlchemy models because there are none --
the schema is hand-written SQL. So `--autogenerate` won't help; you write
migrations by hand using `op.execute(...)` or `op.add_column(...)` etc.

Env var ORVA_DB_URL overrides the URL in alembic.ini -- useful for
running migrations against a tempdir DB in tests.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool


# Ensure project root is on sys.path so `import database` works
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Allow ORVA_DB_URL env var to override sqlalchemy.url
env_url = os.environ.get("ORVA_DB_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)


# We don't have SQLAlchemy MetaData -- the schema is in raw SQL inside
# database.py. Autogenerate is therefore useless; leave target_metadata
# as None and write migrations by hand.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode -- emit SQL without a live DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite doesn't support most ALTER TABLE operations natively;
        # batch mode lets Alembic emulate them via copy-and-rename.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode -- against a live DB."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite-friendly ALTER TABLE
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
