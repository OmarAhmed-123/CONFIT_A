# CONFIT_A — CYCLE 5 BASELINE (final-closure run)

**Date:** 2026-09-07 (late) · **Baseline main:** `d158942` (PR #90 merge — verified unchanged: zero new commits, **0 open PRs**, PR #75 remains closed) · Secret policy: statuses only.

## Repository & CI

| Check | Result |
|---|---|
| `main` HEAD | `d158942` |
| Open PRs | 0 |
| CI on main | **6/6 green** (backend, frontend, parity, migration chain + schema gate, gitleaks, Workers) |
| Workspace git | intact (PAT-bearing remote present) |

## Production (`confit-a.vercel.app`) — read-only probes + own account

| Probe | Result |
|---|---|
| `/` + health | 200 · **6/6 security headers** |
| Access cookie (G) | `confit_token` **Max-Age=900 s (15 min)** — flip holding |
| login → `/auth/me` | 200 / 200 (own test account, cleaned up) |
| RBAC | consumer → `/admin/analytics` = **403** |
| Email (C) | `forgot-password` → **501 FEATURE_NOT_CONFIGURED** |
| Storage (D) | env keys absent (`STORAGE_PROVIDER`, `AWS_S3_*`, `S3_ENDPOINT_URL` — names checked via API, no values) |
| Admin (E/F) | bad-password login probe → 401 AUTH_FAILED; DB read-only: `role=ADMIN, is_active=true, mfa_enabled=true`, zero `MFA_DISABLED`/password-change events since recovery |
| Brands (H) | catalog serves **Massimo Dutti / COS / Reiss** (real names, unlabeled) |

## Credential rotation status (§5)

| Credential | Test | Status |
|---|---|---|
| GitHub PAT (the exposed one) | authenticated `git ls-remote` + API **succeeded** | **VALID — NOT ROTATED** (fail-closed: treated as live-compromised) |
| Vercel token (chat-exposed) | deployments API **200** | **VALID — NOT ROTATED** |
| Neon DB password, OpenAI, Gemini, Groq, Modal, Fitroom keys | all pasted in chat (2026-09-07) | **EXPOSED — rotation NOT_VERIFIED** |

## Environment (names only, via Vercel API — 66 vars)

`EMAIL_PROVIDER`/`SMTP_*`/`EMAIL_FROM_ADDRESS`/`FRONTEND_BASE_URL`: **all absent** ⇒ C not provisioned. `STORAGE_PROVIDER`/`AWS_S3_*`: **all absent** ⇒ D not provisioned. `ACCESS_TOKEN_EXPIRE_MINUTES`: present (value proven 15 by live cookie).

## Full regression (§26) — local, on `d158942`

backend **1050 ✅ / 7 ⏭** (identical to cycle-4 close) · frontend **100 ✅ / 18 files** · `tsc --noEmit` clean · `vite build` ✓ · gitleaks ✅ (CI) · migration gate ✅ (CI) — **zero regressions vs baseline**.
