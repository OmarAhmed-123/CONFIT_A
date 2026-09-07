# Cycle 6 — Research Record (CONFIT-A)

Format: source / finding / implication / decision / trade-off.

## R1 — Neon credential rotation (EXECUTED this cycle)

- **Source:** PostgreSQL official docs (ALTER ROLE semantics: a role may change its own password; role membership requires ADMIN option; GRANT object privileges vs ownership) + Neon behavior observed live.
- **Finding:** the exposed `neondb_owner` password could be rotated end-to-end from this environment (DB owner access + Vercel env write). The zero-downtime dual-role path required `GRANT neondb_owner TO <new role>` — **Neon denies it** (no ADMIN option on the owner role). However, the production app performs **no DDL at runtime** (verified in code: `create_all` skipped when `ENVIRONMENT=production`; schema gate is read-only; alembic runs are owner-operated CLI commands) ⇒ a **DML-only app role** suffices for the deployed app.
- **Decision (executed):** `CREATE ROLE confit_app_rw` → `GRANT USAGE ON SCHEMA public` + `GRANT ALL ON ALL TABLES/SEQUENCES` + `ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner` (future migrations by owner auto-grant to app role) → new `DATABASE_URL` (same params incl. `sslmode=require&channel_binding=require`) PATCHed into Vercel (production+preview, sensitive) → redeploy `dpl_ACZM1bL3rqXiRpCGTe9rULHsZZ6R` READY → verified (health/login/products 200) → **owner password rotated** (as the role itself) → **OLD exposed password proven INVALID (auth failure); NEW role proven VALID; production healthy post-rotation.** Master password delivered via `/home/user/ADMIN_HANDOVER.md` (outside git).
- **Trade-off / residual:** future `alembic upgrade head` must run as `neondb_owner` (master password in handover), never as the app role — documented. Blast radius of any app compromise reduced to DML-only.

## R2 — Exposed-credential validity board (evidence for the gate)

- **Source:** live probes, statuses only (no values printed).
- **Finding (2026-09-07, this cycle):**

| Credential | Status |
|---|---|
| Neon DB password (old, exposed in chat) | **REVOKED** (login fails — proven) |
| Neon app role (new) | VALID (production runs on it) |
| GitHub PAT (exposed) | **VALID** (authenticated API 200) — rotation owner-only (no self-revocation API) |
| Vercel token (exposed) | **VALID** (deployments API 200) — rotation owner-only (dashboard) |
| OpenAI key (exposed) | **VALID** (models API 200) — no key-management API |
| Groq key (exposed) | **VALID** (models API 200) |
| Gemini key (exposed) | **VALID** (models API 200) |
| Modal token (exposed) | exposed; validity NOT_VERIFIED |
| Fitroom key (exposed) | exposed; validity NOT_VERIFIED |

- **Implication:** seven exposed credentials remain live-or-unverified and none can be revoked from this environment ⇒ hard NO-GO condition persists (§28) despite the Neon closure.
- **Decision:** status BLOCKED — OWNER for each, with proof requirements OLD=invalid + NEW=valid.

## R3 — Preview credential freeze (rotation side-effect, expected)

- **Finding:** pre-rotation preview deployments froze the OLD `DATABASE_URL` in their build-time env; after revocation they fail with `FUNCTION_INVOCATION_FAILED` (observed on `confit-y67ea1un4…`). Production — redeployed post-rotation — is healthy on the new role.
- **Implication:** destructive preview testing must run on previews created AFTER the rotation (any new push). Older dead previews are harmless (and prove the revocation bit).
- **Decision:** cycle-6 destructive smoke executed on the fresh PR preview; production smoke executed safely on production (browse + guest cart add 201 + login/logout + RTL + zero CSP violations, 6/6).

## R4 — Carried decisions (unchanged)

Email → stdlib SMTP transport (deployed `9d7ac4c`), provider recommendation Resend (cycle-4 R1 sources). Storage → existing S3/R2 adapter, recommendation Cloudflare R2 (cycle-4 R2). Bucket/account creation remains owner action per §31 (billable resources).
