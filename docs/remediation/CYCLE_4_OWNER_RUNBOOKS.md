# CONFIT_A — CYCLE 4 OWNER RUNBOOKS

Every item below can ONLY be executed by the owner (accounts, payments, domain
DNS, production env, production database). Engineering runways are verified and
merged; each runbook ends with the check that flips its blocker to VERIFIED.
**No secrets belong in this file or in git — values go directly into the
Vercel/dashboard env fields.**

---

## A+B — Credential rotation (GitHub PAT + Vercel token) — *minutes, do first*

1. GitHub → Settings → Developer settings → Personal access tokens: **revoke**
   the exposed PAT (the one used by repo automation). Create a fine-grained
   replacement with only `CONFIT_A` access + needed permissions; store in a
   secret manager; update local remotes: `git remote set-url origin https://x-access-token:<NEW>@github.com/OmarAhmed-123/CONFIT_A.git`.
2. Vercel → Settings → Tokens: **revoke** the exposed token; create a new one
   scoped to the project; update anywhere it was used.
3. **Proof required for closure (both):** OLD token → INVALID/REVOKED (API
   returns 401) AND NEW token → VALID (git push works / deployments API 200).
   A replacement existing is NOT proof the old one died.
4. Post-checks: git operations work; CI green on next PR; deployment works;
   `grep` CI workflows for references to old credentials (none expected).

## C — Email delivery (recommended provider: Resend — research R1)

1. Create Resend account → verify sending domain (add their SPF/DKIM/DMARC
   DNS records; wait for green).
2. Create API key (Sending access). Set Vercel env (preview + production):
   `EMAIL_PROVIDER=smtp`, `SMTP_HOST=smtp.resend.com`, `SMTP_PORT=587`,
   `SMTP_USERNAME=resend`, `SMTP_PASSWORD=<API key>`,
   `EMAIL_FROM_ADDRESS=CONFIT <no-reply@<your-domain>>`,
   `FRONTEND_BASE_URL=https://confit-a.vercel.app`.
   (Note: the app boots REFUSED if `EMAIL_PROVIDER=smtp` lands without
   `SMTP_HOST`/`EMAIL_FROM_ADDRESS`/https `FRONTEND_BASE_URL` — set all at
   once and redeploy.)
3. **Closure check:** on production, request password reset for a real inbox →
   email arrives (check SPF/DKIM pass) → the 30-minute one-time link redeems →
   new password logs in. Then blocker C flips to VERIFIED (delivery).

## D — Persistent object storage (recommended: Cloudflare R2 — research R2)

1. Create R2 bucket (e.g. `confit-a-uploads`) + API token with Object Read &
   Write scoped to that bucket only.
2. Vercel env: `STORAGE_PROVIDER=r2`, `AWS_S3_BUCKET=confit-a-uploads`,
   `AWS_ACCESS_KEY_ID=<key id>`, `AWS_SECRET_ACCESS_KEY=<secret>`,
   `S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`,
   `S3_PUBLIC_URL_BASE=https://pub-<hash>.r2.dev` (enable public access on the
   bucket for wardrobe image serving, or front it with your domain).
3. **Closure checks (production):** login → wardrobe upload a real image →
   item persists → full logout/login → image still renders → delete removes
   it from the bucket. Redeploy survival = durability proof (local FS never
   counted). Then blocker D flips to VERIFIED.

## E+F — Admin account recovery + MFA (emergency, DB-scoped, audited)

No admin-bootstrap exists in code (by design). Recovery is a deliberate,
time-boxed procedure against the production DATABASE_URL (from Vercel env):

1. Inspect: `SELECT id, email, role, is_active, mfa_enabled FROM users WHERE role='admin';`
2. If NO admin row: register a new account via the normal API with a strong
   unique password, then promote: `UPDATE users SET role='admin' WHERE email='<that address>';`
3. If a row exists but is locked: `UPDATE users SET is_active=true WHERE id=<id>;`
4. If the password is unknown/lost: set a temporary hash generated with the
   app's own algorithm — one-off from a clean checkout (password read from an
   env var, never shell history):
   `DATABASE_URL=<prod> PYTHONPATH=. python3 -c "import os;from backend.app.core.security import get_password_hash;from sqlalchemy import create_engine,text;e=create_engine(os.environ['DATABASE_URL']);h=get_password_hash(os.environ['NEW_PASS']);e.execute(text('UPDATE users SET hashed_password=:h WHERE id=:i'),{'h':h,'i':<id>});e.dispose()"`
5. MFA recovery (if secret lost): `UPDATE users SET mfa_secret=NULL, mfa_enabled=false WHERE id=<id>;`
   → admin signs in with the temp password → **immediately** enrolls MFA via
   `/auth/mfa/setup` + `/auth/mfa/verify` + `/mfa/regenerate-codes` → change
   password (`/auth/change-password` or reset flow once C is live).
6. **Closure checks:** admin login ✓ logout ✓ password change ✓ MFA challenge
   on login ✓ recovery code works once ✓ sessions revocable (logout-all /
   refresh-family revocation already implemented). Audit trail rows exist for
   each step. Then E+F flip to VERIFIED.

## G — Access-token lifetime 1440 → 15 minutes (SAFE since cycle-3 `44fa877`)

Pre-conditions already proven in production (cycle 3): refresh cookie issued
(httpOnly, 30 d), rotation + reuse detection live, SPA silent renewal verified
(13/13). Remaining:

1. Vercel env: `ACCESS_TOKEN_EXPIRE_MINUTES=15` → redeploy.
2. **Closure check (production, non-destructive):** login → keep a tab open >
   15 min (or clear only `confit_token`+`confit_csrf` cookies to simulate
   expiry) → next authenticated call triggers exactly ONE `/auth/refresh` →
   user stays signed in (`/auth/me` 200). No user is kicked every 15 minutes
   — that was the pre-cycle-3 failure mode this fixes.

## H — Brand licensing (decision, then one PR)

No contract/license artifact exists in the repo for Massimo Dutti / COS /
Reiss / Arket (verified cycle-4 baseline). Pick one:
- **DEMO_ONLY:** keep names, add clear demo labeling in UI copy → we implement
  in `fix/brand-truthfulness` (copy + catalog demo flag).
- **Rebrand:** provide the real brand set → same branch, full rename.
Either way the current state (real names, no license evidence, no disclosure)
cannot ship — that is why H blocks the gate.

## I — PR #75 — CLOSED this cycle

Closed 2026-09-07 with documented evidence (production DB stamped 0017, admin
routes live, merging the revert would reintroduce drift). See the PR comment
and `CYCLE_4_BASELINE.md` §5. Nothing further to do.
