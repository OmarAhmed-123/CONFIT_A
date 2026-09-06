# Cycle 3 — Research Record (CONFIT-A)

Format per remediation contract: source / type / finding / implication / decision.

## R1 — Auth token lifetimes (feature `fix/auth-session-lifecycle`, BLOCKER J)

- **Source (official, primary):** OWASP Cheat Sheet Series — Session Management
  Cheat Sheet (cheatsheetseries.owasp.org — session ID properties, expiry,
  rotation) and Authentication Cheat Sheet (token storage guidance:
  browser-safe httpOnly cookies over web storage).
- **Source (secondary, 2026 practice summary):** guptadeepak.com CIAM compass
  token-lifetimes article (2026-08) — industry defaults survey.
- **Type:** standards/best-practice.
- **Finding:** Recommended default: short-lived access token (5–15 min) +
  long-lived refresh token (~30 days) **with mandatory rotation and reuse
  detection** (revoking the family on replay). JWT revocation requires
  server-side state. Web-session cookies: idle timeout on the order of 30 min,
  absolute cap on the order of 30 days. Rotate session identifiers at
  privilege changes; re-authenticate for sensitive actions.
- **Implication:** CONFIT's backend already matches the recommendation exactly
  (15 min access in code, 30 d rotating refresh, reuse detection, DB-backed).
  The entire gap is transport (refresh token never persisted browser-side)
  and client behavior (no silent refresh, no 401 retry). Production's
  1440-minute override exists only to compensate for that gap.
- **Decision:** implement httpOnly `confit_refresh` cookie from the backend +
  single-flight retry-401 in `apiClient` (this feature). Keep 15 min / 30 d
  code defaults (researched, not arbitrary). Do NOT exempt `/auth/refresh`
  from CSRF in code — the guard is inapplicable when the access cookie is
  expired (the only case the browser hits), and rotation/reuse detection stay
  authoritative. Lowering the production env value is deferred to the owner
  (env change; PR only makes it safe).

## R2 — Carried forward from earlier cycles (verified still relevant)

- Vercel Functions 4.5 MB body limit / RFC 9110 §413 → client-side compression
  for uploads (BLOCKER C work, upcoming).
- tus (MIT) reference for resumable uploads when a bucket exists.
- WCAG 2.2 (1.4.4, 1.4.3, 2.1.1–2) + axe-core (MPL-2.0) for a11y work.
- OWASP API Top-10 2023 + ASVS 4.0 for the remaining security review.
- Medusa/Adobe guest-token + merge + Idempotency-Key patterns for journeys.
