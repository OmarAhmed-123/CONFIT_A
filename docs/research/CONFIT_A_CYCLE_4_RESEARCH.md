# Cycle 4 — Research Record (CONFIT-A)

Format: source / type / finding / implication / decision. Official/vendor-first per contract §23.

## R1 — Transactional email provider (BLOCKER C)

- **Sources (primary/vendor):** Resend official docs (resend.com — SMTP: `smtp.resend.com:587/2465`, username `resend` + API-key password, SPF/DKIM/DMARC domain verification, free tier 3,000/mo & 100/day, 10 req/s team rate limit, instant production access); AWS SES official pricing (US$0.10/1k, SMTP interface, manual production-access review); Postmark official pricing (US$15/mo 10k, transactional-only network).
- **Sources (secondary, 2026 comparisons):** wpmailsmtp.com Resend review 2026; buildmvpfast.com Resend-vs-SES-vs-Postmark 2026; sequenzy.com provider roundups 2026.
- **Type:** vendor documentation + multi-source 2026 comparisons (cross-checked).
- **Finding:**
  - All three expose standard SMTP ⇒ a stdlib `smtplib` transport makes the provider a pure config choice (no SDK lock-in).
  - Resend: instant approval, free tier sufficient for verification traffic, SES-backed infrastructure, domain auth included. 10 req/s per team (shared across keys).
  - SES: cheapest at scale but production sending requires manual review and self-managed bounce/suppression — slower to first verified email.
  - Postmark: best deliverability reputation, higher per-email cost.
  - Domain authentication (SPF/DKIM/DMARC) is mandatory for inbox placement regardless of provider.
- **Implication:** CONFIT needs exactly three mails (verification, reset, resend) — low volume, deliverability-sensitive (reset links are security-critical). The engineering gap was not the provider but the transport: the API would have answered a fake "queued" with `EMAIL_PROVIDER` set (stub sender).
- **Decision:** implement provider-agnostic stdlib SMTP transport (`backend/app/services/email_service.py`) — works with Resend/SES/Postmark/Mailgun unchanged. **Operator recommendation: Resend** (instant approval, free tier verifies end-to-end delivery, SMTP + SPF/DKIM/DMARC); SES acceptable at scale; Postmark if deliverability-first budget. Production boot now REFUSES `EMAIL_PROVIDER=smtp` without `SMTP_HOST`/`EMAIL_FROM_ADDRESS`/https `FRONTEND_BASE_URL` (honesty gate in `config._production_contract`).

## R2 — Object storage provider (BLOCKER D)

- **Sources (vendor/official-derived, 2026):** Cloudflare R2 docs-derived comparisons — S3-API compatible incl. presigned URLs, 11-nines durability design, US$0.015/GB-mo storage, **US$0 egress always**, permanent free tier 10 GB + 1M writes/10M reads per month; AWS S3 — US$0.023/GB-mo, US$0.09/GB egress beyond 100 GB free, deeper classes/compliance (Object Lock, Glacier, CloudTrail).
- **Type:** vendor documentation + 2026 cross-comparison.
- **Finding:** R2 and S3 are both drop-in for the EXISTING `S3StorageBackend` (endpoint_url switch). R2's zero egress dominates for read-heavy user-media workloads (wardrobe images/VTON inputs served on every page view). S3 leads only for compliance/archival needs CONFIT does not have.
- **Implication:** no code change required for either — the missing piece is account provisioning + bucket + credentials + `STORAGE_PROVIDER=s3|r2` env (owner action). Wardrobe upload stays honest-501 until then.
- **Decision:** recommend **Cloudflare R2** to the owner (zero egress, permanent free tier covers launch volume, S3-compatible with existing code path). AWS S3 documented as the alternative. Retention/TTL policy for VTON artifacts to be decided with the owner (§12 of the cycle contract) — default recommendation: wardrobe images kept until user deletion (GDPR export/delete already implemented); VTON renders TTL 24 h unless the owner opts into persistent history.

## R3 — Access-token lifetime (BLOCKER G, carried from cycle 3)

- OWASP Session Management CS + Authentication CS (primary): short access (5–15 min) + rotating refresh (~30 d) with reuse detection. Already implemented and verified in production (cycle 3, PR #84 `44fa877`).
- **Decision:** production flip `ACCESS_TOKEN_EXPIRE_MINUTES` 1440 → 15 is an owner env action, now provably safe; post-change verification runbook: login → wait/expire → observe silent refresh (one `/auth/refresh`, `/auth/me` 200) → session continues.
