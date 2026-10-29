# Security & Operational Readiness Review — 2026-10-29

This is an **engineering review of controls present in the code and CI**, with the commands that were run. It is **not a security audit or penetration test**; no third party has assessed the system.

## 1. Controls verified by reading code and/or running a check

| Area | Control | Evidence | Status |
|---|---|---|---|
| Session | JWT in `confit_token` cookie: `httponly=True`, `samesite=lax`, `secure` **only when `ENVIRONMENT=production`**; CSRF double-submit cookie `confit_csrf` (not httpOnly, by design) | `backend/app/controllers/auth_controller.py` L49–68; browser E2E confirms cookie present after UI login | VERIFIED |
| Secrets | No secret in repo; gitleaks job with custom DSN rule (`.gitleaks.toml`) green on `ffd6118`; credentials only in local env file | CI `gitleaks` ✓ | VERIFIED |
| Dependencies (Python) | `pip-audit -r backend/requirements.txt` → **No known vulnerabilities found** (2026-10-29) | command output | VERIFIED |
| Dependencies (Node, runtime) | `npm audit --omit=dev` → **0 vulnerabilities** | command output | VERIFIED |
| Dependencies (Node, dev toolchain) | `npm audit` → 7 (4 moderate, 3 high) all in **dev-only** packages: vite/launch-editor, vitest/@vitest/mocker, undici, source-map-js, postcss-selector-parser; fixes available via toolchain bump | command output | OPEN (SEC-1, proposed: bump vite/vitest in a dedicated PR with full regression) |
| Rate limiting | SlowAPI; auth register 5/min/IP, login 5/min, recommendation 40/h/user, uploads 30/h; client IP taken from the socket, **not** `X-Forwarded-For` (spoofing fixed earlier) ; storage Redis when `RATE_LIMIT_STORAGE_URL` set, else in-memory (per-worker!) | `backend/app/core/rate_limit.py` L97–101, controllers | VERIFIED; **OPEN SEC-2**: production must set `RATE_LIMIT_STORAGE_URL` or limits are per-process |
| Upload limits | 15 MB per image, MIME allow-list (jpeg/png/webp) server-side and client-side | `wardrobe_service.py` L26, L503; `WardrobeView.tsx` | VERIFIED (code) — oversize/MIME rejection covered by backend tests |
| Security headers (frontend) | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy` in `vercel.json` | file | VERIFIED (config) — **NOT TESTED live** (Vercel 402) |
| Security headers (API) | CORS allow-list from `CORS_ORIGINS`; no HSTS/CSP middleware on the API itself | `main.py` L97 | OPEN SEC-3 (proposed: add `Strict-Transport-Security` and `X-Content-Type-Options` on API responses or at the reverse proxy) |
| Schema drift | Production refuses to serve if DB ≠ migration head | `core/schema_gate.py` | VERIFIED (CI job + unit tests) |
| Startup safety | No create_all/seed in production; dev init serialised with advisory lock | `core/startup_init.py` + concurrency test | VERIFIED |
| Error tracking | GlitchTip/Sentry SDK, fail-open, disabled when `GLITCHTIP_DSN` unset | `core/error_tracking.py` | VERIFIED (code) — DSN not configured anywhere yet (OPS-1) |
| Correlation | `X-Request-Id` on every response, structured logs | `main.py` L106 | VERIFIED |
| Health | `/health` (liveness; exempt from schema guard) | `main.py` L157 | VERIFIED; readiness probe exists for AI providers (log line) |
| AI provider | Retries bounded (2), timeouts 45 s, no silent provider substitution, source labelled | `providers/watsonx/client.py` | VERIFIED |

## 2. Operational readiness

| Item | Status |
|---|---|
| Runbooks | `docs/deployment/{VERCEL_RECOVERY,NEON_RECOVERY,CLOUDFLARE_BUILDS}.md`, `docs/local-development.md`, `docs/deployment-recovery.md` | PRESENT |
| Backups / PITR | Neon-managed; retention window **unknown until the project is unlocked** | BLOCKED |
| Monitoring / alerting | No dashboards or alerts configured (no hosting currently live) | NOT CONFIGURED (OPS-2) |
| Log retention | platform default | NOT CONFIGURED |
| Secret rotation | procedure in `NEON_RECOVERY.md §3`; watsonx API key rotation = IBM Cloud IAM | DOCUMENTED, not exercised |
| Incident history | 2026-09-03 schema drift incident → gate added | RECORDED |
| On-call / ownership | undefined | OPEN (OPS-3) |

## 3. Summary
No critical code-level security finding was identified by this review. Blocking items for production are operational (SEC-2 Redis-backed limiter, OPS-1 error-tracking DSN, OPS-2 alerting) and platform (hosting/DB locked). This document should be re-run, not copied, after the platforms are recovered.
