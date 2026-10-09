# CONFIT_A — Feature Traceability Matrix

**Status:** Planning artifact — NO application implementation performed.

**Date:** 2026-10-09

Maps every forensic finding (from the five [`docs/audits/`](../audits/) plans) to its severity, current end-to-end status, the owning Spec Kit workstream under [`specs/`](../../specs/), and the implementation wave from the [master roadmap](./CONFIT_A_MASTER_IMPLEMENTATION_ROADMAP.md). "✓ positive" marks verified guarantees to protect (no regression), which carry no repair workstream.

Status vocabulary: `VERIFIED / IMPLEMENTED / BUG-VERIFIED / GAP / PARTIAL / LIKELY / UNVERIFIED`.

## Coverage summary

- **Total distinct findings mapped:** 101 (ADM ×20, BRD ×18, CUS ×24, STY ×17, VTON ×15, DB ×7). Verified by `comm` against the audit corpus: 0 findings missing from this matrix, 0 matrix IDs absent from the audits.
- **Repair-bearing findings:** every `BUG-VERIFIED`, `GAP`, `PARTIAL`, and `LIKELY` finding is assigned to exactly one owning workstream (cross-cutting UI items are owned by 010 and referenced by the feature workstream).
- **Verified-positive findings:** assigned "protect (no workstream)" — tracked so later work does not regress them.
- **Workstreams:** 12 (001–012); every repair-bearing finding resolves to one owner.

## Admin (ADM)

| Finding | Severity | Status | Workstream | Wave |
|---|---|---|---|---|
| ADM-01 users/roles UI | P1 | GAP | 004 | 2 |
| ADM-02 no role escalation on register | — | ✓ positive | protect | — |
| ADM-03 DB-role auth (not JWT) | — | ✓ positive | protect | — |
| ADM-04 order transition/capture UI | P1 | GAP | 004 | 2 |
| ADM-05 order list/search UI | P1 | GAP | 004 | 2 |
| ADM-06 step-up re-auth silent fail | P2 | BUG-VERIFIED | 004 | 2 |
| ADM-07 promotions admin CRUD | P1 | GAP | 002 | 1 |
| ADM-08 brand verify/suspend UI | P1 | GAP | 004 | 2 |
| ADM-09 catalog takedown UI | P2 | GAP | 004 | 2 |
| ADM-10 ad-billing w/o BrandProfile | P2 | BUG-VERIFIED | 004 | 2 |
| ADM-11 email outbox diagnostics | P2 | GAP | 004 | 2 |
| ADM-12 readiness ops panel | P2 | GAP | 004 | 2 |
| ADM-13 audit viewer/export | P2 | GAP | 004 | 2 |
| ADM-14 KPIs from ledger | P2 | LIKELY | 007 (ledger) → 004 | 3→2 |
| ADM-15 audit hash-chain integrity | — | ✓ positive | protect | — |
| ADM-16 abuse/rate console | P3 | GAP | 004 (later) | 4 |
| ADM-17 feature-flag/kill-switch | P3 | GAP | 004 (later) | 4 |
| ADM-18 confirmation/rollback UX | P2 | LIKELY | 010 (+004) | 0/2 |
| ADM-19 B2B i18n/RTL | P2 | LIKELY | 010 | 0 |
| ADM-20 governance CSV export | P3 | GAP | 004 | 2 |

## Brand owner (BRD)

| Finding | Severity | Status | Workstream | Wave |
|---|---|---|---|---|
| BRD-01 account provisioning | P1 | GAP | 005 | 2 |
| BRD-02 team/RBAC (1:1) | P1 | GAP | 005 | 2 |
| BRD-03 product lifecycle | P1 | GAP | 006 | 2 |
| BRD-04 synchronous import | P2 | BUG-VERIFIED | 006 | 2 |
| BRD-05 ad delivery loop | P1 | BUG-VERIFIED | 007 | 3 |
| BRD-06 spend counters not ledger | P2 | BUG-VERIFIED | 007 | 3 |
| BRD-07 billing statement/PDF | P2 | GAP | 007 | 3 |
| BRD-08 funnel analytics display | P2 | GAP | 007 | 3 |
| BRD-09 tenant isolation fail-closed | — | ✓ positive | protect | — |
| BRD-10 IDOR regression tests | — | ✓ positive | protect | — |
| BRD-11 product media pipeline | P2 | LIKELY | 006 | 2 |
| BRD-12 dashboard static | P2 | LIKELY | 010 (+007) | 0/3 |
| BRD-13 budget pacing/caps | P2 | LIKELY | 007 | 3 |
| BRD-14 order/returns visibility | P2 | LIKELY | 007 | 3 |
| BRD-15 B2B i18n/RTL + a11y | P2 | LIKELY | 010 | 0 |
| BRD-16 revenue attribution display | P2 | LIKELY | 007 | 3 |
| BRD-17 self-serve API keys/webhooks | P3 | GAP | 007 (later) | 4 |
| BRD-18 import partial-failure report | P2 | LIKELY | 006 | 2 |

## Customer (CUS)

| Finding | Severity | Status | Workstream | Wave |
|---|---|---|---|---|
| CUS-01 express parity | P1 | BUG-VERIFIED | 001 | 1 |
| CUS-02 settlement currency mismatch | P1 | BUG-VERIFIED | 001 | 1 |
| CUS-03 stale optimistic totals | P2 | BUG-VERIFIED | 001 | 1 |
| CUS-04 demo banner always shown | P2 | BUG-VERIFIED | 012 | 3 |
| CUS-05 coupon caps not enforced | P1 | BUG-VERIFIED | 002 | 1 |
| CUS-06 live payments fail-closed | — | ✓ positive | protect (012) | — |
| CUS-07 saved cards demo-only | P2 | VERIFIED (honesty) | 012 | 3 |
| CUS-08 PSP-grade validation seam | P2 | LIKELY | 012 | 3 |
| CUS-09 guest order IDOR | P1 | BUG-VERIFIED | 003 | 1 |
| CUS-10 guest returns unexposed | P1 | GAP | 003 | 1 |
| CUS-11 promo market not enforced | P2 | BUG-VERIFIED | 002 | 1 |
| CUS-12 FX display inconsistency | P2 | LIKELY | 001 | 1 |
| CUS-13 stale promo not cleared | P2 | BUG-VERIFIED | 002 | 1 |
| CUS-14 recently-viewed duplicates | P2 | BUG-VERIFIED | 011 (DB-01) | 0 |
| CUS-15 wishlist toggle | — | ✓ positive | protect | — |
| CUS-16 webhook signature fail-closed | — | ✓ positive | protect (012) | — |
| CUS-17 server stock validation | — | ✓ positive | protect | — |
| CUS-18 discount allocation | — | ✓ positive | protect | — |
| CUS-19 checkout a11y/animation | P2 | LIKELY | 010 | 0 |
| CUS-20 address book UX | P3 | LIKELY | 004/consumer (later) | 4 |
| CUS-21 order timeline not live | P2 | LIKELY | 010 | 0 |
| CUS-22 uneven empty/error states | P2 | LIKELY | 010 | 0 |
| CUS-23 no client-trusted prices | — | ✓ positive | protect | — |
| CUS-24 guest cart merge | P2 | LIKELY | 003 | 1 |

## Database (DB)

| Finding | Severity | Status | Workstream | Wave |
|---|---|---|---|---|
| DB-01 recently-viewed duplicates | P2 | BUG-VERIFIED | 011 | 0 |
| DB-03 coupon cap columns | P1 | GAP | 002 | 1 |
| DB-04 redemption not in order txn | P1 | BUG-VERIFIED | 002 | 1 |
| DB-11 VTON raw base64 in DB | P1 | BUG-VERIFIED | 008 (+011 migration) | 2 |
| DB-19 money Numeric(12,2) | — | ✓ positive | protect (011) | — |
| DB-20 unique cart line | — | ✓ positive | protect | — |
| DB-21 (data-integrity positive) | — | ✓ positive | protect | — |

## StyleList AI (STY)

| Finding | Severity | Status | Workstream | Wave |
|---|---|---|---|---|
| STY-01 Mode A absent | **P0** | BUG-VERIFIED | 009 | 1 |
| STY-02 no image upload UI | **P0** | GAP | 009 | 1 |
| STY-03 wardrobe ignored | P1 | BUG-VERIFIED | 009 | 1 |
| STY-04 failover underused | P1 | BUG-VERIFIED | 009 | 1 |
| STY-05 outfit-photo unsupported | **P0** | GAP | 009 | 1 |
| STY-06 rules-only color | P1 | VERIFIED→enhance | 009 | 1 |
| STY-07 no vision model wired | P1 | BUG-VERIFIED | 009 | 1 |
| STY-08 no AI budget | P2 | LIKELY | 009 | 1 |
| STY-09 no upload moderation | P2 | GAP | 009 | 1 |
| STY-10 looks not persisted | P2 | LIKELY | 009 (later) | 4 |
| STY-11 no streaming/agentic | P2 | LIKELY | 009 (later) | 4 |
| STY-12 Mode B grounding/fallback | — | ✓ positive | protect | — |
| STY-13 real products + currency | — | ✓ positive | protect | — |
| STY-14 drawer a11y/i18n | P2 | LIKELY | 010 | 0 |
| STY-15 no eval harness | P2 | GAP | 009 (later) | 4 |
| STY-16 model IDs not documented | P2 | LIKELY | 009 | 1 |
| STY-17 Mode A → VTON handoff | P3 | GAP | 009 (+008, later) | 4 |

## Virtual Try-On (VTON)

| Finding | Severity | Status | Workstream | Wave |
|---|---|---|---|---|
| VTON-01 `.env` worker keys | P2 | VERIFIED (expected) | 008 (readiness) | 2 |
| VTON-02 synchronous render | P1 | BUG-VERIFIED | 008 | 2 |
| VTON-03 client timeout < server | P2 | BUG-VERIFIED | 008 | 2 |
| VTON-04 partial reported as success | P1 | BUG-VERIFIED | 008 | 2 |
| VTON-05 guest poll broken | P2 | BUG-VERIFIED | 008 | 2 |
| VTON-06 raw base64 in DB | P1 | BUG-VERIFIED | 008 (+011) | 2 |
| VTON-07 no content safety | P2 | GAP | 008 | 2 |
| VTON-08 no intake guardrails | P2 | LIKELY | 008 | 2 |
| VTON-09 no retry/backoff | P2 | LIKELY | 008 | 2 |
| VTON-10 no GPU budget | P2 | LIKELY | 008 | 2 |
| VTON-11 honest 503 absent worker | — | ✓ positive | protect | — |
| VTON-12 delivery token purge | — | ✓ positive | protect | — |
| VTON-13 upload UI a11y | P1 | BUG-VERIFIED | 008 + 010 | 0/2 |
| VTON-14 raw `<img>` in modal | P2 | BUG-VERIFIED | 010 | 0 |
| VTON-15 no result gallery | P2 | LIKELY | 008 (later) | 4 |

## Workstream → findings rollup (every workstream owns ≥1 finding)

| Workstream | Owned findings |
|---|---|
| 001 | CUS-01, CUS-02, CUS-03, CUS-12 |
| 002 | CUS-05, CUS-11, CUS-13, DB-03, DB-04, ADM-07 |
| 003 | CUS-09, CUS-10, CUS-24 |
| 004 | ADM-01, ADM-04, ADM-05, ADM-06, ADM-08, ADM-09, ADM-10, ADM-11, ADM-12, ADM-13, ADM-20 (+ADM-14 consume, +ADM-16/17 later) |
| 005 | BRD-01, BRD-02 |
| 006 | BRD-03, BRD-04, BRD-11, BRD-18 |
| 007 | BRD-05, BRD-06, BRD-07, BRD-08, BRD-13, BRD-14, BRD-16, ADM-14 |
| 008 | VTON-01..13, VTON-15, DB-11 |
| 009 | STY-01..11, STY-16, STY-17 |
| 010 | ADM-18/19, BRD-12/15, CUS-19/21/22, VTON-13/14, STY-14 |
| 011 | DB-01, DB-19(protect), §21 chain, CUS-14 |
| 012 | CUS-04, CUS-06(protect), CUS-07, CUS-08, CUS-16(protect) |
