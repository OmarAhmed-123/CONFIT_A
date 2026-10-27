# IBM watsonx.ai Granite Wardrobe Stylist — Production-Oriented Completion & Verification Report

Date: 2026-10-26 · Branch: `feat/watsonx-granite-stylist` (PR #387) · Author: OmarAhmed-123
Legend: **VERIFIED** (executed here, evidence named) · **MOCKED** (automated tests stubbing watsonx HTTP) · **LIVE** (real watsonx.ai, eu-de) · **PARTIALLY VERIFIED** · **NOT VERIFIED**.
Release-checklist vocabulary used from §0 onward: **PASS — VERIFIED** (executed here, evidence named) · **PASS — AUTOMATED** (CI/suite green, not re-executed by hand) · **PARTIAL** · **BLOCKED** (external) · **FAIL** · **NOT RUN**.

## 00. Fourth pass (2026-10-27, "Production Readiness, AI Accuracy, Performance, Accessibility, Release Validation")

Baseline for this pass: `feat/watsonx-granite-stylist` @ `ae202f6` (== origin, PR #387 open,
`mergeable_state: blocked`). Historical results from 2026-10-26 (§0, §A–§J) are kept as
written; everything in §00 was re-executed on 2026-10-27 unless marked otherwise.

### 00.1 Environment & external-dependency verification (all times UTC)

| Time | Check | Endpoint / command | Result | Evidence source | Status | Action / owner / impact |
|---|---|---|---|---|---|---|
| 14:58 | Repo head | `git rev-parse HEAD` vs `origin/feat/watsonx-granite-stylist` | `ae202f6` both, tree clean | local git after re-clone | VERIFIED | — |
| 14:58 | CI on PR head | GitHub Actions API, `head_sha=ae202f6` | backend, frontend, Postgres migration chain + schema gate, stylist drawer browser gate, production parity, gitleaks: **success**; release gate: **failure** (prod health 402); Cloudflare Workers Builds: **failure** (external app) | `GET /repos/OmarAhmed-123/CONFIT_A/actions/runs?head_sha=…` | VERIFIED | Release gate cannot pass while production is disabled — owner: repo owner (Vercel billing) |
| 14:59 | Production | `GET https://confit-a.vercel.app/`, `/health`, `/api/v1/health` | **HTTP 402**, `x-vercel-error: DEPLOYMENT_DISABLED` (all three) | curl | VERIFIED | S1 blocker — Vercel team billing/pause; owner: account owner; impact: no production surface at all |
| 15:00 | Neon prod (`neondb`) and staging (`confit_fixverify`), owner + app_rw roles | psycopg2 `SELECT 1` on all 4 URLs | connection refused with "Your account or project has exceeded the quota" | psycopg2 error text | VERIFIED (unreachable) | S1 blocker — Neon plan quota; owner: account owner; impact: 0047/0048 state in staging/prod **NOT VERIFIED**, no live-DB smoke possible |
| 15:00 | watsonx.ai (eu-de) | IAM token exchange; `GET /ml/v1/foundation_model_specs` | HTTP 200 / HTTP 200, `ibm/granite-4-h-small` listed | curl with `.env.local` key (never printed) | VERIFIED | Live *inference* not re-run this pass (quota prudence); last live outfit 2026-10-26 (§0.1) |
| 15:00 | Redis / shared rate-limit store | — | no `REDIS_URL` available | — | **BLOCKED — NOT VERIFIED** | Rate limits are per-worker (`memory://`); 40/h per user is therefore ≈40×workers. Owner: platform; impact: S4 |
| 15:00 | Sandbox | `/home/user/CONFIT_A` restore | `.git`, `node_modules`, `.venv`, PostgreSQL lost between sessions again; re-cloned (`ae202f6`), `npm ci`, venv rebuilt, PostgreSQL 17.11 reinstalled, cluster re-initialised on :5433 | shell | VERIFIED | Local only; no impact on the repo |
| 11:24 | `main` uptime monitor | GitHub Actions scheduled run | failing since production 402 | Actions API | VERIFIED | Same root cause as the 402 |

**Not performed, by design:** no deploy, no merge, no new branch, no force-push; no live Granite spend.

### 00.2 Stylist List lifecycle map & defects found (Phase 1)

Lifecycle (unchanged files are referenced, not re-described): `WardrobeStylistPanel.tsx` →
`apiServices.recommendOutfit` → `POST /api/v1/wardrobe/outfit-recommendation`
(`wardrobe_controller.recommend_outfit_from_wardrobe`, JWT user, 40/h) →
`WardrobeStylistService.recommend` → closet (caller's ready, un-binned rows only) →
`prompts.build_stylist_user_message` → `WatsonxClient.chat` (granite-4-h-small, JSON mode, bounded
retries) → `_validate_selection` (ids, duplicates, excluded ids, role from stored category) →
`OutfitRecommendation` (provenance) → optional `POST /wardrobe/outfits` (0048, model-id allow-list).

| # | Defect / gap (reproduced 2026-10-27) | Severity | Root cause | Fix in this pass |
|---|---|---|---|---|
| D1 | **Excluded colours were never enforced.** "no black" reached the model only as prose in `exclusions`; `_validate_selection` checked ids/roles only, so a model answer containing black pieces was returned verbatim. Reproduced with a mocked model that ignores the instruction. | S2 (AI accuracy / fidelity to the user's description) | No structured field, no post-validation | `excluded_colors: list[str]` (≤8) added to the request; `banned_color_families()` derives bans from the list **and** from negated colour words in `exclusions` (EN + AR); offending items are dropped in the model path **and** filtered from the fallback candidates; limitation names colour + count (EN/AR); prompt gains a "colours to avoid" line. UI: new *Colours to avoid* input (EN/AR strings, hint text, axe-clean). |
| D2 | **Arabic colour words did not normalise.** `COLOR_FAMILIES` was English-only, so "أسود" never matched `Black` — preference scoring and D1 could not work for Arabic users. | S2 | Taxonomy gap | 17 families given MSA aliases (hamza / no-hamza / feminine forms) |
| D3 | `normalize_color()` returns `Black` for any unknown word. Harmless for labelling, dangerous for a ban list (an unrecognised or injected string would have banned black). Found by the new injection test *during* this pass, before commit. | S2 (introduced-then-fixed) | Default family | `_known_color_family()` only maps strings containing a real alias; unrecognised entries produce an explicit limitation instead |
| D4 | **Requested outfit count not supported.** The contract is one outfit per call; a `count` field was silently discarded (pydantic default `extra=ignore`), so a user asking for three outfits got one with no explanation. | S3 (documented gap) | Design | `extra="forbid"` → `count` returns 422 naming the field; documented as NOT IMPLEMENTED (alternatives via `previous_item_ids` / "Another outfit"). Multi-outfit generation is a product/prompt change that multiplies latency per request — not done here. |

Tests added: `backend/tests/test_stylist_colour_constraints_eval.py` (23 cases: unit ban
derivation EN/AR, model-path enforcement EN/AR, no-exclusion regression guard, fallback
enforcement, position lost to a ban, `count` → 422, bounds, prompt-injection containment).
Frontend: `wardrobeStylistPanel.test.tsx` extended (payload now includes `excluded_colors`),
11/11 incl. axe EN + AR/RTL.

### 00.3 PostgreSQL startup & migrations (Phase 2/§8, PostgreSQL 17.11, re-executed)

| Scenario | Result | Evidence |
|---|---|---|
| Fresh DB → `alembic upgrade head` | PASS, head `0048_wardrobe_outfits` | shell |
| `downgrade 0046` → `upgrade head` | PASS | shell |
| Existing migrated DB, 2 workers, restart | PASS, both workers `verdict=ok` | rig log |
| **Migrated-but-empty DB, 2 workers concurrently (non-production)** | **FAIL before** (3/3: false `verdict=drift` + "relation does not exist" on one worker) → **PASS after** advisory-lock fix (3/3: both `ok`, seeded once) | `/tmp/race_{before,after}_{1,2,3}.log`; `backend/app/core/startup_lock.py`; `test_startup_seed_lock_postgres.py` 3/3 |
| Restart after partial init | Covered by the same lock: a second worker waits for the first to finish seeding; not separately fault-injected (NOT RUN as a kill-mid-seed test) | — |
| DB unavailable at startup | Existing behaviour unchanged (lifespan logs "Database initialization notice", gate logs, app serves degraded health) — observed incidentally at 15:26 UTC, not re-run as a dedicated scenario | rig log |
| MFA single-use invariants under concurrency | 3/3 PASS on PG 17 | pytest |
| 0047/0048 state in Neon staging / production | **BLOCKED — NOT VERIFIED** (quota lock) | psycopg2 error |

### 00.4 Performance (Phase 4) — summary; full detail in `docs/qa/LOAD_TEST_STYLIST.md` § "Fourth pass"

Baseline reproduced today at 1/5/10/20 VU (same workload as 2026-10-26). Bottleneck
isolated by measurement: the stylist request held its DB connection **idle in
transaction** for the whole model await (15 pinned connections at 20 VU = one worker's
pool), queueing every other request. Fix: release the connection before awaiting the
model (`_release_db_connection`). 20 VU like-for-like: recommend p50 5.93 → **5.11 s**,
p95 8.15 → **6.48 s (target 6.5 met)**, p99 11.56 → 11.50 s (**still > 8.0**: injected
fault + bounded retry ≈ 2 × model latency — visible already at 1 VU), `save_outfit` p95
1.55 → **0.03 s**, throughput 4.73 → 5.76 rps, 0 errors, idle-in-transaction 15 → **0**.
Targets not relaxed. Live-Granite / staging rerun: NOT RUN (blockers unchanged).

### 00.4b CI on the first push of this pass (`36a372a`) — two failures, both fixed in the follow-up commit

| Job | Failure | Cause | Fix |
|---|---|---|---|
| backend → "Dependency security audit (pip-audit)" | `dnspython 2.7.0` — CVE-2026-114605, fix 2.9.0 | New advisory against an existing explicit pin (brand-domain TXT verifier); unrelated to this pass's code — it would fail on `ae202f6` too if re-run today | Pin bumped to 2.9.0 in `requirements.txt`, `backend/requirements.txt` and the byte-identical Vercel mirror `api/requirements.txt` (the manifest-drift test caught the mirror); `pip-audit` locally: "No known vulnerabilities found"; manifest tests 15/15 |
| postgres migration chain → isolated-PostgreSQL step | `ModuleNotFoundError: psycopg` in the new `test_startup_seed_lock_postgres.py` | CI passes a bare `postgresql://` DSN, which SQLAlchemy 2 maps to psycopg v3; the test built its engine from the raw DSN instead of the app's `normalise_postgres_url` | Test now normalises like the MFA test and the application; 3/3 locally with the bare DSN form |

Other jobs on `36a372a`: frontend, stylist drawer browser gate, production parity, gitleaks — **success**; release gate — failure (production 402, unchanged); Workers Builds — failure (external, unchanged).

### 00.5 Test results this pass (all executed 2026-10-27, local)

| Suite | Result |
|---|---|
| Backend full (3 sequential pytest processes, SQLite default) | **4,617 passed, 0 failed, 25 skipped** (4,591 + 26 new) |
| New `test_stylist_colour_constraints_eval.py` | 24/24 (23 colour/contract + 1 connection-hygiene) |
| Stylist-related regression set (`test_watsonx_stylist`, saved outfits, eval harness, colour tests) | 76 passed |
| PostgreSQL-only: `test_mfa_concurrency_postgres.py` + `test_startup_seed_lock_postgres.py` + `test_startup_seed_no_open_session.py` | 3 + 3 + 2 passed (PG 17.11) |
| Frontend (vitest) | **157 files / 2,361 passed**; `tsc --noEmit` clean |
| Panel a11y (axe) EN + AR/RTL with the new control | 0 violations |
| API security recheck on the Postgres/2-worker rig | unauth `GET/POST /wardrobe/outfits`, `GET /wardrobe/outfits/{id}`, `POST /outfit-recommendation` → **401**; malformed bearer → 401; cross-user save → 422 refused; forged `model_id` → refused; `count` → 422 naming the field; excluded-colour enforcement observed end-to-end (2 black pieces dropped, limitation shown) |
| Alembic 0046 ⇄ 0048 on PG 17 | PASS |
| Live Granite inference | NOT RUN this pass (IAM + catalogue HTTP 200 only; 17 multitenant models, 0 granite-vision, 15:57 UTC) |

## 0. Re-validation pass (2026-10-26, "Production Readiness & Deployment Recovery")

Everything below in §A–§J was re-checked against the current repository, CI
and infrastructure. Baseline: `feat/watsonx-granite-stylist` @ `f1a881d`
(PR #387, tree clean), `main` @ `cfc6d80`; 14 open PRs.

### 0.1 Baseline (P0)

| Check | Status | Evidence |
|---|---|---|
| CI on `f1a881d`: backend, frontend, postgres migration chain + schema gate (0048), stylist drawer browser gate, production parity, gitleaks | **PASS — AUTOMATED** | GitHub check-runs, all SUCCESS |
| CI "release gate (production schema parity)" | **BLOCKED** (external) | reads prod `/health` → HTTP 402 |
| CI "Workers Builds: confit-a" (Cloudflare GitHub app) | **BLOCKED** (external, pre-existing) | fails identically on `13a3622`; no wrangler/Cloudflare config exists in the repo and no Cloudflare credentials are available — an account-side integration, not a code gate |
| Single Alembic head | **PASS — VERIFIED** | `alembic heads` → `0048_wardrobe_outfits` (PostgreSQL 16 + sqlite) |
| Secrets not in bundles / repo | **PASS — AUTOMATED** | gitleaks SUCCESS; `WATSONX_*` only server-side (`core/config.py`); keys live in the local env file only |
| Backend focused suite (watsonx/stylist/outfit/migration) | **PASS — VERIFIED** | 510 passed / 2 skipped |
| Backend full suite | see §0.6 | |
| Frontend `npm run verify` | **PASS — VERIFIED** | i18n gate ✔ · tsc ✔ · 157 files / 2,361 tests ✔ · build ✔ |
| Production `/health` | **FAIL** (external) | `HTTP 402`, `x-vercel-error: DEPLOYMENT_DISABLED` |

### 0.2 Database (P1)

| Check | Status | Evidence |
|---|---|---|
| Neon staging `confit_fixverify` read-only preflight (owner + `confit_app_rw`) | **BLOCKED** | re-probed this pass: "Your account or project has exceeded the quota" on all four connections |
| Neon production `neondb` (both roles) | **BLOCKED** | same |
| Backup-then-migrate staging | **NOT RUN** (blocked) | runbook unchanged in `docs/qa/MIGRATION_0047_0048_CHECKLIST.md` |
| Production migration | **NOT RUN** — requires written authorisation *and* Neon recovery | |
| 0046 → 0048 → 0046 → 0048 on **PostgreSQL 16** (local) | **PASS — VERIFIED** | columns `analysis_source`/`analysis_description`; `wardrobe_outfit_items` FKs `ON DELETE CASCADE` (`confdeltype=c`); 3 indexes; schema gate `verdict=ok` at startup |
| Startup on a fresh PostgreSQL database | **FAIL → FIXED** | self-deadlock in the dev seed path (`main.py`); regression test added — see §0.5 |

### 0.3 Deployment (P2)

| Check | Status | Evidence |
|---|---|---|
| Root cause of 402 | **VERIFIED (diagnosis)** | Last Production deployment `cfc6d80` (2026-10-22 00:41Z) **succeeded**; since then the alias **and** the immutable deployment URL both serve `402 Payment required / DEPLOYMENT_DISABLED` from the edge → team-level billing pause on the Vercel team, not a project or code regression (`vercel.json` intact; no deploy since) |
| Recovery | **BLOCKED** (billing; no Vercel token here) | Owner: Vercel team owner → settle billing / re-enable; deployments resume automatically |
| Post-restore validation (health, CORS, auth, routing, smoke) | **NOT RUN** | script of checks in §J "Post-restore validation" |

### 0.4 Granite Vision (P3)

Unchanged conclusion, re-stated without new live calls this pass: no
multitenant `ibm/granite-vision-*` in any region; Deploy-on-Demand only
(`WATSONX_VISION_DEPLOYMENT_ID` routing is implemented, unit-tested, **NOT
VERIFIED LIVE** — no deployment exists, creating one is a billing decision).
Vision today is disclosed Llama-4 on watsonx.ai; **Granite Vision is NOT
enabled** and the product says so per item (`analysis_source`). Decision
record: `docs/GRANITE_VISION_AVAILABILITY_INVESTIGATION.md`.

### 0.5 Code changes in this pass (small, reversible, tested)

| File | Change | Why |
|---|---|---|
| `backend/app/main.py` | close the catalogue-probe session **before** calling `seed_database()` | PostgreSQL self-deadlock on first boot of any non-production DB (idle-in-transaction lock on `categories` vs. seeder's `DROP TABLE products`); reproduced with 1 and 2 workers, invisible on SQLite |
| `backend/tests/test_startup_seed_no_open_session.py` (new, 2 tests) | pins "zero checked-out connections when the seeder runs"; fails on the old code (`1 == 0`) | regression guard that works on SQLite |
| `backend/app/services/wardrobe_outfit_service.py` | `source=watsonx` looks must carry the configured reasoning model/deployment id; otherwise 422 | negative test on the Postgres rig persisted `model_id=gpt-4o` under `source=watsonx` → would be badged as Granite (provenance integrity) |
| `backend/tests/test_wardrobe_saved_outfits.py` (+1 test) | foreign id rejected; configured model id and configured deployment id accepted; fallback unchanged | |

No test was weakened; no target was relaxed; no migration, deployment or
billing change was made.

### 0.6 Test results this pass

| Suite | Result |
|---|---|
| Backend focused (`-k "watsonx or stylist or outfit or alembic or migration"`) | 510 passed, 2 skipped |
| `test_wardrobe_saved_outfits.py` + `test_startup_seed_no_open_session.py` | 10 passed |
| Backend full | **4,591 passed, 0 failed, 25 skipped** (run as three sequential pytest processes — a single process exceeds the 2 GB sandbox at ~98 %; identical test set, `ls backend/tests/test_*.py | split -n l/3`) |
| Frontend `npm run verify` | 157 files / 2,361 tests, tsc, i18n gate, build — all green |
| Style List negative battery over HTTP on PostgreSQL / 2 workers | 21 checks — `docs/qa/load/style_list_negative_tests_postgres.json` (20 PASS before the `model_id` fix; the one FAIL is the defect fixed above, re-run recorded in the same file) |
| Load, mocked, 20 VU, PostgreSQL / 2 workers, 0.9 s model | **PASS** — p50 1.23 / p95 1.69 / p99 2.01 s (targets 2.4 / 3.9), 0 errors, 400/400 Granite-labelled |
| Load, mocked, 20 VU, PostgreSQL / 2 workers, **5 s ± 1.5 s model + 3 % faults (like-for-like)** | **PARTIAL / MISSED** — p50 5.96 / p95 8.25 / p99 9.52 s vs 6.5 / 8.0; 0 errors, 400/400 Granite. The double alone is p95 6.44 / p99 ≈ 11 s, so the targets as written cannot be met with this double; app overhead ≈ 0.9 s p50 / 1.8 s p95 at 20 concurrent — ours to reduce (see `LOAD_TEST_STYLIST.md`) |
| Live bounded probe, PostgreSQL / 2 workers | **PASS** — 8/8 `ibm/granite-4-h-small`, p95 6.10 s |
| Accessibility / Arabic | **no new execution this pass** — statuses in §F stand (axe 0 violations; Orca EN; AR real-AT, NVDA/VoiceOver/TalkBack/JAWS **NOT RUN**; Arabic native review **NOT RUN** — no reviewer or approval is claimed) |

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
| P0 release gate (prod `/health`) | BLOCKED — external (re-confirmed) | Vercel `DEPLOYMENT_DISABLED` HTTP 402; diagnosis §0.3 |
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
| Migration 0047 + 0048 chain | PASS — VERIFIED (sqlite + **PostgreSQL 16 local** up/down/up with FK/index inspection) · PASS — AUTOMATED (CI Postgres 17 on `f1a881d`) | checklist doc |
| Staging/production DB revision | NOT VERIFIED — Neon quota lock | checklist §"observed" |
| Accessibility automated | VERIFIED (0 axe violations, keyboard, focus, live regions, RTL) | `stylist_a11y_report.json` |
| Accessibility real AT | PARTIALLY VERIFIED (Orca, EN, Firefox) | `stylist_orca_report.json` |
| Arabic native review | NOT VERIFIED (sheet delivered) | `ARABIC_REVIEW_SHEET_STYLIST.csv` |
| Load — correctness | VERIFIED (mocked) | 660 req, 0×5xx, retries recover faults |
| Load — latency targets | **PARTIAL** — PostgreSQL / 2 workers: 0.9 s-model run PASS (p95 1.69 / p99 2.01 s), live probe PASS (p95 6.10 s), like-for-like 5 s-model run MISSED (p95 8.25 / p99 9.52 vs 6.5 / 8.0; targets unattainable as written with the jittered/faulting double, and ≈ 1.8 s p95 app overhead remains to be profiled) | `LOAD_TEST_STYLIST.md` §Re-validation |
| Provenance cannot be forged at save time | PASS — VERIFIED (new) | `test_watsonx_look_cannot_claim_a_foreign_model_id` |
| Startup on fresh PostgreSQL (non-prod) | PASS — VERIFIED (after fix) | 2 workers bind in < 2 s; `test_startup_seed_no_open_session.py` |

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
| local PostgreSQL 16 (UTF8) | same chain + `pg_constraint`/`pg_indexes`/`information_schema` inspection + API FK-cascade check | OK — head 0048; 0047 columns; both 0048 FKs `ON DELETE CASCADE`; 3 indexes; schema gate `ok` |
| CI Postgres 17 | `check_migration_chain_postgres.py` (job "postgres migration chain + schema gate") | PASS on PR #387 for 0047; must be re-checked on the push carrying 0048 |
| Neon staging `confit_fixverify` | read-only connect as owner and as `confit_app_rw` (re-probed in the re-validation pass) | **refused: project quota exceeded** — revision unknown, nothing applied → BLOCKED |
| Neon production `neondb` | same | **refused: project quota exceeded** — revision unknown, nothing applied → BLOCKED |

Known from session 1 (before the lock): neither DB had 0047. Both now also need 0048.

## F. Accessibility and localisation

See `docs/qa/STYLIST_A11Y_REPORT.md` and `docs/qa/ARABIC_REVIEW_SHEET_STYLIST.md`.
Summary: 0 axe violations (EN/AR, Chromium + Firefox), keyboard-complete, focus
management and live regions confirmed by Orca (EN); one AT defect found and
fixed; Arabic strings complete and placeholder-parity-checked (81 strings) but
**not natively reviewed**; AR real-AT transcript not obtained.

## G. Performance

See `docs/qa/LOAD_TEST_STYLIST.md`. First pass (SQLite, 1 worker): mocked
20 VUs p95 9.3 s / p99 12.4 s → missed. **Re-validation pass (PostgreSQL 16,
2 workers, idle host): mocked 20 VUs 22.2 req/s, 0 errors, p50 1.23 s / p95
1.69 s / p99 2.01 s against 2.4 / 3.9 → PASS; application overhead above the
model ≈ 0.8 s at p95. Live bounded probe on the same rig: 8/8 Granite, p50
3.51 s / p95 6.10 s → within 6.5 / 8.0. Like-for-like 5 s ± 1.5 s model with
3 % injected faults: p50 5.96 / p95 8.25 / p99 9.52 → MISSED 6.5 / 8.0 — but
the double alone is p95 6.44 / p99 ≈ 11 s, so those targets cannot be met as
written; the application's own share (≈ 0.9 s p50 / 1.8 s p95 at 20
concurrent, 2 workers) is the actionable part.** Targets were not relaxed; a
restatement against measured model percentiles needs the owner's decision.
Still NOT RUN: the same probe against the real staging (Neon + Vercel).

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
| **S2** (narrowed) | Load latency: on PostgreSQL / 2 workers the 0.9 s-model run and the live probe pass; the like-for-like 5 s-model run still misses 6.5 / 8.0. Targets are unattainable as written with the jittered/faulting double (owner decision to restate), and ≈ 1.8 s p95 app overhead at 20 concurrent remains | Engineering (profile one worker under 10 concurrent recommendations; threadpool/worker count) + Product owner (target restatement) | Correctness clean in every run; repeat live probe on real staging once S1 clears |
| **S3** (new, fixed) | Fresh-PostgreSQL startup self-deadlock in the dev seed path | Engineering | Fixed + regression test in this pass; would have blocked a Postgres staging first boot |
| **S3** (new, fixed) | Saved look could claim a foreign `model_id` under `source=watsonx` | Engineering | Fixed + test; UI provenance badge can no longer be forged by a client |
| **S3** | Cloudflare "Workers Builds" GitHub check fails on every commit | Operator | No Cloudflare config in repo and no credentials here: either remove the integration from the GitHub app or add the intended wrangler project; it is not a code gate |
| **S4** | Dev rate limiter is per-process (`memory://`) when no external Redis is configured | Engineering / Ops | Observed on the rig: sign-up throttle tripped after 4 → 9 → 14 → 19 users with 2 workers instead of every 5. Set `REDIS_URL` to a shared store for any multi-worker deployment where limits must be global |
| **S4** | Observability: with `ENVIRONMENT=development` the API emits `httpcore` trace lines (`connect_tcp.started`, full response headers) and five `wardrobe_stylist_role_corrected` info lines per recommendation | Engineering | Confirm the production log level excludes `httpcore`/`httpx` trace output and consider aggregating the role-correction log to one line per request; no secrets were observed in the traces (bearer values are not printed) |
| **S3** | Granite Vision requires a paid Deploy-on-Demand instance | Operator decision | Config-only switch ready; default remains disclosed Llama-4 vision |
| **S3** | Arabic native review; Arabic real-AT pass; non-Orca screen readers | QA / l10n | Sheets and scripts delivered |

## J. Release recommendation

**NO-GO for production (unchanged); GO for merge-to-integration and staging
once Neon is reachable.** S1 blockers are environmental and outside this
repository; every code-side item that could be verified without staging has
been, on a production-like PostgreSQL rig.

### Post-restore validation (run in this order once Vercel + Neon are back)
1. `curl -sS https://confit-a.vercel.app/health` → 200, `checks.schema.verdict`
   is `ok` and `database_revision = 0048_wardrobe_outfits` (after the staging/prod migration).
2. CORS: preflight `OPTIONS /api/v1/wardrobe/outfits` from the production origin → allowed headers include `Authorization`.
3. Auth: register/login → bearer works; cookie-auth POST without CSRF header → 403 (as on the rig).
4. Routing: `/`, `/wardrobe`, deep link refresh → `index.html` rewrite; `/api/v1/*` → function.
5. Smoke: `scripts/load/stylist_load.py --mode live --vus 2 --requests 4 --base https://confit-a.vercel.app` → 0 errors, 8/8 `ibm/granite-4-h-small`.
6. Re-run the CI release gate; confirm the uptime monitor on `main` turns green.

**Do not release to production now** (S1 blockers are environmental and
outside this repository). **Merge PR #387 to the integration branch and deploy
to staging as soon as Neon is unlocked**, following
`docs/qa/MIGRATION_0047_0048_CHECKLIST.md` (0047+0048, owner role, Neon branch
backup, parity check), then re-run the mocked 20-VU load test against staging
and complete the Arabic native review. Production requires: Neon + Vercel
restored, staging soak clean, explicit written authorisation for the production
migration.
