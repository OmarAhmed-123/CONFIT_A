# CONFIT_A — CYCLE 4 BASELINE (VERIFY FIRST)

**Date:** 2026-09-07 · **Recorded before any change** · Secret policy: statuses only (VALID/INVALID/NOT_VERIFIED/BLOCKED) — no values printed anywhere.

## 1. Repository & CI

| Item | Value | Evidence |
|---|---|---|
| `main` HEAD | `0dcb0f3` (PR #86 merge — cycle-3 final report) | `git log origin/main` after fetch+prune |
| Note vs. tasking | Tasking said `20d0e3f`; repo is one docs-merge ahead (#86) — repo is source of truth | git |
| CI on main HEAD | **6/6 green** (backend, frontend, parity, migration-chain+schema-gate, gitleaks, Workers) | check-runs API |
| Open PRs | exactly one: **#75** (see §5) | pulls API |
| Remote branches | ~80 (history of cycles 0–3; no unmerged feature work found open beyond #75) | `git branch -r` |
| Workspace git | intact this session (no rebuild needed) | `.git` present |

## 2. Production (read-only probes — `confit-a.vercel.app`)

| Probe | Result |
|---|---|
| `/` status | 200 · **6/6 security headers** (CSP, XFO, XCTO, Referrer-Policy, Permissions-Policy, HSTS) |
| `/api/v1/health` | 200 |
| Login (own test account) → cookies | `confit_token` Max-Age **86400 s = 1440 min** · `confit_csrf` 86400 · `confit_refresh` 2592000 (30 d) — values never printed |
| Catalog | 9 products live; **brand names served: Reiss, Massimo Dutti, COS** (real-world brands) |
| `POST /auth/forgot-password` (own account) | **501 FEATURE_NOT_CONFIGURED `email_delivery`** — honest |
| `POST /wardrobe/upload` (own account, valid PNG) | **501 FEATURE_NOT_CONFIGURED `wardrobe_upload`** — honest ("set STORAGE_PROVIDER=s3 (or r2)…") |
| Admin API (`/admin/analytics`, `/admin/overview`, `/admin/audit`) | **401** = routes deployed & guarded (ADMIN-01 code live in production) |

**Schema-gate inference (important):** the boot-time schema gate refuses to serve if the DB's alembic revision ≠ code head (0017). Production is healthy on current main code ⇒ **production DB is stamped 0017** ⇒ PR #74's deploy-sequencing incident (DB at 0016) is resolved.

## 3. Blocker re-verification (cycle-4 letters, each re-tested — none assumed)

| ID | Blocker | Re-verification result | Status |
|---|---|---|---|
| A | GitHub PAT exposed & active | The PAT still authenticates repo-admin API calls (used for this baseline) ⇒ rotation NOT done | **BLOCKED — OWNER** |
| B | Vercel token exposed | Token not present in this workspace ⇒ cannot test the old value; prior cycle-3 evidence: active. Owner must rotate AND prove OLD=invalid + NEW=valid | **NOT_VERIFIED — OWNER** |
| C | Email provider | Live 501 probe above; **and** code audit: token infra (hashed one-time, TTL, audit) EXISTS, but `_send_password_reset_email` is an intentional stub — setting EMAIL_PROVIDER today would return a FAKE "queued" with zero delivery (latent dishonesty). Transport is a real engineering gap | **PARTIALLY_AVAILABLE** — code gap closable this cycle; delivery needs owner account+domain |
| D | Object storage | Live 501 probe above; **and** code audit: `S3StorageBackend` (S3+R2 via endpoint) implemented, boto3 in requirements, 6 contract tests, honest 501 gate | **PARTIALLY_AVAILABLE** — engineering ready; needs owner bucket+keys |
| E | Admin account inaccessible | Admin API deployed+guarded (401s); no admin-bootstrap/emergency-recovery path exists in code ⇒ recovery requires production DATABASE_URL access | **BLOCKED — OWNER** (runbook to be documented) |
| F | Admin MFA not operational | MFA endpoints exist (`/mfa/setup|verify|disable|regenerate-codes` + recovery codes); operational enrollment blocked on E | **BLOCKED — OWNER** (depends on E) |
| G | Access-token lifetime 1440 min | Measured live: `confit_token` Max-Age=86400 s = **1440 min** (target 15). Safe to lower since `44fa877` (cycle-3 refresh-lifecycle proof, re-verifiable) | **BLOCKED — OWNER env** (Vercel dashboard; no token in workspace) |
| H | Brand licensing | Live catalog serves Massimo Dutti / COS / Reiss names; repo contains **zero** license/contract artifacts | **OWNER_DECISION_REQUIRED** (no evidence ⇒ no claim either way) |
| I | PR #75 disposition | See §5 — evidence supports CLOSE (incident resolved; merging would now be harmful) | decision recorded this cycle |

## 4. Environment configuration (outside-in)

Direct env read-out requires Vercel access (no token in workspace ⇒ **NOT_VERIFIED**). Outside-in observations: `ENVIRONMENT=production` behavior confirmed (secure cookies, seed skipped), `ACCESS_TOKEN_EXPIRE_MINUTES=1440` (measured), `STORAGE_PROVIDER` unset/local (501 hint), `EMAIL_PROVIDER` unset (501), `DATABASE_URL` functional (healthy API).

## 5. PR #75 review (for §13 disposition)

- **Purpose:** standby revert of PR #74 (ADMIN-01) because code shipping migration 0017 preceded the production DB migration → schema gate correctly refused to serve (deploy-sequencing incident).
- **Current relevance:** production NOW runs main code including 0017 and boots healthy ⇒ DB is stamped 0017 ⇒ the incident exit-A (run migration) happened.
- **Conflict with main:** merging #75 today would DELETE migration 0017 while the production DB is stamped 0017 → reintroduces schema drift (the exact failure class #75 was meant to cure) and removes shipped, CI-green admin governance code + tests.
- **Decision: CLOSE — SUPERSEDED BY REALITY (exit A executed).** Documented in this file and in a PR comment before closing; not closed "to tidy the list".

## 6. Carried-forward capabilities (spot-checked, not reopened)

Security Foundation VERIFIED (headers re-checked 6/6) · Auth Session Lifecycle VERIFIED (login/refresh cookies measured live this baseline) · Cart & replay & E-journey VERIFIED (cycle 3, no regression signals) · catalog copy honest (drape absent, re-confirmed cycle 3) · CI 6/6 on main.

## 7. Cycle-4 work plan derived from this baseline

1. Close PR #75 with documented rationale (I).
2. Research record (official sources): email provider comparison → recommendation; storage provider validation for owner runbook; `docs/research/CONFIT_A_CYCLE_4_RESEARCH.md`.
3. Engineering gap fix: `fix/email-delivery` — real SMTP transport (stdlib smtplib; provider-agnostic: works with Resend/SES/Mailgun SMTP), wired into the existing stub, honest errors, rate-limit aware, tests; 501 behavior unchanged while unconfigured (removes the latent fake-"queued" path).
4. Owner runbooks (docs): token rotation (A/B proof requirements), env flip G (with pre/post verification steps), admin recovery E/F (DB-scoped, minimal, audited).
5. Final report + Launch Gate re-run.
