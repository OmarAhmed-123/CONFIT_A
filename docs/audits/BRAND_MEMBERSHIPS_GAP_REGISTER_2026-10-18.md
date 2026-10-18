# Gap Register — BrandMemberships · Brand Analytics · Sleeve Gate (2026-10-18)

Baseline inspected: `main` @ `24d1c08c190e` (clean tree; 0 open PRs; branch
`fix/brand-memberships-sleeve-recalibration` did not exist — created from this SHA).
Sources reconciled: PR #150 close audit comment (authoritative residue list), PR #119 close
audit comment (sleeve-gate deferral rationale), #336 protections, specs/005 +
`docs/audits/BRAND_OWNER_REPAIR_PLAN.md` (T-BRD-02), historical refs recovered from
`pull/119/head` (gate service + `docs/calibration/2026-09-15/*` + `evaluation/human_calibration/*`).

## Feature inventory & status

| Area | Finding (with evidence) | Status |
|---|---|---|
| Brand memberships (model/persistence) | No `brand_memberships` anywhere on main (`grep -rln` over `backend/app` → only `stylist_service.py` prose). Tenant = 1:1 `brand_profiles.user_id UNIQUE` (`models/user.py:82`). Spec 005 T002/T003 planned, never landed. | **Missing → PR 1** |
| Invitations & role management | No `brand_invitations` model/routes/UI. `require_role(BRAND_ROLES)` (`dependencies.py:16,102`) gates on the *global* user role; managers/staff can only act where a global role was set manually — and they still fail `BrandService._resolve_brand` because only the profile owner can resolve a brand. | **Missing → PR 1** |
| Capability separation | Today `brand_auth = require_role(BRAND_ROLES)` grants owner-equal powers to every BRAND_* role on all ~45 partner routes. Spec B acceptance ("owner/manager/staff capabilities differ") unmet. | **Implemented but insufficient (no differentiation) → PR 1** |
| Last-owner protection | Nothing exists (single-owner model had nothing to protect). Becomes a requirement the moment multiple owners are possible. | **Missing → PR 1** |
| Audit integrity | `AuditLog` + HMAC chain (0020–0024) + `UserRepository.log_audit(before=, after=)` exist and are chained by a mapper listener; reused, not duplicated. | **Verified complete (reused)** |
| Global-vs-tenant separation | `register_brand` promotes CONSUMER→BRAND_OWNER *only for the account that itself registers a brand* (self-service provisioning, existing behavior); membership acceptance will NOT touch `users.role` (design rule per brief). | **Verified complete (by design)** |
| Catalog import durability | Mainline has 202 + row validation + `catalog_import_jobs` status rows + per-row error export, executed synchronously in-request — an intentional serverless design (no resident workers on Vercel; the 0038 retention comment records the same rationale). #150's `catalog_import_work` queue with claim/lease has no runner in this deployment model. | **Not applicable — superseded by mainline design** (documented, no duplicate queue) |
| Placement counters | #150 residue claim "placement_counter_events journal missing" is STALE: `brand_controller.py:1046-` "AUDIT P1 CLOSURE" delegates to `AdBillingService` with immutable `AdLedgerEntry`, `UNIQUE(event_key)` exactly-once, daily budget window, click fraud dedupe, reconciliation endpoint. | **Verified complete (superseded design)** |
| Brand-owner analytics | `/partner/analytics*`, BI dashboard, CSV/PDF exports all merged via #355; honesty guards (zero-denominator N/A, funnel labels) enforced by the green BI suite (1944 targeted tests, 2026-10-18). Only real gap: analytics surfaces do not distinguish member roles once memberships exist. | **Verified complete + capability retrofit in PR 1; no second analytics architecture** |
| Frontend team UI | No team/members view anywhere (`views/b2b/` inventory); PartnerPortalBoundary + RoleGuard gate on `user?.role === 'consumer'` only → invited members (consumers globally) could not reach the portal even with a backend. | **Missing → PR 2** |
| VTON current protections | #336: `garment_asset_guard` classifier gate; `assert_layer_applied` canonical per-layer verify; `aggregate_layer_verification`; honest capability registry (`capability_service._vton_capability`). | **Verified complete — must be preserved, not paralleled** |
| Sleeve gate | History recovered: `vton_sleeve_gate.py` v2.3 (changed-garment-color forearm coverage probe; REFUSE <0.15, NOT_VERIFIED [0.15,0.35), PASS ≥0.35; `Product.sleeve_length` authoritative metadata; NULL → never guess). `docs/calibration/2026-09-15/CALIBRATION_REPORT.md`: **"Thresholds UNFROZEN … NOTHING is frozen as a production gate"**; #119 close: needs a fresh engine calibration bench (real `fashn_vton_segfee` worker + human raters). This environment has NO GPU worker and NO engine credentials (`.env.local` holds only GitHub/Neon/S3). | **Blocked by external dependency for the ENFORCE path; independently verifiable work (gate integration, honest contract, calibration harness, tests, fail-safe default OFF) lands in PR 3** |

## Decisions binding the implementation

1. **One-branch, three-PR** per brief; PR 1 backend/domain, PR 2 frontend/analytics verification, PR 3 sleeve gate. Branch reconciled after each merge (repo uses merge commits — verified on `24d1c08`).
2. **Membership is the tenant source of truth**; `brand_profiles.user_id` is kept as the founder/owner anchor and legacy fallback (plan's "keep owner fallback"), never removed.
3. **Single active membership per account** is enforced at invitation acceptance (portal has no brand switcher; multi-brand = documented product limitation, not silent ambiguity).
4. **Capability matrix, server-side only, fail-closed**: `brand:read`/`inventory:write` → any member; `catalog:write`/`stores:write` → manager+owner; `profile:write`/`placements:manage`/`billing:read` → owner; `members:manage` → owner **and no admin override** (platform governance stays separate from tenant governance).
5. **Invitation tokens**: 256-bit `secrets.token_urlsafe(32)`, stored as SHA-256 hash only, 7-day expiry, one-time, per-day email idempotency via `EmailOutbox` event keys; uniform non-enumerating error for unknown/expired/revoked/consumed/email-mismatch.
6. **Last-owner protection** under `SELECT … FOR UPDATE` on the brand row (PostgreSQL; SQLite tests pin the logic, CI postgres job pins the locking semantics).
7. **Migrations append**: `0039_brand_memberships` continues the single-head chain from `0038_vton_job_retention`; backfill is idempotent (`ON CONFLICT DO NOTHING`); prod upgrade is additive-only (the 2026-09-20 documented ordering lesson applies: DB before deploy).
8. **Sleeve gate safety**: `VTON_SLEEVE_GATE_MODE = off | observe | enforce`, default `off`; `enforce` refuses to start unless a validated calibration manifest for the CURRENT engine build is present; missing evidence can never produce a pass; `observe` annotates only.
