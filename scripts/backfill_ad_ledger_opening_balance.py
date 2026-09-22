#!/usr/bin/env python3
"""Reconcile pre-ledger placement spend by writing an explicit opening balance.

THE PROBLEM THIS SOLVES
-----------------------
Migration 0019 introduced ``ad_ledger_entries`` as the journal of record for ad
billing and demoted ``SponsoredPlacement.spent_today`` to a cached projection of
it. Placements that were charged BEFORE the ledger existed therefore carry a
counter with no journal behind it. The integrity auditor correctly reports this
as ``ad_billing_reconciliation`` FAIL:

    placement_id=1  spent_today=32.50  ledger_total=0  -> counter does not match ledger

That finding is real and must not be silenced. There are exactly three honest
ways to resolve it, and only one of them is defensible:

  1. Zero the counter. REJECTED — it destroys the record of money the platform
     believes was charged, and makes the discrepancy disappear rather than be
     explained. Never quietly delete a financial number you cannot justify.
  2. Ignore it / suppress the check. REJECTED — the reconciliation control
     exists precisely to catch counters that no journal supports. Muting it is
     how the original "counters as billing" problem happened.
  3. Record what is actually true: at ledger cutover, this placement had an
     inherited balance of 32.50 whose per-event history predates the journal
     and cannot be reconstructed. ADOPTED.

So this writes ONE ``entry_type='adjustment'`` row per affected placement,
carrying the inherited amount, with a ``reason`` that states plainly that it is
an opening balance and that no per-event detail exists for it. The counter and
the ledger then agree, the auditor passes, and — crucially — the reason why they
agree is written down in the ledger itself rather than lost in a shell history.
This is the standard accounting treatment for opening balances when a new
ledger is adopted mid-life.

PROPERTIES
----------
* IDEMPOTENT. The entry uses a deterministic ``event_key``
  (``opening-balance:<placement_id>:<spend_date>``) and ``event_key`` is UNIQUE,
  so re-running this script cannot double-credit a placement. It also skips any
  placement that already reconciles.
* APPEND-ONLY. It never updates or deletes an existing ledger row, and never
  modifies ``spent_today``. It only adds the missing explanation.
* DRY-RUN BY DEFAULT. It prints what it would write and changes nothing unless
  ``--apply`` is passed.
* HONEST ABOUT SCOPE. It only ever touches placements whose counter EXCEEDS the
  ledger. A ledger that exceeds the counter is a different and more serious
  condition (the journal recorded a charge the projection lost) and is reported
  as an error for a human, never auto-corrected.

Usage:
    DATABASE_URL=... python3 scripts/backfill_ad_ledger_opening_balance.py
    DATABASE_URL=... python3 scripts/backfill_ad_ledger_opening_balance.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402

# Must fit ad_ledger_entries.reason -> VARCHAR(200). Kept deliberately terse but
# self-explanatory: whoever reads this row later must not need this script.
OPENING_BALANCE_REASON = (
    "Opening balance at ad-ledger cutover (migration 0019): spend predates the "
    "journal, so no per-event history exists for it. Recorded so counter and "
    "ledger reconcile and the balance stays visible."
)
assert len(OPENING_BALANCE_REASON) <= 200, (
    f"reason is {len(OPENING_BALANCE_REASON)} chars; ad_ledger_entries.reason is VARCHAR(200)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--apply", action="store_true",
                    help="Actually write the adjustment rows (default: dry run).")
    args = ap.parse_args()

    if not args.database_url:
        print("ERROR: no database URL (pass --database-url or set DATABASE_URL).",
              file=sys.stderr)
        return 2

    engine = create_engine(args.database_url)
    written = problems = 0

    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.brand_id, p.spend_date, p.spent_today,
                   COALESCE((SELECT SUM(l.amount) FROM ad_ledger_entries l
                              WHERE l.placement_id = p.id
                                AND l.spend_date   = p.spend_date
                                AND l.billable IS TRUE), 0) AS ledger_total
              FROM sponsored_placements p
             WHERE p.spend_date IS NOT NULL
             ORDER BY p.id
        """)).fetchall()

        for pid, brand_id, spend_date, spent_today, ledger_total in rows:
            counter = Decimal(str(spent_today or 0))
            ledger = Decimal(str(ledger_total or 0))
            if counter == ledger:
                continue

            if ledger > counter:
                # The journal knows about money the projection does not. Never
                # paper over this: it means the cached counter lost a charge.
                print(f"  [ERROR] placement {pid}: ledger {ledger} EXCEEDS counter "
                      f"{counter} by {ledger - counter}. This is a lost projection "
                      f"update, not an opening balance — not auto-correcting; "
                      f"a human must investigate.", file=sys.stderr)
                problems += 1
                continue

            delta = counter - ledger
            key = f"opening-balance:{pid}:{spend_date.isoformat()}"
            print(f"  placement {pid} (brand {brand_id}, {spend_date}): "
                  f"counter={counter} ledger={ledger} -> opening balance {delta}")

            if args.apply:
                conn.execute(text("""
                    INSERT INTO ad_ledger_entries
                        (placement_id, brand_id, entry_type, event_key, amount,
                         bid_at_event, spend_date, billable, reason, created_at)
                    VALUES
                        (:pid, :bid, 'adjustment', :key, :amt,
                         NULL, :sdate, TRUE, :reason, NOW())
                    ON CONFLICT (event_key) DO NOTHING
                """), {"pid": pid, "bid": brand_id, "key": key, "amt": delta,
                       "sdate": spend_date, "reason": OPENING_BALANCE_REASON})
                written += 1

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to record these.")
    else:
        print(f"\nWrote {written} opening-balance adjustment(s).")
    if problems:
        print(f"{problems} placement(s) need human investigation (ledger > counter).",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
