"""Every test module that owns an engine must own the SUITE's engine.

MEASURED 2026-09-24, on PostgreSQL, and it cost real verification time:

    CONFIT_TEST_DB_URL=postgresql+psycopg2://confit@/confit_conc?host=/tmp&port=55432
    pytest backend/tests            ->  17 failed, 2592 passed
    FAILED test_admin_atomic_audit.py::...        x4
    FAILED test_audit_hash_chain.py::...         x13

Those two modules built their own engine from a hardcoded
``sqlite:///./backend/data/confit_test.db``, so they ignored the configured
backend entirely: the failures were about a stale SQLite side-file (leftover rows
from an earlier local run) or about a side-file that did not exist at all (a
fresh checkout — then the tables are missing). CI never noticed because CI runs
that module on SQLite only, where the side-file happens to exist. The control run
that proved this was pre-existing: the same 17 failures reproduce on the commit
before the change being verified, with the same side-file.

A module that silently tests a different database than the suite reports is worse
than a failing test — it makes every "verified on PostgreSQL" claim untrustworthy.
The suite's ``new_test_engine()`` (conftest) is the single owner of that decision.

These checks are behavioural: they compare the module's engine URL with the
configured one. No source-text searching, which cannot tell a live engine from a
dead constant.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

from backend.tests.conftest import TEST_DB_URL, new_test_engine


def _configured_url() -> str:
    return str(new_test_engine().url)


def _modules_with_an_engine():
    """Every test module exposing a module-level engine of its own."""
    import backend.tests as tests_pkg

    for info in pkgutil.iter_modules(tests_pkg.__path__):
        if not info.name.startswith("test_"):
            continue
        module = importlib.import_module(f"backend.tests.{info.name}")
        for attr in ("engine", "test_engine"):
            candidate = getattr(module, attr, None)
            if candidate is not None and hasattr(candidate, "url"):
                yield info.name, attr, candidate


@pytest.mark.parametrize("name,attr,engine", list(_modules_with_an_engine()))
def test_module_engines_are_the_suite_engine(name, attr, engine):
    assert str(engine.url) == _configured_url(), (
        f"{name}.{attr} points at {engine.url} while the suite runs on "
        f"{_configured_url()} (CONFIT_TEST_DB_URL={TEST_DB_URL!r}). A module that "
        "tests a different database than the suite reports makes every "
        "environment claim untrustworthy — use conftest.new_test_engine()."
    )


def test_the_audit_modules_specifically_are_covered():
    """Pin the two modules whose hardcoded engines produced the 17 failures.

    The parametrised test above would silently stop covering them if a refactor
    renamed the attribute, so the names are asserted directly as well.
    """
    from backend.tests import test_admin_atomic_audit, test_audit_hash_chain

    assert str(test_audit_hash_chain.engine.url) == _configured_url()
    assert str(test_admin_atomic_audit.engine.url) == _configured_url()


def test_the_guard_would_catch_a_hardcoded_sqlite_engine():
    """Negative control: prove the comparison can fail.

    Without this, a guard that accidentally compared a value with itself would
    pass forever. A genuinely different engine must be rejected by the same
    comparison the parametrised test performs.
    """
    from sqlalchemy import create_engine

    rogue = create_engine("sqlite:///./backend/data/definitely_not_the_suite.db")
    assert str(rogue.url) != _configured_url(), (
        "the guard compares two different engines, so it can detect a module "
        "that built its own"
    )
