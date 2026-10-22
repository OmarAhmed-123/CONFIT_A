# CONFIT_A — Repository Audit & Proposed Plan

- **Date:** 2026-10-22
- **Auditor:** Lead engineer (onboarding)
- **Clone:** `https://github.com/OmarAhmed-123/CONFIT_A` @ `main` `cfc6d80` (public)
- **Production:** `https://confit-a.vercel.app`
- **Status of this document:** uncommitted working-tree file on `main`. No code changed. No branch, commit, push, deploy, migration, or production action taken.

> Evidence standard: every claim below was observed by running something (git,
> the GitHub API, HTTP probes against production, or reading the source). Items I
> have not yet verified by running are labelled **PENDING** and never stated as fact.

---

## 0. Headline

**Production is down at the API layer, and the cause is infrastructure, not code.**
The Neon PostgreSQL database has exceeded its plan quota and refuses connections.
The application detects this correctly and fails honestly (`503 DATABASE_UNREACHABLE`),
but every data-backed endpoint is unavailable until the database is restored. This
is an **owner action** (Neon billing/quota) and is the top blocker. Nothing else can
be deployed in the meantime, because the `release gate` required check reads
production health and fails closed while the API is down.

---

## 1. What was done

| Step | Result |
|---|---|
| Clone | Failed first into the scratch workspace (Windows path-length limit on a ~200-char base path); re-cloned into `E:\CONFIT` with `core.longpaths=true`. 1,529 files, OK. |
| Structure inspection | Complete (git + filesystem). |
| PRs / issues / CI | Complete (GitHub public REST API; `gh` CLI is not installed on this machine). |
| Production health probes | Complete (`curl` against the live URL). |
| Key source read | `api/index.py`, `backend/app/main.py`, `core/config.py`, `core/schema_gate.py`, CI workflows, README, AGENTS.md, `.env.example`, both `requirements.txt`, `frontend/package.json`. |
| Local dependency install | **PENDING** — backend (`.venv`, Python 3.13) and frontend (`npm ci`) installs are running in the background. |
| Test suite + security scans | **PENDING** — blocked on the installs above. |

Environment note: this machine has git 2.54, Node 24.18 / npm 11.16, Python 3.13 and
3.14. It does **not** have Python 3.12 (which CI uses), `gh`, or Docker.

---

## 2. Repository state

- **Default branch:** `main`, branch-protected (required checks `backend`, `frontend` per README).
- **Branches:** ~180 remote branches. Heavy sprawl: many `docs/cycle*`, `fix/*`, `feat/*`, `feature/*`, `final-*`, `archive/*`. Most look stale/merged. Cleanup candidate (P3).
- **Open PRs: 2** (your brief said five):
  - **#372** `work/production-hardening → main` — a11y announcement-slot + upload-refusal hardening. `mergeable=true`, state `unstable`. Checks: `backend`, `frontend`, `postgres migration chain`, `production parity`, `stylist browser gate`, `gitleaks` all **green**; **`release gate` FAIL** (prod health down — see §3); **`Workers Builds: confit-a` FAIL** (Cloudflare Workers check, not a README-listed required check).
  - **#358** `fix/brand-memberships-sleeve-recalibration → main` — VTON sleeve-integrity gate (mode-gated, default off), +3542/−22 across 35 files. `mergeable=unknown` (needs refresh). Same pattern: core checks green, `release gate` FAIL, `Workers Builds` FAIL.
- **Open issues: 0.**
- **Recent CI (main):** `ci`, `gitleaks`, `release gate` green at 00:39 UTC; **`uptime-monitor` FAIL at 05:39 UTC** — the live outage signal.
- **Migrations:** linear chain `0001` → `0046_user_wishlist_items` (46 revisions). Code's expected head = `0046` (confirmed from the production error body).
- **Tests:** ~230 backend test files; frontend vitest suite (~2060 tests per AGENTS.md).
- **Tags:** `vton-audit-cut1`, `vton-audit-cut2`.

---

## 3. P0 — Production outage (root-caused)

**Evidence (live, 2026-10-22):**

| Endpoint | Status | Body |
|---|---|---|
| `/` (SPA) | 200 | static `index.html` |
| `/api/v1/products?limit=1` | 503 | `DATABASE_UNREACHABLE` |
| `/api/v1/health/ready` | 503 | `DATABASE_UNREACHABLE` |
| `/api/v1/health` | 500 | generic `INTERNAL_SERVER_ERROR` (empty details) |

The 503 body carries the real cause verbatim:

```
pg8000.dbapi.ProgrammingError  {'S':'ERROR','C':'53000',
 'M':'Your account or project has exceeded the quota. Upgrade your plan to increase limits.'}
verdict=unreachable  database_revision=null  expected_head=0046_user_wishlist_items
```

**Root cause:** the Neon Postgres project has **exceeded its plan quota** (Postgres
SQLSTATE `53000`, Neon's quota message). The DB refuses connections → `schema_gate`
returns `unreachable` → `main.py`'s `schema_drift_guard` refuses every non-exempt
path with a structured `503 DATABASE_UNREACHABLE`. This is correct, honest behaviour.

**Why it is not a code fix:** nothing in the repo can make a quota-capped database
accept connections. Resolution is an owner action on Neon (restore/upgrade/raise the
quota, or wait for a resetting usage window). This is behind the approval gates
(spending money / paid-tier upgrade / production infrastructure), so it is yours to
authorise, not mine to perform.

**Collateral effects while the DB is down:**
- `uptime-monitor` fails every 15 min (emails the repo owner — expected).
- `release gate` fails closed on every PR and every push to `main`, so **no PR can merge** until production health returns.
- The authorised read-only production schema check (AGENTS.md gate `G-MIG-1`) cannot run until the DB is reachable.

**Secondary bug exposed (P1, fixable in code):** during `DATABASE_UNREACHABLE`,
`/api/v1/health` returns a bare **500**, not the structured, readable response the
design intends. `schema_gate.py`'s own docstring says `/health` must stay reachable
and *name* the cause so the uptime monitor and operators can read it — here it does
the opposite (the one endpoint that should explain the outage is the one that dies).
The health handler is doing an unguarded DB operation. A small, low-risk fix makes
`/health` return a structured degraded/503 payload (the same cause the request guard
already reports), with a regression test that simulates an unreachable DB. This
touches no production data or infrastructure.

---

## 4. Discrepancies vs the brief (code wins; recorded)

1. **Open PRs:** 2, not 5. Open issues: 0.
2. **AI providers:** not just Groq/Gemini/OpenAI. The failover chain is
   `local_gpu,nvidia,groq,gemini,openai,unorouter`, plus a large **NVIDIA NIM**
   role-routed key pool, **UnoRouter** gateway, a self-hosted vLLM leg, and a
   **Qwen2.5-VL** vision worker. (`core/config.py`, `.env.example`.)
3. **Payment PSPs:** Stripe, Tabby, Tamara **plus Paymob and Fawaterak** (5 adapters), not 3.
4. **Workers:** 8 services, not just `vton-worker` — also `wardrobe`, `anthropometry`,
   `tagging`, `outfit`, `catalog`, `moda-embed`, `vlm`.
5. **Prod DB driver:** production (Vercel) uses **pg8000** (pure-Python); the Docker/CI
   path uses psycopg2-binary. Deliberate (`POSTGRES_DRIVER_POLICY.md`), not a defect.
6. **`AGENTS.md` is stale:** §3 states "repo head is `0034`" and "No Alembic migration
   file exists for the planned workstreams yet." The tree is at `0046`. The agent entry
   point under-reports the real schema state and should be reconciled.
7. **`GROK_API_KEY` vs `GROQ_API_KEY`:** both accepted; `GROQ_API_KEY` is canonical.
   Known past foot-gun (operator set the documented name and silently disabled the one
   verified provider); handled by the `groq_api_key` property.
8. **Python parity:** CI uses 3.12; only 3.13/3.14 are available locally. The backend
   pins `mediapipe>=1.0.0`, which may have no wheel on 3.13/3.14 — backend install may
   partially fail. **PENDING** confirmation from the running install.

---

## 5. Preliminary security posture (full OWASP/ASVS review is a later phase)

Positives observed by reading (not yet by testing):
- Fail-closed production contract in `config.py`: refuses publicly-known/short secrets,
  requires Postgres, requires a dedicated `AUDIT_HMAC_KEY` distinct from `SECRET_KEY`,
  validates email-provider consistency.
- CSRF double-submit for cookie-authed mutations; Bearer requests exempt by design.
- Server-authoritative schema gate + per-request guard (serverless-safe).
- Tamper-evident audit hash chain (migrations 0020–0024).
- httpOnly/Secure/SameSite cookie sessions, bcrypt, Fernet body-data encryption,
  slowapi rate limiting, gitleaks in CI (incl. full-history variant).

Not yet verified: IDOR/object-level authz, file-upload handling, rate-limit coverage
on auth/GPU endpoints, dependency CVEs (`pip-audit`/`npm audit`), secret exposure in
git history. These are the real security-review phase and remain **PENDING**.

---

## 6. Proposed prioritised plan

**P0 — restore service**
1. **Neon quota (owner action).** Decide how to restore the production DB. I can draft
   the runbook and a read-only verification (schema_gate / `validate_database.py`) to
   run the moment it is reachable, but I cannot upgrade/pay. *Blocked on you.*

**P1 — correctness/observability once DB is back**
2. Fix `/health` so `DATABASE_UNREACHABLE` returns a structured, readable response
   instead of a 500 (+ regression test). Safe, no prod access.
3. Review PRs #372 and #358 for merge-readiness; determine whether `Workers Builds:
   confit-a` is a required/meaningful check or noise, and why `release gate` is the
   only functional blocker (expected: it clears itself once prod health returns).
4. Run the authorised read-only production schema parity check (gate `G-MIG-1`) to
   confirm prod DB revision vs `0046` after the DB is restored. *Approval-gated.*

**P2 — baseline & hygiene**
5. Establish the real local test baseline (backend `pytest`, frontend `verify`,
   `pip-audit`, `npm audit`) — install result pending; may require Python 3.12 for parity.
6. Reconcile `AGENTS.md` staleness (head 0034 → 0046) and the doc/spec structure.

**P3 — polish**
7. Branch cleanup (~180 branches), doc consolidation.

**Milestones:** M1 = production live + green uptime; M2 = both open PRs resolved and
merge path unblocked; M3 = verified local/CI parity + security review; M4 = hygiene.

---

## 7. Decisions needed from you

1. **Neon (P0):** How do you want production restored — upgrade the Neon plan, confirm
   it is a resetting usage window, or something else? This is the only thing standing
   between the current outage and a live site.
2. **Git identity / attribution:** `AGENTS.md` §6.2 mandates commits authored **as Omar**
   (`omarsafealden@gmail.com`), with **no** `Co-authored-by` and **no** AI-attribution
   lines. My default would add a Claude `Co-Authored-By` trailer. Confirm I should follow
   `AGENTS.md` (my recommendation) — the two rules conflict and your repo's rule should win.
3. **Doc system:** Your brief defines `docs/00-idea.md … docs/11-*.md` and `docs/STATUS.md`.
   The repo already has an authoritative system (`AGENTS.md` → `.specify/constitution.md`
   → `specs/NNN-*` → `docs/STATUS_MATRIX.md` → `docs/roadmap/*`). I recommend **integrating**
   with that rather than creating a parallel set of docs. Which do you want?
4. **Go-ahead:** Approve this plan? May I start the P1 `/health` fix now (safe, no prod
   access), or hold everything until the DB is back?

Until you decide 2–4, I will not commit, branch, or edit application code. The P0 is yours.
