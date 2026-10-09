# CONFIT_A Constitution

<!--
This constitution governs how CONFIT_A is specified, planned, implemented, and verified.
It is the top gate referenced by every Spec Kit plan's "Constitution Check".
Version 1.0.0 — ratified 2026-10-09 (authored during the master planning assignment).
-->

## Core Principles

### I. Evidence Before Appearance (NON-NEGOTIABLE)
No feature, fix, test result, or integration may be claimed to work without evidence. A page that renders, an endpoint that exists, or a button that shows a success toast is NOT proof of working functionality. Every status uses the strict vocabulary: `VERIFIED / IMPLEMENTED / TESTED-PASS / TESTED-FAIL / BUG-VERIFIED / GAP / LIKELY / UNVERIFIED / BLOCKED / NO-GO / NOT FOUND IN SEARCHED SCOPE`. Implementation status and verification status are tracked separately; a thing may be `IMPLEMENTED` yet `UNVERIFIED`. "Done" is forbidden as a standalone claim.

### II. Server-Authoritative Commerce
The server is the sole authority for every financial calculation: prices, quantities, discounts, currency, taxes, shipping, and totals. The client MUST NOT be trusted for any value that affects money. The amount displayed and the amount charged MUST derive from one pricing authority for the same business context. Coupon eligibility and redemption limits are enforced server-side and are race-safe. Failed financial operations MUST produce honest states — never a misleading success.

### III. Real Authorization, Not Hidden UI
Hiding a control in the UI is not authorization. Every privileged or object-scoped action MUST be enforced server-side with DB-backed roles (never a client-selected or JWT-forgeable role), object-level ownership checks, and tenant isolation that fails closed. Sensitive admin actions require step-up re-authentication and emit tamper-evident audit records.

### IV. Honest AI & External Integrations
AI and external providers MUST degrade honestly. Never fabricate a rendered image, a recommendation, a product, stock, price, or a provider capability. When a provider/worker is unconfigured or unavailable, return an explicit blocked/unavailable state (e.g. honest 503), never a fake result. Recommendations MUST be grounded in the real catalog. The model actually served MUST be reported truthfully.

### V. Test-First & End-to-End Verification
Every meaningful feature has a defined verification strategy spanning unit, API/integration, frontend, end-to-end, security, accessibility, reliability, and regression tests as applicable. Confirmed bugs get regression tests. Skipped tests are not passing tests; environmental failures are identified and separated from application defects but never silently ignored. A workstream is "verified complete" only to the extent its required tests actually ran and passed, with remaining limitations documented.

## Additional Constraints (Technology & Platform)

- **Backend:** FastAPI (controllers → services → repositories), SQLAlchemy 2, Alembic migrations, Pydantic v2 request/response validators on all public functions, `await` on all async DB/scheduler calls, indexed queries (no unbounded scans), money as `Numeric(12,2)`.
- **Frontend:** React 18 + TypeScript, Vite, Tailwind, MVVM, zustand, i18n (EN/AR + RTL), framer-motion (respecting `prefers-reduced-motion`).
- **Data & privacy:** sensitive/biometric-adjacent images (try-on person photos, stylist outfit photos) are never stored as raw base64 in the DB; use short-TTL encrypted storage or discard, and scrub on account deletion.
- **Deployment:** Vercel serverless (`api/index.py`, `maxDuration 300`, region `fra1`), ephemeral filesystem — long-running work (VTON render, large imports) MUST NOT run inside a single serverless request; durable storage MUST be a real object-storage provider, never local disk in production.
- **Secrets:** only variable NAMES and presence/status may be inspected or documented. Secret values are never printed, logged, committed, or embedded in any artifact.
- **Accessibility:** WCAG 2.2 AA is the planning target; automated (axe) and manual verification are tracked separately.

## Development Workflow & Quality Gates

- **Spec-driven:** every implementation-sized workstream has `spec.md` → `plan.md` → `tasks.md` under `specs/NNN-*/`. Specs carry stable requirement IDs (FR-###), measurable success criteria (SC-###), and link to forensic finding IDs. Tasks carry stable IDs, linked requirements/findings, acceptance criteria, required tests, and a verifiable completion signal. Vague tasks ("fix the API", "make it professional") are prohibited.
- **Planning vs implementation vs verified completion** are three distinct states and are never collapsed.
- **Convergence:** after implementation, run `/speckit.analyze` (cross-artifact consistency) and `/speckit.converge`; add tasks for unmet acceptance criteria; repeat until criteria pass or a concrete blocker remains. Record the exact final commit and tested environment per workstream.
- **Safety:** no production mutations during planning (no migrations, seeds, emails, orders, payments, paid AI jobs, deploys). No PR is merged without explicit authorization.

## Governance

This constitution supersedes ad-hoc practice. Amendments require a version bump, a dated rationale, and propagation to dependent templates/plans. Every `plan.md` MUST include a Constitution Check gate and justify any violation in its Complexity Tracking section; unjustified violations are a `NO-GO`. The five forensic audit plans under `docs/audits/` are preserved as historical evidence sources and are not rewritten; current re-checks record new evidence and explain discrepancies rather than editing history.

**Version**: 1.0.0 | **Ratified**: 2026-10-09 | **Last Amended**: 2026-10-09
