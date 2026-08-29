"""Fix Postgres enum-vs-string column drift (root cause of the live signup 500).

The current models persist enums as plain strings via TypeDecorators
(UserRoleType -> String(50); TryOnJobStatus -> String), but databases created
by an older model revision hold NATIVE Postgres ENUM columns (userrole,
tryonjobstatus). Postgres then rejects every INSERT with
'column "role" is of type userrole but expression is of type character varying'
— signup and try-on job creation 500 in production while SQLite tests pass.

This migration converts those columns to VARCHAR, preserving every value
(USING column::text). The orphaned enum TYPES are left in place harmlessly —
dropping them is optional and not required for correctness.

Run:  PYTHONPATH=. python3 backend/scripts/migrate_enum_columns_to_varchar.py
"""

import sqlalchemy as sa

from backend.app.core.database import engine

# (table, column) pairs whose current model type is string-based but which may
# exist as native enums in older databases.
ENUM_COLUMNS = [
    ("users", "role"),
    ("tryon_jobs", "status"),
]


def main() -> None:
    with engine.begin() as conn:
        # Detect enum columns via information_schema directly — SQLAlchemy's
        # inspector misreports USER-DEFINED types as VARCHAR under pg8000.
        rows = conn.execute(sa.text(
            "SELECT table_name, column_name, data_type, udt_name "
            "FROM information_schema.columns "
            "WHERE (table_name, column_name) IN ("
            + ", ".join(f"('{t}', '{c}')" for t, c in ENUM_COLUMNS)
            + ")"
        )).fetchall()
        found = {(r[0], r[1]): (r[2], r[3]) for r in rows}

        converted, already_ok = [], []
        for table, column in ENUM_COLUMNS:
            info = found.get((table, column))
            if not info:
                already_ok.append(f"{table}.{column} (absent)")
                continue
            data_type, udt = info
            if data_type != "USER-DEFINED":
                already_ok.append(f"{table}.{column} ({data_type})")
                continue
            conn.execute(sa.text(
                f'ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR(50) USING {column}::text'
            ))
            converted.append(f"{table}.{column} (was enum {udt})")

    print("Enum -> VARCHAR migration complete.")
    for c in converted:
        print(f"  converted: {c}")
    for c in already_ok:
        print(f"  ok:        {c}")
    if not converted:
        print("  Nothing to convert — schema already aligned.")


if __name__ == "__main__":
    main()
