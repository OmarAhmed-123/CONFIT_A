# Non-functional requirements — stylist feature

| NFR | Target | Measured / status (date) | Evidence |
|---|---|---|---|
| **Latency** — recommendation p95 / p99, 20 concurrent users, model double 5 s ± 1.5 s with 2 % 503 + 1 % 429 injected, PostgreSQL, 2 workers | p95 ≤ 6.5 s, p99 ≤ 8.0 s (provisional) | see `performance-test-report.md` (2026-10-29 run) and history: p95 **6.48 s PASS** / p99 11.5 s **FAIL** (2026-10-27) | `docs/qa/load/*.json`, `docs/qa/LOAD_TEST_STYLIST.md` |
| **Latency** — live Granite, 2 VUs | p95 < 15 s | p50 2.91 s, max 6.21 s (16-scenario eval 2026-10-28); probe p95 6.10 s | eval JSON |
| **Availability of honest answer** | 0 × 5xx from our code under load | 660 req / 0 × 5xx (every PG run) | load reports |
| **Correctness under faults** | injected 503/429 retried; no mislabelled provenance; no id leakage | PASS in all runs | load harness `verdict` |
| **Security** — secrets | never in repo, logs, client bundle | gitleaks gate green; key redacted to last-4; `frontend/dist` grep 0 hits; Neon creds server-only | CI; acceptance FR-17 |
| **Security** — auth | httpOnly cookie session + CSRF; stylist endpoints 403 unauthenticated | verified 2026-10-29 (403) | API probe |
| **Rate limiting** | 40/h/user recommendations; 5/min/IP sign-up | enforced (the load harness has to pace sign-ups) | `test_rate_limit_header_present` |
| **Data** — migrations | reversible, idempotent, PostgreSQL-verified | 0001→0048 clean on PG 17.11; 0048→0046→0048 round-trip | 2026-10-29 |
| **Data** — provenance integrity | saved looks cannot claim a foreign model id | PASS | `test_watsonx_look_cannot_claim_a_foreign_model_id` |
| **Resource footprint** | run on 2 vCPU / 2 GB | 2 API workers ≈ 350 MB RSS; I/O-bound | load report |
| **Accessibility** | WCAG 2.1 AA automated clean; keyboard complete; EN + RTL AR | axe 0 violations ×8 states; manual AT partial (Orca EN only) | `accessibility-audit.md` |
| **Internationalisation** | full EN/AR parity incl. error and disclosure strings | i18n parity CI gate green; occasion labels localised (`_OCCASION_AR`) | CI parity job |
| **Observability** | structured logs with provenance, latency; `/health` liveness + schema gate + capability states | present; `ready=false` when core capability blocked/unprobed — never a silent ok | `/health` contract |
| **Honesty** | fixture never presented as Granite; model id shown is the **served** one | enforced in code + tests (FR-18, D13) | — |
| **Portability** | runs without Neon/Vercel/Cloudflare | verified 2026-10-29 | `local-development.md` |

Not measured (and not claimed): sustained soak (> 10 min), > 20 concurrent users,
production-runtime (Vercel function) latency — blocked by provider account state
(`deployment-recovery.md`).
