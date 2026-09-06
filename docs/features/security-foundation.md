# Security Foundation — Feature Remediation Doc
**Branch:** `fix/security-foundation` (NEW — no suitable existing branch: `security/*` branches in the inventory are merged/closed; see MASTER_REMEDIATION_PLAN §1) · **Base:** `main` @ `d95db67`

## Finding (P1 hardening)
Live probe of production (2026-09-06, `confit-a.vercel.app`): only `Strict-Transport-Security` was set. Missing: `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy` — clickjacking, MIME-sniffing, and script-injection surface left open.

## Architecture
Headers are declared once in `vercel.json` under `"source": "/(.*)"` — Vercel applies them to every response, SPA routes AND `/api/*` function routes alike (verified live post-deploy on both `/` and `/api/v1/health`). No application middleware duplication.

CSP is allow-list based on the app's real external surface (audited via repo grep):
- `images.unsplash.com` + `placehold.co` (catalog imagery), `blob:`/`data:` (try-on canvas previews)
- `fonts.googleapis.com` (styles) + `fonts.gstatic.com` (fonts)
- `script-src 'self'` only — no inline scripts exist (index.html audited)
- `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`
- `Permissions-Policy: camera=(self)` (try-on live scan), `microphone=()`, `geolocation=()`, `payment=()`

## Failure modes / trade-offs
- Over-restrictive CSP would break images/fonts/canvas → covered by pinned contract test + preview smoke (SPA render, catalog images, styled DOM) before merge.
- `X-Frame-Options: DENY` + `frame-ancestors 'none'`: the app is never legitimately framed.

## Security considerations
Complements existing controls: HSTS (edge), CSRF enforcement, rate limits (429 verified live), RBAC gates, gitleaks full-history on every PR, redaction tests.

## Tests
- `backend/tests/test_deployment_security_headers.py` (3): global headers present, CSP contract (incl. product-critical allowances and no-inline-scripts), Permissions-Policy camera allowance. Guards accidental removal in any future refactor.
- Live verification: preview curl (`/` and `/api/v1/health`) + SPA smoke; production curl post-merge.

## Owner actions discovered this feature (not code — recorded, not faked)
1. **Access-token lifetime:** code default is 15 min, but production env `ACCESS_TOKEN_EXPIRE_MINUTES` overrides to 1440 (24 h). Refresh endpoint exists (`/auth/refresh`); owner should confirm the frontend refresh path and lower the env to ≤30 min.
2. Session-token rotation (Vercel/GitHub) — still open from the readiness gate.
3. PR #75 (`hotfix/revert-74-deploy-sequence`, pre-existing, owner-opened) — disposition is an owner decision; it does not conflict with this feature.

## Rollback
Single revert of the vercel.json commit (headers vanish at next deploy); test commit reverts independently. No data implications.

## Commit summary / PR
- fix(security): global security headers (vercel.json) + pinned contract test
- docs(security): this feature doc
- PR: see MASTER_REMEDIATION_PLAN §4 cycle-2 table.
