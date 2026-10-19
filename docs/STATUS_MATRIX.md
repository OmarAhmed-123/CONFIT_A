# CONFIT_A — Status Matrix

**Generated:** 2026-10-19 · **Session:** cloud workspace (read-only clone of `OmarAhmed-123/CONFIT_A`, branch `main`)
**Status vocabulary:** VERIFIED (ran & passed) · FAILED (ran & failed) · BLOCKED (cannot run — environment/policy) · NOT TESTED (not attempted / no surface)

> **Evidence rule (constitution Principle I):** every row cites something run or read. "Reviewed by reading" and "Verified by running" are labelled distinctly. No value of any credential appears in this document.

---

## 0. Environment constraints that shape this matrix

| Constraint | State | Effect |
|---|---|---|
| Outbound egress | Allowlisted proxy; **only Gemini (`generativelanguage.googleapis.com`) reachable** | All other live provider checks are BLOCKED by `403 CONNECT` policy denial or DNS refusal — not by bad keys |
| GitHub (push/PR/merge) | **BLOCKED** — account not linked to session (`add_repo push` → "link your GitHub account"); PAT also rejected via proxy | Deliverable is a **patch**, not a PR |
| Database | SQLite (local) only; Neon unreachable (DNS) | All tests on disposable SQLite; **no production DB touched** |
| Secrets | `backend/.env` (73 vars) + `/home/user/confit-secrets/env.secrets`, both git-ignored, `-rw-------` | Tracked-file secret scan: **clean** |

---

## 1. Credentials & providers (read-only verifier: `backend/scripts/verify_provider_credentials.py`, from `backend/.env`)

| Provider / capability | Configured | Live result | Cause / evidence |
|---|---|---|---|
| **Gemini** (vision + stylist) | ✅ | **VERIFIED (PASS)** | `generateContent` on `gemini-flash-latest` → HTTP 200; auth + model + endpoint OK |
| NVIDIA NIM pool (19 model slots) | ✅ 19/19 canonical `NVIDIA_KEY_<MODEL>` | **BLOCKED** | `integrate.api.nvidia.com` → 403 CONNECT policy denial (key never reached provider) |
| OpenAI | ✅ | BLOCKED | `api.openai.com` 403 policy denial |
| Groq | ✅ | BLOCKED | 403 policy denial |
| UnoRouter / OpenRouter | ✅ | BLOCKED | host(s) unreachable (403) |
| Neon Postgres (4 role DSNs) | ✅ | BLOCKED | DNS `Name or service not known` (raw TCP egress not permitted) |
| Neon S3 / RunPod S3 | ✅ | BLOCKED | proxy connect error / host denied |
| Brevo (API + SMTP), Resend | ✅ | BLOCKED | 403 policy denial / SMTP DNS refusal |
| FX (exchangerate, fixer) | ✅ | BLOCKED | 403 policy denial |
| Sentry, BetterStack | ✅ | BLOCKED | 403 policy denial |
| HuggingFace, Kaggle | ✅ | BLOCKED | 403 policy denial |
| Baseten, Cerebrium, RunPod (GPU) | ✅ | BLOCKED | 403 policy denial |
| Vercel | ✅ | BLOCKED | 403 policy denial |
| Dynu (DNS) | ✅ | BLOCKED | 403 policy denial |
| Modal | ✅ (id+secret+secure token) | NOT TESTED | no public REST surface; needs `modal app list` |
| GlitchTip | ⚠ project key only | NOT TESTED | needs full DSN `https://<key>@<host>/<project>` |
| DNSHE, DigitalPlat, confit-HUB, FitRoom | ⚠ present | NOT TESTED | no documented read-only endpoint in repo |
| GitHub | ✅ PAT present | BLOCKED | session not linked; PAT rejected via proxy |

**Fingerprint-collision recheck:** the verifier's "same value in two slots" for `GITHUB_TOKEN`/`AWS_ACCESS_KEY_ID` is a **false positive** — full SHA-256 differ (`76c8376d…` vs `eb44d8c7…`, lengths 93 vs 41). Distinct credentials; the 8-char fingerprint prefix coincided. (Minor verifier bug: fingerprint prefix too short.)

**To unblock live verification:** add these hosts to the environment's Allowed domains (or raise the access level): `integrate.api.nvidia.com`, `api.openai.com`, `api.groq.com`, `*.neon.tech`, `api.brevo.com`, `api.resend.com`, plus any others above you want validated.

---

## 2. Onboarding wizard reappearing bug — FIXED (frontend regression VERIFIED)

**Root cause (confirmed by reading):** `UserProfileView.handleSaveQuiz()` POSTed the quiz and closed the modal but **never refreshed `user.has_profile`**. Both gates — `AppRoutes.OnboardingGate` (route redirect) and the `UserProfileView` auto-open effect — key off `user.has_profile`, which the store only sets from login/`fetchMe` and caches in `localStorage.confit_user`. So after completion the stale `false` kept re-triggering the wizard on every navigation/refresh until a full re-login. Backend was already correct: `/auth/me` sets `has_profile = user.profile is not None`, and the quiz's `create_or_update_profile` creates exactly that row.

**Fix (smallest correct; frontend only):**
| File | Change |
|---|---|
| `frontend/src/views/consumer/UserProfileView.tsx` | After successful `submitOnboardingQuiz`, `await fetchMe()` (existing pattern) to refresh `has_profile` in store + persisted cache; added dismissible `closeQuiz` for skip |
| `frontend/src/router/AppRoutes.tsx` | `OnboardingGate` exported + respects session dismissal (skip = non-blocking across routes) |
| `frontend/src/stores/authStore.ts` | `isOnboardingDismissed` / `dismissOnboarding` / `clearOnboardingDismissed` (session-scoped, storage-safe); cleared on logout |

**Regression tests (VERIFIED — 33 passed, 0 failed):**
- `router/__tests__/onboardingGate.test.tsx` (new): completed → no reappear; skip → non-blocking; first-run redirect; guest passthrough.
- `stores/__tests__/onboardingDismissal.test.ts` (new): dismissal set/clear/default.
- Existing `authStore.session`, `authStore.bootstrap`, `PartnerPortalBoundary` suites still green (refresh/persist across reload covered).
- `tsc --noEmit`: exit 0.

**Not verified live:** the running app flow (click-through) was not exercised against a browser — egress/no-backend-server here. Covered by unit/contract tests + reading.

---

## 2A. Phase 0.2 · Slice A — server-side onboarding completion metadata

**Session:** 2026-10-19 (second pass) · **Branch:** `phase-0.2/onboarding-completion-metadata` (stacked on `fix/wizard-reappearing` @ `98af062`)

### Why §2 was not enough

§2 fixed the *client* half: refresh `user.has_profile` after saving. But `has_profile` is the wrong predicate — it only means "a `user_style_profiles` row exists", and that row is created by the **first saved field**. So a shopper who opened the wizard, saved one budget value and closed it was `has_profile = true` → the gate said "onboarded, never prompt" while the auto-open effect read the same stale/partial state as "not onboarded". Two paths, one ambiguous flag, wizard reappears.

Slice A replaces the inference with a server-recorded fact.

### Changes

| File | Change | Status |
|---|---|---|
| `backend/app/models/profile.py` | `onboarding_completed_at` (DateTime, nullable), `onboarding_version` (Integer, nullable) on `UserStyleProfile` | IMPLEMENTED |
| `backend/app/core/config.py` | `ONBOARDING_WIZARD_VERSION: int = 1` — the only place the wizard revision is declared | IMPLEMENTED |
| `backend/app/repositories/profile_repository.py` | `create_or_update_profile` stamps completion + timestamp + version in the same transaction | IMPLEMENTED |
| `backend/app/services/profile_service.py` | **Defect fix:** `save_quiz_and_preferences(is_onboarding=…)` defaulted to **True**, so every split PATCH (`/me/budget`, `/me/size-fit`, `/me/brands`, `/me/style-profile`, …) marked the whole wizard complete. Default is now fail-closed (`False`) and only the two full-wizard endpoints opt in | BUG-VERIFIED → FIXED |
| `backend/app/schemas/auth.py` | `UserOut` gains `onboarding_completed`, `onboarding_completed_at`, `onboarding_version` | IMPLEMENTED |
| `backend/app/controllers/auth_controller.py` | `_user_out` derives them from the profile row; no profile → `False` / `None` (never assumed) | IMPLEMENTED |
| `backend/alembic/versions/0040_onboarding_completion_metadata.py` | Additive migration; backfills `onboarding_version = 1` for already-completed rows and deliberately leaves `onboarding_completed_at` NULL | VERIFIED |
| `frontend/src/router/AppRoutes.tsx` | `OnboardingGate` keys on `user.onboarding_completed`, not `has_profile` | VERIFIED |
| `frontend/src/views/consumer/UserProfileView.tsx` | auto-open effect + skip-dismissal use `onboarding_completed` | VERIFIED |
| `frontend/src/stores/authStore.ts` | `selectOnboardingCompleted`; `selectHasProfile` kept but documented as NOT an onboarding signal | VERIFIED |
| `frontend/src/models/index.ts` | `User` gains the three optional fields (absent = not completed, the fail-safe direction) | VERIFIED |
| `frontend/src/views/b2b/BrandRegistrationView.tsx` | brand accounts are `onboarding_completed: true` (never routed through the consumer wizard) | VERIFIED |

### Evidence (this session, local only)

| Check | Command | Result |
|---|---|---|
| New backend regression suite | `pytest backend/tests/test_onboarding_completion_metadata.py` | **VERIFIED** — 5 passed |
| Identity/profile + GDPR + migration chain neighbours | `pytest test_group1_identity_profile test_gdpr_export_completeness test_migration_single_head test_migration_roundtrip test_schema_drift_gate test_api_contract_schema_alignment` | **VERIFIED** — 155 passed, 1 skipped |
| Migration applies on a fresh DB | `alembic upgrade head` against `sqlite:////tmp/migcheck.db` | **VERIFIED** — chain 0001→`0040_onboarding_completion_metadata`, both columns present |
| Migration is reversible | `alembic downgrade -1` then `upgrade head` | **VERIFIED** — columns dropped, then restored, version round-trips to `0040` |
| Backfill policy | seed a completed row on the `0039` schema, then `upgrade head` | **VERIFIED** — `(onboarding_completed, version, completed_at) = (1, 1, None)` — version backfilled, instant left NULL (never invented) |
| Frontend gate suite | `vitest run src/router/__tests__/onboardingGate.test.tsx` | **VERIFIED** — 7 passed (incl. the new "row exists but onboarding not completed → still redirects" regression) |
| Frontend full gate | `npm run verify` (i18n + tsc + vitest + build) | **VERIFIED** — i18n ✓ · tsc ✓ · 142 files / all tests pass · build ✓ · exit 0 |
| Backend full suite (post-change) | `pytest backend/tests` | see §3A |

### The regression test that pins the bug

`backend/tests/test_onboarding_completion_metadata.py::test_profile_row_without_completion_is_not_reported_as_onboarded`
— creates a profile row through a split PATCH and asserts `has_profile is True` **and** `onboarding_completed is False`. If anyone ever re-derives the gate from row existence, this fails.
`::test_split_patches_do_not_complete_onboarding` — exercises four split PATCHes and asserts none of them stamps completion (the fail-closed fix).

### Not verified

- The change was **not** exercised against a running browser + live backend (no deployed environment in this workspace). Covered by unit/API-integration tests and code reading. Marked **NOT TESTED (live E2E)**.
- No production database was touched: every migration run used a disposable SQLite file under `/tmp`.

---

## 3. Test suites

| Suite | Command | Result |
|---|---|---|
| Frontend targeted (fix + neighbors) | `vitest run <5 files>` | **VERIFIED** — 5 files, 33 tests, 0 fail (6.65s) |
| Frontend typecheck | `tsc --noEmit` | **VERIFIED** — exit 0 |
| Frontend full gate | `npm run verify` (i18n + tsc + vitest + build) | **VERIFIED** — i18n ✓ · 142 files / **2060 tests pass** · tsc ✓ · build ✓ (exit 0) |
| Backend hermetic | `PYTHONPATH=. CONFIT_IGNORE_DOTENV=1 pytest backend/tests` (SQLite) | **4031 passed · 40 FAILED · 24 skipped** — all 40 pre-existing & environmental (triage below); none caused by this change |

**Backend failure triage** — backend code is byte-identical to `origin/main`, and the 5 non-VTON failures fail even with `backend/.env` moved aside, so none are caused by this change:
- **~25** VTON image-fetch / worker-chain tests → egress blocks image/worker fetch; app fails *honestly* (`VTON_INPUT_INVALID`, job `failed`). **BLOCKED (env)**.
- **4** VTON pose-artifact tests → `libEGL.so.1` missing (headless-GL system lib not installed). **BLOCKED (missing system dep)**.
- **~6** stylist/vision/capabilities/visual-search → NVIDIA/Gemini egress-blocked → honest `503` where the test wants `200`. **BLOCKED (env)**.
- **5** Groq key-spelling / verifier dotenv-precedence → pre-existing env-handling failures. **FAILED (pre-existing, needs maintainer follow-up)**.

---

## 3A. Test suites — measured again this session (supersedes §3 numbers)

§3's row for the backend suite recorded **40 failures**. On this workspace those 40 do **not reproduce**: they were consequences of the egress allowlist described in §0, which does not apply here. Re-measured on the identical commit (`98af062`) before any Slice A edit:

| Suite | Command | Result |
|---|---|---|
| Backend baseline (pre-change, pristine worktree @ `98af062`) | `PYTHONPATH=. CONFIT_IGNORE_DOTENV=1 pytest backend/tests -q` | **VERIFIED** — **4071 passed · 0 failed · 24 skipped** (652s, exit 0) |
| Backend full suite (post-Slice-A) | same | **VERIFIED** — **4076 passed · 0 failed · 24 skipped** (632s, exit 0) — the +5 are the new Phase 0.2 regression tests |
| Frontend full gate (post-Slice-A) | `npm run verify` | **VERIFIED** — i18n ✓ · tsc ✓ · 142 files pass · build ✓ · exit 0 |

**One test needed a conscious expectation update, not a loosening:**
`test_flow_e_purchase_to_wardrobe.py::test_migration_chain_has_a_single_head_at_0036` hard-pins the Alembic head. Migration `0040` moves that head, which is exactly the event that test exists to force a human to document — so the assertion and the chain-rationale comment were both extended to `0040_onboarding_completion_metadata` with its reason. No assertion was deleted, skipped, or made permissive.

**Corrections to §0** (both were true of the earlier session's environment, not this one):
- *Egress*: `github.com`, `api.github.com`, `pypi.org`, `registry.npmjs.org`, `generativelanguage.googleapis.com` and `integrate.api.nvidia.com` all answered from this workspace. The "only Gemini reachable" constraint did not hold, which is why §3's provider failures were absent.
- *GitHub*: push/PR **worked** over REST + git-with-askpass; see §6A.

---

## 4. Database safety

- Automated tests ran on **local SQLite** only (`sqlite:///./backend/data/confit.db`).
- Neon (`neondb` = production, `confit_fixverify` = harness) was **not reachable** (DNS), and **nothing was written, migrated, or seeded** against any external DB.
- No schema change, no seed, no production mutation.

## 5. Security

- Tracked-file secret scan (strict, full-length token patterns): **clean**.
- `backend/.env` git-ignored and never staged; `secrets.env` gap noted earlier (fix available, not yet applied to `.gitignore`).
- Fix diff self-scan: no `console.log`/`debugger`/TODO/secret markers.
- **Exposure/rotation:** the provided credentials were pasted in chat earlier this engagement → treat as exposed; rotation advised after the engagement (owner's decision; not performed).

## 6. GitHub & delivery

- Push/PR/merge: **BLOCKED** (session GitHub not linked). Nothing pushed, merged, or deployed.
- Reviewable patch: `/home/user/confit-secrets/../scratchpad/wizard_fix.patch` (tracked-file changes) + 2 new untracked test files (listed in §2). Final patch re-exported after the full gate passes.

---

## 6A. Delivery — this session

- Branch `phase-0.2/onboarding-completion-metadata` cut from `fix/wizard-reappearing` @ `98af062`.
- Push + PR via `git`/REST with an askpass helper; the token never appears in a URL, in `.git/config`, or in any file (§5 rules unchanged).
- Commit identity: `OmarAhmed-123 <omarsafealden@gmail.com>`, no `Co-authored-by`, no AI attribution (`AGENTS.md` §6.2).
- **Nothing was merged.** Merge is the owner's decision and was explicitly withheld.

---

## Known blockers (owner action)

1. **Network allowlist** — add the provider hosts in §1 to verify the remaining integrations live.
2. **GitHub link** — connect at `claude.ai/connect-github` + install the Claude GitHub App on the repo + start a session with it selected, to enable PRs/merges.
