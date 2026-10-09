# Implementation Plan: Data Integrity & Migration Reconciliation

**Branch**: `011-data-integrity-migrations` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Act as the single authority for Alembic chain ordering. Establish (via a future authorized read-only check) the true production head vs repo head `0034_mfa_email_codes`, reconcile the prod-reported `0035_product_images` so repo and prod share one linear history, number all six workstream migrations (002/005/006/007/008/011) off the confirmed head with no collisions, verify reversibility on the test DB, and add the recently-viewed unique constraint (DB-01). No production migration is executed during planning.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: Alembic, SQLAlchemy 2
**Storage**: SQLite (test DB) for verification; production DB out of scope for planning
**Testing**: pytest + alembic (single-head assertion, upgrade/downgrade round-trip, down_revision uniqueness, recently-viewed dedup, money-column grep)
**Target Platform**: Vercel serverless (migrations run out-of-band, authorized)
**Project Type**: Web application (backend/data)
**Constraints**: §21 — no assuming prod state from old reports; no prod mutation during planning; reversible chain; one head.

## Constitution Check

- **I. Evidence Before Appearance**: PASS/core — prod head is recorded honestly as UNVERIFIED-pending-authorized-check; nothing is claimed about prod without evidence.
- **Safety constraint**: PASS/core — no migration executed against prod during planning.
- **Data constraint**: PASS — `Numeric(12,2)` preserved.
- **II/III/IV**: N/A. **V**: PASS — reversibility + single-head tests.

No violations.

## Project Structure

```text
backend/
├── alembic/versions/
│   ├── 0034_mfa_email_codes.py            # current repo head (down_revision 0033)
│   ├── 00NN_recently_viewed_unique.py     # NEW (DB-01)
│   └── (sequential numbering authority for 002/005/006/007/008 migrations)
├── app/models/ (RecentlyViewed unique (user_id, product_id))
└── tests/
    ├── test_migration_single_head.py      # NEW (SC-002/003)
    ├── test_migration_roundtrip.py        # NEW (SC-002)
    └── test_recently_viewed_dedup.py      # NEW (SC-004)
docs/roadmap/DEPENDENCY_AND_RELEASE_GATES.md  # records the prod-head check gate (§21)
```

**Structure Decision**: Backend/data; this workstream owns revision numbering for all schema-touching workstreams.

## Complexity Tracking

> No violations. Centralizing migration ordering here is the simplest way to prevent cross-workstream collisions; the alternative (each workstream numbering independently) is explicitly rejected as collision-prone.
