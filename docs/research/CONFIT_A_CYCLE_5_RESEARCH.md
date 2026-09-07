# Cycle 5 — Research Record (CONFIT-A)

Format per contract §24: Source / Type / Finding / Implication / Decision / Trade-offs.

## R0 — Scope decision: no new engineering decisions this cycle

Cycle 5 is a **verification cycle** (ENGINEERING COMPLETE → OPERATIONALLY VERIFIED).
Delta audit at start (2026-09-07): `main` = `00ffd7a` (cycle-4 closure), **zero new
commits, zero open PRs, PR #75 still closed, CI 6/6 green on main HEAD** — the owner
has not executed any runbook action since cycle 4 closed (probes below confirm).
No new infrastructure decision was therefore required; the cycle-4 research
(`CONFIT_A_CYCLE_4_RESEARCH.md` R1 email→Resend, R2 storage→R2, R3 token lifetime)
remains the operative record and is NOT re-litigated (§7: "لا تتعامل مع الاختيار
كحقيقة مقدسة" — re-validation of vendor docs is deferred to the moment provisioning
actually happens, so it reflects then-current pricing/limits rather than today's).

## R1 — New finding: workspace credential loss (honesty handling)

- **Source:** workspace observation + platform snapshot policy (credential paths
  excluded from persistence by design).
- **Type:** operational fact.
- **Finding:** the `.git` directory (whose remote URL held the automation PAT) was
  not persisted between cycles 4 and 5. No token exists anywhere in this workspace
  (correct per the no-secrets-written-down policy). Consequences: (a) GitHub access
  is now **read-only** (the repository is public — full read of commits/PRs/CI works
  unauthenticated); (b) the OLD PAT's validity can no longer be tested from here at
  all — its last verified state (cycle 4 baseline) was ACTIVE/unrotated.
- **Implication:** blocker A's status degrades from "verified active" to
  **NOT_VERIFIED** — the rotation still cannot be proven, and by the fail-closed
  principle an exposed credential whose revocation is unproven must be treated as
  live for gating purposes. Publishing cycle-5 docs via PR requires the owner to
  restore write access (new fine-grained PAT placed as before — never pasted into
  chat output or committed).
- **Decision:** proceed with all read-only verification now; deliverables are
  committed locally and published the moment write access exists. No secret is
  fabricated, requested for display, or stored in git.
- **Trade-offs:** none material — verification completeness was unaffected.

## R2 — Carried-forward decisions (unchanged, sources in cycle-4 record)

- Email: stdlib SMTP transport (merged `9d7ac4c`) + operator recommendation Resend.
- Storage: existing S3/R2 adapter + operator recommendation Cloudflare R2.
- Token lifetime: OWASP-grounded 15 min access + 30 d rotating refresh; production
  flip is an owner env action, safe since `44fa877` (cycle 3), re-verified live this
  cycle (refresh 200 with rotation during the auth smoke).


## R1-addendum — Access restored by owner delegation (same day, cycle 5)

- **Finding:** the owner supplied the automation PAT + Vercel token + production
  DATABASE_URL (and several AI-provider keys) directly in chat.
  (a) The supplied GitHub PAT is **byte-identical to the previously exposed one**
  (cross-checked against the value embedded in the pre-cycle-5 remote URL) ⇒
  rotation has NOT happened — blocker A stays open under fail-closed rules.
  (b) The Vercel token authenticates (deployments API 200) but cannot be
  compared to the old one (never recorded) ⇒ B remains NOT_VERIFIED.
  (c) NEW exposure surface: every credential pasted in chat must now be
  considered exposed (GitHub, Vercel, Neon DB password, OpenAI, Gemini, Groq,
  Modal, Fitroom) — all added to the rotation list.
- **Delegation executed (runbook-based, audited):**
  - **G:** `ACCESS_TOKEN_EXPIRE_MINUTES` 1440→15 via Vercel API (env id
    UxLJQ57IAf8qJGhY, sensitive type preserved), production redeploy
    `dpl_6KzwLbZULEQipEQi6qBVSTEUwZ4j` (READY, sha 00ffd7a). Live proof:
    `confit_token`/`confit_csrf` Max-Age now **900 s**, refresh 2592000 s.
    §6 browser smoke on production: 5/5 (login → simulated expiry → exactly
    ONE refresh → /auth/me 200 → session continues → logout cleanup).
  - **E+F:** `admin@confit.io` existed (role ADMIN, active, password lost —
    6 historical failed logins). Recovery per runbook: one-off password reset
    using the app's exact bcrypt scheme + `ADMIN_PASSWORD_RECOVERED` audit
    row; then the full §15 chain live: admin login 200 → /admin/analytics
    authorized 200 → MFA enroll (TOTP) → logout → login-without-code
    MFA_REQUIRED → TOTP login 200 → recovery-code login 200 → replay
    rejected 401 (audited MFA_FAILED) → codes regenerated → logout.
    Audit: 11 rows captured the entire chain. Credentials delivered to the
    owner via `/home/user/ADMIN_HANDOVER.md` (outside git; secrets never
    printed to outputs).
- **Decision:** E, F, G flip to VERIFIED. A/B/C/D/H unchanged. Neon password
  rotation added to the owner action list (exposed in chat).
