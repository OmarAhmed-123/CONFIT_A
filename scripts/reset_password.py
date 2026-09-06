#!/usr/bin/env python3
"""Securely reset a CONFIT account password directly in the database.

WHY THIS EXISTS (2026-09-06 audit, P0-05): the production demo accounts
(admin@confit.io / shopper@confit.io / brand@massimodutti.com) had drifted to
unknown passwords, no email provider is configured (forgot-password honestly
returns 501 FEATURE_NOT_CONFIGURED), so operator lockout had no recovery
path. This script is that path.

Security rules:
  - The new password is read from the environment or an interactive prompt —
    it is NEVER accepted as a CLI argument (shell history / process list
    leakage) and is NEVER logged.
  - Connects via DATABASE_URL / ALEMBIC_DATABASE_URL from the environment.
  - Refuses to run against a non-production-looking URL without --yes.

Usage:
  CONFIT_NEW_PASSWORD='...' python3 scripts/reset_password.py admin@confit.io
  CONFIT_NEW_PASSWORD='...' python3 scripts/reset_password.py admin@confit.io --yes
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.app.core.security import get_password_hash  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(args) != 1:
        print(__doc__)
        return 2
    email = args[0].strip().lower()

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("ALEMBIC_DATABASE_URL")
    if not db_url:
        print("ERROR: set DATABASE_URL (or ALEMBIC_DATABASE_URL) first.")
        return 2
    looks_local = "localhost" in db_url or "127.0.0.1" in db_url or db_url.startswith("sqlite")
    if not looks_local and "--yes" not in flags:
        confirm = input(f"This will rewrite the password of {email!r} in a REMOTE database. Continue? [type YES] ")
        if confirm.strip() != "YES":
            print("Aborted.")
            return 1

    new_password = os.environ.get("CONFIT_NEW_PASSWORD") or getpass.getpass(f"New password for {email}: ")
    if len(new_password) < 8:
        print("ERROR: password must be at least 8 characters.")
        return 2

    pw_hash = get_password_hash(new_password)  # bcrypt, cost 12
    engine = create_engine(db_url)
    with Session(engine) as session:
        row = session.execute(
            text("SELECT id, role, is_active FROM users WHERE lower(email) = :e"), {"e": email}
        ).fetchone()
        if row is None:
            print(f"ERROR: no user found with email {email!r}.")
            return 1
        session.execute(
            text("UPDATE users SET hashed_password = :h, mfa_enabled = false WHERE id = :id"),
            {"h": pw_hash, "id": row.id},
        )
        session.execute(
            text("DELETE FROM refresh_tokens WHERE user_id = :id"), {"id": row.id}
        )
        session.commit()
        # Audit trail (no secrets, per observability rules). Best-effort:
        # column sets differ slightly across schema revisions, and a failed
        # audit write must never roll back the reset itself.
        try:
            session.execute(
                text(
                    "INSERT INTO audit_logs (user_id, action, resource_type, resource_id, details_json) "
                    "VALUES (:u, 'OPERATOR_PASSWORD_RESET', 'User', :u, :d)"
                ),
                {"u": row.id, "d": '{"via": "scripts/reset_password.py", "mfa_reset": true}'},
            )
            session.commit()
        except Exception as audit_err:  # noqa: BLE001
            session.rollback()
            print(f"NOTE: audit row could not be written ({audit_err.__class__.__name__}); the password reset itself is committed.")
        print(f"OK: password updated for {email} (id={row.id}, role={row.role}); sessions revoked; MFA disabled — re-enable it after login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
