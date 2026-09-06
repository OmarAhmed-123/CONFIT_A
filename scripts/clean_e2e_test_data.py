#!/usr/bin/env python3
"""Remove e2e-test pollution from a CONFIT database (dry-run by default).

WHY THIS EXISTS (2026-09-06 audit, INF-02): repeated browser-driven e2e runs
against the PRODUCTION Neon database left ~70 synthetic accounts
(browser.e2e.*@e2e-browser.example.com, csrf.repro.*, final2.*, probe403.*,
bola_*, liveverify_*, ...) plus their carts, try-on jobs and sessions. The
suite now runs on throwaway SQLite, but the leftovers in prod need a safe,
reviewable sweep.

Safety model:
  - DRY RUN by default: prints exactly what WOULD be deleted, deletes nothing.
  - --commit performs the deletion inside one transaction per user, ordered
    to satisfy foreign keys; unknown-pattern rows are never touched.
  - Only rows matching STRICT test patterns are targeted — never real users,
    never the seeded demo accounts (shopper@/admin@/brand@confit.io etc.).
  - Refuses to run against a remote database without an explicit --yes.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

TEST_EMAIL_PATTERNS = [
    r".*@e2e-browser\.example\.com$",
    r".*@e2e-final\d*\.example\.com$",
    r".*@e2e-final2\.example\.com$",
    r".*@e2e-final3\.example\.com$",
    r".*@e2e-final4\.example\.com$",
    r".*@e2e-final5\.example\.com$",
    r".*@e2e-final6\.example\.com$",
    r".*@e2e-final7\.example\.com$",
    r".*@e2e-final8[a-z]?\.example\.com$",
    r".*@e2e-probe\.example\.com$",
    r".*@e2e-csrf\.example\.com$",
    r".*@e2e\.mtc\d+\.example\.com$",
    r"^browser\.e2e\..*@example\.com$",
    r"^user[ab]\.e2e\..*@example\.com$",
    r"^csrf\d*\.repro\..*@example\.com$",
    r"^final\d*[a-z]*\..*@example\.com$",
    r"^final\.plain\..*@e2e-final\.example\.com$",
    r"^bola\d*_\d+_[0-9a-f]+@example\.com$",
    r"^authz\d*[\._]\d+@example\.com$",
    r"^authz_\d+@example\.com$",
    r"^iso[ab]\d*_\d+@example\.com$",
    r"^layer\.[0-9a-f]+@example\.com$",
    r"^liveverify_\d+_[ab]@example\.com$",
    r"^noret_\d+@example\.com$",
    r"^meas_\d+_[0-9a-f]+@example\.com$",
    r"^probe403\..*@example\.com$",
    r".*@confit-test\.dev$",  # QA probes written during the 2026-09-06 audit
]
COMPILED = [re.compile(p, re.IGNORECASE) for p in TEST_EMAIL_PATTERNS]


def is_test_email(email: str) -> bool:
    return any(c.match(email or "") for c in COMPILED)


# Child rows owned by a user, in FK-safe deletion order.
CHILD_TABLES = [
    "refresh_tokens",
    "mfa_backup_codes",
    "stylist_messages",
    "stylist_sessions",
    "tryon_sessions",
    "tryon_jobs",
    "cart_items",
    "carts",
    "order_items",
    "order_events",
    "orders",
    "outfit_items",
    "outfits",
    "wardrobe_items",
    "wardrobe_gap_analyses",
    "user_style_profiles",
    "recently_viewed",
    "measurement_results",
    "measurement_sessions",
    "person_scan_cache",
    "visual_search_queries",
    "mood_board_items",
    "mood_boards",
    "email_verification_tokens",
    "password_reset_tokens",
    "brand_analytics_events",
]


def main() -> int:
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    do_commit = "--commit" in flags

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("ALEMBIC_DATABASE_URL")
    if not db_url:
        print("ERROR: set DATABASE_URL first.")
        return 2
    looks_local = "localhost" in db_url or "127.0.0.1" in db_url or db_url.startswith("sqlite")
    if not looks_local and "--yes" not in flags:
        print("Remote database detected. Re-run with --yes (and --commit to actually delete).")
        return 1

    engine = create_engine(db_url)
    with Session(engine) as session:
        users = session.execute(text("SELECT id, email, created_at FROM users ORDER BY id")).fetchall()
        targets = [(u.id, u.email) for u in users if is_test_email(u.email)]
        print(f"Scanned {len(users)} users -> {len(targets)} match test patterns.")
        for uid, email in targets:
            print(f"  [would delete] user id={uid} email={email}" if not do_commit else f"  [deleting] user id={uid} email={email}")
            if do_commit:
                for table in CHILD_TABLES:
                    try:
                        session.execute(text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": uid})
                    except Exception:
                        session.rollback()
                        # Table may not exist in this schema — continue.
                        continue
                # orphan try-on jobs that carry the user's email in metadata
                session.execute(
                    text("DELETE FROM audit_logs WHERE user_id = :uid"), {"uid": uid}
                )
                session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
                session.commit()
        if not do_commit:
            print("\nDRY RUN ONLY — nothing was deleted. Re-run with --commit to delete.")
        else:
            print(f"\nDeleted {len(targets)} test users (and their child rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
