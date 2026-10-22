# CONFIT_A — Audit Findings

Running list. Severity: **P0** outage/security/data-loss · **P1** broken core flow ·
**P2** degraded/incorrect/parity · **P3** polish. Status: Open / Fix-in-flight /
Fixed / Won't-fix. All claims are evidence-backed (command output or source read);
items not yet executed are marked PENDING.

Date opened: 2026-10-22.

---

## F-001 — Production API is down: Neon database over quota (P0, Open)
- **Where:** production `https://confit-a.vercel.app/api/*` (all data endpoints).
- **Repro:** `curl https://confit-a.vercel.app/api/v1/products?limit=1` → HTTP 503.
- **Expected/Actual:** expected 200 with products; actual `503 DATABASE_UNREACHABLE`.
- **Evidence (503 body):** `pg8000.dbapi.ProgrammingError … SQLSTATE 53000: "Your
  account or project has exceeded the quota. Upgrade your plan to increase limits."`
  `verdict=unreachable; expected_head=0046_user_wishlist_items`.
- **Root cause:** the Neon Postgres project exceeded its plan quota and refuses
  connections. The app's schema gate correctly returns `unreachable` and the
  request guard fails closed with an honest 503. **Not a code defect.**
- **Fix:** owner action on Neon (restore/upgrade/raise quota). Behind approval gate
  (spend/paid tier/production infra). Blocks the `release gate` CI check on every PR
  until resolved, so no PR can merge meanwhile.

## F-002 — /health returns opaque 500 when the database is unreachable (P1, Fix-in-flight)
- **Where:** `GET /api/v1/health` (`backend/app/controllers/telemetry_controller.py`,
  `backend/app/services/capability_service.py`).
- **Repro:** with the DB unreachable (F-001), `/api/v1/health` → HTTP 500, empty body;
  `/api/v1/health/ready` and data endpoints correctly return structured 503.
- **Root cause:** `capability_probes()` ran `db.query(StoreLocation).count()`
  (click_and_collect) unguarded; a dead DB raised there and escaped to the generic
  500 handler — defeating the design intent that `/health` names the cause.
- **Fix:** guard the store-count query (skip when DB down; catch mid-probe death),
  degrade `click_and_collect` to blocked-with-reason. `/health` now returns
  `status=unhealthy, ready=false, blocking=[database]`.
- **Status:** committed on `fix/health-db-unreachable-500`, pushed, **PR #376**;
  2 regression tests added; 74 local tests green. Merge blocked by F-001 (release gate).

## F-003 — Backend suite cannot be collected on Windows (UTF-8/parity) (P2, Fix-in-flight — PR #377)
- **Where:** `backend/tests/test_fit_engine_acceptance.py:41` (and
  `test_suite_engine_contract.py`, which imports it).
- **Repro:** `python -m pytest backend/tests -q` on Windows →
  `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81` during collection →
  **exit 2, zero tests run**. Passes with `PYTHONUTF8=1` or on Linux/CI.
- **Root cause:** `FIXTURE.read_text()` with no `encoding=` uses the platform default
  (cp1252 on Windows) instead of UTF-8.
- **Fix (proposed):** add `encoding="utf-8"` to the fixture reads. Small, safe parity
  fix. Violates "a clean clone runs locally" until fixed.

## F-004 — release gate blocks all PRs while production is down (P2, Open; consequence of F-001)
- **Evidence:** PRs #372, #358, #376 all show `release gate (production schema parity)`
  = failure; core `backend`/`frontend` checks pass. The gate reads production
  `/api/v1/health`, which is down.
- **Note:** expected fail-closed behaviour; clears itself once F-001 is resolved. No
  code change needed. Recorded so the merge block is not mistaken for a PR defect.

## F-005 — Duplicate try-on route families: /try-on/* and /tryon/* (P3, Open)
- **Evidence:** OpenAPI shows both `/api/v1/try-on/*` and `/api/v1/tryon/*` (≈20 ops
  duplicated), plus the app mounts every router at `/api/v1`, `/v1`, and bare.
- **Impact:** larger contract surface; two canonical spellings for the same feature.
  Likely an intentional alias — confirm which the frontend consumes and whether the
  alias is still needed. PENDING confirmation against frontend API client.

## F-006 — AGENTS.md is stale about the migration head (P3, Fix-in-flight — PR #377)
- **Evidence:** `AGENTS.md` §3 states "repo head is 0034" and "no Alembic migration
  file exists for the planned workstreams yet." Tree is at `0046_user_wishlist_items`.
- **Fix:** reconcile AGENTS.md with the real migration state.

## F-007 — Frontend vitest: 11/2325 failing locally (P3, PENDING classification)
- **Evidence:** `npm run verify` → vitest `11 failed | 2314 passed (2325)`, 8 files,
  plus 4 "Failed to start forks worker — Timeout waiting for worker to respond".
  Failure texts are `Test timed out in 5000ms` and worker-startup timeouts.
- **Assessment:** signature of resource starvation on a loaded local Windows box, not
  assertion failures; the authoritative CI `frontend` check is currently green. To be
  confirmed by re-running the 8 files single-threaded with a higher timeout. Not yet
  classified as a real regression.

## F-008 — Frontend dev toolchain has known vulnerabilities (P3, Open)
- **Evidence:** `npm audit` reports 12 advisories (5 moderate, 7 high) in dev-only
  packages: `vitest` / `@vitest/mocker` / `@vitest/coverage-v8` (code injection via
  manual mock registration; Windows backslash traversal) and `vite` 8.2.0–8.2.2
  (dev-server middleware / `server.fs` exposure).
- **Scope:** dev/build-time only — none ship in the production bundle.
  `npm audit --omit=dev --audit-level=high` (the CI gate) reports **0**, and
  `vite build` succeeds; `pip-audit` on backend deps is clean.
- **Fix (proposed):** bump vite/vitest to patched releases and re-check. Low urgency.

## F-009 — Virtual try-on is not live in production: GPU worker not deployed (P1, Open)
- **Where:** production; `VTON_WORKER_URL` unset → `tryon_service.py` raises
  `VTON_ENGINE_UNAVAILABLE`.
- **Evidence:** `GET /api/v1/try-on/capabilities` → `VTON_ENGINE_UNAVAILABLE`;
  `/health` lists `virtual_try_on` in `blocking_capabilities` (pre-F-001).
- **Root cause:** the commercially-clean `fashn_vton_segfee` worker (code present and
  GPU-proven, `MODEL_REGISTRY.json`) is not deployed and no worker URL is configured.
  Honest 503 by design — a deployment gap, not a code defect, but try-on is a headline
  feature so it is P1.
- **Fix:** deploy the Modal worker and set `VTON_WORKER_URL` (approval gate: GPU/spend;
  also blocked behind F-001). Plan: `docs/tryon/00-research-plan.md` §10.

## F-010 — Deployment-manifest test hardcodes a POSIX PATH → fails on Windows (P2, Fix-in-flight — PR #379)
- **Where:** `backend/tests/test_deployment_dependency_manifest.py::test_cli_exit_code_zero_on_current_tree`.
- **Repro:** run that file on Windows → `TypeError: argument of type 'NoneType' is not iterable`
  (`proc.stdout` is None), plus a `UnicodeDecodeError: 0x97` in the subprocess reader thread.
- **Root cause:** the test spawns `check_runtime_imports.py` with
  `env={"PATH": "/usr/bin:/bin:/usr/local/bin"}` — a Linux-only PATH — so the child can't
  resolve its environment on Windows and its stdout is never produced/decodable. Same
  local/cloud parity class as F-003. CI (Linux) is unaffected.
- **Fix (proposed):** inherit/compose the real PATH instead of hardcoding POSIX, and decode
  subprocess output as UTF-8 with explicit error handling. Test-only.

## F-011 — Dead-broker enqueue latency exceeds threshold on Windows (P3, Fix-in-flight — PR #379; documented Windows skip, guard still runs on CI)
- **Where:** `backend/tests/test_broker_unavailable_latency.py::test_enqueue_against_dead_broker_fails_in_seconds`.
- **Repro:** on Windows, `auto_tag_wardrobe_task.delay(1)` against a down Redis took **16.8s**
  (threshold `<8s`); observed Celery "Retry (0/2), (1/2)" then give up. CI (Linux) passes.
- **Assessment:** Celery/redis-py connection-retry timing differs on Windows. The product's
  serverless path uses a 1s broker probe (`WARDROBE_ANALYSIS_MODE=auto`), so this raw
  `.delay()` timing is a test-environment measurement, not the production fast-fail path.
  Classify as local-env/timing; confirm against CI. Not a confirmed product regression.

---

## Discrepancies vs the brief (code is the source of truth)
- Open PRs = 2 pre-existing (#372, #358), 0 open issues (brief implied five PRs).
- AI stylist providers are not only Groq/Gemini/OpenAI: chain is
  `local_gpu,nvidia,groq,gemini,openai,unorouter` plus an NVIDIA NIM key pool,
  UnoRouter, a self-hosted vLLM leg, and a Qwen2.5-VL vision worker.
- Payment PSPs: Stripe, Tabby, Tamara **plus Paymob and Fawaterak** (5 adapters).
- Worker services: 8 (vton, wardrobe, anthropometry, tagging, outfit, catalog,
  moda-embed, vlm), not just the VTON worker.
- Production DB driver is pg8000 (serverless) vs psycopg2 (Docker/CI) — by policy.
