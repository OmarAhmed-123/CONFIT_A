# Production-readiness slice 3 — sleeve gate, Cloudflare check, screen reader

Date: 2026-10-18 · Branch: `fix/brand-memberships-sleeve-recalibration`
Base: main @ `6636356` (PR #357 merged). Scope: master task phases 2–5.

## A. Sleeve gate — shipped state

* Gate: `backend/app/services/vton_sleeve_gate.py` (v3.0-recovered.1). The
  probe + decision semantics are recovered from the historical 2026-09
  line; the historical numbers are reference only (the module docstring
  says why; thresholds are UNFROZEN defaults used for observe-mode
  measurement, never a pass guarantee).
* Authoritative metadata: `products.sleeve_length` (migration
  `0040_product_sleeve_length`, additive/nullable, chain-verified
  upgrade+downgrade on sqlite; postgres CI job verifies the same chain;
  never edited an existing migration — the historical 0018 number is
  untouched in this chain's meaning).
* Wiring: one choke point — `_call_gpu_worker` applies the gate after
  `assert_layer_applied` for EVERY transport (worker one-shot, sequential
  chain per-stage with the correct layer input, pilot fallback). The PR #336
  protections remain the upstream gate; nothing bypasses them, this only
  adds a check AFTER they pass. Gate-only metadata is stripped from the
  worker wire payload (test-proven).
* Modes: `VTON_SLEEVE_GATE_MODE=off|observe|enforce`, **default off**
  (test-proven). Observe never blocks (test-proven). Enforce fails the
  render with canonical `VTON_SLEEVES_NOT_VERIFIED` — controller maps it to
  502 in all four taxonomy sites; async job classifier records it as
  `error_code` with the honest message (test-proven at API level).
* Fail-safe everywhere: NULL/undeclared metadata refuses (never guessed);
  undecodable render/garment refuses; degenerate dominant color refuses;
  indeterminate coverage refuses; gate internals crashing refuses under
  enforce; an invalid mode string FAILS STARTUP; enforce WITHOUT a valid
  manifest refuses at startup and at every render — no fallback to
  defaults, no fallback to pass.
* Manifest binding: `VTON_SLEEVE_CALIBRATION_MANIFEST` — schema
  `sleeve-calibration/1`; validated at startup + per render: gate version,
  engine id, engine build fields, threshold envelope, dataset
  re-hash (tamper → invalid), 3 distinct human raters + agreement report,
  evaluation metrics present, revocation flag.
* Honesty surfaces: job `metrics_json.sleeve_gate` (+ per-layer
  `outfit_layers[].sleeve`), sync `multi-render` response `sleeve_gate`
  (only when the gate ran), `/catalog/capabilities` `vton_sleeve_gate`
  state object. Frontend maps verdicts via
  `frontend/src/components/tryon/sleeveGateDisplay.ts` (unit-tested):
  verified | NOT verified (advisory when uncalibrated) | probe-unavailable —
  absence is never rendered as a claim, and a REFUSE never displays as
  success. Under enforce, a refused render has no image to display at all.
* Calibration tooling: `scripts/vton_sleeve_calibration.py` — synthetic
  fixtures explicitly cannot enter an approved dataset; freeze is
  hash-locked/immutable; deterministic 60/40 split; threshold selection is
  the encoded most-conservative-zero-calibration-FA rule; publish refuses
  without 3 human raters; live-render mode REFUSES in environments without
  the configured worker rather than substituting mocks. Manifest published
  by the harness is accepted by the runtime validator (round-trip test).
* Tests added (all green locally): 35 gate/manifest unit cases, 14 service
  + API integration cases (fake worker — labelled), 5 harness cases.
  **None of these is engine calibration evidence**; they prove wiring and
  fail-safe semantics only.

## B. Sleeve gate — what still BLOCKS enforcement (operator path)

1. GPU worker reachable with the current `fashn_vton_segfee` build
   (staging). This workspace has **no GPU/engine credentials** (env audit
   2026-10-18: only GitHub/Neon/AWS-S3 variables present).
2. ≥50 real captured artifacts reviewed by **three human raters**
   (procedure + dataset spec: `docs/vton/SLEEVE_CALIBRATION_PROTOCOL_2026-10-18.md`).
   Synthetic/AI sign-offs are refused by construction.
3. Run freeze → benchmark → publish-manifest, set
   `VTON_SLEEVE_CALIBRATION_MANIFEST`, flip mode to enforce on staging.
   Until then: keep enforce OFF (default), run observe on staging to
   collect verdict-vs-render pairs.
4. Production promotion of mode/config changes is an operator action; this
   PR changes no runtime behavior by default.

## C. Cloudflare `Workers Builds: confit-a` — measured timeline

| commit | where | result |
|---|---|---|
| `24d1c08` (main) | push | success |
| `264d4598` (main) | push | success |
| `7b64ac4` (PR #357 head) | PR checks | **failure** — build `056fa770-f1e8-41e6-a519-7d210306c7ee`, details link → dashboard (account `e3269d9680d92a18d3e9492b2ac38989`), GitHub-side annotations empty (`[]`, API-verified) |
| `6636356` (main, includes that exact tree) | push after merge | **success** (re-verified 2026-10-18 via checks API: all listed contexts success) |

Interpretation (evidence-bounded): the failing run was the PR-preview build
of a tree that the SAME Worker builds successfully on main. This is not an
app defect on merged code, not a branch-protection requirement (required
checks = backend/frontend/release gate — re-verified), and it self-resolved
on the merge commit. The precise PR-preview failure reason (transient
runner, dependency fetch, or preview-env setting) is visible ONLY in the
Cloudflare dashboard build log, which needs owner access — requested
instead of guessed. NO repository change was made to "green" a check
(no wrangler.jsonc invented; repo deployment docs remain Vercel + FastAPI;
unlinking/reconfiguring the preview integration is an owner decision — if
preview builds are unwanted, the owner can disable the PR-preview toggle in
the Cloudflare dashboard). The red status was never silenced, rewritten,
or deleted; it is documented here and in the PR #357 comment (id
6253000199).

## D. Manual screen-reader review — NOT RUN (exact limitation)

* No human screen-reader session is possible in this sandbox (headless CI
  container; NVDA/VoiceOver are desktop ATs). `docs/audits/
  SCREEN_READER_TEST_PROTOCOL_2026-10-18.md` ships the full 15-row manual
  protocol for the operator; rows 14–15 cover this PR's new UI states.
* Attempted automated supplement: installed `python3-pyatspi` +
  `at-spi2-core` + `xvfb` + `orca`/`espeak-ng`/`speech-dispatcher`
  (apt, root available); automated AT-SPI probe ATTEMPTED, PARTIALLY PROVEN,
  then stopped (timeboxed): Xvfb + private D-Bus session with
  `org.a11y.Status.IsEnabled/ScreenReaderEnabled=true`, real Chromium
  (`--force-renderer-accessibility`) against the LIVE app (uvicorn + vite
  dev). The browser REGISTERED on the AT-SPI bus (application node readable)
  but this headless build never exposed the page `document web area` node —
  its first-run Terms-of-Service dialog renders as unexposed views-widgets
  (xdotool and AT-SPI action queries found no pressable button), so
  page-level SR semantics could not be captured in-container. That outcome
  is itself evidence for why the manual desktop session is required; rows
  1–15 of `SCREEN_READER_TEST_PROTOCOL_2026-10-18.md` remain the operator's
  to execute. No SR pass is claimed either way.

## E. Regression suite performed (see PR body for exact commands/results)

Backend full pytest (count + time), sleeve suites, migration upgrade/
downgrade rehearsal, frontend `npm run verify` (i18n gate + tsc + vitest +
build), Playwright PR#357 brand-journeys re-run unchanged (shared surfaces
were only additively extended).
