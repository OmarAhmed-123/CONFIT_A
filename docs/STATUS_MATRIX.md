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

## Known blockers (owner action)

1. **Network allowlist** — add the provider hosts in §1 to verify the remaining integrations live.
2. **GitHub link** — connect at `claude.ai/connect-github` + install the Claude GitHub App on the repo + start a session with it selected, to enable PRs/merges.
