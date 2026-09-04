"""Schema-drift gate — the database must match the code that is about to serve it.

Production truth that motivated this module (2026-09-03): the Neon production
database sat at alembic revision 0007 while the deployed code expected 0013.
Four endpoints (brand/analytics, brand/placements, admin/analytics,
commerce/orders/{n}) returned 500 for weeks because tables/columns the ORM
referenced did not exist. Nothing detected it: Vercel's build never runs
Alembic, startup skipped ``create_all`` in production (correctly), and the
health endpoint only ran ``SELECT 1``.

This module answers one question with evidence: *is this database at the
schema revision this code was written for?*  It never repairs anything and
never hides a mismatch behind an empty result.

Evaluation
----------
1. ``expected_head_revision()``  – parsed from backend/alembic/versions/*.py
   (the single linear chain), so the runtime does not need the alembic package.
2. ``inspect_database(engine)``  – reads ``alembic_version`` and the live table /
   column inventory through SQLAlchemy's inspector (works on PostgreSQL and
   SQLite).
3. ``evaluate(engine)``          – returns a ``SchemaGateReport`` with a
   verdict and a list of concrete findings:
     ``ok``        revision == head and every required object present
     ``unmanaged`` no ``alembic_version`` at all but every ORM-backed required
                   object present — a ``create_all`` database (dev/test).
                   Acceptable outside production, REJECTED in production.
     ``drift``     anything else (behind/ahead/unknown revision, missing
                   table or column). Always rejected in production.
     ``unknown``   the database could not be inspected.

Wiring
------
* ``backend/app/main.py`` lifespan: in production a ``drift`` verdict raises
  ``SchemaDriftError`` so the deployment fails loudly instead of serving 500s.
  In other environments it is logged (dev/test DBs are created by ``create_all``
  and legitimately carry no ``alembic_version`` row).
* ``GET /health``: ``checks.schema`` reports the verdict, the DB revision and
  the expected head — so the uptime monitor and a human can see drift.
* ``python -m backend.app.core.schema_gate`` : deploy-pipeline CLI, exit 1 on
  drift. Use it right after ``alembic upgrade head`` and before promoting a
  release.

Required-object list
--------------------
``REQUIRED_TABLES`` / ``REQUIRED_COLUMNS`` are the objects whose absence
produced the 2026-09-03 production 500s plus the tables added by later
revisions. They are checked *in addition to* the revision comparison so that a
DB whose ``alembic_version`` row was hand-edited (or a partially applied
migration) is still caught.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# Objects that MUST exist for the ORM in this tree to function. Keep in sync
# with new migrations: add the table/column here in the same commit that adds
# the migration (tests/test_schema_drift_gate.py enforces that every listed
# object exists in Base.metadata).
REQUIRED_TABLES: tuple[str, ...] = (
    "users",
    "products",
    "product_skus",
    "orders",
    "order_items",
    "order_events",           # 0008 — /commerce/orders/{n}/tracking
    "shipments",              # 0008
    "return_items",           # 0008 — item-level refunds
    "payment_transactions",   # 0008
    "checkout_sessions",      # 0009
    "brand_analytics_events",  # 0010 — /brand/analytics, /admin/analytics
    "catalog_import_jobs",    # 0010
    "sponsored_placements",   # /brand/placements
    "migration_audit_log",    # 0013
)

# Tables created by a migration only (no ORM model): a create_all database
# legitimately lacks them, an Alembic-managed one must have them.
MIGRATION_ONLY_TABLES: frozenset[str] = frozenset({"migration_audit_log"})

REQUIRED_COLUMNS: Dict[str, tuple[str, ...]] = {
    "orders": ("payment_mode", "shipping_method", "estimated_delivery_date", "guest_session_token"),
    "order_items": ("is_returned", "fulfillment_group_id"),
    "sponsored_placements": ("start_date", "end_date", "updated_at"),
    "brand_analytics_events": ("event_id", "order_id", "revenue_amount", "order_item_id"),  # order_item_id: 0014
    "wardrobe_items": ("source_order_item_id",),  # 0015 — FLOW E purchase->wardrobe idempotency key
}


class SchemaDriftError(RuntimeError):
    """Raised at production startup when the database does not match the code."""


@dataclass
class SchemaGateReport:
    verdict: str                                  # "ok" | "unmanaged" | "drift" | "unknown"
    expected_head: Optional[str]
    database_revision: Optional[str]
    findings: List[str] = field(default_factory=list)
    missing_tables: List[str] = field(default_factory=list)
    missing_columns: Dict[str, List[str]] = field(default_factory=dict)
    dialect: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.verdict == "ok"

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "expected_head": self.expected_head,
            "database_revision": self.database_revision,
            "missing_tables": list(self.missing_tables),
            "missing_columns": dict(self.missing_columns),
            "findings": list(self.findings),
        }


# --------------------------------------------------------------------------- code side
_REV_RE = re.compile(r"^revision(?:\s*:\s*str)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)
_DOWN_RE = re.compile(r"^down_revision(?:\s*:\s*[^=\n]+)?\s*=\s*(None|['\"]([^'\"]+)['\"])", re.M)


def migration_chain(versions_dir: Path = VERSIONS_DIR) -> Dict[str, Optional[str]]:
    """{revision: down_revision} parsed from the migration scripts."""
    chain: Dict[str, Optional[str]] = {}
    for f in sorted(versions_dir.glob("*.py")):
        src = f.read_text(encoding="utf-8", errors="ignore")
        m = _REV_RE.search(src)
        if not m:
            continue
        d = _DOWN_RE.search(src)
        chain[m.group(1)] = (d.group(2) if d and d.group(2) else None)
    return chain


def expected_head_revision(versions_dir: Path = VERSIONS_DIR) -> Optional[str]:
    """The single head of the linear migration chain (None if no scripts)."""
    chain = migration_chain(versions_dir)
    if not chain:
        return None
    downs = {d for d in chain.values() if d}
    heads = [r for r in chain if r not in downs]
    if len(heads) != 1:
        raise SchemaDriftError(f"migration chain has {len(heads)} heads: {heads}")
    return heads[0]


def revision_ordinal(rev: Optional[str], versions_dir: Path = VERSIONS_DIR) -> Optional[int]:
    """Position of ``rev`` in the chain (0 = baseline) or None if unknown."""
    if rev is None:
        return None
    chain = migration_chain(versions_dir)
    if rev not in chain:
        return None
    n, cur = 0, rev
    while chain.get(cur):
        cur = chain[cur]
        n += 1
    return n


# ----------------------------------------------------------------------- database side
def inspect_database(engine: Engine) -> tuple[Optional[str], Set[str], Dict[str, Set[str]]]:
    """(alembic revision or None, table names, {table: columns} for required tables)."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    revision: Optional[str] = None
    if "alembic_version" in tables:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        if len(rows) == 1:
            revision = rows[0][0]
        elif len(rows) > 1:
            revision = "MULTIPLE:" + ",".join(sorted(r[0] for r in rows))
    columns: Dict[str, Set[str]] = {}
    for tbl in REQUIRED_COLUMNS:
        if tbl in tables:
            columns[tbl] = {c["name"] for c in insp.get_columns(tbl)}
    return revision, tables, columns


def evaluate(engine: Engine, *, versions_dir: Path = VERSIONS_DIR) -> SchemaGateReport:
    """Compare the live database against this code's expectations."""
    expected = expected_head_revision(versions_dir)
    try:
        db_rev, tables, columns = inspect_database(engine)
    except Exception as exc:  # DB unreachable: report, never pretend ok
        return SchemaGateReport(
            verdict="unknown", expected_head=expected, database_revision=None,
            findings=[f"database inspection failed: {type(exc).__name__}: {str(exc)[:200]}"],
            dialect=engine.dialect.name,
        )

    findings: List[str] = []
    unmanaged = False
    if db_rev is None:
        unmanaged = True
        findings.append("alembic_version table/row missing — database was never migrated by Alembic")
    elif db_rev != expected:
        db_ord = revision_ordinal(db_rev, versions_dir)
        exp_ord = revision_ordinal(expected, versions_dir)
        if db_ord is None:
            findings.append(f"database revision {db_rev!r} is unknown to this code (expected {expected!r})")
        elif exp_ord is not None and db_ord < exp_ord:
            findings.append(
                f"database is BEHIND the code: {db_rev} < {expected} "
                f"({exp_ord - db_ord} migration(s) not applied) — run: alembic upgrade head"
            )
        else:
            findings.append(f"database is AHEAD of the code: {db_rev} > {expected} — deploy newer code or downgrade")

    missing_tables = [t for t in REQUIRED_TABLES if t not in tables]
    for t in missing_tables:
        findings.append(f"required table missing: {t}")

    missing_columns: Dict[str, List[str]] = {}
    for tbl, cols in REQUIRED_COLUMNS.items():
        if tbl not in tables:
            continue  # already reported as a missing table
        gone = [c for c in cols if c not in columns.get(tbl, set())]
        if gone:
            missing_columns[tbl] = gone
            findings.append(f"required column(s) missing on {tbl}: {', '.join(gone)}")

    orm_tables_missing = [t for t in missing_tables if t not in MIGRATION_ONLY_TABLES]
    if unmanaged and not orm_tables_missing and not missing_columns:
        # create_all database: complete for the ORM, just not Alembic-managed
        # (migration-only bookkeeping tables are legitimately absent).
        verdict = "unmanaged"
    elif findings:
        verdict = "drift"
    else:
        verdict = "ok"

    return SchemaGateReport(
        verdict=verdict,
        expected_head=expected,
        database_revision=db_rev,
        findings=findings,
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        dialect=engine.dialect.name,
    )


# Process-wide cached verdict shared by the startup gate, the request guard
# and /health. The inspector issues a handful of catalog queries; a short TTL
# keeps requests cheap and lets instances recover within a minute after the
# operator applies the missing migrations.
# keyed by engine URL: a verdict for one database must never be served for another
_CACHE: Dict[str, tuple[float, SchemaGateReport]] = {}
CACHE_TTL_SECONDS = 60.0


def _cache_key(engine: Engine) -> str:
    return engine.url.render_as_string(hide_password=True)


def cached_report(engine: Engine, *, ttl: float = CACHE_TTL_SECONDS, force: bool = False) -> SchemaGateReport:
    import time as _time

    now = _time.time()
    key = _cache_key(engine)
    hit = _CACHE.get(key)
    if force or hit is None or (now - hit[0]) > ttl:
        rep = evaluate(engine)
        _CACHE[key] = (now, rep)
        return rep
    return hit[1]


def reset_cache() -> None:
    _CACHE.clear()


def acceptable(report: SchemaGateReport, environment: str) -> bool:
    """Production accepts only ``ok``; other environments also accept a
    complete ``create_all`` schema (``unmanaged``)."""
    if report.verdict == "ok":
        return True
    return report.verdict == "unmanaged" and (environment or "").lower() != "production"


def enforce_at_startup(engine: Engine, environment: str, logger=None) -> SchemaGateReport:
    """Production: raise unless the verdict is ``ok``. Elsewhere: log and continue.

    ``CONFIT_SCHEMA_GATE=warn`` downgrades production enforcement to logging
    for an explicit, auditable emergency override — never the default.
    """
    report = cached_report(engine, force=True)
    mode = (os.environ.get("CONFIT_SCHEMA_GATE") or "enforce").lower()
    is_prod = (environment or "").lower() == "production"
    ok = acceptable(report, environment)
    if logger is not None:
        log = logger.error if (not ok and is_prod) else logger.info
        log("schema_gate", **report.as_dict(), environment=environment, mode=mode)
    if is_prod and not ok and mode != "warn":
        raise SchemaDriftError("; ".join(report.findings) or report.verdict)
    return report


def request_guard_verdict(engine: Engine, environment: str) -> Optional[SchemaGateReport]:
    """Per-request production guard (serverless-safe).

    On Vercel the ASGI lifespan may or may not run for a given function
    instance, so startup enforcement alone cannot be relied upon. This returns
    the report when the request MUST be refused (production + not acceptable +
    no explicit override), otherwise None. Cheap: cached per process.
    """
    if (environment or "").lower() != "production":
        return None
    if (os.environ.get("CONFIT_SCHEMA_GATE") or "enforce").lower() == "warn":
        return None
    report = cached_report(engine)
    return None if acceptable(report, environment) else report


def _cli(argv: Optional[list] = None) -> int:
    """Deploy-pipeline entrypoint.

        python -m backend.app.core.schema_gate [DATABASE_URL] [--env production]

    The database is taken from (first wins): the positional URL, ``$SCHEMA_GATE_DATABASE_URL``,
    ``$ALEMBIC_DATABASE_URL``, ``$DATABASE_URL``. It is NEVER silently the application's
    development default: evaluating the wrong database and printing OK is the failure mode
    this tool exists to prevent, so a missing URL is an error (exit 2).
    The environment defaults to ``$ENVIRONMENT`` (or ``production`` when unset): the CLI
    is a release gate, so the strictest policy is the default.
    """
    import argparse
    import os
    from sqlalchemy import create_engine

    parser = argparse.ArgumentParser(prog="schema_gate")
    parser.add_argument("database_url", nargs="?", default=None)
    parser.add_argument("--env", default=os.environ.get("ENVIRONMENT") or "production")
    args = parser.parse_args(argv)

    url = (
        args.database_url
        or os.environ.get("SCHEMA_GATE_DATABASE_URL")
        or os.environ.get("ALEMBIC_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        print("schema gate: ERROR no database URL given (positional arg, SCHEMA_GATE_DATABASE_URL, "
              "ALEMBIC_DATABASE_URL or DATABASE_URL)")
        return 2
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        report = evaluate(engine)
    finally:
        engine.dispose()
    print(f"schema gate: {report.verdict.upper()}  dialect={report.dialect}  "
          f"db={report.database_revision}  expected={report.expected_head}  env={args.env}  "
          f"target={engine.url.render_as_string(hide_password=True)}")
    for f in report.findings:
        print(f"  ✗ {f}")
    return 0 if acceptable(report, args.env) else 1


if __name__ == "__main__":  # pragma: no cover - deploy pipeline entrypoint
    raise SystemExit(_cli())
