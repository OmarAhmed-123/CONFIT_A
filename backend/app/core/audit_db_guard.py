"""Database-level append-only guard for the audit trust boundary (PostgreSQL).

Trust-model context (docs/ADMIN_GOVERNANCE_THREAT_MODEL.md):

* The HMAC hash chain (audit_chain.py) makes tampering **tamper-evident** —
  it detects mutation but cannot prevent it.
* This module makes the audit tables **database-restricted append-only** for
  the runtime credential: UPDATE/DELETE/TRUNCATE are blocked by
  (a) REVOKE of those privileges from the runtime role, and
  (b) BEFORE-triggers that RAISE EXCEPTION even for roles that still hold
      the privileges (defence in depth against accidental owner mutations).

Honest limitation — this is NOT immutability: the table owner (the
migration credential) can DROP the trigger and mutate rows. Doing so is a
DDL action, distinct from the runtime credential, and any mutation of a
chained row still breaks the HMAC chain. True immutability requires
external anchoring (WORM storage) outside this database's trust boundary.

SQLite (dev/test) has no privilege system or plpgsql: the guard is a
documented no-op there, exercised in CI by the PostgreSQL jobs.

Shared by migration 0022 and the PostgreSQL behavioural tests so both
always exercise the same SQL (single source of truth).
"""

from __future__ import annotations

from typing import List

# Tables covered by the guard. audit_verification_runs is included because a
# verification history that can be rewritten is worthless as evidence.
GUARDED_TABLES = ("audit_logs", "audit_verification_runs")

# Runtime application role (Neon: the credential in the production
# DATABASE_URL). The REVOKE is conditional so the migration also succeeds on
# databases where the role does not exist (CI, local PostgreSQL).
RUNTIME_ROLE = "confit_app_rw"

GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION confit_audit_append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'audit table % is append-only: % is not permitted (see docs/ADMIN_GOVERNANCE_THREAT_MODEL.md)',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'raise_exception';
END;
$$;
"""


def guard_install_sql() -> List[str]:
    """Idempotent statements that install the append-only guard."""
    statements = [GUARD_FUNCTION_SQL]
    for table in GUARDED_TABLES:
        statements += [
            f"DROP TRIGGER IF EXISTS {table}_no_update ON {table};",
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION confit_audit_append_only_guard();",
            f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table};",
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION confit_audit_append_only_guard();",
            f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};",
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION confit_audit_append_only_guard();",
            # Least privilege for the runtime role: INSERT + SELECT only.
            # Conditional: the role exists on Neon, not necessarily in CI.
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN
                    REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
                        ON {table} FROM {RUNTIME_ROLE};
                END IF;
            END
            $$;
            """,
        ]
    return statements


def guard_remove_sql() -> List[str]:
    """Statements for the migration downgrade path.

    The downgrade restores the pre-0022 state faithfully (including the
    over-broad grants) so upgrade→downgrade→upgrade is exact.
    """
    statements: List[str] = []
    for table in GUARDED_TABLES:
        statements += [
            f"DROP TRIGGER IF EXISTS {table}_no_update ON {table};",
            f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table};",
            f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};",
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN
                    GRANT UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
                        ON {table} TO {RUNTIME_ROLE};
                END IF;
            END
            $$;
            """,
        ]
    statements.append("DROP FUNCTION IF EXISTS confit_audit_append_only_guard();")
    return statements
