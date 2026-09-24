"""PostgreSQL driver selection — the URL must name the driver we chose.

THE DEFECT (found 2026-09-24, same day SQLAlchemy 2.1.0 was published)
----------------------------------------------------------------------
``normalise_postgres_url()`` probed for a DBAPI and then returned the URL
UNCHANGED — a bare ``postgresql://``. Under SQLAlchemy 2.0 that meant psycopg2, so
it worked and was never questioned. SQLAlchemy 2.1 changed the default DBAPI for a
bare ``postgresql://`` URL to psycopg 3 (docs: "Changed in version 2.1: psycopg
(psycopg 3) is now the default PostgreSQL dialect when no specific dialect is
specified in the URL"). This project installs psycopg2-binary and NOT psycopg 3,
so ``create_engine()`` raised ``ModuleNotFoundError: No module named 'psycopg'``
before opening a connection:

    $ python -c "from sqlalchemy import create_engine; create_engine('postgresql://…')"
    ModuleNotFoundError: No module named 'psycopg'

The requirement is the floor ``sqlalchemy>=2.0.35``, so which behaviour a fresh
install gets depended on the calendar, not on the code. Every PostgreSQL-backed
path was affected: the API engine, the schema gate, and the CI PostgreSQL job.

WHAT IS ASSERTED HERE
---------------------
The contract is *not* "SQLAlchemy's default is psycopg2" (that is precisely the
assumption that broke). It is: **the URL returned by the rule names the driver the
rule selected.** These tests fail if that regresses, in either direction — and
``test_sqlalchemy_resolves_the_driver_we_selected`` fails on day one under
SQLAlchemy 2.1 if the URL is left bare, which is how the defect was caught.
"""
import os

import pytest

from backend.app.core.postgres_url import (
    DIALECT_FOR_DRIVER,
    DRIVER_PREFERENCE,
    normalise_postgres_url,
    select_postgres_driver,
)


def _only(*installed):
    """An availability probe that reports exactly ``installed``."""
    return lambda name: name in installed


# ── the rule's own contract ──────────────────────────────────────────────────

@pytest.mark.parametrize("driver", DRIVER_PREFERENCE)
def test_the_returned_url_names_the_selected_driver(driver):
    """POSITIVE: whichever driver is available, the URL says so."""
    url, _args = normalise_postgres_url("postgresql://user:pw@host:5432/db",
                                        available=_only(driver))
    assert url.startswith(f"postgresql+{DIALECT_FOR_DRIVER[driver]}://"), (
        f"driver {driver!r} was selected but the URL does not name a driver: {url!r}"
    )


def test_a_bare_postgresql_scheme_is_never_returned():
    """NEGATIVE CONTROL: the exact shape that broke must not escape.

    This is the assertion that would have failed on 2026-09-23 and passes now. It
    is written against the *shape*, not against a driver name, so it keeps holding
    if the preference order changes.
    """
    for probe in (_only("psycopg2"), _only("pg8000"), _only("psycopg"),
                  _only("psycopg2", "pg8000", "psycopg")):
        url, _args = normalise_postgres_url("postgresql://user:pw@host:5432/db", available=probe)
        assert not url.startswith("postgresql://"), (
            "the URL was handed to SQLAlchemy with no driver named; SQLAlchemy decides "
            f"the DBAPI from its own version-dependent default: {url!r}"
        )
        assert "+" in url.split("://", 1)[0], f"no driver in scheme: {url!r}"


def test_preference_order_is_stable():
    """psycopg2 → pg8000 → psycopg 3, with every driver present."""
    assert select_postgres_driver(_only(*DRIVER_PREFERENCE)) == "psycopg2"
    assert select_postgres_driver(_only("pg8000", "psycopg")) == "pg8000"
    assert select_postgres_driver(_only("psycopg")) == "psycopg"


def test_an_explicit_driver_in_the_input_is_respected():
    """An operator who names a driver is not overruled, and not double-prefixed."""
    for scheme in ("postgresql+psycopg2", "postgresql+psycopg", "postgresql+pg8000"):
        url, _args = normalise_postgres_url(f"{scheme}://user:pw@host:5432/db",
                                            available=_only("psycopg2"))
        assert url.startswith(f"{scheme}://"), url
        assert url.count("+") == 1, f"driver prefix duplicated: {url!r}"


def test_no_driver_installed_raises_with_the_installation_hint():
    with pytest.raises(RuntimeError) as excinfo:
        normalise_postgres_url("postgresql://user:pw@host:5432/db", available=_only())
    assert "driver" in str(excinfo.value).lower()
    assert "psycopg2-binary" in str(excinfo.value)


def test_pg8000_strips_libpq_only_parameters_and_keeps_tls():
    """The Vercel path: `sslmode` is not a pg8000 parameter, TLS is still on."""
    url, args = normalise_postgres_url(
        "postgresql://user:pw@host:5432/db?sslmode=require&channel_binding=require",
        available=_only("pg8000"))
    assert url == "postgresql+pg8000://user:pw@host:5432/db"
    assert "ssl_context" in args

    url_off, args_off = normalise_postgres_url(
        "postgresql://user:pw@host:5432/db?sslmode=disable", available=_only("pg8000"))
    assert url_off == "postgresql+pg8000://user:pw@host:5432/db"
    assert args_off == {}


def test_postgres_scheme_alias_is_upgraded():
    url, _args = normalise_postgres_url("postgres://user:pw@host:5432/db",
                                        available=_only("psycopg2"))
    assert url.startswith("postgresql+psycopg2://"), url


# ── the part that actually broke: what SQLAlchemy does with the URL ──────────

def test_sqlalchemy_resolves_the_driver_we_selected():
    """The load-bearing check.

    SQLAlchemy is the component that turns a URL into a DBAPI import. This asserts
    that the dialect it picks for our URL is the driver this module selected — so a
    change in SQLAlchemy's defaults can no longer silently redirect us to a package
    that is not installed.
    """
    from sqlalchemy import create_engine

    selected = select_postgres_driver()
    url, connect_args = normalise_postgres_url("postgresql://user:pw@host:5432/db")
    engine = create_engine(url, connect_args=connect_args)
    assert engine.dialect.driver == DIALECT_FOR_DRIVER[selected], (
        f"selected {selected!r} but SQLAlchemy resolved {engine.dialect.driver!r} "
        f"from {url!r}"
    )
    engine.dispose()


def test_the_dialect_we_resolve_is_actually_importable():
    """A resolved dialect whose DBAPI cannot be imported is the failure mode."""
    from sqlalchemy import create_engine

    url, connect_args = normalise_postgres_url("postgresql://user:pw@host:5432/db")
    engine = create_engine(url, connect_args=connect_args)   # imports the DBAPI here
    assert engine.dialect.dbapi is not None
    engine.dispose()


# ── integration: a real connection, when a PostgreSQL is offered ─────────────

PG_URL = os.environ.get("CONFIT_TEST_PG_URL", "")


@pytest.mark.skipif(not PG_URL.startswith(("postgresql://", "postgres://", "postgresql+")),
                    reason="CONFIT_TEST_PG_URL not set to a PostgreSQL DSN")
def test_a_real_postgresql_connection_opens_through_the_rule():
    from sqlalchemy import create_engine

    url, connect_args = normalise_postgres_url(PG_URL)
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("select 1").scalar() == 1
    finally:
        engine.dispose()
