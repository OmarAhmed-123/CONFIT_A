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
0  safe — production is on the revision this commit expects, or AHEAD of it
   (a newer schema still satisfies code that asks only for its own head; the
   runtime required-object check is what actually proves that per request)
1  blocked — production is BEHIND this commit: merging would deploy code the
   database cannot serve (the 2026-09-20 incident)
2  indeterminate — production state could not be read, or the two revisions
   cannot be ordered (never treated as success)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import NoReturn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.core.schema_gate import expected_head_revision, revision_ordinal  # noqa: E402


def _indeterminate(message: str) -> "NoReturn":
    """Production state could not be determined. Never a pass, never a plain failure."""
    print(message, file=sys.stderr)
    raise SystemExit(2)


DEFAULT_HEALTH_URL = os.environ.get(
    "PRODUCTION_HEALTH_URL", "https://confit-a.vercel.app/api/v1/health"
)
TIMEOUT_SECONDS = float(os.environ.get("RELEASE_GATE_TIMEOUT", "45"))
ATTEMPTS = int(os.environ.get("RELEASE_GATE_ATTEMPTS", "3"))


def fetch_production_schema(url: str = DEFAULT_HEALTH_URL) -> dict:
    """The deployed app's own view of the database it is talking to.

    Retries on timeout/connection errors before giving up.

    Production runs on Vercel serverless. A cold invocation has to boot the
    runtime and open a fresh pooled connection to Neon, which was measured at
    ~26s on 2026-09-22 — against the 20s single-shot timeout this function used
    to apply. So the gate reported "production is unreachable" and failed the
    release for a healthy deployment that was merely asleep. An idle app is not
    an unreachable one, and a gate that cries wolf on a cold start teaches
    people to bypass it.

    The first request pays the cold start and warms the instance, so a retry
    answers in well under a second. INDETERMINATE is still the outcome when
    production genuinely cannot be reached — this widens the window, it does
    not soften the verdict, and it never infers a revision it did not read.
    """
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    last_error: Exception | None = None

    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                status = response.status
                body = response.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as exc:  # 500 while the gate refuses to boot
            _indeterminate(
                f"RELEASE GATE: INDETERMINATE — production {url} answered HTTP {exc.code}.\n"
                "  A production API that cannot serve /health cannot certify a deploy.\n"
                "  Fix or roll back production first; this gate never passes on a guess."
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < ATTEMPTS:
                delay = 2 ** (attempt - 1)
                print(
                    f"  /health attempt {attempt}/{ATTEMPTS} failed ({exc}); "
                    f"retrying in {delay}s (serverless cold start can exceed "
                    f"{TIMEOUT_SECONDS:.0f}s).",
                    file=sys.stderr,
                )
                time.sleep(delay)
    else:
        _indeterminate(
            f"RELEASE GATE: INDETERMINATE — production {url} is unreachable after "
            f"{ATTEMPTS} attempts ({last_error}).\n"
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


def _ordinal(rev: str) -> int | None:
    """The ordering signal for a revision id, or None when there is none.

    `revision_ordinal` answers from the migration chain in this tree, so it
    cannot order a revision that belongs to a branch that has not merged yet —
    which is exactly the case that matters here (production carries a migration
    this commit has never seen). The revision ids in this repository are
    zero-padded and numerically ordered (`0017_audit_before_after_request_id`),
    so the leading number is the fallback ordering signal.

    Returns None rather than guessing when neither source yields a position:
    the caller then refuses to claim a direction it did not establish.
    """
    chain_ord = revision_ordinal(rev)
    if chain_ord is not None:
        return chain_ord
    m = re.match(r"^(\d+)", rev or "")
    return int(m.group(1)) if m else None


def evaluate(expected: str | None, schema: dict) -> tuple[int, str]:
    """Pure comparison, so the three outcomes are testable without a network."""
    observed = schema.get("database_revision")
    if expected is None:
        return 2, "this commit declares no migration head (empty versions dir?) — cannot gate."
    if observed is None:
        return 2, "production reports no schema revision (unmanaged database) — cannot gate."
    if observed == expected:
        return 0, f"production reports {observed}, identical to this commit's head {expected}."

    # Production and this commit disagree. Direction decides everything, and
    # until 2026-09-21 this function did not look at direction at all — it
    # blocked on any difference. That conflated two opposite situations:
    #
    #   production BEHIND the code — merging really would deploy code the
    #       database cannot serve. This is the 2026-09-20 incident. BLOCK.
    #   production AHEAD of the code — the database already carries a newer
    #       migration. Code that needs only 0017 runs fine on a 0018 schema,
    #       which is precisely what `schema_gate` verifies with its
    #       required-object check. Blocking here does not protect anything; it
    #       just means the first branch to ship a migration freezes every
    #       other merge to main until it lands.
    #
    # On 2026-09-21 a preview deployment applied 0018_outfit_share_lifecycle
    # while main still expected 0017, and this gate blocked the repository.
    exp_ord = _ordinal(expected)
    obs_ord = _ordinal(observed)

    if exp_ord is None or obs_ord is None:
        return 2, (
            f"production is at {observed} and this commit requires {expected}, but neither\n"
            "  revision can be placed in an order (not in this tree's chain and no numeric\n"
            "  prefix). This gate never passes on a guess."
        )

    if obs_ord < exp_ord:
        return 1, (
            f"production is at {observed} but this commit requires {expected} "
            f"({exp_ord - obs_ord} migration(s) not applied).\n"
            f"  Merging now would deploy code production cannot run: the startup schema gate\n"
            f"  would refuse to boot and the API would return 500 (this is the 2026-09-20 incident).\n"
            f"  Order of operations: apply the migration FIRST, then merge:\n"
            f"    ALEMBIC_DATABASE_URL='<owner DSN>' PYTHONPATH=. alembic -c backend/alembic.ini upgrade head\n"
            f"    ALEMBIC_DATABASE_URL='<owner DSN>' PYTHONPATH=. alembic -c backend/alembic.ini current\n"
            f"  Then re-run this gate: it passes on its own once production reports {expected}."
        )

    return 0, (
        f"production is at {observed}, which is AHEAD of this commit's head {expected}.\n"
        "  Safe to merge: this code asks for a schema production already has and more.\n"
        "  The runtime gate independently refuses to serve if any required table or\n"
        "  column is actually missing (verdict `drift`), so this is not an unchecked pass.\n"
        "  Still worth resolving — and the real fix is per-environment databases: a\n"
        "  preview deployment should never migrate the database production serves."
    )


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
