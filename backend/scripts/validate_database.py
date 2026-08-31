"""Database integrity validator — usable against dev, test, staging, or prod.

This is a READ-ONLY tool. It never mutates data. It walks every important
cross-table relationship the application depends on and reports:

  * orphan rows (FK targets missing)
  * invalid domain values (unknown enum/status)
  * numeric-domain violations (negative counters/prices/quantities)
  * uniqueness invariants that the application relies on

Run:

    PYTHONPATH=. python3 backend/scripts/validate_database.py

    # or against a specific environment (default = ``DATABASE_URL`` env)
    DATABASE_URL="postgresql+psycopg2://..." \\
        PYTHONPATH=. python3 backend/scripts/validate_database.py

Exit code:

    0 — every check passed
    1 — one or more integrity violations found (details on stdout)
    2 — script failed to run against the target database

The intent is to be safe to run on production: every statement is executed
inside a ``SET TRANSACTION READ ONLY`` block, so a bug in this script cannot
mutate live data.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Iterable, List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


VALID_WARDROBE_PROCESSING_STATUS = {"uploaded", "processing", "ready", "failed"}


@dataclass(frozen=True)
class Check:
    """One integrity check with an expected result.

    ``expected`` is the exact count the SQL should return when the invariant
    holds (usually 0 for orphan/violation counts).
    """

    label: str
    sql: str
    expected: int = 0
    severity: str = "P1"  # P0 blocks production, P1 major, P2 hardening


ORPHAN_CHECKS: List[Check] = [
    Check("orphan wardrobe_items.user_id",
          "SELECT count(*) FROM wardrobe_items w "
          "WHERE w.user_id NOT IN (SELECT id FROM users)",
          severity="P0"),
    Check("orphan outfits.user_id",
          "SELECT count(*) FROM outfits o "
          "WHERE o.user_id NOT IN (SELECT id FROM users)",
          severity="P0"),
    Check("orphan carts.user_id (non-null)",
          "SELECT count(*) FROM carts c WHERE c.user_id IS NOT NULL "
          "AND c.user_id NOT IN (SELECT id FROM users)",
          severity="P0"),
    Check("orphan cart_items.cart_id",
          "SELECT count(*) FROM cart_items ci "
          "WHERE ci.cart_id NOT IN (SELECT id FROM carts)",
          severity="P0"),
    Check("orphan cart_items.product_sku_id",
          "SELECT count(*) FROM cart_items ci "
          "WHERE ci.product_sku_id NOT IN (SELECT id FROM product_skus)",
          severity="P0"),
    Check("orphan cart_items.outfit_id (non-null)",
          "SELECT count(*) FROM cart_items ci WHERE ci.outfit_id IS NOT NULL "
          "AND ci.outfit_id NOT IN (SELECT id FROM outfits)",
          severity="P1"),
    Check("orphan orders.user_id",
          "SELECT count(*) FROM orders o "
          "WHERE o.user_id NOT IN (SELECT id FROM users)",
          severity="P0"),
    Check("orphan order_items.order_id",
          "SELECT count(*) FROM order_items oi "
          "WHERE oi.order_id NOT IN (SELECT id FROM orders)",
          severity="P0"),
    Check("orphan order_items.product_id (non-null)",
          "SELECT count(*) FROM order_items oi WHERE oi.product_id IS NOT NULL "
          "AND oi.product_id NOT IN (SELECT id FROM products)",
          severity="P1"),
    Check("orphan outfit_items.outfit_id",
          "SELECT count(*) FROM outfit_items oi "
          "WHERE oi.outfit_id NOT IN (SELECT id FROM outfits)",
          severity="P0"),
    Check("orphan outfit_items.product_id (non-null)",
          "SELECT count(*) FROM outfit_items oi WHERE oi.product_id IS NOT NULL "
          "AND oi.product_id NOT IN (SELECT id FROM products)",
          severity="P1"),
    Check("orphan mood_board_items.board_id",
          "SELECT count(*) FROM mood_board_items m "
          "WHERE m.board_id NOT IN (SELECT id FROM mood_boards)",
          severity="P0"),
    Check("orphan tryon_sessions.user_id (non-null)",
          "SELECT count(*) FROM tryon_sessions t WHERE t.user_id IS NOT NULL "
          "AND t.user_id NOT IN (SELECT id FROM users)",
          severity="P0"),
    Check("orphan tryon_sessions.product_id (non-null)",
          "SELECT count(*) FROM tryon_sessions t WHERE t.product_id IS NOT NULL "
          "AND t.product_id NOT IN (SELECT id FROM products)",
          severity="P1"),
    Check("orphan recently_viewed.user_id",
          "SELECT count(*) FROM recently_viewed rv "
          "WHERE rv.user_id NOT IN (SELECT id FROM users)",
          severity="P1"),
    Check("orphan recently_viewed.product_id",
          "SELECT count(*) FROM recently_viewed rv "
          "WHERE rv.product_id NOT IN (SELECT id FROM products)",
          severity="P1"),
    Check("orphan refresh_tokens.user_id",
          "SELECT count(*) FROM refresh_tokens r "
          "WHERE r.user_id NOT IN (SELECT id FROM users)",
          severity="P0"),
]

NUMERIC_CHECKS: List[Check] = [
    Check("negative wear_count",
          "SELECT count(*) FROM wardrobe_items WHERE wear_count < 0"),
    Check("negative purchase_price",
          "SELECT count(*) FROM wardrobe_items WHERE purchase_price < 0"),
    Check("cart_items quantity < 1",
          "SELECT count(*) FROM cart_items WHERE quantity < 1"),
    Check("order_items quantity < 1",
          "SELECT count(*) FROM order_items WHERE quantity < 1"),
    Check("order total_amount < 0",
          "SELECT count(*) FROM orders WHERE total_amount < 0"),
    Check("product base_price < 0",
          "SELECT count(*) FROM products WHERE base_price < 0"),
    Check("ai_confidence outside [0,1]",
          "SELECT count(*) FROM wardrobe_items "
          "WHERE ai_confidence IS NOT NULL AND (ai_confidence < 0 OR ai_confidence > 1)",
          severity="P2"),
]

UNIQUENESS_CHECKS: List[Check] = [
    Check("duplicate (user_id, image_hash)",
          "SELECT count(*) FROM ("
          "  SELECT user_id, image_hash FROM wardrobe_items "
          "   WHERE image_hash IS NOT NULL"
          "   GROUP BY user_id, image_hash HAVING count(*) > 1) x",
          severity="P0"),
    Check("duplicate users.email",
          "SELECT count(*) FROM ("
          "  SELECT email FROM users GROUP BY email HAVING count(*) > 1) x",
          severity="P0"),
    Check("duplicate orders.order_number",
          "SELECT count(*) FROM ("
          "  SELECT order_number FROM orders GROUP BY order_number HAVING count(*) > 1) x",
          severity="P0"),
]


def _run_check(engine: Engine, check: Check) -> tuple[bool, str]:
    """Run one check in an isolated read-only connection.

    Returns (passed, description). ``passed`` is False if the count differs
    from ``check.expected`` OR if the query itself errored (e.g. missing
    table — treated as a violation since the target of the audit is broken).
    """
    try:
        with engine.connect() as conn:
            # Postgres supports READ ONLY; SQLite tolerates the statement
            # silently. Wrap in try/except in case the dialect complains.
            try:
                conn.execute(text("SET TRANSACTION READ ONLY"))
            except Exception:
                pass
            n = conn.execute(text(check.sql)).scalar()
        return (n == check.expected, f"{n} (expected {check.expected})")
    except Exception as e:
        return (False, f"query error: {type(e).__name__}: {str(e)[:80]}")


def _run_domain_checks(engine: Engine) -> Iterable[tuple[str, bool, str, str]]:
    """Domain checks that need SELECT DISTINCT semantics."""
    label = "wardrobe_items.processing_status domain"
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("SET TRANSACTION READ ONLY"))
            except Exception:
                pass
            r = conn.execute(
                text("SELECT DISTINCT processing_status FROM wardrobe_items")
            ).fetchall()
        distinct = {row[0] for row in r}
        invalid = distinct - VALID_WARDROBE_PROCESSING_STATUS
        yield (label, not invalid,
               f"distinct={sorted(distinct) or 'empty'}, invalid={sorted(invalid) or 'none'}",
               "P0")
    except Exception as e:
        yield (label, False,
               f"query error: {type(e).__name__}: {str(e)[:80]}", "P0")


def validate(engine: Engine) -> int:
    """Run every check. Returns the number of failed checks (0 = healthy)."""
    fail_count = 0

    def header(name: str) -> None:
        print()
        print(name)
        print("-" * len(name))

    def render(section: List[Check]) -> None:
        nonlocal fail_count
        for chk in section:
            ok, detail = _run_check(engine, chk)
            mark = "OK  " if ok else f"FAIL[{chk.severity}]"
            print(f"  {mark} {chk.label}: {detail}")
            if not ok:
                fail_count += 1

    header("FK / orphan integrity")
    render(ORPHAN_CHECKS)

    header("Domain validity")
    for label, ok, detail, sev in _run_domain_checks(engine):
        mark = "OK  " if ok else f"FAIL[{sev}]"
        print(f"  {mark} {label}: {detail}")
        if not ok:
            fail_count += 1

    header("Numeric validity")
    render(NUMERIC_CHECKS)

    header("Uniqueness invariants")
    render(UNIQUENESS_CHECKS)

    return fail_count


def _resolve_engine(url: str | None) -> Engine:
    if not url:
        raise SystemExit(
            "No DATABASE_URL configured. Pass --url or set DATABASE_URL."
        )
    return create_engine(url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only database integrity validator."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy database URL (defaults to $DATABASE_URL)",
    )
    args = parser.parse_args(argv)

    try:
        engine = _resolve_engine(args.url)
    except SystemExit:
        raise
    except Exception as e:
        print(f"failed to connect: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    print(f"validating database integrity ({engine.url.database or engine.url.host})")
    fail_count = validate(engine)

    print()
    if fail_count == 0:
        print("RESULT: OK — all integrity checks passed.")
        return 0
    print(f"RESULT: {fail_count} check(s) FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
