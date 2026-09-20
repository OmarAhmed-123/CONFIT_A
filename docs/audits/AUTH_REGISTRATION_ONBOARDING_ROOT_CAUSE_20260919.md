# CONFIT_A — Authentication / Registration / Onboarding / Email — Phase 1–2 Evidence & Root-Cause Matrix

**Date:** 2026-09-19 · **Branch audited:** `origin/main` @ `928e615` (feat(tooling): integrate engineering toolchain utilities)
**Scope:** authentication, authorization entry flows, registration, first-time onboarding, email-verification / password / email lifecycle, post-auth routing.
**Method:** source inspection (backend MVC + frontend MVVM), migration inspection, test inspection, live production probes. No change made before this document.

---

## 0. Symptom under investigation

Screenshot (`uploads/image-1.png`): user **ismaeil1234@gmail.com**, role **consumer**, hitting a B2B/Brand portal route:

```
403 FORBIDDEN · ROLE RESTRICTION — Access Restricted
"…requires one of the following permissions: brand_owner, brand_manager, brand_staff, admin."
```

Rendered by `frontend/src/components/auth/RoleGuard.tsx` (lines 100–145) for `allowedRoles = ['brand_owner','brand_manager','brand_staff','admin']` (`AppRoutes.tsx:53`, applied to `/b2b`, `/partner`, `/admin`).

**The 403 is correct authorization behaviour.** The defect is the *absence of any legitimate workflow* by which a real person can reach a brand role, and the absence of any in-product explanation/next step other than a dead-end page.

---

## 1. Phase-1 audit — what actually exists (verified in source)

### 1.1 Backend authentication (`backend/app/…`) — operational
| Area | Evidence | Status |
|---|---|---|
| Password hashing | `core/security.py:29-52` bcrypt only, malformed hash fails closed | IMPLEMENTED |
| Password policy | `core/security.py:68-88` length 8–72 + ≥3 of 4 categories, server-side | IMPLEMENTED |
| Access/refresh split | `core/security.py:91-119` different signing keys, `type` claim, iss/aud | IMPLEMENTED |
| Refresh rotation + reuse detection | `models/user.py` `RefreshToken` (jti, family_id, revoked_at, replaced_by_jti); `auth_service.refresh` | IMPLEMENTED |
| Session cookies | `controllers/auth_controller.py:48-70` `confit_token` (HttpOnly), `confit_csrf` (readable double-submit), `confit_refresh`; `secure` only when `ENVIRONMENT=production`; `samesite=lax` | IMPLEMENTED (gap: no HSTS/CSP-level cookie prefix, no idle timeout) |
| CSRF | `main.py:117-139` double-submit guard for cookie-auth mutations; exemptions only login/register/social-login | IMPLEMENTED |
| RBAC | `core/dependencies.py:100-148` `require_role`, `require_brand_scope`, `require_admin_recent` | IMPLEMENTED |
| MFA | TOTP + bcrypt-hashed single-use backup codes (`auth_service`) | IMPLEMENTED |
| Rate limiting | slowapi per-IP: register 5/min, login 10/min, forgot/reset/verify-request 5/min, verify 10/min, change-password 10/min | IMPLEMENTED |
| Audit log | `AuditLog` with before/after JSON + `request_id` (`models/user.py`, `0017`) | IMPLEMENTED |
| Registration | `AuthService.register` hard-codes `UserRole.CONSUMER`; `UserRegister` schema has **no role field** (`extra="ignore"`) | IMPLEMENTED (secure) |
| Password reset / verification tokens | SHA-256 hashed, one-time, 30 min / 24 h TTL (`PasswordResetToken`, `EmailVerificationToken`) | IMPLEMENTED |
| Email change | — | **MISSING** |
| Partner/brand registration intent | — | **MISSING** |
| Partner application / approval workflow | — | **MISSING** (BRD G6 §2.2 requires *admin: partner onboarding approvals*) |
| Invitations | — (BRD G6 §2.1 requires *owner: user invitations*) | **MISSING** |
| Onboarding state model (server) | only `UserOut.has_profile` | **MISSING / partial** |

### 1.2 Email infrastructure
| Area | Evidence | Status |
|---|---|---|
| Transport | `services/email_service.py` real stdlib `smtplib` (STARTTLS/SSL), 10 s timeout, 2 attempts on transient, hard rejection raises `EmailDeliveryError` | IMPLEMENTED |
| Templates | verification + password-reset only (EN/AR) | PARTIAL |
| Delivery record | **none** — no persisted delivery status; `request_email_verification` returns `{"status": "queued"}` even when the send failed (`auth_service._send_verification_email` swallows `EmailDeliveryError`) | **GAP (honesty)** |
| Idempotency / duplicate-resend control | none | **GAP** |
| Config template | `backend/.env.example §9` documents `SMTP_USER` / `SMTP_PASS` / `MAIL_FROM_NAME` — code reads `SMTP_USERNAME` / `SMTP_PASSWORD` / `EMAIL_FROM_ADDRESS`; `EMAIL_PROVIDER`, `EMAIL_FROM_ADDRESS`, `FRONTEND_BASE_URL` undocumented | **GAP (config drift)** |
| Production provisioning | live probe `POST /api/v1/auth/verify-email` → **HTTP 501 `FEATURE_NOT_CONFIGURED`** | **BLOCKED in production** |

### 1.3 Production probe evidence (2026-09-19, `https://confit-a.vercel.app`)
```
GET  /api/v1/health            → 200 healthy; schema head 0017_audit_before_after_request_id == expected; database healthy
GET  /api/v1/auth/me           → 401 {"code":"AUTH_FAILED","message":"Authorization bearer token required."}
POST /api/v1/auth/verify-email → 501 FEATURE_NOT_CONFIGURED  (email provider not configured in production)
POST /api/v1/auth/forgot-password (reserved-domain address) → 422 (EmailStr domain rule) — probe artifact, not a finding
```
Consequence: **in production, registration cannot send a verification email, and password recovery is impossible.** Accounts are created with `is_verified=True` because `UserRepository.create` uses `is_verified=not bool(settings.EMAIL_PROVIDER)` (`repositories/user_repository.py:40`). The flag is therefore *never earned* in the current production configuration.

### 1.4 Frontend (`frontend/src/…`)
| Area | Evidence | Status |
|---|---|---|
| Session bootstrap | `App.tsx:27` root-level `fetchMe()`; `authStore.hasSessionEvidence()` avoids guaranteed-401 calls | IMPLEMENTED |
| Role gate | `components/auth/RoleGuard.tsx` — UX-only; role from `/auth/me`, `admin` implicitly passes every gate (line 98) | IMPLEMENTED (UX) |
| 403 page | static dead-end; no route to resolution, no distinction between *not authorized* and *not yet provisioned* | **GAP (UX)** |
| Registration form | `views/auth/AuthModal.tsx` collects email/password/name/phone only; no intent | **GAP** |
| Verify-email / reset-password / invitation routes | **do not exist**; email links point to `/verify-email?token=…` and `/reset-password?token=…`, which the SPA catch-all (`AppRoutes.tsx:215`) redirects to `/` | **GAP (dead links)** |
| Onboarding gate | `AppRoutes.tsx:15-28` uses `has_profile` only; no email-verification state; partner intent would loop | PARTIAL |
| Post-login landing | `AuthModal.tsx:18-23` role→route mapping (admin→/admin, brand_*→/b2b) | IMPLEMENTED |
| `authService.register` still types `role?: string` | `services/apiServices.ts:37` (server ignores it) | GAP (contract debt) |

### 1.5 BRD ↔ implementation contradictions (explicit, not silently normalised)
| BRD statement | Reality | Verdict |
|---|---|---|
| G1 §5.1 `POST /auth/register` payload includes `"role": "consumer"` | Field removed server-side after the P0 privilege-escalation incident (production exploit 2026-09-05) | **BRD stale — security wins**; BRD/RTM must be corrected |
| G1 §2.1 access token 60 min | `ACCESS_TOKEN_EXPIRE_MINUTES=15` | BRD stale (documented remediation) |
| G6 §2.1 brand roles `owner / manager / analyst / catalog_editor` | code: `brand_owner / brand_manager / brand_staff` | **Divergence — needs recorded disposition** |
| G6 §2.2 admin roles `admin / super_admin` | code: `admin` only | **Divergence** |
| G6 §2.1 owner can invite users; G6 §2.2 admin approves partner onboarding | neither workflow exists in any layer | **BRD requirement unimplemented** |
| RTM G1-01 "role: consumer passed through" | contradicted by the hardened implementation | RTM row must be updated |

---

## 2. Root causes (causes, not symptoms)

**RC-1 — No role-provisioning workflow of any kind.**
Grep over `backend/` and `frontend/`: zero occurrences of invitation, partner application, brand provisioning, or approval code. Roles other than `consumer` exist only via `seed_data.py` and direct repository writes. A real user who wants brand access has **no path**; the 403 page is the only thing that ever reports the state.

**RC-2 — Registration conflates *intent* with *authorization*.**
`register()` forces `role=consumer` for everyone (correct for security) but nothing captures *why* the person registered. A brand/partner registrant is silently turned into a consumer with no pending-application state and no follow-up — the exact user in the screenshot.

**RC-3 — No server-side onboarding/account state machine.**
The only state the server exposes is `has_profile`; email-verified, partner-pending, invited, suspended and recovery states are invisible to routing. The frontend therefore cannot route deterministically and the backend cannot enforce a lifecycle.

**RC-4 — Email delivery is honest about *configuration* but dishonest about *outcome*.**
501 when unconfigured (good). But when configured and the relay fails, the API still reports `{"status":"queued"}`, no delivery record is persisted, and the UI is free to claim "we sent you an email". There is also no resend/idempotency control.

**RC-5 — Production has no email provider configured (BLOCKED).**
Verified live 501. Registration e-mails, verification and password recovery are non-functional in production today.

**RC-6 — The 403 surface is a dead end.**
`RoleGuard` shows "Access Restricted" with no way forward; it does not distinguish `401 unauthenticated`, `403 not provisioned`, `pending approval`, `suspended`, or `pending verification`, contrary to the required UX (§18 of the task).

**RC-7 — Config-template drift on the email settings.**
Operators following `backend/.env.example` set variables the code never reads → provider appears configured, boots fail or sends silently mis-target. (Compounds RC-5.)

---

## 3. Gap matrix (Requirement → Current → Gap → Root cause → Fix → Test → Evidence → Status)

| # | Requirement (BRD/task §) | Current implementation | Gap | Root cause | Fix (planned) | Test | Evidence | Status |
|---|---|---|---|---|---|---|---|---|
| G-01 | Registration must never grant privilege (task §3) | register hard-codes CONSUMER | none | — | keep + regression-lock | `test_register_role_escalation.py` | prod probe | VERIFIED |
| G-02 | Registration intent separate from role (task §3, §9) | absent | no intent field/storage | RC-2 | `users.registration_intent` + register accepts intent (validated enum) | `test_registration_intent.py` | migration 0018 | GAP→fix |
| G-03 | Brand/partner entry workflow (BRD G6 §2.2) | absent | no application flow | RC-1 | `partner_applications` + submit/withdraw/status API + admin approve/reject provisioning | `test_partner_onboarding_workflow.py` | new endpoints | GAP→fix |
| G-04 | Admin approves partner onboarding (BRD G6 §2.2) | absent | no admin review surface | RC-1 | `/admin/partner-applications` + guarded approve/reject with audit + email | same | audit rows | GAP→fix |
| G-05 | Brand users bound to brand tenant (BRD G6 §7) | `require_brand_scope`, `brand_profile` | provisioning path missing | RC-1 | approval creates `BrandProfile` + `role=brand_owner` transactionally | same + cross-tenant test | 200/403 assertions | GAP→fix |
| G-06 | User invitations (BRD G6 §2.1) | absent | no invite model/API | RC-1 | `invitations` + brand-owner issue/list/revoke + accept flow (role only from server-issued token) | `test_invitations.py` | tokens hashed | GAP→fix |
| G-07 | Server-side onboarding state machine (task §4) | `has_profile` only | routing state not authoritative | RC-3 | `account_state`/`next_action` computed server-side + `/auth/onboarding-state` | `test_onboarding_state_machine.py` | API payload | GAP→fix |
| G-08 | Consumers hitting B2B get a precise, actionable state (task §8, §18) | static 403 | dead end | RC-6 | `PartnerAccessGate` with distinct states + CTAs (apply / pending / suspended), backend still authoritative | vitest + api | screenshots/tests | GAP→fix |
| G-09 | Real verification/reset emails redeemable from links (task §5,§12) | API exists; **no frontend routes** | dead link | RC-6 | `/verify-email`, `/forgot-password`, `/reset-password` routes; token consumption server-side | vitest + e2e api | route tests | GAP→fix |
| G-10 | No false “email sent” claims (task §15,§18,§33) | `queued` even on failure | fake success | RC-4 | persist `email_deliveries` (status/provider/error class), return honest status, idempotency key | `test_email_delivery_honesty.py` | table rows + API | GAP→fix |
| G-11 | Production email delivery (task §17, §32) | 501 live | provider unset | RC-5 | document required env; adapter supports smtp/resend; verification only with real creds | prod probe | 501 today | **BLOCKED** |
| G-12 | Email-change flow (task §11) | absent | — | RC-1 | two-step request/confirm with hashed single-use token + audit + notice mail | `test_email_change_flow.py` | tokens | GAP→fix |
| G-13 | Templates for all lifecycle mails (task §16) | 2 of 8 | missing | RC-4 | `email_templates.py` with escaping + plain-text alt | template tests | rendered output | GAP→fix |
| G-14 | Config template matches code (task §17) | drifted names | operator misconfig | RC-7 | rewrite `backend/.env.example §9` + `.env.example` | config test | file diff | GAP→fix |
| G-15 | Open-redirect safety on auth redirects (task §27) | no `next=` handling at all | will be introduced by new flows | RC-3 | internal-route allowlist helper | negative test | 400 on external | GAP→fix |
| G-16 | Duplicate/race/idempotency guarantees (task §22) | partial (unique email) | no constraints on new flows | RC-1 | partial unique indexes (`pending` application per user, pending invite per email+brand) + IntegrityError→409 | concurrency tests | DB constraints | GAP→fix |
| G-17 | MCP Market email integration decision (task §13) | not done | — | — | evaluate directory, document decision, no MCP in the auth send path | decision doc | `docs/audits/` | GAP→fix |
| G-18 | Prod `is_verified=True` without verification (task §5) | `not EMAIL_PROVIDER` default | flag not earned | RC-5 | with provider configured → `False` + verification required before partner application; keep legacy honest gate where provider absent and surface state explicitly | tests | API payload | GAP→fix |

**Pre-existing failure recorded (not caused by this work):** `backend/tests/test_auth_rbac_and_gating.py::test_platform_admin_has_global_oversight` fails on `origin/main` (`tryon_adoption_rate == 0.0` on a freshly seeded DB) — analytics/seed-data dependency, outside auth scope; reported, not silently "fixed".

---

## 4. Target design (Phase 3 — approved before implementation)

```
Registration (intent: shopper | brand_partner)   ← intent is DATA, never authorization
        │
        ├─ role := consumer (server hard-code)
        ├─ email verification (when a provider is configured)
        └─ onboarding state machine (server-computed)

Consumer intent → style-profile onboarding → storefront
Brand intent    → partner application → admin review (BRD G6 §2.2) → BrandProfile + brand_owner
                                        └─ rejected → precise state + re-apply
Invitation      → brand owner/admin issues single-use token → invitee accepts → role bound to brand

Authorization is granted ONLY by:  admin approval | server-issued invitation acceptance
                                  (never by request body, URL, localStorage, cookie or JWT claim)
```

Deliverables of this change set: migration `0018_partner_onboarding_email_lifecycle`, `token_service`, email adapter + delivery ledger, `partner_service`, onboarding state API, new auth/brand/admin endpoints, frontend routes + gates + admin review UI, tests at unit/integration/negative level, docs, PR.
