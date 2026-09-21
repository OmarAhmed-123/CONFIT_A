# BRD — Identity, Profile, MFA & Data Rights (matches the implementation)

**Scope:** consumer identity, auth/session, profile, measurements, onboarding,
password management, MFA, data export, account deletion, authorization.
**Status:** every requirement below is implemented and covered by the test
listed next to it. This document describes what the code DOES — it is kept
consistent with the implementation, not aspirational.

> ملاحظة: هذه الوثيقة لتحسين المنتج والتعلم — ليست أداة عقاب. أي فجوة تُكتشف
> لاحقًا تُسجَّل هنا وتُصلَّح، لا تُخفى.

---

## 1. Authentication

| Req | Behavior | Enforced in | Test |
|---|---|---|---|
| AUTH-1 | Public registration always creates role=CONSUMER; client `role` keys silently ignored | `AuthService.register`, `UserRegister(extra="ignore")` | `test_register_role_injection_ignored`, `test_register_role_escalation.py` |
| AUTH-2 | Login requires email+password; MFA-enrolled accounts get an explicit `MFA_REQUIRED` 401 challenge before any session exists | `AuthService.login` | `test_mfa_full_lifecycle_end_to_end` |
| AUTH-3 | Invalid credentials → 401, identical path for unknown email vs wrong password (no account-existence oracle) | `AuthService.login` | `test_group1_identity_profile` |
| AUTH-4 | Sessions: 15-min access JWT + 30-day rotating refresh token, server-side rows, family revocation on reuse | `AuthService.refresh` | `test_session_refresh_lifecycle` |
| AUTH-5 | Logout revokes the presented refresh token and clears cookies | `AuthService.logout` | `test_logout_revokes_refresh_token` |
| AUTH-6 | `/auth/me` returns only the JWT subject's row; deleted/deactivated users → 401 | `get_current_user` (DB-backed) | authz matrix D |
| AUTH-7 | Rate limits: register 5/min, login 10/min, MFA endpoints 5–10/min, export 5/min, delete 5/min | slowapi decorators | `test_rate_limiting` |
| AUTH-8 | Passwords: bcrypt only; policy = 8–72 chars AND ≥3 of {lower, upper, digit, symbol} | `validate_password_policy` | `test_password_policy_enforced_server_side` |

## 2. Profile & Onboarding

| Req | Behavior | Test |
|---|---|---|
| PROF-1 | `GET /profile/me` never fabricates a profile; fresh users get explicit `not_completed` | `test_get_profile_me_returns_not_completed_for_fresh_user_no_write` |
| PROF-2 | Onboarding quiz persists atomically; resubmission updates (idempotent), never duplicates | runtime probe (§ evidence) + `test_onboarding_partial_then_completion_persists` |
| PROF-3 | Body attributes optional — skipping step 3 stores NULL, never fabricated numbers | `test_body_step_optional_no_fabricated_defaults` |
| PROF-4 | Body measurements encrypted at rest (Fernet); decryption failure raises, never leaks ciphertext | `test_decrypt_wrong_key_raises_encryption_error_not_returns_ciphertext` |
| PROF-5 | Enum-like fields validated server-side against allow-lists (422 on unknown values); numeric ranges enforced (height 100–250 etc.) | `test_server_side_style_validation_rejects_unknown_values` |
| PROF-6 | `PATCH /me/profile` is a typed DTO: full_name 1–255 (blank refused), phone normalized E.164-ish, language ∈ {en, ar}; privileged keys (role, is_active, email, id) provably ignored | `test_me_profile_patch_validation_enforced`, `test_me_profile_patch_privileged_keys_ignored` |
| PROF-7 | Ownership: user identity comes exclusively from the JWT subject; no profile route accepts a target user id | authz matrix B |

## 3. Password management

| Req | Behavior | Test |
|---|---|---|
| PW-1 | Change requires the CURRENT password; MFA accounts also a current TOTP/recovery code | `test_auth_change_password` (10 tests) |
| PW-2 | New password must differ and satisfy policy; failures mutate nothing | same |
| PW-3 | Success revokes EVERY refresh session and audits `USER_PASSWORD_CHANGED`; old credential dead, new works | same + runtime probe |

## 4. MFA (TOTP, standards-based — pyotp; no custom crypto)

| Req | Behavior | Test |
|---|---|---|
| MFA-1 | Secret encrypted at rest (`enc:v1:` Fernet envelope); legacy plaintext rows readable, rewritten on next enroll/disable | `test_totp_secret_stored_encrypted_at_rest`, `test_legacy_plaintext_secret_still_verifies` |
| MFA-2 | Enrollment: setup → QR/provisioning URI → verify with a REAL device code → enabled + 10 single-use bcrypt-hashed recovery codes shown exactly once | `test_mfa_setup_verify_backup_codes_are_random_and_hashed` |
| MFA-3 | Setup refused (422) while MFA already enabled — hijacked-session secret rotation impossible | `test_setup_refused_while_mfa_enabled_secret_not_rotated` |
| MFA-4 | Accepted TOTP time-step never accepted twice (replay guard, persisted marker); markers purged on account deletion | `test_totp_code_cannot_be_replayed_within_window`, authz matrix D |
| MFA-5 | Disable requires password AND a current TOTP/recovery code | `test_disable_mfa_password_alone_is_rejected` |
| MFA-6 | Login challenge: no code → `MFA_REQUIRED`; wrong code → 401 (audited `MFA_FAILED`); correct → session | `test_mfa_login_challenge_flow_and_backup_code_single_use` |
| MFA-7 | Recovery codes single-use, consumed atomically | same |

## 5. Data export (GDPR Art. 15/20)

| Req | Behavior | Test |
|---|---|---|
| EXP-1 | Export = the ACTUAL owned data: profile (incl. decrypted measurements), consents (+policy version), mood boards, wardrobe, outfits, orders + line items, try-on & stylist sessions | `test_export_contains_actual_profile_and_wardrobe_data` |
| EXP-2 | NEVER exported: password hash, MFA secret, recovery codes, refresh tokens, session ids, other users' anything | `test_export_cross_user_isolation` + serialization is explicit field-by-field (no `__dict__` dumps) |
| EXP-3 | Integrity: sha256 + byte size over canonical JSON (sorted keys, compact, raw UTF-8); frontend recomputes via WebCrypto BEFORE download; mismatch blocks the file | `test_export_checksum_matches_payload`, cross-runtime Node.js proof |
| EXP-4 | Export audited with checksum; rate-limited 5/min | `test_export_audited_with_checksum` |

## 6. Account deletion

**What "delete" means (product language = implementation):**
- **Deleted:** user row, style profile (incl. encrypted measurements), wardrobe,
  saved outfits, mood boards, refresh tokens, MFA secret + recovery codes,
  password/email verification tokens, MFA replay markers.
- **Anonymized (retained for tax/audit):** orders, try-on sessions, stylist
  sessions — `user_id → NULL`, no PII link remains.
- **Retained:** audit events (they carry the user_id of a now-nonexistent row
  by design — the audit trail must survive the account).

| Req | Behavior | Test |
|---|---|---|
| DEL-1 | Step-up: explicit `confirm="DELETE"` + current password; MFA accounts also a current code; social-only accounts exempt from password (none exists) but not from MFA | `test_delete_refused_without_password`, `test_delete_mfa_user_requires_code` |
| DEL-2 | Failed re-auth mutates nothing and audits `ACCOUNT_DELETE_REAUTH_FAILED` | `test_delete_refused_with_wrong_password_and_wrong_confirm` |
| DEL-3 | Success: related rows per policy above; access token, refresh token and login all dead; second delete = 401 (idempotent refusal, no ghost path) | `test_delete_cleans_related_rows_and_kills_sessions` |
| DEL-4 | No target id exists in the contract — cross-user deletion impossible by construction | `test_cross_user_deletion_impossible_by_construction` |
| DEL-5 | Rate-limited 5/min | decorator |

## 7. Authorization

| Req | Behavior | Test |
|---|---|---|
| AZ-1 | All `/me/*`, `/profile/*`, export, delete: identity = JWT subject only | authz matrix A/B |
| AZ-2 | Id-taking resources (mood boards, sessions): foreign ids → 403/404, never data | `test_cross_user_mood_board_id_manipulation`, `test_tryon_session_idor`, `test_measurement_session_security` |
| AZ-3 | Role checks read the DB row, never the token claim — a forged `role=admin` claim does not escalate | `test_forged_role_claim_does_not_escalate` |
| AZ-4 | Consumer tokens refused by admin/brand endpoints regardless of frontend | `test_consumer_token_refused_by_admin_and_brand_endpoints` |

## Documented assumptions (decisions made where the product was silent)

1. **Social-only accounts and deletion:** no local password exists, so the
   step-up for them is session + (when enrolled) MFA code. Alternative
   (emailing a confirmation link) requires the email provider that
   production does not yet have — revisit when EMAIL_PROVIDER ships.
2. **Order anonymization vs deletion** follows the pre-existing spec §15
   (tax/audit retention); this BRD documents it as the product language so
   the UI copy ("order history is anonymized") matches reality.
3. **MFA replay markers in audit_logs:** operational security state rides on
   the audit table to avoid a schema migration (the release gate makes
   out-of-order migrations a production outage). If a dedicated column is
   ever added (e.g. `users.totp_last_step`), migrate the marker then.
