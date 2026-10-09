# AGENTS.md — CONFIT_A Agent Entry Point

> **Read this first.** This file is the mandatory starting point for every AI agent
> (and every human) working in this repository. It tells you where the authoritative
> requirements, constitution, forensic audits, specifications, dependencies, and
> execution rules live, and the order in which to consult them. It does not duplicate
> those documents — it points to them so there is a single source of truth.

CONFIT_A is a fashion-commerce platform: **FastAPI** backend (controllers → services →
repositories, SQLAlchemy 2, Alembic, Pydantic v2) and a **React 18 + TypeScript / Vite /
Tailwind (MVVM)** frontend, deployed to **Vercel serverless** (ephemeral filesystem).

---

## 1. The non-negotiable gate: the Constitution

**[`.specify/memory/constitution.md`](.specify/memory/constitution.md)** (v1.0.0) governs how
everything is specified, planned, implemented, and verified. Every plan's "Constitution
Check" gate references it. Its five core principles are binding:

1. **Evidence Before Appearance (NON-NEGOTIABLE)** — nothing is "working" without proof;
   use the strict status vocabulary; implementation status and verification status are
   tracked separately; "Done" is forbidden as a standalone claim.
2. **Server-Authoritative Commerce** — the server is the sole authority for every
   financial value; the client is never trusted for anything that affects money.
3. **Real Authorization, Not Hidden UI** — privileged/object-scoped actions are enforced
   server-side on DB-backed roles with tenant isolation that fails closed.
4. **Honest AI & External Integrations** — providers degrade honestly (e.g. honest 503);
   never fabricate images, recommendations, products, stock, price, or capability.
5. **Test-First & End-to-End Verification** — a workstream is "verified complete" only to
   the extent its required tests actually ran and passed.

If a change would violate a principle, stop and justify it in the plan's Complexity
Tracking section (an unjustified violation is a `NO-GO`).

---

## 2. Where the authoritative knowledge lives

| You need… | Go to |
| --- | --- |
| The binding rules of engagement | [`.specify/memory/constitution.md`](.specify/memory/constitution.md) |
| **Forensic audits / findings** (evidence source) | [`docs/audits/`](docs/audits/) — the five role-based repair plans: `ADMIN_REPAIR_PLAN.md`, `CUSTOMER_REPAIR_PLAN.md`, `BRAND_OWNER_REPAIR_PLAN.md`, `VIRTUAL_TRY_ON_REPAIR_PLAN.md`, `STYLELIST_AI_REPAIR_PLAN.md` |
| **Specifications** (what to build, per workstream) | [`specs/NNN-short-name/`](specs/) — each has `spec.md` → `plan.md` → `tasks.md` |
| The master plan & sequencing | [`docs/roadmap/CONFIT_A_MASTER_IMPLEMENTATION_ROADMAP.md`](docs/roadmap/CONFIT_A_MASTER_IMPLEMENTATION_ROADMAP.md) |
| Finding → spec → requirement traceability | [`docs/roadmap/FEATURE_TRACEABILITY_MATRIX.md`](docs/roadmap/FEATURE_TRACEABILITY_MATRIX.md) |
| **Dependencies & release/execution gates** | [`docs/roadmap/DEPENDENCY_AND_RELEASE_GATES.md`](docs/roadmap/DEPENDENCY_AND_RELEASE_GATES.md) |
| Cross-artifact consistency verdict | [`docs/roadmap/CROSS_ARTIFACT_CONSISTENCY_ANALYSIS.md`](docs/roadmap/CROSS_ARTIFACT_CONSISTENCY_ANALYSIS.md) |
| Spec Kit slash commands (authoring tools) | [`.cursor/commands/speckit.*.md`](.cursor/commands/) |

### The 12 workstreams (specs)

| # | Workstream | Primary findings |
| --- | --- | --- |
| 001 | Checkout total parity | CUS-01/02/03/12 |
| 002 | Promotions integrity | CUS-05/11/13, DB-03/04, ADM-07 |
| 003 | Guest order trust & returns | CUS-09/10/24 |
| 004 | Admin console | ADM-01/04/05/06/08/09/10/11/12/13/20 |
| 005 | Brand provisioning & RBAC | BRD-01/02 |
| 006 | Brand catalog management | BRD-03/04/11/18 |
| 007 | Advertising loop | BRD-05/06/07/08/13/14/16, ADM-14 |
| 008 | Virtual try-on (async, privacy) | VTON-01..15, DB-11 |
| 009 | StyleList AI modes | STY-01..17 |
| 010 | UI/UX & accessibility system | cross-cutting |
| 011 | Data integrity & migrations | DB-01/19, §21 chain |
| 012 | Payments / PSP seam | CUS-04/06/07/08 |

---

## 3. Execution rules every agent MUST follow

- **Spec-driven only.** Every implementation-sized change flows through
  `specs/NNN-*/{spec,plan,tasks}.md`. Specs carry `FR-###` requirements and `SC-###`
  success criteria linked to forensic finding IDs. No vague tasks.
- **Three distinct states.** *Planning* ≠ *implementation* ≠ *verified completion*. Never
  collapse them. Report status with the constitution's strict vocabulary.
- **Migrations are PROPOSED, not authored.** No Alembic migration file exists for the
  planned workstreams yet; repo head is `0034`. Workstream **011** is the single numbering
  authority. The true production head is **UNVERIFIED pending an authorized read-only
  check** (gate `G-MIG-1`). Do not create or run migrations during planning.
- **No production mutations during planning** — no migrations, seeds, emails, orders,
  payments, paid AI jobs, or deploys. No PR is merged without explicit authorization and
  passing safeguards (branch protection, required reviews, required CI).
- **Secrets: names only.** Only variable **names** and presence/status may be inspected or
  documented. **Never** print, log, commit, or embed secret values in any artifact
  (Markdown, specs, this file, fixtures, screenshots, or PR comments). See the
  "Secrets & environment configuration" section below.
- **Preserve history.** The five forensic audit plans under `docs/audits/` are historical
  evidence and are not rewritten; re-checks record new evidence and explain discrepancies.

### Suggested 12-step workflow for a new workstream

1. Read this file, then the [constitution](.specify/memory/constitution.md).
2. Read the relevant forensic plan(s) in [`docs/audits/`](docs/audits/) for the findings.
3. Open the workstream spec in [`specs/`](specs/); confirm the `FR-###` / `SC-###` scope.
4. Check [`DEPENDENCY_AND_RELEASE_GATES.md`](docs/roadmap/DEPENDENCY_AND_RELEASE_GATES.md)
   for upstream dependencies and gates that block you.
5. Use `/speckit.specify`, `/speckit.plan`, `/speckit.tasks` to refine artifacts if needed.
6. Satisfy the plan's **Constitution Check** gate before writing code.
7. Write tests first (Principle V); add regression tests for confirmed bugs.
8. Implement behind the server-authoritative / real-authorization / honest-integration
   constraints (Principles II–IV).
9. Run unit/API/frontend/E2E/security/a11y/regression tests as applicable.
10. Run `/speckit.analyze` and `/speckit.converge`; add tasks for unmet criteria; repeat.
11. Record the exact final commit and the tested environment per workstream.
12. Report honestly with the strict status vocabulary — never claim "done".

---

## 4. Secrets & environment configuration

- Required configuration is supplied via **environment variables**; only names/placeholders
  are documented (see the example/template env files in the repo, e.g. `backend/.env.example`
  and `frontend/.env.example` where present).
- `.env` and other real secret files MUST be **git-ignored and untracked**. If you add a new
  required variable, add its **name** to the appropriate `*.env.example` template — never its
  value.
- If a credential is ever pasted into chat or a log, treat it as **compromised** and advise
  the owner to rotate it. Do not reuse it in commits or files.

---

## 5. Pull-request & git conventions

- Keep PRs scoped: planning/documentation PRs must not touch application source, business
  logic, DB schemas, Alembic migrations, production config, or business data.
- Do not bypass branch protection, required reviews, or failing required CI. If a merge is
  blocked, report the precise blocker rather than working around a safeguard.
