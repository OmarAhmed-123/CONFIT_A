"""Release gate: can PRODUCTION actually run THIS commit?

Why this exists (2026-09-20 incident)
-------------------------------------
PR #117 was merged while the production database was still one migration behind.
Vercel deployed ``main`` seconds later, ``schema_gate.enforce_at_startup``
correctly refused to boot, and *every* endpoint — including ``/api/v1/health`` —
returned 500 until the previous deployment was re-promoted.

The safety detector behaved exactly as designed. The RELEASE PROCESS was wrong:
nothing compared the schema the merged code requires with the schema production
actually has *before* the merge was allowed to happen.

What this script is
-------------------
That comparison, as an executable gate. It runs in CI
(``.github/workflows/release-gate.yml``) and is a required status check on
``main``, so code that production cannot run is stopped before it is merged —
i.e. before Vercel can deploy it and take the API down.

It deliberately needs **no production credential**. The fact it compares is the
one the application itself checks at startup — the database's Alembic revision —
observed through the deployment's own ``/api/v1/health`` endpoint, which reads
that value straight from the database. There is no second code path and no
mocked comparison: if this gate is green, production's schema is the schema this
commit declares.

Relationship to the rest of the design
--------------------------------------
* ``backend/app/core/schema_gate.py`` is the runtime detector (unchanged, and it
  must stay strict: it is what turned an incompatibility into a safe refusal
  instead of silent corruption).
* ``backend/scripts/check_migration_chain_postgres.py`` proves the chain on a
  throwaway PostgreSQL in CI.
* This script is the missing *release-order* control: migration → provider →
  merge → deploy, enforced instead of merely documented.

Exit codes
----------
0  parity — production is on the revision this commit expects
1  mismatch — merging/deploying this commit would break production
2  indeterminate — production state could not be read (never treated as success)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import NoReturn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.core.schema_gate import expected_head_revision  # noqa: E402


def _indeterminate(message: str) -> "NoReturn":
    """Production state could not be determined. Never a pass, never a plain failure."""
    print(message, file=sys.stderr)
    raise SystemExit(2)


DEFAULT_HEALTH_URL = os.environ.get(
    "PRODUCTION_HEALTH_URL", "https://confit-a.vercel.app/api/v1/health"
)
TIMEOUT_SECONDS = float(os.environ.get("RELEASE_GATE_TIMEOUT", "20"))


def fetch_production_schema(url: str = DEFAULT_HEALTH_URL) -> dict:
    """The deployed app's own view of the database it is talking to."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # 500 while the gate refuses to boot
        _indeterminate(
            f"RELEASE GATE: INDETERMINATE — production {url} answered HTTP {exc.code}.\n"
            "  A production API that cannot serve /health cannot certify a deploy.\n"
            "  Fix or roll back production first; this gate never passes on a guess."
        )
    except (urllib.error.URLError, TimeoutError) as exc:
        _indeterminate(
            f"RELEASE GATE: INDETERMINATE — production {url} is unreachable ({exc}).\n"
            "  Production state must be determinable before a release can be approved."
        )

    if status != 200:
        _indeterminate(f"RELEASE GATE: INDETERMINATE — production returned HTTP {status}.")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        _indeterminate(f"RELEASE GATE: INDETERMINATE — /health did not return JSON: {exc}")

    schema = (payload.get("checks") or {}).get("schema")
    if not isinstance(schema, dict) or "database_revision" not in schema:
        _indeterminate("RELEASE GATE: INDETERMINATE — /health carried no checks.schema.database_revision.")
    return schema


def evaluate(expected: str | None, schema: dict) -> tuple[int, str]:
    """Pure comparison, so the three outcomes are testable without a network."""
    observed = schema.get("database_revision")
    if expected is None:
        return 2, "this commit declares no migration head (empty versions dir?) — cannot gate."
    if observed is None:
        return 2, "production reports no schema revision (unmanaged database) — cannot gate."
    if observed != expected:
        return 1, (
            f"production is at {observed} but this commit requires {expected}.\n"
            f"  Merging now would deploy code production cannot run: the startup schema gate\n"
            f"  would refuse to boot and the API would return 500 (this is the 2026-09-20 incident).\n"
            f"  Order of operations: apply the migration FIRST, then merge:\n"
            f"    ALEMBIC_DATABASE_URL='<owner DSN>' PYTHONPATH=. alembic -c backend/alembic.ini upgrade head\n"
            f"    ALEMBIC_DATABASE_URL='<owner DSN>' PYTHONPATH=. alembic -c backend/alembic.ini current\n"
            f"  Then re-run this gate: it passes on its own once production reports {expected}."
        )
    return 0, f"production reports {observed}, identical to this commit's head {expected}."


def main() -> int:
    expected = expected_head_revision()
    schema = fetch_production_schema()
    code, detail = evaluate(expected, schema)
    label = {0: "PASS", 1: "BLOCK", 2: "INDETERMINATE"}[code]
    print(f"RELEASE GATE: {label}")
    print(f"  commit requires : {expected}")
    print(f"  production has  : {schema.get('database_revision')}")
    print(f"  production health verdict: {schema.get('verdict')} (acceptable={schema.get('acceptable')})")
    print(f"  {detail}")
    return code


if __name__ == "__main__":  # pragma: no cover - CI entrypoint
    raise SystemExit(main())
