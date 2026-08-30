"""Alembic environment — reads DATABASE_URL from settings and uses the
same declarative Base as the runtime app. `render_as_batch=True` lets
SQLite handle ALTER TABLE for the dev/test DB where the app runs today.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure every model module is imported so Base.metadata is complete
# before Alembic reflects it.
from backend.app.core.database import Base
import backend.app.models  # noqa: F401  (registers all mappers)
from backend.app.core.config import settings as app_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The application's configured DATABASE_URL (env var / settings) is the
# authoritative target database. The static `sqlalchemy.url` value that ships
# in alembic.ini is only a fallback for bare dev checkouts and must NOT
# silently override a real production DATABASE_URL — that is exactly the
# "migrations ran against a developer's local SQLite" failure mode.
if app_settings.DATABASE_URL:
    config.set_main_option("sqlalchemy.url", app_settings.DATABASE_URL)
elif not config.get_main_option("sqlalchemy.url"):
    raise RuntimeError("No database URL configured for Alembic (set DATABASE_URL).")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
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
