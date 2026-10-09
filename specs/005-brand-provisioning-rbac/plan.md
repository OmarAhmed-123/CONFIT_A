# Implementation Plan: Brand Account Provisioning & Team RBAC

**Branch**: `005-brand-provisioning-rbac` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Add a lead→brand-account provisioning path (BRD-01) and a BrandMembership model with server-enforced roles (BRD-02), replacing the 1:1 `BrandProfile.user_id` assumption while preserving fail-closed tenant isolation (BRD-09) and the IDOR regression suite (BRD-10). One forward-chained migration moves existing brands into the membership model.

## Technical Context

**Language/Version**: Python 3.12; TypeScript/React 18
**Primary Dependencies**: FastAPI, SQLAlchemy 2, Alembic, Pydantic v2; existing `brand_service.py` isolation (`:203-221`), `UserRole` (`models/user.py:12-14`)
**Storage**: New `brand_memberships` table; migration to backfill from existing 1:1 profiles; `Numeric(12,2)` unaffected
**Testing**: pytest (role matrix, tenant isolation/IDOR, migration backfill), frontend (team management UI)
**Target Platform**: Vercel serverless
**Project Type**: Web application
**Constraints**: No data loss on migration; fail-closed isolation; no role self-escalation.

## Constitution Check

- **I**: PASS — provisioning + role matrix proven by E2E/role tests.
- **III. Real Authorization**: PASS/core — DB-role + tenant scope server-side; existing IDOR suite extended.
- **II/IV**: N/A. **V**: PASS.

No violations. Migration executed on test DB only; prod reconciliation gated by workstream 011.

## Project Structure

```text
backend/
├── alembic/versions/00NN_brand_memberships.py   # NEW (down_revision = head; reconcile via 011)
├── app/
│   ├── models/ (BrandMembership; BrandProfile 1:many)
│   ├── services/brand_service.py (membership-aware auth; preserve :203-221 isolation)
│   └── controllers/ (provisioning + team CRUD)
└── tests/
    ├── test_brand_provisioning.py     # NEW (SC-001)
    ├── test_brand_role_matrix.py      # NEW (SC-002)
    ├── test_brand_tenant_isolation.py # EXTEND existing IDOR suite (SC-003)
    └── test_brand_membership_migration.py # NEW (SC-004)
frontend/
└── src/views/brand/ (team management; post-provision login→dashboard)
```

**Structure Decision**: Web app; introduce membership as the authorization unit; preserve existing isolation code.

## Complexity Tracking

> No violations. Multi-brand membership is the minimum model needed for BRD-02; a simpler flag-based approach was rejected because roles must be per-brand and tenant-scoped.
