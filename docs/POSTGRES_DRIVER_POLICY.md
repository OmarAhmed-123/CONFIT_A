# PostgreSQL driver policy

**Status: decided and enforced in code (2026-09-24). Owner: backend.**
Created because SQLAlchemy 2.1.0 — published 2026-09-24T20:36Z — silently changed
which DBAPI a bare `postgresql://` URL resolves to, and this repository installs a
different one. The break was found by an independent re-verification, not by CI,
because CI installed the new SQLAlchemy mid-day while the build was already running.

## The policy

| Environment | Driver | Why |
|---|---|---|
| Local dev / Docker / CI (`backend/requirements.txt`) | **psycopg2** (`psycopg2-binary`) | The canonical backend stack; C-accelerated and battle-tested. |
| Vercel serverless (repo-root `requirements.txt`) | **pg8000** | Pure Python — Vercel's build cannot compile C extensions such as psycopg2. This is why the two requirement files declare different drivers on purpose. |
| Anything else (future) | **psycopg 3** | Only if a future environment installs it *and* neither of the above is present. |

Preference order is **psycopg2 → pg8000 → psycopg 3**, implemented once in
`backend/app/core/postgres_url.py::select_postgres_driver`, injectable so the
decision is testable without installing or uninstalling packages.

## The rule

**The URL always names the driver.** `normalise_postgres_url()` returns
`postgresql+<driver>://…`, never a bare `postgresql://`. A bare scheme means
"whatever the installed SQLAlchemy prefers", which is a property of the SQLAlchemy
version, not of this code — the exact assumption that broke on 2026-09-24.

An operator-supplied driver (`postgresql+psycopg2://…`) is respected and never
double-prefixed. `postgres://` is upgraded to `postgresql://`. With pg8000 the
libpq-only `sslmode` parameter is stripped and translated into an SSL context
(`sslmode=disable` → no TLS; anything else → verified TLS).

## Single source of truth

`backend/app/core/postgres_url.py` is side-effect free (stdlib only), so every
engine construction in the repository can consult the production rule without
importing a module that opens a connection:

* `backend/app/core/database.py` — the application engine (re-exports the rule).
* `backend/app/core/schema_gate.py` — the schema gate.
* `backend/alembic/env.py` — migrations. Alembic builds its own engine from
  `sqlalchemy.url`; if it did not follow this rule, `alembic upgrade` and the API
  could disagree about the driver.
* `backend/scripts/check_migration_chain_postgres.py`, `validate_database.py`,
  `verify_audit_chain.py` — operator tools.
* `backend/tests/conftest.py::new_test_engine` and the PostgreSQL-gated suites.

Duplicating the rule is how it drifted in the first place: the previous version
lived inside `database.py` (which builds an engine at import time), so scripts and
tests either imported a module with connection side effects or re-implemented the
logic.

## Supported SQLAlchemy range and upgrade policy

* **Supported:** `sqlalchemy>=2.0.35,<2.2` — see `backend/requirements.txt` and
  `requirements.txt`.
* The upper bound is `2.2`, not `2.1`, because the *known* breaking behaviour
  (default DBAPI change) is handled explicitly in code and therefore also works on
  2.1. The bound exists to make the **next** silent default change arrive as a
  deliberate dependency decision rather than as a production incident.
* Patches within a minor (`2.0.x`, `2.1.x`) are free upgrades.
* Bumping the bound requires: running the PostgreSQL-gated suite
  (`CONFIT_TEST_PG_URL`, `CONFIT_CONCURRENCY_PG_URL`, `CONFIT_PORTAL_TEST_PG_URL`),
  the migration chain gate, and `backend/tests/test_postgres_driver_selection.py`,
  then updating this document.

## The regression test that protects this

`backend/tests/test_postgres_driver_selection.py` asserts the *contract* — "the URL
names the driver we selected" — not "SQLAlchemy's default is psycopg2". That
distinction matters: the second statement was true until it wasn't.

* Positive: for each driver, the returned URL names it.
* Negative: a bare `postgresql://` scheme is never returned, for any availability
  combination.
* Integration: `test_sqlalchemy_resolves_the_driver_we_selected` builds a real
  engine and asserts the dialect SQLAlchemy picked equals the driver this module
  chose — this is the test that fails on day one under SQLAlchemy 2.1 if the
  explicit-driver step is removed.
* Mutation control: removing the step produced 7 failures + 11 errors
  (`CONFIT_evidence/44-mutation-controls-postgres-driver.txt`).

## Environment matrix (explicit, so no environment silently differs)

| Environment | Driver available | Rule resolution |
|---|---|---|
| CI `backend` + `postgres migration chain + schema gate` | psycopg2 (`backend/requirements.txt`) | `postgresql+psycopg2://` |
| CI Vercel-manifest job (`requirements.txt`) | pg8000 | `postgresql+pg8000://` |
| Local dev (this workspace) | psycopg2 | `postgresql+psycopg2://` |
| Vercel production | pg8000 | `postgresql+pg8000://` |

Production was already naming pg8000 in its DSN, so this change is not what fixes
production; it removes the latent failure in every environment that relies on
"whatever SQLAlchemy prefers".
