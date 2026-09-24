"""Full-history audit-chain verifier — the deliberate, offline counterpart to
the dashboard's window-sampled integrity check.

Why this exists (re-audit finding): the admin integrity endpoint verifies a
bounded window sample (its response now says so explicitly in ``coverage``).
That is the right cost model for a dashboard, but it means NO endpoint ever
proves the WHOLE chain from genesis. This script is that proof, meant to be
run deliberately (incident response, after a key rotation, periodic ops
check) — never wired into a per-request path.

What it does, strictly READ-ONLY (a single SELECT stream, no writes):

1. Streams every ``audit_logs`` row in id order from genesis.
2. Recomputes every HMAC and every prev_hash link (``verify_chain`` with
   ``expected_prev=GENESIS_HASH`` — same code the endpoint uses, no fork).
3. Classifies unchained rows: legacy (id before the first chained row)
   vs chain_bypass_suspected (id after it).
4. Cross-checks the newest persisted ``audit_verification_runs`` head
   against the live table (tail-truncation check, same rule as 0021).

Exit codes: 0 = intact, 1 = violations found, 2 = could not run.

Usage::

    DATABASE_URL=postgresql://... AUDIT_HMAC_KEY=... \\
        python -m backend.scripts.verify_audit_chain [--batch-size 1000]

Retired key versions must be supplied as ``AUDIT_HMAC_KEY_V{n}`` or the
affected rows are reported as ``key_unavailable`` (fail closed, exit 1).
The key is read from the environment and never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def run(database_url: str, batch_size: int = 1000) -> Dict[str, Any]:
    from backend.app.core.audit_chain import GENESIS_HASH, verify_chain
    from backend.app.models.user import AuditLog, AuditVerificationRun

    engine = create_engine(database_url)
    session = sessionmaker(bind=engine)()
    try:
        total = session.query(AuditLog).count()
        breaks: List[Dict[str, Any]] = []
        legacy_rows = 0
        bypass_rows = 0
        chained = 0
        first_chained_id = None
        expected_prev = GENESIS_HASH
        head_hash = None
        head_row_id = None
        last_id = 0

        while True:
            batch = (
                session.query(AuditLog)
                .filter(AuditLog.id > last_id)
                .order_by(AuditLog.id.asc())
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            last_id = batch[-1].id
            for row in batch:
                if row.entry_hash is None:
                    if first_chained_id is None:
                        legacy_rows += 1
                    else:
                        bypass_rows += 1
                        breaks.append({
                            "row_id": row.id,
                            "issue": "chain_bypass_suspected",
                            "detail": "unchained row written after chaining began",
                        })
                    continue
                if first_chained_id is None:
                    first_chained_id = row.id
                result = verify_chain([row], expected_prev=expected_prev)
                breaks.extend(result["breaks"])
                chained += 1
                expected_prev = row.entry_hash
                head_hash, head_row_id = row.entry_hash, row.id
            session.expunge_all()

        truncation = {"verdict": "no_prior_run"}
        prior = (
            session.query(AuditVerificationRun)
            .order_by(AuditVerificationRun.id.desc())
            .first()
        )
        if prior is not None and prior.head_hash:
            alive = (
                session.query(AuditLog.id)
                .filter(AuditLog.id == prior.head_row_id,
                        AuditLog.entry_hash == prior.head_hash)
                .first()
            )
            truncation = {
                "verdict": "anchored" if alive else "tail_truncation_detected",
                "prior_head_row_id": prior.head_row_id,
            }
            if not alive:
                breaks.append({
                    "row_id": prior.head_row_id,
                    "issue": "tail_truncation_detected",
                    "detail": f"head recorded by verification run {prior.id} is gone",
                })

        return {
            "coverage": {"mode": "full_history", "from_genesis": True,
                         "total_rows": total, "full_history": True},
            "chained_rows": chained,
            "legacy_unchained_rows": legacy_rows,
            "bypass_suspected_rows": bypass_rows,
            "first_chained_row_id": first_chained_id,
            "head_row_id": head_row_id,
            "head_hash": head_hash,
            "truncation_check": truncation,
            "breaks": breaks,
            "intact": not breaks,
        }
    finally:
        session.close()
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--database-url", default=None,
                        help="defaults to settings/DATABASE_URL from the environment")
    args = parser.parse_args()

    url = args.database_url
    if not url:
        from backend.app.core.config import settings
        url = getattr(settings, "DATABASE_URL", None)
    if not url:
        print("ERROR: no database URL (set DATABASE_URL)", file=sys.stderr)
        return 2

    report = run(url, batch_size=args.batch_size)
    print(json.dumps(report, indent=2, default=str))
    if report["intact"]:
        print(f"\nINTACT: {report['chained_rows']} chained rows verified from genesis "
              f"({report['legacy_unchained_rows']} legacy unchained).", file=sys.stderr)
        return 0
    print(f"\nVIOLATIONS: {len(report['breaks'])} break(s) found — see report above.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
