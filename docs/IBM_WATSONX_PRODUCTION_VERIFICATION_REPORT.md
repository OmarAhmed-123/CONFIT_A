# IBM watsonx.ai Granite Wardrobe Stylist — Production-Oriented Completion & Verification Report

Date: 2026-10-26 · Branch: `feat/watsonx-granite-stylist` (PR #387) · Author: OmarAhmed-123
Legend: **VERIFIED** (executed here, evidence named) · **MOCKED** (automated tests stubbing watsonx HTTP) · **LIVE** (real watsonx.ai, eu-de) · **PARTIALLY VERIFIED** · **NOT VERIFIED**.

## A. Executive summary

* The branch from the first pass was re-verified from scratch (fresh venv +
  `npm ci`): **backend 4,588 passed / 0 failed / 25 skipped; frontend 157
  files / 2,361 tests, tsc, i18n gate, build; `npm audit --omit=dev
  --audit-level=high` → 0 vulnerabilities** (zod 3 → 4.6.7, the CI blocker on PR #387).
* **P1 — Style List end-to-end:** the one missing journey step, *save/revisit*,
  is now implemented (migration 0048, `/wardrobe/outfits` CRUD, "Save this
  look", "Saved wardrobe looks") with server-side re-validation of item
  ownership, roles from stored categories, provenance kept truthful, cross-user
  404s, and binned garments never shown. 7 backend + 9 frontend tests; exercised
  live end-to-end in the browser (EN/AR) with real Granite answers.
* **P2 — Granite Vision:** answered with live evidence across six regions: no
  `granite-vision-*` is served pay-per-token anywhere; current generations are
  **Deploy-on-Demand only** (paid dedicated hardware). Not a code or permission
  defect. A config-only Deploy-on-Demand route was added and unit-tested; no
  deployment was created (billing decision for the operator).
* **P3 — Database:** nothing could be read or applied: **Neon refuses all
  connections for both staging and production ("exceeded the quota — upgrade
  your plan")**. The 0047+0048 chain is verified on sqlite locally and on
  Postgres 17 in CI; a runbook is ready.
* **P4:** axe-clean (0 violations, 8 states, 2 engines) + **real GNOME Orca
  session** (EN) which found and confirmed the fix of one defect (unnamed "Swap
  out" buttons). Arabic review sheet produced; native review outstanding.
* **P5:** load harness with a watsonx double + capped live probe. Correctness
  under load is clean (0×5xx, 0 mislabelled answers, retries recover injected
  faults); latency targets missed on the single-worker/SQLite rig — attributed,
  not excused.
* **Release recommendation: NOT releasable to production today** for reasons
  outside this code: Neon project quota-locked, Vercel production deployment
  disabled (HTTP 402), migrations unapplied. Code is **ready for staging** once
  the database is reachable.

## B. Changes made in this pass

| Area | Change |
|---|---|
| `backend/app/providers/watsonx/client.py` | `chat(deployment_id=…)` → `/ml/v1/deployments/{id}/text/chat`; provenance from served `model_id`; `WATSONX_IAM_URL` honoured |
| `backend/app/core/config.py` | `WATSONX_VISION_DEPLOYMENT_ID`, `WATSONX_REASONING_DEPLOYMENT_ID`, `WATSONX_IAM_URL` |
| `backend/app/models/wardrobe.py`, `alembic/versions/0048_wardrobe_outfits.py` | `wardrobe_outfits`, `wardrobe_outfit_items` (FK → `wardrobe_items` ON DELETE CASCADE, grants to `confit_app_rw`) |
| `backend/app/services/wardrobe_outfit_service.py` (new) | save/list/get/delete with ownership + readiness re-validation, role derivation, provenance coercion, dropped-item accounting |
| `backend/app/controllers/wardrobe_controller.py` | `POST/GET /wardrobe/outfits`, `GET/DELETE /wardrobe/outfits/{id}` (60/hour on save) |
| `backend/app/schemas/wardrobe_stylist.py` | `SaveWardrobeOutfitRequest`, `SavedWardrobeOutfitOut` |
| `backend/app/core/schema_gate.py`, `tests/test_flow_e_purchase_to_wardrobe.py` | head = 0048; new tables required |
| `backend/tests/test_wardrobe_saved_outfits.py` (new, 7), `test_watsonx_stylist.py` (+3 DoD routing) | acceptance tests |
| `frontend/package.json` | zod ^4.6.7 (+ `z.record(key, value)` signature fix) |
| `frontend/src/services/apiClient.ts` | 204 No Content no longer treated as a JSON parse failure |
| `frontend/src/services/apiServices.ts` | saved-outfit types + `saveOutfit/listSavedOutfits/getSavedOutfit/deleteSavedOutfit`, `toSaveWardrobeOutfitRequest` |
| `frontend/src/components/wardrobe/WardrobeStylistPanel.tsx` | "Save this look" (idle/saving/saved/error; 201-gated success; live status; reset on regenerate); `aria-label="Swap out {{item}}"` |
| `frontend/src/components/wardrobe/SavedWardrobeLooks.tsx` (new) + `WardrobeView.tsx` | "Saved wardrobe looks" section on *My Looks* |
| `frontend/src/i18n/{en,ar}.json` | 20 new `wardrobe_stylist.*` strings (incl. Arabic CLDR plurals) |
| Tests | `savedWardrobeLooks.test.tsx` (5), `wardrobeStylistPanel.test.tsx` (+4) |
| Tooling | `scripts/load/{watsonx_double,stylist_load}.py`, `frontend/scripts/stylist_a11y_audit.mjs`, `scripts/qa/orca_stylist_session.sh` |
| Docs | this report; `GRANITE_VISION_AVAILABILITY_INVESTIGATION.md`; `STYLE_LIST_WORKFLOW.md`; `qa/MIGRATION_0047_0048_CHECKLIST.md`; `qa/STYLIST_A11Y_REPORT.md`; `qa/ARABIC_REVIEW_SHEET_STYLIST.{md,csv}`; `qa/LOAD_TEST_STYLIST.md` + `qa/load/*.json`; README/.env.example |

Nothing was rebuilt; the existing framework, model-id configuration, and the
editorial React/Tailwind design were preserved. No test was weakened; one test
assertion was updated to the new accessible name ("Swap out Blue Plaid Shirt").

## C. Acceptance matrix

| Item | Status | Evidence |
|---|---|---|
| P0 branch/tests baseline | VERIFIED | commands in §H; logs `/tmp/be_full.log`, `/tmp/fe_verify.log` (session) |
| P0 provider config (keys server-side only, model ids configurable) | VERIFIED | `core/config.py`; status endpoint never returns the key; `.env.example` |
| P0 CI blocker (zod audit) | VERIFIED | `npm audit --omit=dev --audit-level=high` → 0 |
| P0 release gate (prod `/health`) | NOT VERIFIED — external | Vercel `DEPLOYMENT_DISABLED` HTTP 402 |
| FR-01…FR-20 (first pass) | unchanged; see `IBM_WATSONX_STYLIST_ACCEPTANCE.md` | re-run of the same suites this session |
| Style List: upload → stable ids → vision metadata → categories | VERIFIED (MOCKED + LIVE session 1) | §C of workflow doc |
| Context inputs → generate from real wardrobe → correct photos | LIVE | live probe 8/8; browser audit EN/AR with real Granite |
| Refine / exclude / regenerate | MOCKED + LIVE (UI) | Scenario I; panel tests; Orca transcript "Swap out Navy Chinos" |
| Honest failures / AI-vs-fallback labelling | MOCKED + LIVE | Scenario F/G/J; load run 400/400 labelled; save coerces fallback → `ai_generated=false` |
| **Save / revisit** | VERIFIED (unit) + LIVE (browser, both locales) | `test_wardrobe_saved_outfits.py` 7/7; a11y report "Saved to your wardrobe looks (#5)" |
| Cross-user rejection (styling + saving + reading + deleting) | VERIFIED | `test_cross_user_items_are_not_styled`, `test_foreign_and_unknown_ids_are_rejected_not_stored`, `test_look_made_only_of_foreign_ids_is_refused`, `test_other_user_cannot_read_or_delete_a_saved_look` |
| Incomplete wardrobes / binned garments | VERIFIED | `missing_categories` scenarios; `test_binned_item_is_rejected_at_save_and_hidden_afterwards` |
| StyleList chat wardrobe grounding (STY-03) still works | VERIFIED (existing tests in full run) | `test_stylist_wardrobe_influence.py` et al. |
| Granite Vision availability | VERIFIED LIVE | investigation doc (6 regions, 3 model ids) |
| Deploy-on-Demand routing | MOCKED | `TestDeployOnDemandRouting` 3/3; **NOT VERIFIED LIVE** (no deployment) |
| Migration 0047 + 0048 chain | VERIFIED (sqlite up/down/up; CI Postgres 17 for 0047; 0048 runs on push) | checklist doc |
| Staging/production DB revision | NOT VERIFIED — Neon quota lock | checklist §"observed" |
| Accessibility automated | VERIFIED (0 axe violations, keyboard, focus, live regions, RTL) | `stylist_a11y_report.json` |
| Accessibility real AT | PARTIALLY VERIFIED (Orca, EN, Firefox) | `stylist_orca_report.json` |
| Arabic native review | NOT VERIFIED (sheet delivered) | `ARABIC_REVIEW_SHEET_STYLIST.csv` |
| Load — correctness | VERIFIED (mocked) | 660 req, 0×5xx, retries recover faults |
| Load — latency targets | PARTIALLY VERIFIED (live single-user PASS; 20-VU p95/p99 MISSED on rig) | `LOAD_TEST_STYLIST.md` |

## D. Granite compliance

* Reasoning: **`ibm/granite-4-h-small`** on watsonx.ai, LIVE on every path that
  claims it; prompt versioned (`wx-stylist-1.0`); served `model_id` is what the
  UI shows. No other provider is ever substituted for Granite silently: when
  Granite is unavailable the answer is labelled `deterministic_fallback`
  (`ai_generated=false`) or, in strict mode, the request fails with
  501/503.
* Vision: **not Granite** today — `meta-llama/llama-4-maverick-17b-128e-instruct-fp8`
  via watsonx.ai, disclosed per item (`analysis_source`). Reason, with live
  proof: IBM serves Granite Vision only as Deploy-on-Demand; the 3-2-2b model in
  the tutorial is removed. Switching to real Granite Vision is a config change
  once the operator pays for a deployment (`WATSONX_VISION_DEPLOYMENT_ID`).
* No mock is ever called "real inference"; the load-test double is explicitly
  labelled and lives under `scripts/load/`, never deployed.

## E. Database readiness — per environment actually checked

| Environment | What was done | Result |
|---|---|---|
| local sqlite | `alembic upgrade head` → `downgrade 0046` → `upgrade head` | OK, head `0048_wardrobe_outfits`, both tables present |
| CI Postgres 17 | `check_migration_chain_postgres.py` (job "postgres migration chain + schema gate") | PASS on PR #387 for 0047; must be re-checked on the push carrying 0048 |
| Neon staging `confit_fixverify` | read-only connect as owner and as `confit_app_rw` | **refused: project quota exceeded** — revision unknown, nothing applied |
| Neon production `neondb` | same | **refused: project quota exceeded** — revision unknown, nothing applied |

Known from session 1 (before the lock): neither DB had 0047. Both now also need 0048.

## F. Accessibility and localisation

See `docs/qa/STYLIST_A11Y_REPORT.md` and `docs/qa/ARABIC_REVIEW_SHEET_STYLIST.md`.
Summary: 0 axe violations (EN/AR, Chromium + Firefox), keyboard-complete, focus
management and live regions confirmed by Orca (EN); one AT defect found and
fixed; Arabic strings complete and placeholder-parity-checked (81 strings) but
**not natively reviewed**; AR real-AT transcript not obtained.

## G. Performance

See `docs/qa/LOAD_TEST_STYLIST.md`. Live: p50 5.5 s / p95 8.0 s per Granite
recommendation (model-bound). Mocked 20 VUs: 4.4 req/s, 0 errors, p95 9.3 s /
p99 12.4 s against targets 6.5 / 8.0 → missed; 1-VU baseline shows our overhead
≈ tens of ms, so the tails are rig concurrency (1 worker, SQLite) plus retries.
Re-run on Postgres staging with ≥ 2 workers before sign-off.

## H. Tests and commands (all run this session)

```bash
# backend (venv at ~/.venv)
PYTHONPATH=. python -m pytest backend/tests -q            # 4588 passed, 25 skipped, 0 failed (695 s)
PYTHONPATH=. python -m pytest backend/tests/test_wardrobe_saved_outfits.py backend/tests/test_watsonx_stylist.py -q   # 7 + 37
alembic -c backend/alembic.ini upgrade head / downgrade 0046_user_wishlist_items / upgrade head   # sqlite
# frontend
npm run verify   # i18n gate ✔, tsc ✔, vitest 157 files / 2361 tests ✔, vite build ✔
npm audit --omit=dev --audit-level=high   # 0 vulnerabilities
node scripts/apply-button-motion.mjs      # 390/390 controls declare an intent
# live / load / a11y
python scripts/load/stylist_load.py --mode live --vus 2 --requests 4 --base http://127.0.0.1:8001
python scripts/load/stylist_load.py --mode mocked --vus 20 --requests 20 --model-latency 5.0
(cd frontend && node scripts/stylist_a11y_audit.mjs) --app http://127.0.0.1:4173 --api http://127.0.0.1:8001
scripts/qa/orca_stylist_session.sh http://127.0.0.1:4173 http://127.0.0.1:8001 docs/qa/stylist_orca_report.json
```

## I. Blockers by severity

| Sev | Blocker | Owner | Notes |
|---|---|---|---|
| **S1** | Neon project quota exceeded — staging and production databases unreachable | Operator / billing | Blocks P3 entirely; nothing can be verified or migrated |
| **S1** | Vercel production deployment disabled (HTTP 402) | Operator / billing | Release gate fails on `/health`; no production app to validate against |
| **S2** | Migrations 0047 + 0048 not applied to any Neon DB | Operator (with runbook) | Apply to staging first; production only with written authorisation |
| **S2** | Load latency targets missed on test rig; Postgres/multi-worker re-run outstanding | Engineering | Correctness clean; see §G |
| **S3** | Granite Vision requires a paid Deploy-on-Demand instance | Operator decision | Config-only switch ready; default remains disclosed Llama-4 vision |
| **S3** | Arabic native review; Arabic real-AT pass; non-Orca screen readers | QA / l10n | Sheets and scripts delivered |

## J. Release recommendation

**Do not release to production now** (S1 blockers are environmental and
outside this repository). **Merge PR #387 to the integration branch and deploy
to staging as soon as Neon is unlocked**, following
`docs/qa/MIGRATION_0047_0048_CHECKLIST.md` (0047+0048, owner role, Neon branch
backup, parity check), then re-run the mocked 20-VU load test against staging
and complete the Arabic native review. Production requires: Neon + Vercel
restored, staging soak clean, explicit written authorisation for the production
migration.
