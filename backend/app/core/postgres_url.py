"""PostgreSQL URL normalisation — the single owner of the driver decision.

WHY THIS IS ITS OWN MODULE (it used to live inside ``database.py``):
``database.py`` builds an engine at import time. Every script, CI job and test that
only needed the *URL rule* therefore had to import a module with connection side
effects, so they either duplicated the rule or skipped it — and the duplicates are
exactly how a driver decision drifts from production. This module imports nothing
but the standard library.

STANDARDS / SOURCES
  * SQLAlchemy 2.1 migration guide, "Default PostgreSQL driver changed to psycopg
    (psycopg 3)": a bare ``postgresql://`` URL no longer means psycopg2.
    https://docs.sqlalchemy.org/en/21/changelog/migration_21.html
  * SQLAlchemy 2.1 PostgreSQL dialect docs: "Changed in version 2.1: psycopg
    (psycopg 3) is now the default PostgreSQL dialect when no specific dialect is
    specified in the URL (e.g. postgresql://...)".
    https://docs.sqlalchemy.org/en/21/dialects/postgresql.html
  * SQLAlchemy 2.1.0 was published 2026-09-24T20:36Z; the repository requirement is
    the floor ``sqlalchemy>=2.0.35``, so a fresh install (Python >= 3.11) resolves
    to 2.1.0 and the rule below must be explicit rather than inherited from a
    default that has changed.

THE DEFECT THIS FIXES (measured 2026-09-24): the function probed for psycopg2 and,
finding it, returned the URL UNCHANGED — a bare ``postgresql://``. Under
SQLAlchemy 2.0 that resolved to psycopg2 and everything worked. Under 2.1 it
resolves to psycopg 3, which is not installed in this project (``backend/
requirements.txt`` ships ``psycopg2-binary``), so ``create_engine()`` raised
``ModuleNotFoundError: No module named 'psycopg'`` before a single query ran: the
API, the schema gate and every PostgreSQL-backed test could not connect. The
selection was always documented as deterministic; now the URL makes it so.
"""
import ssl

#: Driver preference order. psycopg2 first (backend/requirements.txt, Docker, CI),
#  then pg8000 (Vercel's Python runtime — pure Python, no C extensions), then
#  psycopg 3 (newer environments where psycopg2 is absent).
DRIVER_PREFERENCE = ("psycopg2", "pg8000", "psycopg")

#: The SQLAlchemy dialect name for each DBAPI module.
DIALECT_FOR_DRIVER = {"psycopg2": "psycopg2", "pg8000": "pg8000", "psycopg": "psycopg"}


def _postgres_driver_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def select_postgres_driver(available=None) -> str:
    """Return the DBAPI module name to use, deterministically.

    ``available`` is injectable so the decision is testable without installing or
    uninstalling drivers.
    """
    probe = available or _postgres_driver_available
    for name in DRIVER_PREFERENCE:
        try:
            if probe(name):
                return name
        except ImportError:
            continue
    raise RuntimeError(
        "DATABASE_URL is PostgreSQL but none of the supported drivers is installed "
        f"({', '.join(DRIVER_PREFERENCE)}) "
        "(backend/requirements.txt provides psycopg2-binary; the Vercel manifest "
        "requirements.txt provides pg8000)"
    )


def normalise_postgres_url(url: str, available=None):
    """Return ``(sqlalchemy_url, connect_args)`` for a PostgreSQL DSN.

    The returned URL ALWAYS names the driver explicitly
    (``postgresql+<driver>://``). That is not cosmetic: SQLAlchemy 2.1 changed the
    default DBAPI behind a bare ``postgresql://`` scheme from psycopg2 to psycopg 3,
    so a URL that does not name its driver means "whatever the installed SQLAlchemy
    prefers", which is not the same thing as the driver this code selected, and is
    not stable across a dependency upgrade.

    With pg8000 the libpq-only ``sslmode`` query parameter is stripped and
    translated into an SSL context (``sslmode=disable`` -> no TLS).
    """
    url = url.replace("postgres://", "postgresql://", 1)
    explicit_driver = url.startswith("postgresql+")
    if explicit_driver:
        driver = url.split("+", 1)[1].split("://", 1)[0]
    else:
        driver = select_postgres_driver(available)

    args = {}
    if driver == "pg8000":
        base, _, query = url.partition("?")
        params = [kv for kv in query.split("&") if kv]
        sslmode = None
        kept = []
        for kv in params:
            k, _, v = kv.partition("=")
            if k == "sslmode":
                sslmode = v
            elif k in ("channel_binding",):
                continue  # libpq-only
            else:
                kept.append(kv)
        url = base + ("?" + "&".join(kept) if kept else "")
        if not url.startswith("postgresql+pg8000://"):
            url = url.replace("postgresql://", "postgresql+pg8000://", 1)
        if sslmode != "disable":
            args = {"ssl_context": ssl.create_default_context()}
    elif not url.startswith(f"postgresql+{DIALECT_FOR_DRIVER.get(driver, driver)}://"):
        # The step that did not exist before 2026-09-24: make the chosen driver part
        # of the URL instead of trusting SQLAlchemy's default.
        url = url.replace("postgresql://", f"postgresql+{DIALECT_FOR_DRIVER.get(driver, driver)}://", 1)
    return url, args
