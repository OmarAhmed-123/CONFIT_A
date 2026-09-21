# Closure Report — Identity, Profile, MFA & Data Rights

**Project:** CONFIT_A
**Audit closed:** feature audit dated 2026-09-21 ("الهوية والملف الشخصي وMFA وحقوق البيانات" — status was *متحققة جزئيًا — consumer فقط*)
**Branch:** `feat/identity-mfa-data-rights-hardening` (single branch, multiple PRs to `main`, per the workflow contract)
**PRs:** #124 (MFA hardening — merged), #129 (GDPR export completeness), #1xx (this report + production probe)

> اطمن — هذا التقرير لا يعاقب أحدًا. هدفه الوحيد أن نصلح ونتعلّم. كل بند أدناه
> مرتبط بكود قابل للتشغيل أو اختبار قابل للتكرار؛ وعندما لا يوجد دليل نكتب
> «غير متحقق» بدل الادعاء.

---

## 1. What the audit found vs. what is now true

| # | Audit gap (quoted) | Status now | Evidence |
|---|---|---|---|
| 1 | «لم أتحقق من نجاح MFA end-to-end، ولا من وصول رمز authenticator أو منع الدخول قبل الرمز» | **Closed** | `backend/tests/test_mfa_hardening.py::test_mfa_full_lifecycle_end_to_end` (enroll → MFA_REQUIRED challenge → wrong code 401 → right code 200 → disable → plain login again) + production probe steps 2–5 |
| 2 | «اعرض نتيجة التصدير مع checksum أو حجم الملف بدل الاكتفاء ببدء التنزيل» | **Closed** | `export_integrity{checksum_sha256, canonical_bytes}` in the API response; the frontend **recomputes** the sha256 via WebCrypto before the download and blocks on mismatch; toast shows checksum prefix + size |
| 3 | «لم أتحقق من أن ملف التصدير يحتوي فعلًا على الصور/القياسات» | **Closed** | The export now contains the actual records (decrypted measurements, consents, wardrobe incl. image URLs, outfits, mood boards, orders + line items, try-on & stylist sessions). `test_gdpr_export_completeness.py` asserts the content, not the counts |
| 4 | «أضف اختبارات ملكية تمنع أن يرى المستخدم ملف تصدير أو قياسات مستخدم آخر» | **Closed** | `test_export_cross_user_isolation` — data planted for two users; user A's archive provably free of user B's records/email/profile |
| 5 | «أضف اختبارات إنتاج آمنة لـMFA تشمل التفعيل، رمز خاطئ، رمز صحيح، وإلغاء التفعيل» | **Closed** | `backend/scripts/production_mfa_data_rights_probe.py` — 14 assertions incl. replay rejection, run against a live server; JSON evidence report; exit-code contract |
| 6 | «وفّر حسابات اختبارية مؤقتة وموسومة مع تنظيف موثق» | **Closed** | The probe registers `probe+mfa-<ts>-<rand>@confit-probe.example.com`, deletes it via `DELETE /auth/account` in the same run, and **verifies** deletion (login → 401). Cleanup failure fails the probe |
| 7 | Roles above consumer not verifiable from the provided accounts | **Not closed — honestly out of scope.** Requires staging brand/admin accounts provisioned by the owner. Nothing here pretends otherwise |

## 2. Defects found during remediation (beyond the audit's list)

These were discovered while reading the implementation and are fixed in PR #124 — with regression tests that would catch reintroduction:

1. **TOTP secret stored in plaintext** (`users.mfa_secret`). Now: Fernet
   `enc:v1:` envelope; legacy rows keep verifying via transparent fallback
   (zero-downtime). Test asserts against the raw DB row.
2. **No TOTP replay protection** — the same code was accepted repeatedly in
   its 30s window. Now: last accepted time-step persisted per user; any
   code from step ≤ last accepted is rejected. Tests replay on both the
   login and enrollment surfaces.
3. **`/mfa/disable` accepted password alone** — a stolen password could
   remove the second factor. Now: password + current TOTP/recovery code
   (401 `MFA_CODE_REQUIRED`), with a state-unchanged assertion on refusal.
4. **`/mfa/setup` restarted enrollment while enabled** — a hijacked session
   could rotate the secret and wipe backup codes. Now: 422 with secret and
   codes provably untouched.
5. **No rate limits** on `/mfa/setup`, `/mfa/disable`,
   `/mfa/regenerate-codes`. Now limited (5/min).

## 3. Deliberate engineering decisions (and why)

- **No DB migration.** The replay marker rides on the existing
  `audit_logs` table. Reason: the production schema-drift gate (correctly)
  refuses a database that is AHEAD of deployed code — applying a migration
  before merge would 503 production; merging a migration that production
  does not have is exactly the 2026-09-20 outage class the release gate
  exists to prevent. The audit-log approach ships atomically with the code.
- **Checksum is cross-runtime reproducible by construction.** Canonical
  JSON = sorted keys + compact separators + raw UTF-8; money exported as
  strings; integral floats normalized. Verified byte-for-byte between
  Python (producer) and Node.js (the browser's algorithm): `MATCH: true`.
- **Backwards compatibility:** counts and the legacy fields remain in the
  export response; existing clients keep working (additive contract).
- **DRY:** one `_verify_totp_with_replay_guard` is the single TOTP
  verification path for login, change-password, disable and enrollment —
  no drift between surfaces.

## 4. Test & gate evidence

| Suite | Result |
|---|---|
| `test_mfa_hardening.py` (new) | 9/9 pass |
| `test_gdpr_export_completeness.py` (new) | 6/6 pass |
| `test_auth_change_password.py` (updated for replay guard) | 10/10 pass |
| `test_group1_identity_profile.py` | 22/22 pass |
| Cookie/CSRF/RBAC auth suites | pass (1 pre-existing failure on `main` — `tryon_adoption_rate`, unrelated, reproduced on a clean `main` checkout) |
| Frontend `tsc && vite build` | clean |
| Frontend vitest | 106/106 pass |
| Local live-server probe (14 steps incl. cleanup) | passed=true |
| CI required checks (backend / frontend / release gate) | green on every push of this branch |

## 5. How to re-run the production probe

```bash
pip install httpx pyotp
python backend/scripts/production_mfa_data_rights_probe.py \
    --base-url https://confit-a.vercel.app --report mfa_probe_report.json
```

The report JSON contains one entry per assertion (timestamps + status
codes + checksums; never passwords, secrets or codes). The probe account
is tagged, synthetic, and deleted-and-verified within the same run.

## 6. Evidence limits (honesty section)

- The replay guard stores the accepted step via the audit-log table; on a
  hypothetical deployment where audit logging were disabled entirely, the
  guard would degrade to standard pyotp window checking. Audit logging is
  a hard invariant of this codebase (`log_audit` is called on every
  security event), so this is a theoretical note, not a live risk.
- HTTP 200 on export proves content + checksum returned; it does not prove
  every historical record class (e.g. guest orders never linked to the
  account) — those are outside the user's owned set by design.
- Brand/admin role surfaces remain unverifiable without owner-provisioned
  staging accounts (gap #7 above). Recommendation stands: tagged staging
  accounts + a mirror of this probe for elevated roles.
