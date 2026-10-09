# CONFIT_A — Master Implementation Roadmap

**Status:** Planning artifact — NO application implementation performed.

**Date:** 2026-10-09

**Owner review required before any implementation begins.**

This roadmap is the dependency-aware, priority-ordered plan that enables later implementation agents to repair and complete every CONFIT_A feature end-to-end. It is grounded in:

- the five forensic audit plans under [`docs/audits/`](../audits/) (preserved, not rewritten);
- the Spec Kit workstreams under [`specs/`](../../specs/) (12 workstreams, `spec.md`/`plan.md`/`tasks.md` each);
- the project constitution at [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) (v1.0.0);
- the feature traceability matrix ([`FEATURE_TRACEABILITY_MATRIX.md`](./FEATURE_TRACEABILITY_MATRIX.md)) and release gates ([`DEPENDENCY_AND_RELEASE_GATES.md`](./DEPENDENCY_AND_RELEASE_GATES.md)).

> **Scope note (planning only).** Per the master assignment §§20–24, this document plans work; it does not implement application features, run production migrations, send email, place orders, charge payments, or trigger paid AI requests. No branch is merged.

---

## 1. Repository & baseline evidence

| Dimension | Observation (evidence) |
|---|---|
| Backend | FastAPI (controllers → services → repositories), SQLAlchemy 2, Alembic, Pydantic v2, PyJWT cookie sessions, slowapi. 14 controllers, **192 backend test files**. |
| Frontend | React 18 + TypeScript, Vite, Tailwind, MVVM, zustand, i18n EN/AR + RTL, framer-motion. **229 `.ts/.tsx`**, **41 `*View*` screens**. |
| Database | **34 Alembic migrations, repo head `0034_mfa_email_codes`** (`down_revision 0033_email_preferences`). Money as `Numeric(12,2)`. A production-reported `0035_product_images` is **not in the repo** → see §21 reconciliation (workstream 011). |
| Deployment | Vercel serverless (`api/index.py`, `maxDuration 300`, region `fra1`), ephemeral filesystem. |
| Baseline tests (prior run, test DB) | backend ≈ 3732 passed / 4 environmental-fail (`libEGL.so.1` mediapipe pose) / 21 skipped; frontend build PASS. Environmental failures are separated from app defects per Constitution Principle V and must be re-run in a GL-capable environment. |

**Verified-positive guarantees to protect (do not regress):** DB-role authorization not forgeable JWT (ADM-03), registration cannot escalate role (ADM-02), hash-chained audit log (ADM-15), tenant isolation fail-closed + IDOR tests (BRD-09/10), server-authoritative prices / no client-trusted prices (CUS-23), server-side stock validation (CUS-17), discount allocation correctness (CUS-18), webhook signature fail-closed (CUS-16), live payments fail-closed in demo (CUS-06), honest 503 when VTON worker absent (VTON-11), hashed single-claim delivery token (VTON-12), Mode B catalog grounding + honest fallback (STY-12), real products + currency in outfits (STY-13), `Numeric(12,2)` money (DB-19), unique cart line (DB-20).

---

## 2. Feature inventory by role (end-to-end status)

Status vocabulary: `VERIFIED / IMPLEMENTED / BUG-VERIFIED / GAP / PARTIAL / LIKELY / UNVERIFIED`. Full action→UI→API→auth→service→DB/provider tracing lives per-finding in the audits; the traceability matrix maps every finding to a workstream.

### 2.1 Customer / consumer
| Capability | End-to-end status | Findings | Workstream |
|---|---|---|---|
| Browse, wishlist, recently-viewed | IMPLEMENTED (recently-viewed has dup rows) | CUS-15 ✓, CUS-14/DB-01 | 011 |
| Cart & totals | BUG-VERIFIED (express parity, stale optimistic) | CUS-01/02/03/12/23 | 001 |
| Coupons/promotions | BUG-VERIFIED (caps/market/stale) | CUS-05/11/13, DB-03/04 | 002 |
| Checkout & payment | PARTIAL (demo banner, PSP seam) | CUS-04/06/07/08/16 | 012 (+001 totals) |
| Guest order access & returns | BUG-VERIFIED / GAP (IDOR, returns unexposed) | CUS-09/10, CUS-24 | 003 |
| Stock / discount allocation | VERIFIED | CUS-17/18 | — (protect) |

### 2.2 Admin
| Capability | End-to-end status | Findings | Workstream |
|---|---|---|---|
| Users & roles management | GAP (no UI; DB-only) | ADM-01 | 004 |
| Order ops (list/transition/capture) | GAP (API exists, no UI) | ADM-04/05 | 004 |
| Step-up re-auth handling | BUG-VERIFIED (silent fail) | ADM-06 | 004 |
| Promotions admin CRUD | GAP (+ enforcement cols missing) | ADM-07 | 002 |
| Brand/catalog governance | GAP | ADM-08/09 | 004 |
| Ad-billing admin w/o BrandProfile | BUG-VERIFIED | ADM-10 | 004 |
| Observability / audit / export | GAP | ADM-11/12/13/20 | 004 |
| KPIs from ledger | LIKELY (counters) | ADM-14 | 007 (ledger) → 004 |
| Abuse console / kill-switch | GAP (P3) | ADM-16/17 | 004 (later wave) |

### 2.3 Brand owner / partner
| Capability | End-to-end status | Findings | Workstream |
|---|---|---|---|
| Onboarding → account provisioning | GAP (lead-capture only) | BRD-01 | 005 |
| Team / RBAC | GAP (1:1 only) | BRD-02 | 005 |
| Product lifecycle (create/publish/archive) | GAP (`ProductCreateInput` unused) | BRD-03 | 006 |
| Catalog import | BUG-VERIFIED (synchronous) / GAP (no partial report) | BRD-04/18 | 006 |
| Product media pipeline | LIKELY GAP (ephemeral FS) | BRD-11 | 006 |
| Ad delivery loop | BUG-VERIFIED (no consumer serving) | BRD-05 | 007 |
| Ad spend ledger & pacing | BUG-VERIFIED / LIKELY | BRD-06/13 | 007 |
| Billing statement/PDF | GAP | BRD-07 | 007 |
| Analytics (funnel/attribution/orders) | GAP / LIKELY | BRD-08/16/14 | 007 |
| Tenant isolation | VERIFIED | BRD-09/10 | — (protect) |

### 2.4 Virtual Try-On (cross-role)
| Capability | End-to-end status | Findings | Workstream |
|---|---|---|---|
| Async render pipeline | BUG-VERIFIED (synchronous) | VTON-02/03/09 | 008 |
| Partial-layer honesty | BUG-VERIFIED (partial as success) | VTON-04 | 008 |
| Biometric privacy (no base64 in DB) | BUG-VERIFIED | VTON-06/DB-11 | 008 (+011 migration) |
| Guest poll / token claim | BUG-VERIFIED / VERIFIED | VTON-05/12 | 008 |
| Intake safety / guardrails / budget | GAP / LIKELY | VTON-07/08/10 | 008 |
| Availability honesty | VERIFIED | VTON-01/11 | — (protect) |
| Upload UI a11y / honest image / history | BUG-VERIFIED / LIKELY | VTON-13/14/15 | 008 + 010 |

### 2.5 StyleList AI (cross-role)
| Capability | End-to-end status | Findings | Workstream |
|---|---|---|---|
| Mode A (multi-image/vision) | BUG-VERIFIED / GAP (absent) | STY-01/02/05/07 | 009 |
| Wardrobe grounding | BUG-VERIFIED (ignored) | STY-03 | 009 |
| Provider failover chain | BUG-VERIFIED (underused) | STY-04/16 | 009 |
| Image color extraction | VERIFIED rules-only | STY-06 | 009 |
| Upload safety / AI budget | GAP / LIKELY | STY-08/09 | 009 |
| Mode B grounding / real products | VERIFIED | STY-12/13 | — (protect) |
| Looks / streaming / eval / VTON handoff | LIKELY / GAP (P2/P3) | STY-10/11/14/15/17 | 009 + 010 (+008) |

### 2.6 Shared / unauthenticated & cross-cutting
| Capability | End-to-end status | Workstream |
|---|---|---|
| Accessibility (WCAG 2.2 AA), i18n/RTL, motion, honest imagery, state consistency | BUG-VERIFIED / LIKELY across roles | 010 |
| Alembic chain governance + prod reconciliation (§21) | UNVERIFIED-prod / risk | 011 |
| Consumer ad serving (unauthenticated tracking) | BUG-VERIFIED | 007 |

---

## 3. Workstreams (Spec Kit) index

| # | Workstream | Top severity | Primary findings |
|---|---|---|---|
| 001 | Checkout Total Parity & Settlement Currency | P1 | CUS-01/02/03/12 |
| 002 | Promotions Integrity & Admin CRUD | P1 | CUS-05/11/13, DB-03/04, ADM-07 |
| 003 | Guest Order Trust & Returns | P1 | CUS-09/10/24 |
| 004 | Admin Console | P1 | ADM-01/04/05/06/08/09/10/11/12/13/20 |
| 005 | Brand Provisioning & Team RBAC | P1 | BRD-01/02 |
| 006 | Brand Catalog Management | P1 | BRD-03/04/11/18 |
| 007 | Advertising Delivery Loop, Ledger & Analytics | P1 | BRD-05/06/07/08/13/14/16, ADM-14 |
| 008 | Virtual Try-On Async & Privacy | P1 | VTON-01..15, DB-11 |
| 009 | StyleList AI — Mode A, Grounding, Failover | **P0** | STY-01..17 |
| 010 | UI/UX, Accessibility, i18n/RTL, Motion | P1(a11y) | cross-cutting UI/a11y |
| 011 | Data Integrity & Migration Reconciliation | P1 | DB-01/19, §21 chain |
| 012 | Payments — Honest Demo & PSP Seam | P2 | CUS-04/06/07/08 |

---

## 4. Priority definitions

- **P0 — Fabrication / core-capability-absent:** a headline capability is missing or an honesty violation is severe. (StyleList Mode A, STY-01/05.)
- **P1 — Correctness / security / financial integrity / blocked workflow:** wrong charge, IDOR, broken core loop, unreachable capability.
- **P2 — Honesty/UX/operability defects that mislead or impede but do not mischarge or expose data.**
- **P3 — Enhancements / nice-to-have.**

---

## 5. Implementation waves (dependency-aware sequencing)

Each wave ends at a release gate (see [`DEPENDENCY_AND_RELEASE_GATES.md`](./DEPENDENCY_AND_RELEASE_GATES.md)). Waves are ordered by dependency, not calendar.

### Wave 0 — Foundations & gates (must precede schema work)
- **011** migration reconciliation **gate** (§21): establish the true production head via an authorized read-only check; reconcile prod `0035_product_images` vs repo `0034`; assign collision-free numbering for all schema-touching workstreams. **Blocks execution of every migration below.**
- **010** design-system primitives (a11y/i18n/motion/honest-image) — consumed by all UI work.
- Shared async-job + object-storage abstraction (used by 006 and 008).

### Wave 1 — Financial integrity & security correctness (P0/P1)
- **001** checkout total parity + settlement currency (consumes re-validated discount from 002).
- **002** promotions caps/scope/lifecycle + admin CRUD (migration numbered via 011).
- **003** guest order trust (IDOR) + returns + cart merge.
- **009** StyleList Mode A / grounding / failover (**P0**) — vision via existing providers; no new transport.

### Wave 2 — Role capability completion (P1)
- **005** brand provisioning + team RBAC (migration via 011).
- **004** admin console (consumes 002 promotions, 007 ledger for KPIs; step-up re-auth UX).
- **008** VTON async + partial-layer honesty + biometric privacy (migration via 011; storage from Wave 0).
- **006** brand catalog management (async import + durable media; depends 005 RBAC, Wave 0 storage).

### Wave 3 — Revenue loop & payments (P1/P2)
- **007** advertising delivery loop + ledger billing + analytics (feeds ADM-14 KPIs in 004).
- **012** honest demo payments + PSP seam (charge amount from 001).

### Wave 4 — Enhancements & polish (P2/P3)
- Remaining P2/P3 within each workstream: ADM-16/17, STY-10/11/15/17, BRD-17, VTON-15, CUS-20, address book, streaming stylist, eval harness, result galleries.

---

## 6. Per-workstream verification posture

Every workstream carries, in its `tasks.md`, (a) test-first tasks that MUST fail before implementation, (b) explicit acceptance criteria tied to SC-### success criteria, and (c) a `/speckit.analyze` convergence step. A workstream is "verified complete" only to the extent its required tests ran and passed on a stated commit + environment (Constitution Principle V). Environmental failures (e.g., `libEGL.so.1` for VTON pose) are isolated and must pass in a capable environment or skip with a recorded reason.

---

## 7. What this roadmap deliberately does NOT do

- It does not execute migrations, deploy, send email, place orders, charge payments, or make paid AI calls.
- It does not assume production state from older reports (§21): the prod migration head is recorded as **UNVERIFIED pending an authorized read-only check**.
- It does not merge any branch (including PR #332) or rewrite the five forensic audits.
