"""Alembic env — online mode only (offline mode not useful for ATP)."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Derive URL from app env — DATABASE_SYNC_URL preferred, oracle fallback.
_db_url = os.getenv("DATABASE_SYNC_URL") or os.getenv("DATABASE_URL") or ""
if not _db_url and os.getenv("ORACLE_DSN"):
    user = os.getenv("ORACLE_USER", "ADMIN")
    pw = os.getenv("ORACLE_PASSWORD", "")
    _db_url = f"oracle+oracledb://{user}:{pw}@{os.getenv('ORACLE_DSN')}"

config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = None


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline alembic not supported for ATP — run online")
run_migrations_online()
