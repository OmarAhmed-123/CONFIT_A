# Implementation Plan: Brand Catalog Management

**Branch**: `006-brand-catalog-management` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Wire the unused `ProductCreateInput` into partner-facing create/publish/archive endpoints with role + tenant checks (BRD-03), move catalog import out of the request into an async job with row isolation + partial-failure reporting (BRD-04/18), and add a durable object-storage media pipeline with honest unavailability (BRD-11). Shares the async-job abstraction with workstream 008.

## Technical Context

**Language/Version**: Python 3.12; TypeScript/React 18
**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic v2 (`ProductCreateInput`); object storage via `STORAGE_PROVIDER`; async job mechanism (shared with 008)
**Storage**: Product lifecycle fields; `import_jobs` table; media as object-storage URLs (no raw bytes in DB)
**Testing**: pytest (lifecycle RBAC/tenant, import isolation + timeout simulation, storage honest-503), frontend (catalog UI, import report)
**Target Platform**: Vercel serverless, ephemeral FS — long-running import must not run in-request
**Project Type**: Web application
**Constraints**: No local-disk persistence in prod; honest unavailable states.

## Constitution Check

- **I. Evidence Before Appearance**: PASS — import timeout + storage-honesty tests prove behavior.
- **IV. Honest AI & Integrations**: PASS/core — no fake upload success; honest 503 without provider.
- **III**: PASS — partner actions role+tenant gated. **II**: N/A. **V**: PASS.
- **Platform constraint**: import moved out-of-request; media to object storage — compliant with serverless/ephemeral-FS rule.

No violations.

## Project Structure

```text
backend/
├── alembic/versions/00NN_product_lifecycle_and_import_jobs.py  # NEW (reconcile via 011)
├── app/
│   ├── models/ (product lifecycle state; import_jobs; media URL fields)
│   ├── services/ (catalog lifecycle; async import worker; storage adapter)
│   └── controllers/brand_catalog.py (ProductCreateInput wired; import submit/status)
└── tests/
    ├── test_brand_product_lifecycle.py   # NEW (SC-001)
    ├── test_catalog_import_async.py       # NEW (SC-002/003)
    └── test_product_media_storage.py      # NEW (SC-004)
frontend/
└── src/views/brand/ (product editor, import uploader + report, media manager)
```

**Structure Decision**: Web app; async-job + storage abstractions shared with workstream 008.

## Complexity Tracking

> No violations.
