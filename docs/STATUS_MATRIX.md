# CONFIT_A — Status Matrix

**Generated:** 2026-10-19 · **Workspace:** cloud workspace, clone of `OmarAhmed-123/CONFIT_A`
**Working branch:** `fix/wizard-reappearing` (the only branch)
**`main` head:** `b138c1e` — PR #364 **merged** 2026-10-20 (merge commit, not squash); previously `3d52d95` (PR #363) and `271b065` (PR #359)
**Commits:** `0763c8b` (Slice A code) · `1b70978` + `d8e050a` (matrix) · `5c909d7` (Slice C) · `4141`-test audit · `d446690` (SplashScreen timer fix) · this revision adds the dataset-selection record (§7A)
**Status vocabulary:** VERIFIED (ran & passed) · FAILED (ran & failed) · BLOCKED (cannot run — environment/policy) · NOT TESTED (not attempted / no surface)

> **Evidence rule (constitution Principle I):** every row cites something run or read. "Verified by running" and "verified by reading" are labelled distinctly. Implementation status and verification status are tracked separately. No value of any credential appears in this document.

---

## 0. Environment (measured, not assumed)

| Constraint | State | Evidence |
|---|---|---|
| Outbound egress | **Open.** `github.com`, `api.github.com`, `pypi.org`, `registry.npmjs.org`, `generativelanguage.googleapis.com`, `integrate.api.nvidia.com` all answered | HTTP probes returned 200/404 — i.e. reached the host |
| GitHub push / PR | **Works.** Branch updated `98af062..0763c8b`; PRs opened and closed over REST | `git push` exit 0, REST 200/204 |
| Database | **Local SQLite only.** No external database was contacted at any point | every migration ran against a disposable file under `/tmp` |
| Secrets | `/home/user/.env` — 80 vars, `chmod 600`, outside every git tree. Names mirrored in `.env.example` with empty values | `stat`, key-parity check |
| VCS persistence | The workspace **drops `.git` between turns** (working tree survives, history does not) | observed twice; repositories are re-cloned and every git action is completed inside a single call |

**This supersedes the previous revision of this section**, which asserted a restricted egress proxy and a blocked GitHub. Those statements were true of an earlier session's sandbox and are false here; the provider rows they produced are corrected in §1.

---

## 1. Credentials & providers — measured, with date

**Superseded by measurement.** This section previously carried results from an earlier session in which the sandbox's egress proxy denied every provider before any key was presented; those rows recorded the *proxy's* behaviour, not the credentials'. They are retired.

The live results now live in **[`docs/API_VERIFICATION.md`](API_VERIFICATION.md)** (run 2026-10-19 by the in-repo `backend/scripts/verify_provider_credentials.py`). Summary:

| Verdict | Count |
|---|---|
| `ok` | 30 |
| `shape_only` | 5 |
| `skipped` | 3 |
| `endpoint_unknown` | 3 |
| `not_configured` | 15 |
| `auth_failed` | **0** |

Three findings that change how the product should be described:

1. **No live payment path.** `LIVE_PSP_ADAPTERS` is empty and no PSP credential exists — checkout is demo-mode only. Spec 012 is a seam, not an integration.
2. **13 of 19 NVIDIA keys are configured under names the pool never reads** (shortened slugs such as `NVIDIA_API_KEY_CONTENT_SAFETY` vs `NVIDIA_KEY_NEMOTRON_3_5_CONTENT_SAFETY`). They are inert at runtime; the keys are valid, the names are the defect.
3. **Sentry and GlitchTip hold project keys, not DSNs**, so error tracking is not actually wired to an endpoint.

Previously-listed credential hygiene items that this run resolves or restates:

| Item | Standing |
|---|---|
| Brevo sender verification pending | **RESOLVED** — `GET /v3/senders` returns 1 active sender |
| `GITHUB_ACCOUNT_PASSWORD` == username | **OPEN** — owner action |
| Two `neondb_owner` passwords on file | **OPEN** — consolidate to one |
| `NVIDIA_API_KEY_ISING_CALIB_B` placeholder marker | **OPEN** — and that slot is one of the 13 unread names anyway |

**Correction to an earlier claim in this document:** it stated that `backend/scripts/verify_provider_credentials.py` did not exist. It **does** — added in `04539e2`, 934 lines, with its own test file. The earlier check was `ls backend/scripts/ | head -20`, and the file sorts 22nd of 25, so the listing truncated it. The "does not exist" conclusion was an artefact of the command, not of the repository, and it was never verified before being written down.

---

## 2. Onboarding wizard reappearing — the client half (PR #359, `98af062`)

**Root cause (verified by reading):** `UserProfileView.handleSaveQuiz()` POSTed the quiz and closed the modal but never refreshed `user`. Both gates — `AppRoutes.OnboardingGate` and the `UserProfileView` auto-open effect — keyed off `user.has_profile`, which the store only sets on login/`fetchMe` and caches in `localStorage.confit_user`. After completion the stale value kept re-triggering the wizard on every navigation/refresh until a full re-login.

| File | Change |
|---|---|
| `UserProfileView.tsx` | `await fetchMe()` after a successful `submitOnboardingQuiz`; dismissible `closeQuiz` for skip |
| `AppRoutes.tsx` | `OnboardingGate` exported and honours the session dismissal |
| `authStore.ts` | `isOnboardingDismissed` / `dismissOnboarding` / `clearOnboardingDismissed` — session-scoped, storage-safe, cleared on logout |

**VERIFIED at the time:** 33 frontend tests passed across the gate + dismissal + neighbouring auth-store suites; `tsc --noEmit` exit 0. **NOT TESTED:** click-through against a running browser (no deployed backend in this workspace).

---

## 3. Phase 0.2 · Slice A — server-side onboarding completion metadata (`0763c8b`)

### Why §2 was not enough

`has_profile` only means *"a `user_style_profiles` row exists"* — and that row is created by the **first saved field**. A shopper who opened the wizard, saved one budget value and closed it was `has_profile = true`: the route gate concluded "onboarded, never prompt" while the profile page's auto-open effect read the same partial state as "not onboarded". §2 stopped the client caching a stale `false`; it never gave the server a record of *completion*.

### Changes

| File | Change | Status |
|---|---|---|
| `backend/app/models/profile.py` | `onboarding_completed_at` (DateTime, nullable), `onboarding_version` (Integer, nullable) | IMPLEMENTED |
| `backend/app/core/config.py` | `ONBOARDING_WIZARD_VERSION = 1` — the single declaration of the wizard revision | IMPLEMENTED |
| `backend/app/repositories/profile_repository.py` | `create_or_update_profile` stamps flag + instant + version in one transaction | IMPLEMENTED |
| `backend/app/services/profile_service.py` | **Defect fix:** the helper defaulted `is_onboarding=True` and every split PATCH (`/me/budget`, `/me/size-fit`, `/me/brands`, `/me/style-profile`, …) called it without the keyword — a single budget field marked the whole wizard complete. Default is now fail-closed; only the two endpoints receiving a full `OnboardingQuizInput` opt in | BUG-VERIFIED → FIXED |
| `backend/app/schemas/auth.py`, `controllers/auth_controller.py` | `/auth/me` exposes the three fields; no profile → `false` / `null`, never assumed | IMPLEMENTED |
| `backend/alembic/versions/0040_onboarding_completion_metadata.py` | Additive, nullable; backfills `onboarding_version = 1` for completed rows and leaves the instant NULL | VERIFIED |
| `frontend/src/router/AppRoutes.tsx`, `views/consumer/UserProfileView.tsx`, `stores/authStore.ts`, `models/index.ts` | every gate keys on `onboarding_completed` | VERIFIED |
| `frontend/src/views/b2b/BrandRegistrationView.tsx` | brand accounts are `onboarding_completed: true` (never routed through the consumer wizard) | VERIFIED |

### Migration 0040 backfill policy

`onboarding_version = 1` is backfilled for rows already flagged complete — only v1 has ever existed, so that is a recorded fact. `onboarding_completed_at` is deliberately **left NULL**: the instant was never captured and `updated_at` is not it; filling it in would manufacture evidence.

### Evidence

| Check | Result |
|---|---|
| `pytest backend/tests/test_onboarding_completion_metadata.py` | **VERIFIED** — 5 passed |
| Neighbours: identity/profile, GDPR export, migration single-head, roundtrip, schema drift, release parity, API contract | **VERIFIED** — 155 passed, 1 skipped |
| `alembic upgrade head` on `sqlite:////tmp/migcheck.db` | **VERIFIED** — chain `0001 → 0040`, both columns present |
| `downgrade -1` → `upgrade head` | **VERIFIED** — columns dropped, restored, version round-trips to `0040` |
| Backfill assertion (seed a completed row at `0039`, then upgrade) | **VERIFIED** — `(completed, version, completed_at) = (1, 1, None)` |

### The regression tests that pin it

`test_profile_row_without_completion_is_not_reported_as_onboarded` — creates a profile row through a split PATCH and asserts `has_profile is True` **and** `onboarding_completed is False`. If anyone re-derives the gate from row existence, this fails.
`test_split_patches_do_not_complete_onboarding` — exercises four split PATCHes and asserts none stamps completion.
`onboardingGate.test.tsx` — "row exists but onboarding never completed → **still** redirects", plus "missing field (cached old session) → treated as not completed".

---

## 4. Test suites (current measurements)

| Suite | Command | Result |
|---|---|---|
| Backend, pristine `98af062`, before any edit | `PYTHONPATH=. CONFIT_IGNORE_DOTENV=1 pytest backend/tests -q` | **VERIFIED** — **4071 passed · 0 failed · 24 skipped** (652 s, exit 0) |
| Backend, full suite with this work | same | **VERIFIED** — **4076 passed · 0 failed · 24 skipped** (632 s, exit 0) — the +5 are the new Phase 0.2 tests |
| Frontend full gate | `npm run verify` (i18n → tsc → vitest → vite build) | **VERIFIED** — i18n ✓ · tsc ✓ · **142 test files pass** · build ✓ · exit 0 |

**A previous revision recorded 40 backend failures / 24 skips.** They did not reproduce on the identical commit in this workspace: all 40 were consequences of the restricted proxy described in the old §0 (VTON image fetches, provider calls, a missing headless-GL library surfaced only under that configuration). This is an environment difference, **not evidence that those defects do not exist** — re-run the suite under a restricted-egress configuration before drawing a conclusion about them.

**One test needed a conscious expectation update, not a loosening:** `test_flow_e_purchase_to_wardrobe.py::test_migration_chain_has_a_single_head_at_0036` pins the Alembic head. `0040` moves it — the exact event that test exists to force a human to document — so the assertion and the chain rationale were extended to `0040` with its reason. No assertion was deleted, skipped, or made permissive.

---

## 4A. Slice C — external integration verification (2026-10-19)

**What it is:** the in-repo read-only verifier was confirmed (it exists — see the correction in §1), extended to cover the payments seam and three missing credential spellings, and run live. Results and per-service rows: **[`docs/API_VERIFICATION.md`](API_VERIFICATION.md)**.

| Check | Command | Result |
|---|---|---|
| Verifier unit suite | `pytest backend/tests/test_verify_provider_credentials.py` | **VERIFIED** — **42 passed** (17 pre-existing + 25 added) |
| Those tests actually catch the defects | same suite against the pre-change script | **VERIFIED** — 9 fail on the old code, 0 after |
| Live run | `python3 backend/scripts/verify_provider_credentials.py` | **VERIFIED** — 30 ok · 5 shape_only · 3 skipped · 3 endpoint_unknown · 15 not_configured · **0 auth_failed** |
| No mutating call in the tool | `test_the_verifier_contains_no_mutating_http_call`, `test_smtp_probe_never_sends_a_message`, `test_no_probe_in_the_payments_group_mutates` | **VERIFIED** |
| No value in any output | `test_render_prints_names_and_fingerprints_but_never_values`, `test_the_json_report_carries_no_value`, `test_configured_names_never_returns_values` | **VERIFIED** |

### Defects fixed (each with a regression test)

1. **Neon DSN slot names reversed** — the table expected `DATABASE_URL_NEONDB_OWNER`, the operator stores `DATABASE_URL_OWNER_NEONDB`; 4 of 5 rows reported "not configured" for configured DSNs.
2. **RunPod credentials sent to the AWS endpoint** — both S3 targets shared `AWS_ENDPOINT_URL_S3`, producing a false `auth_failed` for a credential that was never tested against its own host.
3. **Brevo sender check misread the payload** — `{"senders": [...]}` was read as a bare list, so an account with one active sender reported none. (This one was introduced and caught inside this slice.)
4. **Three operator spellings invisible** — `GLITCHTIP_TOKEN`, `CONFITHUB_API_KEY`, `SENTRY_DSN_TOKEN`.
5. **No payments coverage at all** — the payments seam had no probe.

### Honest limits

No message was sent, no object uploaded, no DNS record touched, no GPU job started, no production row written (the Neon probes are `select current_database(), version()`). Model slugs were not individually validated — that needs a billed inference call, which is not read-only.

---

## 5. Database safety

- Automated tests ran on **local SQLite only**.
- Every migration in this work ran against a disposable file under `/tmp`; `backend/data/confit.db` was not modified.
- **Nothing was written, migrated, or seeded against any external database** in Slices A–C.
- **Exception, owner-authorized:** migration `0040` was applied to production `neondb` on 2026-10-19 as `neondb_owner`, after a logical snapshot of `user_style_profiles` (5 rows, sha256 recorded) and with the tested `downgrade -1` path available. That is the only production write in this engagement.
- Slice C's Neon probes are read-only (`select current_database(), version()`) against all four configured DSNs.
- No seed data, no production schema change, no production mutation.

---

## 6. Security

- Secret guard (`scripts/check-secrets.sh`) run in `staged` mode before commit and `push` mode before push: **clean** — no literal credential in either scope.
- `.env` is git-ignored, `chmod 600`, and outside every git tree; `.env.example` carries the 80 names with values stripped.
- `gitleaks` runs in CI and is **green** on `0763c8b`.
- The guard itself was corrected twice while doing this work: the Resend-key pattern (`re_…`) was anchored to a token boundary after it false-positived on Python test names, and the pre-push hook was moved from a whole-tree scan to the actual push range (`80 .env values × N files` made the tree scan minutes long and blocked pushes by timeout).
- **Exposure/rotation:** credentials supplied earlier in this engagement were pasted into chat → treat as exposed, rotate after the engagement. Not performed here; owner's decision.

---

## 7. Delivery (this workspace)

| Item | State |
|---|---|
| Branch | **one branch: `fix/wizard-reappearing`** |
| Slice A consolidation | `98af062..0763c8b`, a **fast-forward** (checked with `git merge-base --is-ancestor` before sending) |
| Production migration | `0040` applied to `neondb` as `neondb_owner`; `alembic current` 0039 → **0040**; logical snapshot taken first |
| PR #359 | **merged** as a merge commit — `main` `6636356` → **`271b065`**, parents `6636356` + `d8e050a` |
| Merge method | `merge` (not squash, not rebase); branch **retained** |
| PR #360 | closed; it was opened from a second branch, which broke the one-branch rule |
| Branch resync | `git fetch origin && git merge origin/main` → fast-forward to `271b065` |
| Commit identity | `OmarAhmed-123 <omarsafealden@gmail.com>`; no `Co-authored-by`, no AI attribution |
| Token handling | askpass helper; the token never appears in a URL, `.git/config`, or any file |

### Checks on `main` at `271b065` (post-merge, by SHA)

`backend` **success** · `frontend` **success** · `release gate (production schema parity)` **success** · `postgres migration chain + schema gate` **success** · `production parity (deployment contract)` **success** · `gitleaks` **success** · `stylist drawer browser gate` **success** · `Vercel Preview Comments` **success** · `Workers Builds: confit-a` **failure — non-required**, an external Cloudflare pipeline with no definition in this repository.

## 7A. Catalog track · Slice 1 — dataset selection (licence-first), 2026-10-20

**Scope:** documentation only. No data imported, no `backend/app` change, no migration.
Full analysis, verbatim licence quotes and the sign-off block live in
**[`docs/DATASETS.md`](DATASETS.md)**.

| Item | Decision / finding | Status |
|---|---|---|
| **Dataset decision** | **Unsplash License** recommended as the image basis, **Pexels License** as approved secondary. Both are irreversible-but-irrevocable commercial grants and both are already the source of the 50 stock images in production | **DECIDED (proposed)** — awaiting owner sign-off on `DATASETS.md` §8 |
| Rejected — non-commercial | DeepFashion (CUHK): "available for **non-commercial** research purposes only"; forbidden to "sell, trade, resell or exploit for any commercial purposes… any portion of the images and any portion of derived data" | **REJECTED** (licence) |
| Rejected — competition-only | H&M Personalized Fashion Recommendations (Kaggle): "**DATA ACCESS AND USE**: Non-Commercial Purposes & Academic Research" | **REJECTED** (licence) |
| Rejected — unsafe provenance | Fashion Product Images (Small): Kaggle licence field says "MIT", but the images are scraped retailer photography carrying third-party brands; the uploader holds no rights to license | **REJECTED** · **NEEDS-OWNER-CONFIRM** |
| Unresolved | Fashionpedia: no dataset-level licence; rights are per-image via a COCO `licenses` array. Its **ontology** (27 categories / 294 attributes) is reusable as a vocabulary; its **images** need per-image triage | **NEEDS-OWNER-CONFIRM** |
| Rejected — fit | Fashion-MNIST: MIT and clean, but 28×28 greyscale with no price/URL/SKU field | **REJECTED** (fit) |
| Catalog state (measured read-only, production) | 12 products = 9 seed + 3 via the real import path (`brand-<id>-<hash>` slug); 28 SKUs; 54 `product_images` (50 stock / 4 generated); 6 categories; all prices USD 75–395; `alembic_version` = `0040` | **VERIFIED by querying** (read-only transaction) |
| Import path to reuse | `BrandCatalogService` (`preview_csv`/`process_csv_import`/`process_json_import`/`import_products`) behind `require_brand_access("catalog:write")` — **not** raw SQL | **VERIFIED by reading** |
| Blocking constraint | Import writes only `Product.thumbnail_url`/`images`; it **never** writes `product_images`, so provenance + the 4:5/1:1/3:2/16:9 ladder are absent for imported rows | **VERIFIED by reading** |
| Blocking constraint | CSP `img-src` allows only `self`, `data:`, `blob:`, unsplash, pexels, placehold.co and the Neon bucket — any other host needs a policy change | **VERIFIED by reading** (`vercel.json:43`) |
| Defect found (not fixed — out of scope) | `generate_sample_csv()` emits categories `shirts`/`trousers` which do not exist, so 2 of the template's own 4 sample rows fail validation; the error hint repeats the same non-existent slugs | **VERIFIED by reading** (`brand_catalog_service.py:173,713,719` vs `seed_data.py:194-201`) |
| Defect found (not fixed — out of scope) | `send_notifications` defaults to `True` on the CSV import route — a bulk load would email customers unless explicitly disabled | **VERIFIED by reading** (`brand_controller.py:474`, `brand_catalog_service.py:546`) |

**No import work begins until `DATASETS.md` §8 questions 1 and 2 are answered.**

## 8. Known limitations & open items

1. **Live browser E2E — NOT TESTED.** No deployed backend or browser in this workspace. Wizard behaviour is covered by unit/API-integration tests and by reading, not by a click-through.
2. **No live payment path.** `LIVE_PSP_ADAPTERS` is empty and no PSP credential exists — checkout is demo-mode only (spec 012 is a seam). Buying a key would not fix this; the adapter does not exist.
3. **13 of 19 NVIDIA keys are inert** — configured under names the pool never reads (see `docs/API_VERIFICATION.md` §3.2). Valid keys, wrong names; a config change, not a code change.
4. **Error tracking is not wired to an endpoint** — Sentry and GlitchTip hold project keys, not DSNs.
5. **`npm audit`: 8 vulnerabilities (2 moderate, 6 high)** — measured on the committed lockfile. Not addressed.
6. **`Workers Builds: confit-a`** — external to the repo (no `wrangler.*`, `_worker.js`, `_routes.json`, `functions/`); owner action in Cloudflare.
7. **Three provider read-only surfaces are unusable from here** — Cerebrium 502, FitRoom 503, DNSHE 404. Nothing established about those keys in either direction.
8. **PR #358** remains open by the owner's instruction.
9. **Model slugs were not individually validated** — that requires a billed inference call per model, which is not read-only.

---

## 9. Accessibility phase 3 — portals, preferences, reflow (2026-10-21)

**Appended, not substituted.** Sections 0–8 above are the state at their own
dates and are left as they were; several are now superseded (the branch ledger
in the header, for instance — `main` has moved to `eb02668` and PR #365 is
merged and deployed). This section records only what phase 3 measured.

**Tested candidate:** `1db39b2` on `work/production-hardening`, rebased onto the
integration head `43377d8`. **Environment:** local build served from
`127.0.0.1:43124` with `/api` proxied to a local API on the **verify database**
(`confit_fixverify`, revision `0045_brand_verified_domains`) — not production.
Engines: Chromium 156.0.8078.4, Firefox 157.0, WebKit 27.2.

| Area | State | Evidence |
|---|---|---|
| Portal reflow at 320×640, en+ar, 3 engines, 8 brand + 4 admin routes + guest gateway + refusal | **VERIFIED** — 90 loads, 0 horizontal overflow, dir correct per locale, exactly one `h1` | `a11y/p3.final.{ff,wk,cr}320.reflow.json`; a 48px overflow on `/b2b` was found and fixed in `a89c1e8` |
| Portal target geometry (SC 2.5.8) | **VERIFIED** — 1,644 controls across those loads; **0** failures. 84 nodes are under 24px and rely on the spacing exception; three distinct controls account for them, each identified (`p3.undersized-nodes.json`) | `a11y/p3.final.*.targets.json`, `evidence/target-size-summary.json` |
| Reduced motion (`prefers-reduced-motion: reduce`) | **VERIFIED by emulation** — 8 routes: 9 animated elements and 11 running animations at `no-preference` → **0 / 0** at `reduce`; no content hidden | `a11y/p3.preferences.json` |
| Forced colours (`forced-colors: active`) | **VERIFIED by emulation only** — 4 routes, focus ring survives system colours (solid outline 2–3px). **No real Windows High Contrast run.** | `a11y/shots/p3-prefs/forced-colors-*.png` |
| 200% zoom on a portal dialog | **VERIFIED** — 640×400 CSS viewport, dialog opens, 11 controls reachable, no horizontal overflow | `a11y/shots/p3-prefs/zoom200-dialog.png` |
| Public axe matrix (15 routes × en/ar × desktop/mobile × 3 engines) | **VERIFIED** — 180 loads, **0** WCAG A/AA violations; 180 keyboard probes with no step missing a focus ring | `a11y/results.p3.{chromium,firefox,webkit}.json` |
| Authenticated axe matrix (12 routes + 2 negative controls) | **VERIFIED** — 14/14 clean, one `h1` each, no heading-level skips | `evidence/auth-routes.json` |
| Browser journeys: catalogue/empty state, PDP, wishlist | **VERIFIED** — 13/13 steps | `a11y/p3.journeys.json` |
| Screen reader (NVDA / JAWS / VoiceOver) | **BLOCKED** — no display server (`DISPLAY` unset), no AT-SPI, no dbus, no Orca; NVDA/JAWS need Windows, VoiceOver needs macOS/iOS. Not attempted, not passed. | `orca: not installed`; environment probe |
| Real iOS / Android devices | **BLOCKED** — no physical device and no device-farm credentials | — |
| Workers Builds: confit-a | **FAIL** — fails in **0 s** with 0 annotations (no compilation occurs), on the integration base `43377d8` as well as on this branch; succeeds on `main` `eb02668`. Cause not established: the Cloudflare build log needs credentials this workspace does not have. **Not attributable to this PR; unresolved.** | check-run `output`, `annotations_count: 0` |

**Defects found and fixed in phase 3**

1. `a89c1e8` — `/b2b` scrolled horizontally 48px at 320px (WCAG 1.4.10). Root
   cause in two layers: `grid-cols-12` unprescribed below `lg` (eleven 32px gaps
   = 352px in a 320px viewport) **and** `col-span-12` children, which create
   twelve implicit columns of their own. Both fixed; the regression test fails
   on the previous commit and pins both layers.
2. `1db39b2` — `/b2b/analytics` rendered "Reset Filters" in English on the
   Arabic page, although `bi.reset_filters` existed in both locales unused; the
   control was also a 72×16 target relying on the spacing exception.

**Measurement corrections made in this phase** (recorded because each one
briefly produced a wrong number): horizontal overflow must be measured against
`window.innerWidth`, not `clientWidth` (a scrollbar made WebKit report a
phantom 5px with no offending element); the accessible name must be read from
the computed tree, not `aria-label || textContent` (the card image link's name
comes from its `img alt`); and the wishlist is device-local by design, so
asserting 401 on a wishlist endpoint tested an endpoint the product
deliberately does not have.

## 10. Phase 4 — accessibility, performance, E2E and release readiness (2026-10-21)

**Tested candidate:** `ce74577` + the fix below, on `work/production-hardening`.
**Environment:** local build served from `127.0.0.1:43124` (gzip) with `/api`
proxied to a local API on the **verify database** (`confit_fixverify`, revision
`0045_brand_verified_domains`). Performance numbers are **laboratory** numbers
from this host; they are not field data and not production latency.

### 10.1 Performance baseline

The repository has **no performance tooling at all** — no Lighthouse config, no
`web-vitals` dependency, no budgets, no perf job in CI. There is therefore no
existing threshold to pass or fail; the numbers below are a baseline, and any
target would be a *proposal*, not a requirement.

Lab baseline (Chromium 156, 412×915, cold cache, n=3, gzip, median):

| Route | Condition | FCP | LCP | CLS | JS transfer | Long tasks / blocking |
|---|---|---|---|---|---|---|
| `/` | unthrottled | 536 ms | 1,096 ms | **0.759** | 469 kB | 1 / 3 ms |
| `/` | Fast-3G + 4×CPU | 3,280 ms | 3,892 ms | **0.8984** | 469 kB | 8 / 351 ms |
| `/discover` | unthrottled | 576 ms | 668 ms | 0.0097 | 469 kB | 0 / 0 ms |
| `/discover` | Fast-3G + 4×CPU | 3,284 ms | 4,520 ms | 0.0092 | 469 kB | 7 / 282 ms |
| `/product/silk-slip-column-maxi-dress` | unthrottled | 476 ms | 2,200 ms | 0.0118 | 469 kB | 0 / 0 ms |
| `/product/silk-slip-column-maxi-dress` | Fast-3G + 4×CPU | 3,136 ms | 5,188 ms | 0.0116 | 469 kB | 0 / 0 ms |

Bundle: **1,833 kB raw JS (479 kB gzip)**, of which `index-*.js` is 1,428 kB raw
(367 kB gzip), `vendor-react` 174 kB (59 kB gzip), `vendor-ui` 142 kB (46 kB
gzip). CSS 135 kB raw.

**BUG-VERIFIED — CLS 0.759 on `/` is a real defect, not a harness artefact.**
Cross-checked with Google's `web-vitals` attribution build (0.8088 at t=1557.6 ms)
and isolated by ablation: aborting only `/api/v1/catalog/capabilities` drops CLS
to **0.0147** (−98%). The announcement bar renders only after that response
arrives (~1.5 s locally), inserting a 46 px block into the flow above the hero;
margin collapsing then moves the 10,456 px content container by a further −24 px.
Production publishes a threshold too (13,622.21 EGP) and that endpoint answers in
~1.2 s there, so the same gate exists in production. **Not fixed:** every
available remedy is a product decision — reserve the bar's height (shows an empty
strip while loading and collapses when a deployment has no policy), overlay it
(detaches it from the layout), or make the threshold available before first
paint. Recorded for owner decision rather than changed unilaterally.

### 10.2 Backend baseline (§9)

390 read-only requests against the local API (seeded verify DB, remote Neon, no
chargeable operation):

| Endpoint | c | n | p50 | p95 | p99 | rps | errors |
|---|---|---|---|---|---|---|---|
| `/health` | 1 | 25 | 606 ms | 612 ms | 5,241 ms | 1.18 | 0 |
| `/catalog/products?limit=20` | 1 | 25 | 761 ms | 903 ms | 904 ms | 1.25 | 0 |
| `/catalog/products/…` | 1 | 25 | 910 ms | 954 ms | 1,029 ms | 1.09 | 0 |
| `/catalog/brands` | 1 | 25 | 2,256 ms | 2,384 ms | 2,434 ms | 0.44 | 0 |
| `/catalog/categories` | 1 | 25 | 456 ms | 467 ms | 477 ms | 2.19 | 0 |
| `/health` | 8 | 40 | 608 ms | 8,219 ms | 11,040 ms | 3.12 | 0 |
| mixed, 6 endpoints | 8 | 40 each | — | — | — | 5.39 aggregate | 0 |

DB: 1.19 transactions per request, 133 tuples returned per request. Error and
timeout rate **0** across all 390 requests; no invalid payloads.

**Caveat that governs the whole table:** the database is Neon, reached from this
sandbox over the public internet, and `pool_pre_ping` is enabled for a
long-running server, so *every* request pays extra round trips. `/health` at
606 ms is the round-trip cost, not server compute. These numbers describe this
host and rank endpoints against each other; they do not describe production
latency. `/catalog/brands` is the one clear outlier (p50 2.3 s, ~3.7× the next
slowest) and is worth profiling on its own.

### 10.3 Browser journeys (scenarios 5, 6, 7, 10)

| Scenario | State | Evidence |
|---|---|---|
| 5 Fit Finder — rejects implausible measurements, never guesses | **VERIFIED** — height 999 → "Must be 100–250 cm" + "Fix the highlighted measurement fields first", no size shown | `a11y/p4.journeys.json` E2E-5a |
| 5 Fit Finder — real recommendation | **VERIFIED** — the engine returned an honest **refusal** (not a size) for the seeded product, with the refusal footer and a live region | E2E-5b |
| 5 Visual search — real UI flow | **VERIFIED** — card → modal → photo-consent ("I agree — process this photo") → matches, with the banner "Vision analysis is unavailable right now — showing catalog matches without image detection" | `a11y/p4.scen5-6.json` |
| 6 Media upload — success path | **BLOCKED** — `photo_upload_available: false` locally; in production it is `true` with `storage_mode: s3`, so a real upload would write to the project bucket and run a paid vision model | `a11y/p4.scen5-6.json` |
| 6 Media upload — endpoint capability agreement | **BUG-VERIFIED** — `POST /wardrobe/upload` returned **201 created** while `/catalog/capabilities` reported `photo_upload_available: false` and `storage_mode: local`. The flag is advisory; the endpoint does not enforce it, so a deployment that advertises no durable storage still accepts writes it cannot keep. | `a11y/p4.scen5-6.json` |
| 7 Analytics — no prior baseline | **VERIFIED** — 5 `growth-basis-*` chips reading "No prior-period baseline" on the seeded brand | E2E-7a |
| 7 Analytics — genuine empty tenant | **VERIFIED** — Arket (0 products, 0 orders) shows `empty-catalogue` "No products in your catalogue yet" and 3 chips reading "No activity in either period"; `return_rate` is `null`, not `0` | E2E-7b |
| 7 Analytics — real zero vs null | **VERIFIED** — same tenant reports `discount_total: 0.0` and `returned_units: 0` as zeros while `return_rate` is `null`; the UI does not collapse the two | `p4.journeys.json`, `p4.scen5-6.json` |
| 10 Failure + recovery | **VERIFIED** — 3 `/catalog/products` requests aborted at the transport layer → "The catalog couldn't be loaded" + Retry; after unblocking, Retry loaded 54 product links and the error cleared | E2E-10 |

Scenarios 1–4, 8 and 9 remain as closed in Phase 3 (`a11y/p3.journeys.json`,
13/13) plus pytest coverage; they were not re-run.

**Defect found and fixed — `imageUpload.ts` rejected every small image.**
The retry loop guarding `compressImageToDataUrl` is `while (dim >= MIN_DIM)` with
`MIN_DIM = 256`, so for any image whose longest edge is under 256 px the body
never executed once and the function fell through to
`errors.image_compression_failed` — telling the user an 8,277-byte PNG "could not
be compressed small enough to upload safely". Found by driving visual search in a
browser; the client-side guard, not the network, was failing. Fixed by letting the
first pass always run (`|| passes === 0`), which leaves every image ≥ 256 px
byte-for-byte identical in behaviour and still fails honestly if a small image
cannot fit. Regression test added; it fails on the previous revision at
`imageUpload.ts:188` and passes after. `npm run verify` **EXIT 0**, 154 files,
**2,282 tests**.

### 10.4 Still unverified

| Item | State |
|---|---|
| NVDA / JAWS / VoiceOver (macOS + iOS) / TalkBack / Orca | **BLOCKED** — unchanged from Phase 3: no display server, no AT-SPI, no dbus, no Orca, no Windows/macOS/iOS host |
| Real iOS / Android hardware | **BLOCKED** — no devices, no device farm |
| Forced colours on real Windows High Contrast | **NOT TESTED** — emulation only |
| INP / real-user field data | **NOT TESTED** — requires production RUM, which does not exist |
| Media-upload success path | **BLOCKED** — see 10.3 |
| CLS fix on `/` | **NOT FIXED** — defect documented, remedy requires a product decision |
