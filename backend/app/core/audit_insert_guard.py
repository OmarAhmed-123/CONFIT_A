"""Database INSERT provenance guard for both audit chains (migration 0024).

The runtime role must retain INSERT so the application can record audit events
and verification runs. HMAC verification detects invalid signed rows, but the
0020/0023 legacy classifier alone was id-ordered: a direct SQL caller could
choose an explicit low id, omit every chain field, and make the new row sort
into the unsigned legacy prefix.

This guard closes that classification ambiguity at the database boundary.
After it is installed, every *new* INSERT must carry all provenance columns:

* ``audit_logs``: ``prev_hash``, ``entry_hash``, ``chain_key_version``;
* ``audit_verification_runs``: ``run_prev_hash``, ``run_hash``,
  ``run_hmac_key_version``.

The application mapper listeners calculate those values before SQL is emitted.
A DB-only attacker without the HMAC key may still submit non-NULL garbage, but
full/window verification then reports a hash/link mismatch regardless of the
chosen id. Existing NULL legacy rows remain untouched.

This is defence in depth, not cryptographic verification inside PostgreSQL and
not immutability. The table owner can drop the triggers; an actor holding both
DB write access and HMAC keys can forge valid forward history. External
anchoring remains the control for that trust boundary.
"""
from __future__ import annotations

from typing import List

AUDIT_LOG_TRIGGER = "audit_logs_require_chain_provenance"
VERIFICATION_RUN_TRIGGER = "audit_verification_runs_require_chain_provenance"
AUDIT_LOG_FUNCTION = "confit_audit_log_insert_guard"
VERIFICATION_RUN_FUNCTION = "confit_verification_run_insert_guard"


def _postgres_install_sql() -> List[str]:
    return [
        f"""
        CREATE OR REPLACE FUNCTION {AUDIT_LOG_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.prev_hash IS NULL
               OR NEW.entry_hash IS NULL
               OR NEW.chain_key_version IS NULL THEN
                RAISE EXCEPTION
                    'audit_logs INSERT requires signed chain provenance'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """,
        f"""
        CREATE OR REPLACE FUNCTION {VERIFICATION_RUN_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.run_prev_hash IS NULL
               OR NEW.run_hash IS NULL
               OR NEW.run_hmac_key_version IS NULL THEN
                RAISE EXCEPTION
                    'audit_verification_runs INSERT requires signed chain provenance'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """,
        f"DROP TRIGGER IF EXISTS {AUDIT_LOG_TRIGGER} ON audit_logs;",
        f"""
        CREATE TRIGGER {AUDIT_LOG_TRIGGER}
        BEFORE INSERT ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION {AUDIT_LOG_FUNCTION}();
        """,
        f"DROP TRIGGER IF EXISTS {VERIFICATION_RUN_TRIGGER} ON audit_verification_runs;",
        f"""
        CREATE TRIGGER {VERIFICATION_RUN_TRIGGER}
        BEFORE INSERT ON audit_verification_runs
        FOR EACH ROW EXECUTE FUNCTION {VERIFICATION_RUN_FUNCTION}();
        """,
    ]


def _sqlite_install_sql() -> List[str]:
    # SQLite has no role/privilege model, but its official local mode can and
    # should enforce the same new-row provenance invariant.
    return [
        f"DROP TRIGGER IF EXISTS {AUDIT_LOG_TRIGGER};",
        f"""
        CREATE TRIGGER {AUDIT_LOG_TRIGGER}
        BEFORE INSERT ON audit_logs
        FOR EACH ROW
        WHEN NEW.prev_hash IS NULL
          OR NEW.entry_hash IS NULL
          OR NEW.chain_key_version IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'audit_logs INSERT requires signed chain provenance');
        END;
        """,
        f"DROP TRIGGER IF EXISTS {VERIFICATION_RUN_TRIGGER};",
        f"""
        CREATE TRIGGER {VERIFICATION_RUN_TRIGGER}
        BEFORE INSERT ON audit_verification_runs
        FOR EACH ROW
        WHEN NEW.run_prev_hash IS NULL
          OR NEW.run_hash IS NULL
          OR NEW.run_hmac_key_version IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'audit_verification_runs INSERT requires signed chain provenance');
        END;
        """,
    ]


def insert_guard_install_sql(dialect: str) -> List[str]:
    if dialect == "postgresql":
        return _postgres_install_sql()
    if dialect == "sqlite":
        return _sqlite_install_sql()
    return []


def insert_guard_remove_sql(dialect: str) -> List[str]:
    if dialect == "postgresql":
        return [
            f"DROP TRIGGER IF EXISTS {AUDIT_LOG_TRIGGER} ON audit_logs;",
            f"DROP TRIGGER IF EXISTS {VERIFICATION_RUN_TRIGGER} ON audit_verification_runs;",
            f"DROP FUNCTION IF EXISTS {AUDIT_LOG_FUNCTION}();",
            f"DROP FUNCTION IF EXISTS {VERIFICATION_RUN_FUNCTION}();",
        ]
    if dialect == "sqlite":
        return [
            f"DROP TRIGGER IF EXISTS {AUDIT_LOG_TRIGGER};",
            f"DROP TRIGGER IF EXISTS {VERIFICATION_RUN_TRIGGER};",
        ]
    return []
