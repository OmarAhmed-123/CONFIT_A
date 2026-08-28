"""Additive, idempotent schema migration: add columns that exist in the SQLAlchemy
models but are missing from an older live database.

Why this exists: the project creates tables via Base.metadata.create_all(), which
creates missing TABLES but never alters existing ones — so a database created by
an older model revision drifts (e.g. tryon_sessions was missing user_image_url,
which crashed the GDPR purge task with "no such column" on the live dev DB).

Safe by design:
- ADD COLUMN only. Never drops, never renames, never touches existing rows.
- Nullable adds get no default rewrite; NOT NULL model columns are added with the
  model's declared default (or skipped with a loud warning if none exists).
- Idempotent: columns that already exist are skipped.

Run against any environment:

    PYTHONPATH=. python3 backend/scripts/migrate_add_missing_columns.py
    DATABASE_URL="postgresql+pg8000://..." PYTHONPATH=. python3 backend/scripts/migrate_add_missing_columns.py
"""

import importlib
import pkgutil

from sqlalchemy import inspect, text

from backend.app.core.database import Base, engine

# Import every model module so all tables are registered on the metadata.
import backend.app.models as models_pkg

for m in pkgutil.iter_modules(models_pkg.__path__):
    importlib.import_module(f"backend.app.models.{m.name}")


def column_type_sql(column) -> str:
    try:
        return column.type.compile(dialect=engine.dialect)
    except Exception:
        return "TEXT"


def main() -> None:
    inspector = inspect(engine)
    added, skipped, warned = [], [], []

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)} if inspector.has_table(table.name) else set()
            if not existing:
                continue  # create_all handles whole-table creation elsewhere
            for column in table.columns:
                if column.name in existing:
                    continue
                col_sql = f'ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type_sql(column)}'
                if not column.nullable:
                    if column.default is not None and hasattr(column.default, "arg"):
                        default = column.default.arg
                        if isinstance(default, str):
                            col_sql += f" NOT NULL DEFAULT '{default}'"
                        elif isinstance(default, bool):
                            col_sql += f" NOT NULL DEFAULT {int(default)}"
                        elif isinstance(default, (int, float)):
                            col_sql += f" NOT NULL DEFAULT {default}"
                        else:
                            warned.append(f"{table.name}.{column.name}: NOT NULL with non-literal default — skipped, review manually")
                            continue
                    else:
                        warned.append(f"{table.name}.{column.name}: NOT NULL without default — skipped, review manually")
                        continue
                conn.execute(text(col_sql))
                added.append(f"{table.name}.{column.name}")

    print(f"Migration complete: {len(added)} column(s) added.")
    for a in added:
        print(f"  + {a}")
    for w in warned:
        print(f"  ! {w}")
    if not added and not warned:
        print("  Schema already up to date — nothing to do.")


if __name__ == "__main__":
    main()
