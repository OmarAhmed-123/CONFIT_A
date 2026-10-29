# Vercel Recovery — owner checklist

**Observed (2026-10-29, re-confirmed)**: the production deployment answers **HTTP 402 Payment Required** at the edge. The `release-gate` workflow fails closed on this and must keep doing so. Nothing in this repository can clear a 402 — it is an account/billing state. **Nothing here is fixed; this is the recovery procedure.**

## Diagnosis already done (verified)

| Check | Result |
|---|---|
| `curl -sI https://<prod-domain>/` | `402` (Vercel edge, no application headers) |
| Build/config in repo (`vercel.json`) | security headers present (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, CSP); SPA rewrites; unchanged this pass |
| CI `production-parity` job | green (build parity between CI and the Vercel build command) |

## Owner steps (in order; stop at the first one that fails and record it)

1. **Billing** — Vercel dashboard → Team → *Settings → Billing*. Resolve the outstanding invoice / suspended plan. A 402 persists until Vercel marks the account current. Record: date, plan, who actioned.
2. **Project state** — *Project → Settings → General*: confirm the project is not paused; *Deployments*: confirm the latest production deployment is `main @ <sha>` and not a stale preview.
3. **Environment variables** — *Settings → Environment Variables* (production scope only): `VITE_API_BASE_URL` (backend origin), any analytics keys. **Never** `DATABASE_URL`, `WATSONX_*`, or Neon credentials on the frontend project (client bundle is public).
4. **Redeploy** — trigger "Redeploy" on the latest `main` commit (no build cache) *or* push an empty commit through CI. Do **not** bypass the `release-gate`.
5. **Verify** — `curl -sI https://<prod-domain>/` → `200`, `content-type: text/html`, headers from `vercel.json` present; `release-gate` workflow green; open the site, sign in, run the stylist once (deterministic banner must *not* show if backend watsonx is configured).
6. **Record** in `docs/release/PRODUCTION_READINESS_REPORT.md §Deployment` with the run URL.

## Not allowed

* Removing or softening the 402 check in `.github/workflows/release-gate.yml`.
* Deploying from a developer machine (`vercel --prod`) to "get around" CI.
* Putting server secrets in Vercel frontend env to make a demo work.

## Status: **BLOCKED — owner action required** (no repository change can resolve it).
