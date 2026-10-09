# CONFIT_A — Dependencies & Release Gates

**Status:** Planning artifact — NO application implementation performed.

**Date:** 2026-10-09

Defines the cross-workstream dependencies, the hard gates that must pass before each implementation wave ships, and the §21 production-migration reconciliation gate. Companion to the [master roadmap](./CONFIT_A_MASTER_IMPLEMENTATION_ROADMAP.md) and [traceability matrix](./FEATURE_TRACEABILITY_MATRIX.md).

---

## 1. Dependency graph (who-needs-whom)

```
011 (migration chain + §21 reconciliation)  ──gates──▶  002, 005, 006, 007, 008  (all schema-touching)
010 (a11y/i18n/motion/honest-image primitives) ──feeds──▶ 004, 006, 007, 008, 009 (all UI surfaces)
Wave-0 shared async-job + object-storage ──feeds──▶ 006 (import/media), 008 (render/images)

001 (price_quote single engine) ──feeds──▶ 012 (charge == server total), consumes discount from 002
002 (promotions caps/scope) ──feeds──▶ 001 (re-validated discount), 004 (admin promo CRUD)
005 (brand RBAC/memberships) ──gates──▶ 006 (partner role checks), 007 (brand-scoped views)
007 (ad billing ledger) ──feeds──▶ 004 (ADM-14 KPIs from ledger)
008 (VTON privacy/async) ──relates──▶ 009 (STY-17 Mode A→VTON handoff), shares storage w/ 006
009 (StyleList Mode A) ──consumes──▶ 010 (drawer a11y), shares upload-privacy pattern w/ 008
```

### Hard ordering constraints
1. **No migration executes before the 011 §21 gate passes** (true prod head confirmed; chain reconciled; collision-free numbering assigned).
2. **005 before 006/007 brand UI** (role/tenant checks depend on memberships).
3. **002 before/with 001** (parity consumes the re-validated discount).
4. **007 ledger before 004 ADM-14 KPI panel** (KPIs read the ledger).
5. **010 primitives before the UI tasks** of 004/006/007/008/009 (avoid re-solving a11y/i18n per surface).

---

## 2. §21 Production-migration reconciliation gate (CRITICAL)

**Finding:** repo Alembic head is `0034_mfa_email_codes` (`backend/alembic/versions/0034_mfa_email_codes.py`). A production `0035_product_images` is referenced by the audits but is **not in the repo** and **cannot be re-verified during this planning assignment** (no prod access; no prod mutations permitted).

**Current honest status:** production migration head = **UNVERIFIED — pending authorized read-only check.** (§21: an earlier report does not prove current production state.)

**Gate requirements (must ALL pass before any migration wave deploys):**

- [ ] G-MIG-1 — Perform an **authorized, read-only** check of production `alembic_current` and record the true head. (NOT performed during planning.)
- [ ] G-MIG-2 — Reconcile the chain: import or explicitly supersede prod `0035_product_images` so repo and prod share **one linear history** with no duplicate revision ids.
- [ ] G-MIG-3 — Assign collision-free sequential numbering to the six workstream migrations (002 promotions, 005 memberships, 006 product-lifecycle/import, 007 ad-ledger, 008 tryon-image-drop, 011 recently-viewed-unique); **no two share a `down_revision`.**
- [ ] G-MIG-4 — On the test DB, `alembic heads` returns exactly one head and `upgrade head`/`downgrade base` both succeed (reversible).
- [ ] G-MIG-5 — Money-column check: 0 columns converted away from `Numeric(12,2)` (DB-19).

Owner: workstream **011**. Blocks: 002, 005, 006, 007, 008.

---

## 3. Per-wave release gates

A wave ships only when its gate passes. Every gate requires: required tests ran and passed on a recorded commit + environment; no regression of the protected positives (§4); `/speckit.analyze` clean for the wave's workstreams; no secret values exposed.

### Gate W0 — Foundations
- [ ] 011 §21 gate (G-MIG-1..5) satisfied or explicitly deferred with migrations held.
- [ ] 010 primitives published (accessible controls, `HonestProductImage`, i18n catalog, reduced-motion wrapper, state components); axe scan harness in place.
- [ ] Shared async-job + object-storage abstraction available with honest-unavailable behavior.
- [ ] Recently-viewed dedup (DB-01) test green.

### Gate W1 — Financial integrity & security (P0/P1)
- [ ] 001 SC-001..005: cart/order parity to the cent across the shipping×threshold×fulfillment matrix; single settlement resolver; component-sum identity; CUS-01 regression green.
- [ ] 002 SC-001..005: race-safe caps (min(C,K), 0 over-redemption); market/window enforced; redemption atomic with order; admin CRUD RBAC.
- [ ] 003 SC-001..004: order-number-only lookups denied; enumeration discloses 0 orders; guest returns end-to-end; cart merge dedupe.
- [ ] 009 (P0) SC-001..006: Mode A grounded in real catalog with real served model; wardrobe influence proven; failover + honest unavailability; no fabricated products; Mode B positives preserved.

### Gate W2 — Role capability completion (P1)
- [ ] 005 SC-001..004: provisioning E2E; role matrix enforced; IDOR green; membership migration preserves all brands.
- [ ] 004 SC-001..006: users/roles (audited, self-change blocked); orders ops + idempotent transition/capture (fulfillment gate green); step-up re-auth retry; ad-billing w/o BrandProfile; audit/export secret-free.
- [ ] 008 SC-001..006: async submit/poll no client timeout; partial never COMPLETED; 0 raw images in DB + deletion scrub; guest poll + token claim; intake safety/budget; honest readiness/503 preserved; pose test env-gated.
- [ ] 006 SC-001..004: product lifecycle RBAC/tenant; async import no timeout + partial-failure report; durable media or honest 503.

### Gate W3 — Revenue loop & payments (P1/P2)
- [ ] 007 SC-001..005: consumer impression/click from consumer context (no brand auth); spend == ledger (0 drift); cap pacing; statement totals == ledger; attribution not double-counted.
- [ ] 012 SC-001..006: demo banner iff demo mode; honest demo cards (no real token); PSP seam fail-closed (CUS-06); webhook mismatch rejected + idempotent (CUS-16); charge == price_quote total; 0 PSP secrets exposed.

### Gate W4 — Enhancements (P2/P3)
- [ ] Remaining P2/P3 items delivered with their own tests; no regression of W0–W3 gates.

---

## 4. Protected positives (regression gate for every wave)

Any wave that regresses one of these FAILS its gate:
ADM-02, ADM-03, ADM-15, BRD-09, BRD-10, CUS-06, CUS-15, CUS-16, CUS-17, CUS-18, CUS-23, VTON-11, VTON-12, STY-12, STY-13, DB-19, DB-20.

---

## 5. Environmental & safety constraints (all waves)

- **Serverless/ephemeral FS:** long-running work (VTON render, catalog import) MUST run out-of-request; durable storage MUST be object storage, never local disk in production.
- **Environmental test failures** (e.g., `libEGL.so.1` for `test_vton_pose_artifact_regression.py`) must pass in a GL-capable environment or skip with a recorded reason — never silently ignored (Constitution V).
- **Secrets:** only variable NAMES/presence referenced; no secret values printed, logged, committed, or embedded.
- **No production mutations during planning:** no migrations, seeds, emails, orders, payments, paid AI jobs, or deploys. No branch merged (including PR #332) without explicit authorization.
