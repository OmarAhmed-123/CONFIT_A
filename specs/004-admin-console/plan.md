# Implementation Plan: Admin Console

**Branch**: `004-admin-console` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Build the admin UI over existing (and a small number of new) endpoints: Users & Roles (ADM-01, likely new endpoint), Orders Ops over existing idempotent transition/capture APIs (ADM-04/05), transparent step-up re-auth handling (ADM-06), brand/catalog governance over existing services (ADM-08/09), ad-billing admin decoupled from BrandProfile (ADM-10), and ops/observability/export panels (ADM-11/12/13/20). All authorization stays server-side on DB roles; all sensitive actions are audited and step-up-gated. New endpoints are added only where a true GAP exists.

## Technical Context

**Language/Version**: Python 3.12; TypeScript/React 18
**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic v2; `require_role`/`require_admin_recent` in `app/core/dependencies.py`
**Storage**: Reuse existing user/order/audit tables; no new tables anticipated (user/role endpoints operate on existing `users`).
**Testing**: pytest (RBAC, self-lockout, idempotency, ad-billing regression, audit/export secret-scan), frontend tests (re-auth retry, orders ops)
**Target Platform**: Vercel serverless
**Project Type**: Web application
**Constraints**: No secret exposure in ops/export; idempotent order transitions; audit chain integrity preserved.

## Constitution Check

- **I. Evidence Before Appearance**: PASS — each panel ships with a test proving the server-side control and an audit/secret-scan check.
- **III. Real Authorization**: PASS/core — DB-role enforcement, step-up re-auth, object/tenant checks; UI hiding is never the control.
- **II**: order capture reuses the server-authoritative commerce path (unchanged). **IV**: N/A. **V**: PASS.

No violations. Existing positives (ADM-02/03/15) must remain green.

## Project Structure

```text
backend/
├── app/
│   ├── controllers/admin_*.py   # users/roles (NEW), ops panels (NEW); orders/brands reuse existing
│   ├── services/                # reuse order transition/capture, brand verify/suspend
│   └── core/dependencies.py     # require_role([ADMIN]) :102, require_admin_recent :148
└── tests/
    ├── test_admin_users_roles.py     # NEW (SC-001/002)
    ├── test_admin_orders_ops.py      # NEW (SC-003) + existing test_pay01_fulfillment_gate.py
    ├── test_admin_adbilling_no_brandprofile.py  # NEW (SC-005, ADM-10)
    └── test_admin_audit_export_secretfree.py    # NEW (SC-006)
frontend/
└── src/views/admin/   # UsersRoles, OrdersOps, Governance, Ops panels; re-auth modal interceptor
```

**Structure Decision**: Web app; new endpoints limited to user/role management and ops panels; everything else wraps existing services.

## Complexity Tracking

> No violations.
