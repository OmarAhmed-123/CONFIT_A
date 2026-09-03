#!/usr/bin/env python3
"""Mutation gates M1–M13: prove the test-suite KILLS each production defect.

For every mutation the script
  1. applies a textual mutation to the PRODUCTION source (never to a test),
  2. runs the named regression tests,
  3. records KILLED (tests fail under the mutation) or SURVIVED (tests still pass),
  4. restores the original file byte-for-byte (also on Ctrl-C / crash).

It exits non-zero if any mutation survives, so it can run in CI. Run from the
repository root:

    CONFIT_VTON_DISABLE_REMBG=1 PYTHONPATH=. python3 backend/scripts/run_mutation_gates.py [--only M3,M7] [--json out.json]

The mutations are the reverting edits of the fixes made in the production
truth remediation (finance, attribution, VTON masking/polarity, secrets,
schema gate, payments, auth).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.chdir(REPO)


@dataclass
class Mutation:
    mid: str
    title: str
    path: str
    old: str
    new: str
    tests: list[str]
    extra_env: dict = field(default_factory=dict)
    # some fixes are expressed twice in the same file (e.g. four controller
    # branches) — replace every occurrence by default
    count: int | None = None


MUTATIONS: list[Mutation] = [
    Mutation(
        "M1", "Money: quantize with ROUND_HALF_EVEN instead of HALF_UP (0.125 -> 0.12)",
        "backend/app/core/money.py",
        "return dec.quantize(TWOPLACES, rounding=ROUND_HALF_UP)",
        "from decimal import ROUND_HALF_EVEN as _RHE\n        return dec.quantize(TWOPLACES, rounding=_RHE)",
        ["backend/tests/test_money_rate_and_range_regression.py", "backend/tests/test_money_api_boundary.py"],
    ),
    Mutation(
        "M2", "Money: rate quantized to 2 dp (7.5% -> 8%)",
        "backend/app/core/money.py",
        "    if value is None:\n        return Decimal(\"0\")\n    return _finite_decimal(value, field)",
        "    if value is None:\n        return Decimal(\"0\")\n    return _finite_decimal(value, field).quantize(TWOPLACES, rounding=ROUND_HALF_UP)",
        ["backend/tests/test_money_rate_and_range_regression.py", "backend/tests/test_group5_commerce.py"],
    ),
    Mutation(
        "M3", "Money: NaN/Infinity coerced to 0.00 instead of rejected",
        "backend/app/core/money.py",
        "    if not dec.is_finite():\n        raise MoneyValueError(f\"{field}: non-finite value {dec} rejected\")\n    return dec",
        "    if not dec.is_finite():\n        return Decimal(\"0.00\")\n    return dec",
        ["backend/tests/test_money_api_boundary.py", "backend/tests/test_money_rate_and_range_regression.py"],
    ),
    Mutation(
        "M4", "Money: NUMERIC(12,2) upper bound widened (10,000,000,000.00 accepted)",
        "backend/app/core/money.py",
        "MAX_MONEY = Decimal(\"9999999999.99\")",
        "MAX_MONEY = Decimal(\"99999999999.99\")",
        ["backend/tests/test_money_api_boundary.py", "backend/tests/test_money_rate_and_range_regression.py"],
    ),
    Mutation(
        "M5", "Money: sub-cent user input silently rounded (0.005 -> 0.01)",
        "backend/app/core/money.py",
        "        if raw != dec:\n            raise MoneyValueError(",
        "        if False:\n            raise MoneyValueError(",
        ["backend/tests/test_money_api_boundary.py"],
    ),
    Mutation(
        "M6", "Attribution: purchase event written WITHOUT order_item_id (order-grain fallback)",
        "backend/app/repositories/brand_repository.py",
        "order_item_id=order_item_id,",
        "order_item_id=None,",
        ["backend/tests/test_attribution_ledger_conservation.py", "backend/tests/test_attribution_behavioral_e2e.py"],
    ),
    Mutation(
        "M7", "Attribution: refunded/cancelled orders still counted as eligible revenue",
        "backend/app/repositories/brand_repository.py",
        "INELIGIBLE_ORDER_STATUSES = (\"cancelled\", \"refunded\", \"failed\")",
        "INELIGIBLE_ORDER_STATUSES = ()",
        ["backend/tests/test_attribution_ledger_conservation.py"],
    ),
    Mutation(
        "M8", "VTON: mask polarity inverted (garment region BLACK = preserved)",
        "services/vton-worker/pipeline/segmentation.py",
        "        result = Image.fromarray(intersected, mode=\"L\")",
        "        result = Image.fromarray((255 - intersected).astype(np.uint8), mode=\"L\")",
        ["backend/tests/test_vton_single_production_path.py", "backend/tests/test_vton_mask_quality.py"],
    ),
    Mutation(
        "M9", "VTON: rectangle masking substituted in modal_app (second implementation)",
        "services/vton-worker/modal_app.py",
        "    mask = AgnosticMaskGenerator.create_agnostic_mask(person, slot)",
        "    from PIL import ImageDraw\n    mask = Image.new(\"L\", person.size, 0)\n    d = ImageDraw.Draw(mask)\n    d.rectangle((0, 0, person.width, person.height), fill=255)",
        ["backend/tests/test_vton_single_production_path.py"],
    ),
    Mutation(
        "M10", "VTON: worker echo (input image returned unchanged) accepted as success",
        "backend/app/services/tryon_service.py",
        "                if rendered == person_image:\n                    logger.error(\"vton_output_invalid_echo\", job_id=job_id, latency_ms=latency_ms)\n                    raise RuntimeError(\"VTON_OUTPUT_INVALID: Worker returned input unchanged (echo)\")",
        "                if False:\n                    raise RuntimeError(\"VTON_OUTPUT_INVALID: Worker returned input unchanged (echo)\")",
        ["backend/tests/test_vton_single_production_path.py"],
    ),
    Mutation(
        "M11", "Secrets: publicly known SECRET_KEY accepted in production",
        "backend/app/core/config.py",
        "MIN_SECRET_LENGTH = 32",
        "MIN_SECRET_LENGTH = 0\nPUBLICLY_KNOWN_SECRET_VALUES = frozenset()",
        ["backend/tests/test_production_parity.py"],
    ),
    Mutation(
        "M12", "Schema gate: drift verdict downgraded to 'ok' (0007 DB accepted by 0014 code)",
        "backend/app/core/schema_gate.py",
        "    elif findings:\n        verdict = \"drift\"",
        "    elif findings:\n        verdict = \"ok\"",
        ["backend/tests/test_schema_drift_gate.py"],
    ),
    Mutation(
        "M13", "Payments: PAYMENTS_LIVE=true returns fabricated 'authorized' instead of failing closed",
        "backend/app/providers/payment/orchestrator.py",
        "                    \"status\": \"failed\",\n                    \"payment_method\": method_id,",
        "                    \"status\": \"authorized\",\n                    \"payment_method\": method_id,",
        ["backend/tests/test_payment_live_mode_fail_closed.py"],
    ),
    Mutation(
        "M14", "Auth: verify_password plaintext-equality fallback restored",
        "backend/app/core/security.py",
        "    except (ValueError, TypeError):\n        # not a bcrypt hash (or corrupt) -> authentication fails closed\n        return False",
        "    except (ValueError, TypeError):\n        return plain_password == hashed_password",
        ["backend/tests/test_silent_fallback_regressions.py"],
    ),
]


def run_tests(tests: list[str], env: dict) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--tb=line", *tests]
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1500)
    tail = "\n".join((p.stdout or "").strip().splitlines()[-3:])
    return p.returncode, tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated mutation ids")
    ap.add_argument("--json", default="", help="write results to this path")
    ap.add_argument("--skip-baseline", action="store_true")
    args = ap.parse_args()
    wanted = {m.strip().upper() for m in args.only.split(",") if m.strip()}
    env = {**os.environ, "PYTHONPATH": ".", "CONFIT_VTON_DISABLE_REMBG": os.environ.get("CONFIT_VTON_DISABLE_REMBG", "1")}

    results = []
    snapshots = {m.path: (REPO / m.path).read_bytes() for m in MUTATIONS if not wanted or m.mid in wanted}
    all_tests = sorted({t for m in MUTATIONS if not wanted or m.mid in wanted for t in m.tests})
    if not args.skip_baseline:
        print(f"[baseline] running {len(all_tests)} test files unmutated ...", flush=True)
        rc, tail = run_tests(all_tests, env)
        print(f"[baseline] rc={rc} {tail.splitlines()[-1] if tail else ''}")
        if rc != 0:
            print("BASELINE FAILS — fix the suite before measuring mutations", file=sys.stderr)
            return 2

    for m in MUTATIONS:
        if wanted and m.mid not in wanted:
            continue
        path = REPO / m.path
        original = path.read_bytes()
        text = original.decode("utf-8")
        occurrences = text.count(m.old)
        if occurrences == 0:
            results.append({"id": m.mid, "title": m.title, "status": "NOT_APPLICABLE", "reason": "anchor text not found"})
            print(f"[{m.mid}] NOT_APPLICABLE — anchor not found in {m.path}")
            continue
        mutated = text.replace(m.old, m.new, m.count) if m.count else text.replace(m.old, m.new)
        t0 = time.time()
        try:
            path.write_text(mutated, encoding="utf-8")
            rc, tail = run_tests(m.tests, env)
        finally:
            path.write_bytes(original)
            assert path.read_bytes() == original
        status = "KILLED" if rc != 0 else "SURVIVED"
        results.append({"id": m.mid, "title": m.title, "file": m.path, "tests": m.tests,
                        "status": status, "pytest_rc": rc, "tail": tail, "seconds": round(time.time() - t0, 1)})
        print(f"[{m.mid}] {status:<9} {m.title}  ({round(time.time() - t0, 1)}s)  -> {tail.splitlines()[-1] if tail else ''}", flush=True)

    survivors = [r for r in results if r["status"] == "SURVIVED"]
    na = [r for r in results if r["status"] == "NOT_APPLICABLE"]
    print(f"\nMUTATION GATES: {len(results) - len(survivors) - len(na)} killed, {len(survivors)} survived, {len(na)} not applicable")
    if args.json:
        Path(args.json).write_text(json.dumps({"results": results, "git_head": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()}, indent=2))
    # every mutated file must be byte-identical to what it was before the run
    # (restoration is asserted per mutation; this is the belt to that brace)
    changed = [p for p, before in snapshots.items() if (REPO / p).read_bytes() != before]
    if changed:
        print("ERROR: production files left modified: " + ", ".join(changed), file=sys.stderr)
        return 3
    return 1 if survivors or na else 0


if __name__ == "__main__":
    sys.exit(main())
