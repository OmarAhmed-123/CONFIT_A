# CONFIT_A — MASTER REMEDIATION PLAN
**Baseline:** `main` @ `c73dbf3` (PR #77 merge) · **Production:** `dpl_8zmNMDM8nJVLN96ytk6BMpBzEYCm` (READY, `confit-a.vercel.app`) · **CI on baseline:** 6/6 green (backend, frontend, parity, pg-migration-chain+schema-gate, gitleaks, Workers)
**Date opened:** 2026-09-06 · **Source of findings:** `CONFIT_A_PRODUCTION_READINESS_GATE.md` (NO-GO, 2026-09-06) + re-verification cycles PR #76/#77.

---

## 1. Branch inventory decision record

76 remote branches audited (`git branch -r`, ahead/behind vs `main`). 63 MERGED (closed — historical, not reusable). 13 UNMERGED, classified:

| Unmerged branch | Domain | Decision | Reason |
|---|---|---|---|
| `fix/commerce-market-currency-20260904` (+1) | commerce settlement currency | **Do not reuse — superseded** | `fix/market-settlement-currency` (same scope) already merged 09-04; stale vs main |
| `hotfix/revert-74-deploy-sequence` (+1) | deployment | Not needed now | Deploy safety PASS (schema gate fail-closed live); no active action |
| `fix/vton-process-url`, `feat/vton-admin-secret`, `feature/vton-production-e2e` (+1/+1/+2) | VTON | Not needed now | VTON single-garment VERIFIED; multi = PARTIALLY_AVAILABLE (worker dependency) |
| `docs/vton-*` (3), `final-no-excuses-release-gate`, `docs/readme-and-seed-guard` | docs | Not reusable | Different scope; stale |
| `chore/router7-vite8`, `fix/gitleaks-pr-token`, `fix/groq-key-truthfulness-20260904` | tooling/security hygiene | Not needed now | gitleaks green on baseline; keys handled in Security feature |

**Conclusion:** no existing branch matches this cycle's feature scopes → new, professionally-named branches per feature (rule §3/§5). Previously-merged cart work (`fix/confit-audit-2026-09-06`, PR #77) is closed; continuation happens on a fresh branch.

## 2. Feature findings & execution order

| # | Feature | Finding | Sev | Root cause | Existing branch | Branch used | Dependency | PR | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Security foundation | Live exposed tokens (Vercel/GitHub) not rotated; dead provider keys in env | P1 | Operational, outside repo | none | — | Owner action | — | **BLOCKED — OWNER** |
| 2 | Deployment / migration safety | Migration execution is manual; gate is runtime fail-closed | P2 (accepted) | Vercel build runs no Alembic (platform) | `hotfix/revert-74-deploy-sequence` (rejected) | — | Documented in contract | — | VERIFIED (gate live) / process doc |
| 3 | Auth / account recovery | admin locked; temp passwords; no MFA; reset=501 | P1 | Email provider absent + operator lockout | none | — | Feature 15 (email) + owner | — | **BLOCKED — OWNER** |
| 4 | **Cart / commerce** | **Returning guest after checkout = permanent 500 on all cart ops** | **P0** | `carts.session_token UNIQUE` + converted row keeps token → next `get_or_create` INSERT collides | none suitable | `fix/cart-commerce` (NEW) | none | — | IN PROGRESS |
| 4b | Cart / commerce | Duplicate checkout (no idempotency key) → 500 | P2 | Same root cause (IntegrityError masks honest "empty cart" 422) | 〃 | 〃 | 〃 | — | IN PROGRESS |
| 5 | Upload foundation | Verified (4.5MB→0.27MB, honest rejects, zero-POST) | — | — | merged earlier | — | — | — | VERIFIED |
| 6 | VTON reliability | Single-garment VERIFIED; multi-garment unproven live | P2 | GPU worker provisioning | 3 stale branches (rejected) | — | Worker infra (owner) | — | PARTIALLY_AVAILABLE (documented) |
| 7 | AI stylist | Grounding/budget/injection verified live | — | — | — | — | — | — | VERIFIED |
| 8 | Fit finder | Stale-async race fixed (PR #77 `208e833`) + live FF2 | — | — | — | — | — | — | VERIFIED |
| 9 | Smart wardrobe | Upload 501 honest — needs object storage | P1 | `STORAGE_PROVIDER=local` on serverless | none | — | Infra (owner) | — | **BLOCKED — INFRA** |
| 10 | Outfit builder | Real SKUs, honest unavailable states verified | — | — | — | — | — | — | VERIFIED |
| 11 | **Catalog / homepage truth** | "Photorealistic fabric segmentation and silhouette drape" overstates 2D VTON | P2 | Marketing copy ahead of tech | none (catalog branches merged) | `fix/catalog-truthfulness` (NEW) | none | — | PLANNED |
| 12 | Payments | Demo mode declared on every checkout surface + order payload | — | PSP not integrated (intended) | — | — | Owner (PSP keys) | — | DEMO ONLY (honest) |
| 13 | BOPIS / returns | Copy matches DB (`store_count=1` → "boutique"); window=30d consistent | — | — | — | — | — | — | VERIFIED |
| 14 | Brand / legal | MD/COS/Reiss/Arket used without authorization proof | P2 | Business decision | none | — | Owner | — | **OWNER DECISION REQUIRED** |
| 15 | Email | No provider (reset/verify/MFA-recovery 501) | P1 | Infra | none | — | Owner (provider keys) | — | **BLOCKED — INFRA** |
| 16 | Accessibility / RTL | 16/16 live; zoom restriction removed | — | — | — | — | — | — | VERIFIED |
| 17 | Performance | Lazy images verified; no broken assets; CWV not measured | P2 | Tooling | none | — | — | — | ACCEPTED (monitor) |
| 18 | Observability | X-Request-Id live, redaction tests, uptime monitor | — | — | — | — | — | — | VERIFIED |
| 19 | Navigation / error UX | 401/403/404/422/429/500/501 all honest; no infinite spinners found | — | — | — | — | — | — | VERIFIED |

## 3. Execution order this cycle
1. `docs/remediation-plan` — this plan (PR A)
2. `fix/cart-commerce` — P0 returning-guest fix + duplicate-checkout honesty + regression tests + feature doc (PR B)
3. `fix/catalog-truthfulness` — honest VTON capability copy (PR C)
4. Final docs update — statuses, final report, launch decision (PR D)

Features 1/3/9/14/15 stay **BLOCKED / OWNER DECISION** — no fake work; closing them requires owner-provided infrastructure or decisions (token rotation, SMTP, object storage, brand licensing, admin unlock approval).

## 4. Final status (cycle closed 2026-09-06)

| Feature | Branch used | Reused/New | PR | Merge SHA | Production | Tests | Status |
|---|---|---|---|---|---|---|---|
| Remediation plan | `docs/remediation-plan` | New | #78 | `8678337` | docs | CI green | CLOSED |
| Cart / commerce (P0) | `fix/cart-commerce` | New | #79 | `5e5bfb7` | `dpl_8LBHo8NontUqyeihvTVY93FTavDa` — health ok, guest add 201 | backend 1025✅/7⏭, live 2-order journey on branch preview | **VERIFIED** |
| Catalog copy truth | `fix/catalog-truthfulness` | New | #80 | `333ff24` | `dpl_H6RMFT9kaR7H5tvEKmqYrWcbvTDH` — honest copy confirmed in served bundle | vitest 95/95, tsc clean | **VERIFIED** |
| Security rotation | — | — | — | — | — | — | **BLOCKED — OWNER** |
| Auth recovery / admin unlock | — | — | — | — | — | — | **BLOCKED — OWNER** |
| Email provider | — | — | — | — | — | — | **BLOCKED — INFRA** |
| Object storage / wardrobe upload | — | — | — | — | — | — | **BLOCKED — INFRA** |
| Brand licensing | — | — | — | — | — | — | **OWNER DECISION REQUIRED** |

Legend: VERIFIED (live evidence) · BLOCKED (external dependency, honestly declared, no fake work).


---

## 5. Cycle 2 (2026-09-06, later) — baseline `main` @ `d95db67`

Re-audit at cycle start: 76 branches (no delta), ONE pre-existing open PR (#75 `hotfix/revert-74-deploy-sequence` — owner-opened, different domain, left to owner disposition), production healthy/schema-ok.

| Feature | Finding | Sev | Existing branch | Branch used | Reused/New | PR | Status |
|---|---|---|---|---|---|---|---|
| Security foundation | Only HSTS in production; CSP/nosniff/frame/referrer/permissions all absent | P1 | security/* merged/closed | `fix/security-foundation` | New | #82 | **VERIFIED** — merge `937cade`, prod `dpl_zXrDC5V1pusarMVjNUo1qmFTtpMJ`: 6/6 headers on `/` AND `/api/v1/health`, SPA smoke under CSP zero violations |

Owner actions recorded (not faked): production env `ACCESS_TOKEN_EXPIRE_MINUTES=1440` overrides the secure 15-min code default (refresh endpoint exists — owner should confirm frontend refresh path and lower it); token rotation; PR #75 disposition; email/storage/admin/brand items unchanged from §4.

Full-suite baseline after cycle 2: **1028 backend / 95 frontend**. Final decision unchanged: **NO-GO** solely on owner-action blockers (see FINAL_REPORT §10).
