# Cloudflare Workers Builds — status and owner decision

**Observed**: a GitHub check named *Cloudflare Workers Builds* (`confit-a`) posts **failure** on every commit (seen on `3f2fe70`, `ceb8616`, `ffd6118`, `90c8371`). The repository contains **no** `wrangler.toml` / `wrangler.jsonc` and no Worker entry point. Cloudflare is **not** part of the documented deployment contract (Vercel frontend + separately hosted backend + Neon). This is an integration mismatch, not a code failure; nothing in-tree can make the check pass honestly.

## Verified

| Check | Result |
|---|---|
| `ls wrangler.toml wrangler.jsonc` | none |
| Check-run origin | GitHub App (account-level integration), not a workflow in `.github/workflows/` |
| Effect on required checks | the check is not in branch protection; it only adds noise (and hides real failures in the PR summary) |

## Owner decision (pick one — do not leave as-is)

**A. Disconnect (recommended, 5 min)** — Cloudflare dashboard → *Workers & Pages → confit-a → Settings → Builds → Disconnect repository*, then GitHub → *Settings → Integrations → Cloudflare Workers and Pages* → revoke access to `CONFIT_A`. Verify: next push shows no Cloudflare check.

**B. Adopt intentionally** — only if there is a product decision to serve the SPA from Cloudflare. Requires: `wrangler.jsonc` with `assets.directory = "frontend/dist"`, build command `cd frontend && npm ci && npm run build`, `/api` routed to the backend origin, headers equivalent to `vercel.json`, and the `release-gate` extended to the new origin. Not started; estimate 1–2 days incl. parity checks.

## Not allowed

* Marking the check as passing via a stub Worker that serves nothing.
* Treating the red check as "known flaky" in release notes without one of the decisions above.

## Status: **BLOCKED — owner decision required (A or B)**.
