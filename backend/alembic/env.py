"""Alembic environment (G2-S1).

Loads the application's real SQLAlchemy metadata and resolves the database
URL from the environment / app settings — never from a hardcoded credential.
"""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from backend.app.core.config import settings  # noqa: E402
from backend.app.core.database import Base  # noqa: E402

# Importing every model module registers all tables on Base.metadata.
from backend.app.models import (  # noqa: E402,F401
    user,
    profile,
    catalog,
    stylist,
    tryon,
    wardrobe,
    commerce,
    brand_analytics,
)

target_metadata = Base.metadata


def _get_url() -> str:
    """Resolution order: explicit Alembic override -> app configuration.

    No production credential is ever stored in this file or in alembic.ini.
    """
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


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
