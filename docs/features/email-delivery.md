# Feature: `fix/email-delivery` — BLOCKER C engineering half (real email transport)

**Cycle 4 · 2026-09-07 · one feature = one branch = one PR**

## Problem (verified on cycle-4 baseline)

Two honest-but-incomplete states:
1. With `EMAIL_PROVIDER` unset, reset/verification endpoints correctly return 501 — but there was NO way to ever deliver mail: `_send_password_reset_email` was an intentional stub, and `/verify-email` raised 501 "dispatch not wired" even with a provider set (no issuance path existed at all).
2. **Latent fake-success:** setting `EMAIL_PROVIDER` without any transport would have returned `"status": "queued"` while nothing was sent — exactly the dishonesty class this codebase forbids.

## Research → decision

`docs/research/CONFIT_A_CYCLE_4_RESEARCH.md` R1: all leading providers (Resend/SES/Postmark/Mailgun) expose standard SMTP ⇒ stdlib `smtplib` transport, provider = pure configuration. Operator recommendation: Resend (instant approval, free tier, SPF/DKIM/DMARC); SES at scale; Postmark deliverability-first.

## Changes

- **`backend/app/services/email_service.py` (new):** provider-agnostic SMTP transport — STARTTLS (587) / SSL (465), auth, RFC 5322 `EmailMessage` (UTF-8, bilingual), one retry on transient failure, honest `EmailDeliveryError` on hard rejection; never logs credentials/tokens. Bilingual EN/AR templates for reset (30-min, single-use link) and verification (24-h link).
- **`config.py`:** `FRONTEND_BASE_URL` (action-link base; must be https in production) + **production honesty gate**: `EMAIL_PROVIDER=smtp` without `SMTP_HOST`/`EMAIL_FROM_ADDRESS`/https base URL refuses to boot.
- **`auth_service.py`:** password-reset send is real; delivery failure → audited (`PASSWORD_RESET_EMAIL_FAILED`) + non-committal response (no account-existence leak; token stays valid). New `request_email_verification` (hashed one-time token, 24 h, generic response) and `complete_email_verification` (expiry/one-time/is_verified flip + audit). Register now sends a verification email best-effort — registration never fails on transport.
- **`user_repository.py`:** `is_verified` semantics — `True` when no provider (legacy, flag never lies about a check that cannot exist), `False` when email is configured (must be earned via the link).
- **`auth_controller.py`:** new `POST /auth/verify-email/request` (rate-limited 5/min) + real `POST /auth/verify-email` redemption (rate-limited 10/min); 501s preserved when unconfigured.

## Acceptance criteria (Given/When/Then) → tests (15, all green)

| AC | Given/When/Then | Test |
|---|---|---|
| AC1 | Given configured SMTP, when sending, then STARTTLS+auth+RFC5322 message with correct From/To/bodies | transport_starttls_auth_and_shape |
| AC2 | Given a transient network failure, when sending, then exactly one retry then success | transport_retries_once… |
| AC3 | Given hard relay rejection / missing config, when sending, then honest raise, zero silent drops | transport_hard_rejection…, transport_fails_honestly… |
| AC4 | Given a registered user, when forgot-password, then a REAL email leaves with a one-time https link that redeems via /reset-password and the new password logs in | test_forgot_password_sends_real_one_time_link |
| AC5 | Given an unknown email, when forgot-password, then identical 200 "queued", zero sends (no existence leak) | test_forgot_password_unknown_email_no_leak_no_send |
| AC6 | Given SMTP down, when forgot-password, then still non-committal 200 (never leak) | test_forgot_password_smtp_failure_does_not_leak |
| AC7 | Given no provider, when reset/verify endpoints hit, then honest 501 (unchanged) | 2 tests |
| AC8 | Given a registered unverified user, when verify-email/request, then emailed 24h one-time token; redeem → is_verified=true | test_verification_request_and_redeem |
| AC9 | Given a used/expired/garbage token, when redeemed, then honest 401 with reason | 3 tests |
| AC10 | Given email configured, when registering, then exactly one verification email (and none when unconfigured) | test_register_sends_verification_only_when_configured |
| AC11 | Given production env with EMAIL_PROVIDER=smtp and no SMTP_HOST, when booting, then refusal | test_production_boots_refuse_provider_without_smtp_host |

Suites: backend **1050 passed / 7 skipped** (was 1034). Frontend unchanged (existing forgot/reset bindings already call these endpoints; no verify-email UI yet — binding added when a UI exists, not as dead code).

## What this does NOT claim

Delivery is **NOT_VERIFIED against a real relay** — that requires the owner's provider account + verified domain (env: `EMAIL_PROVIDER=smtp`, `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM_ADDRESS`, `FRONTEND_BASE_URL`). The transport is proven against a fake SMTP server with contract-level fidelity; the moment env lands, preview/production verification is a 5-minute check (request reset → receive email → redeem link).

## Rollback

Revert the merge commit. Unconfigured behavior (501s) is untouched; configured behavior returns to stub-era semantics only if env was already set (it is not, anywhere). No DB migration was added or changed (`email_verification_tokens` table already existed in the chain).
