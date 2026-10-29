# Known limitations — as of 2026-10-29

Honest list; each item says whether it is **code**, **account/platform**, or
**process**, and where it is tracked. Nothing here is hidden behind a feature flag or
a default that pretends otherwise.

## AI / product behaviour
1. **Granite Vision is not used** (account: Deploy-on-Demand only). Photo analysis
   runs on a labelled non-Granite watsonx model or manual entry — `vision-integration-decision.md`.
2. **Rule-completed positions** (D12): when the model leaves a core slot empty the rule
   matcher fills it. Disclosed per item ("Added by rules") and in `limitations`; the
   reason text for such pieces is generic, not stylistic. Code, by design.
3. **Deterministic mode is a rule matcher, not a stylist**: it picks by occasion/season
   tags, favourites and neutral colours; reasons are templated. Labelled
   "Rule-based match — not AI" EN/AR. Code, by design.
4. **(RESOLVED 2026-10-29)** Unknown colour words used to fall back to the "Black"
   family. `normalize_color` now returns `"Unknown"`, which is never neutral, preferred,
   banned or matched in gap analysis; the UI shows "Unknown colour / لون غير محدد".
   Items persisted as `Black` before this date from unrecognised words are **not**
   migrated (no way to recover the original word) — users can edit them.
   Tests: `backend/tests/test_color_unknown_family.py`.
5. **Eval heuristic H10** over-fires on negated statements ("lacks moisture-wicking");
   flags are reviewed manually (quality report §8). Process.
6. **Human validation pending**: fashion-expert rubric and native-Arabic review have
   not been performed; model-rubric scores are machine signals only. Process.
7. **Model latency** is what it is: live Granite p50 ≈ 2.9 s, up to ≈ 6 s; a retried
   request doubles it (`performance-test-report.md`). Platform.

## Platform / deployment
8. **Production and staging unverifiable**: Vercel 402, Neon quota — `deployment-recovery.md`. Account.
9. **Rate limits are per worker** (`memory://`) until `REDIS_URL` exists: 40/h/user
   is effectively 40 × workers. Account/platform.
10. **Cloudflare Workers Builds** posts a failing check on every commit with no
    in-repo configuration. Account/integration.
11. **p99 latency target (8 s) is unattainable as written** with retries; p95 passes.
    Process (target definition), documented, not relaxed.

## Local development / testing
12. `docker-compose.dev.yml` is reviewed but **not executed** (no Docker in the
    verification sandbox); the native path is verified. Process.
13. Two uvicorn workers on an **empty** PostgreSQL log a harmless `UniqueViolation`
    notice while racing `create_all`; seed with one worker first. Code (cosmetic).
14. Full backend pytest in one process needs > 2 GB RAM; run in `-k` chunks on small
    machines (CI runs it whole). Process.
15. Manual assistive-technology sessions (NVDA/JAWS/VoiceOver/TalkBack) and an Arabic
    screen-reader transcript have not been performed — `accessibility-audit.md`. Process.
16. Browser E2E (`docs/qa/evidence/local_e2e_20261029/`) is a scripted
    playwright-core run, not yet a CI job; the CI a11y browser gate covers the
    component states. Process.
