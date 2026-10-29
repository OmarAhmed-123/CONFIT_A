# Deployment recovery — provider state, classification, and what unblocks what

Re-probed **2026-10-29 ≈ 11:15 UTC** (previous probes 2026-10-26/27/28 agree). Every
row distinguishes **code** (fixable in this repo) from **account** (needs the account
owner / billing). Nothing below was changed by this project: no purchases, no
deploys, no production migrations — by instruction.

| Provider | Role | Observed today | Classification | Owner action to recover | Code action available |
|---|---|---|---|---|---|
| **Vercel** (`confit-a.vercel.app`) | production API + SPA | `GET /health` → **HTTP 402**, `x-vercel-error: DEPLOYMENT_DISABLED` (unchanged since 2026-10-26) | **Account** (team billing / paused project) | Settle billing or resume the project in the Vercel dashboard; redeploy `main` | None. The repo's deployment contract (`vercel.json`, root `requirements.txt` with pg8000 — `POSTGRES_DRIVER_POLICY.md`) is unchanged and was last green when production was live |
| **Neon** (`neondb` prod, `confit_fixverify` staging; owner + app_rw roles) | PostgreSQL | all 4 DSNs: `Your account or project has exceeded the quota` (psycopg2 `SELECT 1`) | **Account** (plan quota) | Upgrade plan or wait for quota reset; then run `alembic upgrade head` against staging first (`0047`, `0048` pending — see `docs/qa/MIGRATION_0047_0048_CHECKLIST.md`) | Migrations are PostgreSQL-verified locally (PG 17, up/down clean 2026-10-29); the schema gate will refuse to boot an incompatible build rather than 500 |
| **Cloudflare Workers Builds** (`confit-a`) | external GitHub App check | **failure** on every commit incl. `3f2fe70`; no `wrangler.*` in the repo | **Account / integration** (a Cloudflare app connected to the repo with no matching project config in-tree) | Either add a wrangler project intentionally or disconnect the Workers Builds integration from the repo so it stops posting failing checks | None without a product decision; it is not part of the documented deployment contract |
| **GitHub Actions** | CI | on `3f2fe70`: backend ✓ frontend ✓ migration chain + schema gate ✓ stylist a11y browser gate ✓ production parity ✓ gitleaks ✓ ; **release gate ✗** | release gate failure is **by design**: it reads production's `/api/v1/health` to compare Alembic revisions and **fails closed** when production is unreachable (402) | Recovers automatically once Vercel serves `/api/v1/health` **and** Neon is at head | None — removing the fail-closed behaviour would reintroduce the 2026-09-20 outage class |
| **GitHub uptime monitor** | scheduled | failing since the 402 | consequence of Vercel | same as Vercel | none |
| **IBM watsonx.ai** (eu-de) | Granite reasoning | IAM + `granite-4-h-small` live and verified 2026-10-28 (22 inference calls) | healthy | — | — |
| **Granite Vision** | optional vision | 404 `model_not_supported` all regions; Deploy-on-Demand only | **Account/commercial** | create a DoD deployment (billable) → set `WATSONX_VISION_DEPLOYMENT_ID` | path already implemented and unit-tested |
| **Redis** (shared rate-limit store) | prod rate limits | no `REDIS_URL` configured anywhere we can see | **Account/platform** | provision and set `REDIS_URL` | limiter already supports it; today limits are per-worker (`memory://`) |

## Recovery order (when the account owner acts)

1. Vercel billing → production serves `/health` again (expect `ready=false` until 2–3 complete).
2. Neon quota → verify staging `alembic current`, apply `0047`/`0048` to **staging**, run
   the checklist smoke, then production. The release gate on `main` turns green by itself.
3. Re-run `scripts/load/stylist_load.py --mode live --vus 2 --requests 4` against staging
   and record it in `performance-test-report.md` (the only latency measurement still missing).
4. Decide on Cloudflare Workers Builds (configure or disconnect) so PR checks are meaningful.
5. Provision Redis for cross-worker rate limiting (S4 in the verification report).

## What this means for the release decision

Production and staging are **unverifiable, not broken by this branch**. Everything that
can be verified without the hosted accounts — migrations, API, UI, provenance, load,
a11y automation — has been, locally on PostgreSQL (`local-development.md`). The
decision in `release-readiness.md` therefore turns on the account items above and the
pending human reviews, not on open code defects.
