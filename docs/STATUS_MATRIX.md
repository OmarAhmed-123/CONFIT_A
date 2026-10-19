# CONFIT_A — Status Matrix

**Generated:** 2026-10-19 · **Workspace:** cloud workspace, clone of `OmarAhmed-123/CONFIT_A`
**Working branch:** `fix/wizard-reappearing` — PR #359, open, **not merged**
**Commits:** `0763c8b` (Slice A code) · `1b70978` (this reconciliation)
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

## 1. Credentials & providers — recorded earlier, NOT re-run in this workspace

The verifier script named in the previous revision (`backend/scripts/verify_provider_credentials.py`) **does not exist in the repository** — verified by listing `backend/scripts/`. The results below therefore come from an earlier session's environment and are retained only as history. **They are not evidence about the keys themselves**, because in that session the hosts were policy-denied before any key was presented.

| Provider / capability | Configured | Earlier-session result | Standing in this workspace |
|---|---|---|---|
| Gemini (vision + stylist) | ✅ | 200 on `generateContent` | **NOT RE-RUN** |
| NVIDIA NIM pool (19 slots) | ✅ 19/19 canonical `NVIDIA_KEY_<MODEL>` | BLOCKED (403 at the proxy) | host reachable now → **NOT TESTED** |
| OpenAI · Groq · UnoRouter/OpenRouter | ✅ | BLOCKED (403) | **NOT TESTED** |
| Neon Postgres (4 role DSNs) | ✅ | DNS refusal | **NOT TESTED** — and deliberately not contacted: it is production |
| Neon S3 / RunPod S3 · Modal · Baseten · Cerebrium | ✅ | BLOCKED / no REST surface | **NOT TESTED** |
| Brevo (API + SMTP) · Resend | ✅ | BLOCKED | **NOT TESTED** |
| FX (exchangerate, fixer) | ✅ | BLOCKED | **NOT TESTED** |
| Sentry · BetterStack · GlitchTip | ✅ / ⚠ project key only | BLOCKED / needs full DSN | **NOT TESTED** |
| HuggingFace · Kaggle · Vercel · Dynu (DNS) | ✅ | BLOCKED | **NOT TESTED** |
| GitHub (PAT) | ✅ | — | **VERIFIED** — authenticated REST + git push/PR this session |

**Open credential findings (unchanged, still the owner's to resolve):** `GITHUB_ACCOUNT_PASSWORD` is identical to the GitHub username; two `neondb_owner` passwords are on file; `NVIDIA_API_KEY_ISING_CALIB_B` contains a placeholder marker; Brevo sender verification pending for the Gmail address. Live provider verification remains a whole slice of its own (§ Known limitations).

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

## 5. Database safety

- Automated tests ran on **local SQLite only**.
- Every migration in this work ran against a disposable file under `/tmp`; `backend/data/confit.db` was not modified.
- **Nothing was written, migrated, or seeded against any external database.** Neon was not contacted, reachable or not — it is production, and this work needed nothing from it.
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
| Branch | **one branch: `fix/wizard-reappearing`**, head `0763c8b` |
| Consolidation | `98af062..0763c8b` — a **fast-forward**, explicitly not a force-push (`git merge-base --is-ancestor` checked before sending) |
| PR #359 | open, head `0763c8b`, base `main`, **19 files, +899 / −16** |
| PR #360 | **closed** — it was opened from a second branch, which broke the one-branch rule; its commit now lives on `fix/wizard-reappearing`. GitHub records `merged_at` because the head commit became an ancestor of its base (`fix/wizard-reappearing`) at 18:05:21Z; **`main` did not move** |
| Second branch | `phase-0.2/onboarding-completion-metadata` **deleted** |
| `main` | still `6636356` — **no merge occurred** |
| Commit identity | `OmarAhmed-123 <omarsafealden@gmail.com>`, no `Co-authored-by`, no AI attribution (`AGENTS.md` §6.2) |
| Token handling | askpass helper; the token never appears in a URL, in `.git/config`, or in any file |

### Check results, by SHA

Read per commit; no result is borrowed across SHAs.

| Check | `0763c8b` (code) | `1b70978` (docs) |
|---|---|---|
| `backend` | **success** | **success** |
| `frontend` | **success** | **success** |
| `postgres migration chain + schema gate` | **success** | **success** |
| `production parity (deployment contract)` | **success** | **success** |
| `gitleaks secret scan (full history)` | **success** | **success** |
| `stylist drawer browser gate (a11y, keyboard, RTL)` | **success** | **success** |
| `Vercel Preview Comments` | **success** | **success** |
| `release gate (production schema parity)` | *did not run* | **failure — REQUIRED** |
| `Workers Builds: confit-a` | failure — non-required | failure — non-required |

#### `release gate (production schema parity)` — FAILED, and correctly so

The gate is not flaky and not a code defect. It compares the migration head this commit requires against the head production actually reports, and refuses to let a merge deploy code production cannot run. Its own output:

```
RELEASE GATE: BLOCK
  commit requires : 0040_onboarding_completion_metadata
  production has  : 0039_brand_memberships
  production health verdict: ok (acceptable=True)
  ...Merging now would deploy code production cannot run: the startup schema gate
  would refuse to boot and the API would return 500 (this is the 2026-09-20 incident).
```

**Resolving it requires applying migration `0040` to the production Neon database** — a production mutation, which is outside this workspace's mandate and was **not performed**. Until the owner runs it, this required check stays red on every commit, by design. Order of operations, per the gate:

```
ALEMBIC_DATABASE_URL='<owner DSN>' PYTHONPATH=. alembic -c backend/alembic.ini upgrade head
ALEMBIC_DATABASE_URL='<owner DSN>' PYTHONPATH=. alembic -c backend/alembic.ini current
```

The migration is additive and every column is nullable, so applying it before the code merge is safe — that is precisely the ordering this gate exists to enforce.

#### `Workers Builds: confit-a` — non-required, classified

An external Cloudflare Workers pipeline that **has no definition in this repository** — verified: no `wrangler.toml`, `wrangler.json(c)`, `_worker.js`, `_routes.json`, or `functions/`. It cannot be fixed from code here; it needs the Cloudflare project's settings. Together with the release gate it is why the PR reports `mergeable_state = blocked`.

---

## 8. Known limitations & open items

1. **Live browser E2E — NOT TESTED.** No deployed backend or browser in this workspace. The wizard behaviour is covered by unit/API-integration tests and by reading, not by a click-through.
2. **Live provider verification — NOT TESTED here.** See §1. This is the substance of a separate slice (a real, in-repo verifier + a recorded run), not something this matrix can assert.
3. **`npm audit`: 8 vulnerabilities (2 moderate, 6 high)** — measured on the committed lockfile. No automated fix applied; deliberately out of scope for a metadata slice.
4. **`release gate (production schema parity)` is RED and required** — migration `0040` is not applied to production. Owner action: run the upgrade against the production DSN, then re-run the gate. Nothing has been merged, so no deploy is at risk in the meantime.
5. **`Workers Builds: confit-a`** — external to the repo; owner action in Cloudflare.
6. **PR #358** remains open by the owner's instruction.
7. **Merge is the owner's decision and has not happened.** Nothing was deployed.
