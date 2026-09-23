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
    # Which test runner proves this mutation is killed. Added 2026-09-23: the
    # harness only knew how to run pytest, so a gate aimed at a FRONTEND source
    # file would have been executed as `pytest <file.tsx>` — it would have
    # "failed" for being the wrong kind of path, and the gate would have
    # reported KILLED for a reason that has nothing to do with the defect. A
    # gate that cannot fail for the right reason protects nothing, so the
    # runner is now part of the mutation's definition.
    runner: str = "pytest"


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
        "M7", "Revenue policy: refunded/cancelled/failed orders counted as eligible revenue",
        "backend/app/core/revenue_policy.py",
        "NON_REVENUE_ORDER_STATUSES: FrozenSet[str] = frozenset({\"cancelled\", \"failed\", \"refunded\"})",
        "NON_REVENUE_ORDER_STATUSES: FrozenSet[str] = frozenset()",
        ["backend/tests/test_revenue_policy.py", "backend/tests/test_attribution_ledger_conservation.py"],
    ),
    Mutation(
        "M15", "Return-rate denominator drops refunded orders (survivorship bias returns)",
        "backend/app/core/revenue_policy.py",
        "RETURN_DENOMINATOR_EXCLUDED_STATUSES: FrozenSet[str] = frozenset({\"cancelled\", \"failed\"})",
        "RETURN_DENOMINATOR_EXCLUDED_STATUSES: FrozenSet[str] = frozenset({\"cancelled\", \"failed\", \"refunded\"})",
        ["backend/tests/test_revenue_policy.py"],
    ),
    Mutation(
        "M16", "Revenue policy: an unclassified order status silently defaults to revenue",
        "backend/app/core/revenue_policy.py",
        "    raise ValueError(\n        f\"Order status {status!r} is not classified in revenue_policy. \"",
        "    return _BUCKET_REVENUE\n    raise ValueError(\n        f\"Order status {status!r} is not classified in revenue_policy. \"",
        ["backend/tests/test_revenue_policy.py"],
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
    Mutation(
        "M17",
        "VTON: catalog capability flags derive GPU readiness from configuration "
        "presence instead of the live probe (2026-09-22 consumer-role defect)",
        "backend/app/services/capability_service.py",
        '        "vton_gpu_ready": engine_state == ENGINE_STATE_AVAILABLE,',
        '        "vton_gpu_ready": bool(settings.VTON_WORKER_URL),',
        ["backend/tests/test_capability_single_source.py"],
    ),
    Mutation(
        "M18",
        "VTON: try-on capabilities re-derive engine_state locally instead of "
        "using the shared classifier in vton_worker_observability",
        "backend/app/services/tryon_service.py",
        "        engine_state = vwo.engine_state_from_probe(probe, configured=bool(worker_url))",
        "        engine_state = \"available\" if worker_url else \"misconfigured\"",
        ["backend/tests/test_capability_single_source.py"],
    ),
    Mutation(
        "M19",
        "AI stylist: report `ready` from provider-key presence instead of the "
        "measured quarantine signal (configuration-as-measurement, 2026-09-22)",
        "backend/app/services/capability_service.py",
        '        "ai_stylist", STATE_NOT_PROBED, CRITICALITY_SUPPORTING,',
        '        "ai_stylist", STATE_READY, CRITICALITY_SUPPORTING,',
        ["backend/tests/test_health_readiness_contract.py"],
    ),
    Mutation(
        "M20",
        "AI stylist: read the deprecated GROK_API_KEY field instead of the "
        "canonical groq_api_key property (hides the documented GROQ_API_KEY)",
        # RETARGETED 2026-09-23. This gate went NOT_APPLICABLE after
        # `_ai_provider_keys()` was reduced to a delegate of
        # `ai_readiness.configured_provider_names()`: the anchor it mutated no
        # longer existed, so the gate had silently stopped protecting anything.
        # The runner reports NOT_APPLICABLE rather than passing it quietly, which
        # is how it was caught. The defect can still return — at the new single
        # authority — so the mutation moved there.
        "backend/app/services/ai_readiness.py",
        '    groq_key = getattr(settings, "groq_api_key", None)',
        '    groq_key = getattr(settings, "GROK_API_KEY", None)',
        ["backend/tests/test_health_readiness_contract.py::test_ai_provider_keys_honours_the_documented_groq_variable"],
    ),
    Mutation(
        "M21",
        "AI stylist: drop quarantine entries whose `configured` flag is false, "
        "discarding the only real measurement (and hiding a total AI outage)",
        "backend/app/services/capability_service.py",
        "            if float(entry.get(\"cooling_for_seconds\") or 0) > 0:\n                quarantined[name] = entry",
        "            if float(entry.get(\"cooling_for_seconds\") or 0) > 0 and entry.get(\"configured\"):\n                quarantined[name] = entry",
        ["backend/tests/test_health_readiness_contract.py"],
    ),
    Mutation(
        "M22",
        "Checkout: replay an idempotency key globally instead of checking that the "
        "matching order belongs to the caller (cross-account order disclosure, "
        "2026-09-22)",
        "backend/app/services/commerce_service.py",
        "            if existing and self._is_caller_own_idempotent_order(\n"
        "                existing, user_id, session_token, guest_email\n"
        "            ):\n"
        "                return self.get_order(existing.order_number)",
        "            if existing:\n"
        "                return self.get_order(existing.order_number)",
        ["backend/tests/test_group5_commerce.py"],
    ),
    Mutation(
        "M23",
        "Checkout: the IntegrityError (lost-race) branch replays a foreign "
        "idempotency key without the ownership check",
        "backend/app/services/commerce_service.py",
        "            if idempotency_key:\n"
        "                existing = self.commerce_repo.get_order_by_idempotency(idempotency_key)\n"
        "                if existing and self._is_caller_own_idempotent_order(\n"
        "                    existing, user_id, session_token, guest_email\n"
        "                ):\n"
        "                    return self.get_order(existing.order_number)\n"
        "                if existing:\n"
        "                    raise IdempotencyKeyConflictError()",
        "            if idempotency_key:\n"
        "                existing = self.commerce_repo.get_order_by_idempotency(idempotency_key)\n"
        "                if existing:\n"
        "                    return self.get_order(existing.order_number)",
        ["backend/tests/test_group5_commerce.py"],
    ),
    Mutation(
        "M24",
        "Payments: publish a literal `is_live=True` instead of the measured "
        "per-method state (production claimed live Tabby instalment financing "
        "with no key, no adapter and payments_mode=demo)",
        "backend/app/providers/payment/orchestrator.py",
        "                **option.model_dump(), is_live=payment_method_is_live(option.id)",
        "                **option.model_dump(), is_live=True",
        ["backend/tests/test_capabilities_endpoint.py"],
    ),
    Mutation(
        "M31",
        "Payment catalogue: reinstate the optimistic default on the shared "
        "model (`PaymentMethodOption.is_live: bool = True`), so the catalogue "
        "is once again an internal source of truth able to publish a liveness "
        "claim the deployment cannot back — the latent trap #177 left behind",
        "backend/app/providers/payment/schemas.py",
        "    provider_name: str\n    requires_redirect: bool = False",
        "    provider_name: str\n    is_live: bool = True\n    requires_redirect: bool = False",
        ["backend/tests/test_capabilities_endpoint.py::test_catalog_cannot_carry_a_liveness_claim_and_stamping_never_mutates_it"],
    ),
    Mutation(
        "M33",
        "Capability flags: publish `payments_live` from the PAYMENTS_LIVE switch "
        "again instead of the measured PSP rail, so one environment variable "
        "makes the consumer trust footer claim a live payment service provider "
        "(and the COD-only disclosure disappears)",
        "backend/app/services/capability_service.py",
        '        "payments_live": bool(psp_methods_live),',
        '        "payments_live": bool(settings.PAYMENTS_LIVE),',
        ["backend/tests/test_capabilities_endpoint.py::test_payments_live_is_measured_not_the_environment_variable"],
    ),
    Mutation(
        "M32",
        "Availability model: give the measured field a default (`is_live: bool "
        "= True`), so a forgotten stamp publishes a claim instead of raising",
        "backend/app/providers/payment/schemas.py",
        "    is_live: bool\n\n\nclass MarketPaymentCapabilitiesResponse",
        "    is_live: bool = True\n\n\nclass MarketPaymentCapabilitiesResponse",
        ["backend/tests/test_capabilities_endpoint.py::test_a_forgotten_liveness_stamp_is_an_error_not_a_false_claim"],
    ),
    Mutation(
        "M25",
        "BNPL: treat PAYMENTS_LIVE + a provider key as an instalment offer, "
        "dropping the live-adapter requirement (2026-09-23 defect)",
        "backend/app/services/capability_service.py",
        '    provider = (settings.BNPL_DEFAULT_PROVIDER or "tabby").lower()\n'
        '    return payment_method_is_live(f"bnpl_{provider}")',
        '    return _bnpl_configured()',
        ["backend/tests/test_capabilities_endpoint.py", "backend/tests/test_group5_commerce.py"],
    ),
    Mutation(
        "M26",
        "Product page: name the lender unconditionally, even when no live provider "
        "exists (a named offer the lender never made)",
        "backend/app/services/product_context_service.py",
        "        live = bnpl_is_live()",
        "        live = True",
        ["backend/tests/test_group5_commerce.py"],
    ),
    Mutation(
        "M27",
        "Wardrobe: gate photo uploads on the storage provider NAME instead of the "
        "measured probe (s3 with an unreachable bucket offers uploads that fail)",
        "backend/app/services/capability_service.py",
        '    storage = storage_status()\n'
        '    return bool(storage.get("production_grade")) and bool(storage.get("writable", True))',
        '    return (settings.STORAGE_PROVIDER or "local").lower() != "local"',
        ["backend/tests/test_capabilities_endpoint.py"],
    ),
    Mutation(
        "M28",
        "Order states: add a lifecycle state that has no localized copy, so the "
        "shopper would read a raw machine token on the tracking page",
        "backend/app/services/commerce_service.py",
        '    "cancelled": set(),\n    "completed": set(),',
        '    "cancelled": set(),\n    "completed": set(),\n    "awaiting_customs": set(),',
        ["backend/tests/test_capabilities_endpoint.py::test_every_order_state_has_a_frontend_translation_key"],
    ),
    Mutation(
        "M34",
        "AI Stylist: publish `ai_stylist_live` from provider-key presence again "
        "instead of the measured readiness state (configuration standing in for "
        "reachability — the defect the probe was added to remove)",
        "backend/app/services/capability_service.py",
        '        "ai_stylist_live": ai_stylist_state() == "ready",',
        '        "ai_stylist_live": bool(_ai_provider_keys()),',
        ["backend/tests/test_capabilities_endpoint.py::test_stylist_flag_is_measured_and_configuration_has_its_own_name"],
    ),
    Mutation(
        "M35",
        "AI readiness: stop withdrawing a stale snapshot, so `ready` is reported "
        "indefinitely from a measurement nobody can date (stale success)",
        "backend/app/services/ai_readiness.py",
        "        return snap is not None and snap.age_seconds() > self._max_age",
        "        return False",
        ["backend/tests/test_ai_readiness_probe.py::test_a_stale_verdict_is_withdrawn_not_reported"],
    ),
    Mutation(
        "M36",
        "AI readiness: treat an authentication failure as ready, so a revoked or "
        "wrong credential is published as a working stylist",
        "backend/app/services/ai_readiness.py",
        "    if status_code == 200:\n        return ProviderProbe(provider, STATE_READY, status_code, latency_ms,",
        "    if status_code in (200, 401, 403):\n        return ProviderProbe(provider, STATE_READY, status_code, latency_ms,",
        ["backend/tests/test_ai_readiness_probe.py::test_failures_are_classified_not_lumped_together"],
    ),
    Mutation(
        "M37",
        "AI readiness: ignore the total probe budget, so the inline /health "
        "refresh can wait on every provider in turn and the probe becomes the "
        "slowest part of a health check",
        "backend/app/services/ai_readiness.py",
        "        if total_budget_seconds is not None and (time.time() - started) >= total_budget_seconds:",
        "        if False:",
        ["backend/tests/test_ai_readiness_probe.py::test_the_probe_respects_its_total_budget"],
    ),
    Mutation(
        "M38",
        "Rate limiting: drop the limit from the AI stylist chat, so an unlimited "
        "and anonymous endpoint spends this deployment's provider quota per call "
        "(the 2026-09-23 gap)",
        "backend/app/controllers/stylist_controller.py",
        '@limiter.limit("20/hour")\nasync def chat_with_stylist(',
        "async def chat_with_stylist(",
        ["backend/tests/test_rate_limiting.py::test_stylist_chat_rate_limit_returns_429"],
    ),
    Mutation(
        "M39",
        "Rate limiting: key every caller by address only, so all shoppers behind "
        "one proxy share a single bucket (and one client can starve the rest)",
        "backend/app/core/rate_limit.py",
        "    credential = _bearer_token(request) or _session_token(request)",
        "    credential = None",
        ["backend/tests/test_rate_limiting.py::test_the_key_isolates_callers_by_token_not_only_by_address"],
    ),
    Mutation(
        "M29",
        "Payment methods: answer every request with the default market, so a "
        "client asking for AE/SA is silently served EG's rails and currency "
        "(the silent-fallback defect: an unknown parameter value or name must "
        "not be answered as if it were the default)",
        "backend/app/controllers/commerce_controller.py",
        'return orchestrator.get_market_methods(country_code or "EG")',
        'return orchestrator.get_market_methods("EG")',
        ["backend/tests/test_capabilities_endpoint.py::test_payment_methods_answer_for_the_requested_market"],
    ),
    Mutation(
        "M30",
        "Payment disclaimer: restore the unconditional compliance sentence "
        "('All transactions in {code} are processed in compliance with local "
        "central bank regulations and PCI-DSS tokenization standards') so it "
        "is published for markets where nothing but cash on delivery can "
        "settle — a regulated claim standing on nothing measured",
        "backend/app/services/capability_service.py",
        '    if live - {"cod"}:',
        "    if True:",
        ["backend/tests/test_capabilities_endpoint.py::test_payment_disclaimer_makes_no_compliance_claim_nothing_can_back"],
    ),
    # ── 2026-09-23 (this cycle) ──────────────────────────────────────────────
    Mutation(
        "M40",
        "Payment liveness: give the ADAPTER BASE a boolean `is_live` again, so a "
        "subclassed PSP adapter carries a second, defaulted source of truth for "
        "the one fact the platform must not get wrong (the shape that published "
        "`bnpl_tabby` as live with no Tabby credential, one layer down)",
        "backend/app/providers/payment/base.py",
        "    def __init__(self, name: str):\n        self.name = name",
        "    def __init__(self, name: str, is_live: bool = False):\n        self.name = name\n        self.is_live = is_live",
        ["backend/tests/test_payment_adapter_liveness_owner.py"],
    ),
    Mutation(
        "M41",
        "Return label: shrink the capability reference back to 40 bits, so an "
        "unauthenticated endpoint that discloses the order number is protected "
        "by a value below the 64-bit floor for a bearer credential",
        "backend/app/services/commerce_service.py",
        'ref = f"RA-{uuid.uuid4().hex[:16].upper()}"',
        'ref = f"RA-{uuid.uuid4().hex[:10].upper()}"',
        ["backend/tests/test_return_label_capability_entropy.py"],
    ),
    Mutation(
        "M42",
        "i18n naming: stop normalising the language tag before asking "
        "`Intl.DisplayNames`, so a region-qualified tag is rendered through the "
        "spec default (dialect) — 'American English' / 'العربية (مصر)' in a "
        "language switcher — and `en-US` reaches the resolver unguarded",
        "frontend/src/i18n/format.ts",
        "  const base = baseLanguage(lang);",
        "  const base = String(lang);",
        ["src/i18n/__tests__/i18nParity.test.tsx"],
        runner="vitest",
    ),
]


def run_tests(tests: list[str], env: dict, runner: str = "pytest") -> tuple[int, str]:
    if runner == "vitest":
        # Frontend gate: same contract (non-zero exit = the mutation was killed).
        cmd = ["npx", "vitest", "run", *tests]
        p = subprocess.run(cmd, capture_output=True, text=True, env=env,
                           cwd=str(REPO / "frontend"), timeout=1500)
    else:
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
        for runner in sorted({m.runner for m in MUTATIONS if not wanted or m.mid in wanted}):
            subset = sorted({t for m in MUTATIONS
                             if (not wanted or m.mid in wanted) and m.runner == runner for t in m.tests})
            print(f"[baseline:{runner}] running {len(subset)} test file(s) unmutated ...", flush=True)
            rc, tail = run_tests(subset, env, runner)
            print(f"[baseline:{runner}] rc={rc} {tail.splitlines()[-1] if tail else ''}")
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
            rc, tail = run_tests(m.tests, env, m.runner)
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
