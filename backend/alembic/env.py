"""Alembic environment.

Loads the application's real SQLAlchemy metadata and resolves the database
URL from the environment / app settings — never from a hardcoded credential.
`render_as_batch=True` lets SQLite handle ALTER TABLE for the dev/test DB.

Resolution order (Group 2's explicit overrides + Group 1's guarantee that the
application-configured DATABASE_URL always wins over any stale static value):
  1. ALEMBIC_DATABASE_URL environment variable (migrations/tests)
  2. -x dburl=... command-line override
  3. the application's configured DATABASE_URL (backend/app/core/config.py)
The static `sqlalchemy.url` in alembic.ini is intentionally empty so it can
never silently override a real production URL.
"""
import os
from logging.config import fileConfig

from alembic import context
import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importing every model module registers all tables on Base.metadata.
from backend.app.core.database import Base  # noqa: E402
import backend.app.models  # noqa: E402,F401  (registers all mappers)
from backend.app.core.config import settings  # noqa: E402

target_metadata = Base.metadata


def _get_url() -> str:
    """Resolve the target DB URL. No credential is stored in this file."""
    x_args = context.get_x_argument(as_dictionary=True)
    return (
        os.environ.get("ALEMBIC_DATABASE_URL")
        or x_args.get("dburl")
        or config.get_main_option("sqlalchemy.url")
        or settings.DATABASE_URL
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite-safe ALTER support
    )
    with context.begin_transaction():
        context.run_migrations()


def _ensure_wide_version_table(connection) -> None:
    """Pre-create ``alembic_version`` with ``VARCHAR(255)`` on an EMPTY database.

    Alembic auto-creates ``alembic_version.version_num`` as ``VARCHAR(32)``.
    Revision ``0005_group4_wardrobe_dedup_integrity`` is 36 characters, so on a
    fresh PostgreSQL database the chain died at 0005 with
    StringDataRightTruncation — migration 0006 widens the column but runs too
    late to help. Production (already past 0007) was never affected; a fresh
    staging / disaster-recovery database could not be built from the chain at
    all (found 2026-09-03 rehearsing ``upgrade head`` on empty PostgreSQL 17).

    No-op when the table already exists or on SQLite (no length limit).
    """
    if connection.dialect.name == "sqlite":
        return
    if not sa.inspect(connection).has_table("alembic_version"):
        connection.execute(sa.text(
            "CREATE TABLE alembic_version ("
            "version_num VARCHAR(255) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        ))
    # ALWAYS end the transaction this pre-flight autobegan (the inspector
    # query alone starts one under SQLAlchemy 2.x). If a transaction is still
    # open, alembic's begin_transaction() assumes the caller manages it and
    # never commits — every migration would then be rolled back at connection
    # close with EXIT CODE 0. Observed 2026-09-03: ``downgrade base`` reported
    # success while the database stayed at 0013.
    connection.commit()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _ensure_wide_version_table(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
