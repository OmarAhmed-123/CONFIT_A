# CONFIT_A — DYNAMIC REAL-USER MULTI-GARMENT VTON: FINAL PHASE REPORT

Date: 2026-09-15
Master prompt: "Dynamic Real-User Multi-Garment VTON" (52 sections)
Sections A–Q per §51. Status tags per the standing evidence rules.

**RELEASE DECISION (§50): BLOCKED** — required evidence unavailable:
(1) human calibration (Gate A) pending; (2) N=2 lower-layer reliability gap
unresolved on the live worker instance (worker redeploy BLOCKED from this
environment); (3) commercially-cleared production identity model not yet
obtained (LICENSE-GATED). **BLOCKED is not converted to GO.**

---

## A. BASELINE (exact current state)

- **Git**: `main` @ 928e615 (untouched). Work branch
  `research/vton-phase05-calibration` @ 7b56027 (Phase 1 prep) + f754e4d
  (AT suite + report + inputs) + this commit (contracts, E2E, local/global
  validation reports, this report). Push: **BLOCKED** (no GitHub PAT in env).
- **Phase 0.5**: CLOSED — 36/36 checks, CONDITIONAL PASS (report:
  `/home/user/CONFIT_A_vton_phase05_final_report.md`, commit 503c8e1).
- **Worker (live, re-verified 2026-09-15 22:28)**: healthy/ready;
  `fashn-vton-v1.5 (MMDiT 972M, segmentation-free; fork 7c0f10af)`;
  `NVIDIA A10`; gpu_memory allocated 1.83 GB / reserved 3.5 GB;
  git_sha `928e615110640c00df0db80ef1a93f92ff353870-dirty`;
  commercial=true. VERIFIED (health payload).
- **Backend**: FastAPI production service (main @ 928e615) + this branch's
  test/report files. Real production code path used for every live test.
- **Suite state**: AT suite 36 tests → 34 passed / 2 honest failures (AT-04,
  AT-10 — N=2 gap); component contracts 30/30 (hermetic + live); canonical
  E2E (zero fixtures) PASS; local 2/2 + global 3/3 dynamic renders verified.

## B. ARCHITECTURE TEST RESULTS (every test)

Full per-test matrix with MEASURED values:
`docs/vton/ARCHITECTURE_TEST_REPORT.md` (AT-01…AT-19) and this section's
summary. Evidence: `evaluation/results/architecture_test_evidence.json`.

| test | result | key measured evidence |
|---|---|---|
| AT-01 user-image passthrough | PASS | input sha d5800f44… traced; output 20c151d2… ∉ 89 fixture hashes; cos self 0.6767 > other 0.4953 |
| AT-02 unique persons | PASS | a/a 0.6767 > a/b 0.4953; b/b 0.9154 > b/a 0.4217 |
| AT-03 unique garments | PASS | coverage a_teal 0.7623 vs a_mustard 0.0; b_mustard 0.5236 vs b_teal 0.0 |
| AT-04 unique outfits N=2 | **FAIL (honest)** | layer 1 verified; layer 2 (bottom) → 502 VTON_LAYER_NOT_APPLIED (see E-1) |
| AT-05 provenance chain | PASS | job vton_job_cc543e64bf0e; person hash match; garment ids; model; one-shot; gaps documented (§34) |
| AT-06 cache safety / determinism | PASS | identical inputs → identical sha256; one-field change → different |
| AT-07 no fixture substitution | PASS | output b68522df… ∉ 89 known fixture hashes |
| AT-08 unknown person | PASS | rt4: cos self 0.8724 > other 0.7079 |
| AT-09 unknown garment | PASS | olive coverage 0.3909; control 0.0 |
| AT-10 combined unknown (MOST IMPORTANT) | **FAIL (honest)** | same N=2 layer-2 failure mode; explicit 502, no fake image |
| AT-11 person variability (×4) | PASS | all 200 completed (worker normalizes person ref — documented) |
| AT-12 garment variability (×3) | PASS | all 200, distinct outputs |
| AT-13 catalog authority | PASS | schema has no client garment-metadata fields; slots catalog-derived; client slot_mapping lie rejected |
| AT-14 multi-tenant authz | PASS | 404/200/404/404; one-shot token; no existence leakage |
| AT-15 dynamic layering N=2 inner+outer | PASS | both client orders → identical output 6aed7c23…; server order [upper_inner, upper_outer] |
| AT-15b N=3 (EVALUATION-ONLY) | recorded | 502 explicit (consistent with N=2 gap); not a production claim |
| AT-16 failure taxonomy | PASS | corrupt/non-image → explicit codes; undersized → warning; unknown product → 404; no-worker → 503 |
| AT-16b long-sleeve honest gate | PASS | sleeves PRESENT (structural probe 0.7744/0.6403 vs 0.35 threshold; negative control 0.16); eval arm_coverage false-positive recorded, not gating |
| AT-17 dynamic identity ×4 persons | PASS | diagonal argmax all rows; margins 0.1645–0.2407 |
| AT-18 garment fidelity | PASS (MEASURED) | ΔE 24.9 / 38.6 — recorded, no hard gate (Gate A territory) |
| AT-19 generic sleeve detector | PASS | geometry-driven report on unknown garment rt4 |
| Code scan (§21) ×10 | PASS ×10 | ZERO fixture IDs in production decision paths; ZERO fixture-coupled sleeve exceptions |

**§34 component contracts — `backend/tests/test_architecture_contracts.py`
(30/30 hermetic+live):** C-01 PersonReferenceResolver (data-URL passthrough,
raw-b64 normalization, corrupt/undersized/aspect rejection, SSRF target
rejection); C-02 GarmentResolver (server-derived slots in canonical order,
engine-unsupported slot upfront 422-class rejection); C-03 OutfitResolver
(404 before worker on unknown product; client slot lie rejected); C-04
LayeringEngine (order independence, honest unsupported refusal, dress
conflict clearing, same-slot replace, single-source LAYER_HIERARCHY);
C-05 VTONEngine (exact wire payload keys {job_id, user_image, garments,
gender_mode, output_aspect}, no seed, SSRF pre-call rejection, live
response contract with verify + model disclosure); C-06 QualityEvaluator
(assert_layer_applied: PASS True returns; False/None/missing → canonical
VTON_LAYER_NOT_APPLIED with job + metrics); C-07 ResultProvenance (person
reference byte-identical hash trace on job row, garment ids/layers,
delivery-token hash, token-verified status 200 vs 404, no raw bytes in
status, live completed-job model_used); C-08 FailurePolicy (explicit codes
per failure class, no 500s, no image payloads in any failure response).

**§35 canonical E2E — `test_at_e2e_canonical_zero_fixtures`: PASS.**
Unknown person → real API → runtime catalog IDs → server resolution → live GPU
→ runtime-only quality evaluation (coverage + identity) → provenance check
(∉ 89 fixture hashes, ≠ input) → result. The N=2 outfit variant is AT-04/AT-10
(honest red, E-1).

**§36–§38 coverage**: 4 unknown persons same garment (AT-17); ≥2 full unknown
outfits (AT-04/AT-10 — third outfit construction recorded in AT-04; complete
2-garment outputs currently blocked by E-1); one-at-a-time mutations
(AT-06 garment/person, AT-15 client reorder, C-03 slot mutation) — all
deterministic and policy-correct.

## C. DYNAMIC INPUT RESULTS (unknown people/garments/outfits)

- **Persons** (unknown): rt1–rt4 (AT suite), person_local_hijab (local),
  person_global_a / person_global_b (global, incl. difficult lighting). All
  rendered through the real path; identity cos self 0.67–0.95 (ArcFace
  eval-only).
- **Garments** (unknown runtime catalog rows): rt1 teal tee, rt2 olive chinos,
  rt3 mustard tee, rt4 burgundy long-sleeve; local olive Arabic long-sleeve
  tee, charcoal one-piece dress; global white CONFIT tee, navy logo blazer.
- **Outfits**: single-garment (many), inner+outer N=2 (AT-15 PASS), top+bottom
  N=2 (AT-04/AT-10 — honest FAIL per E-1), N=3 (EVALUATION-ONLY, 502 recorded).
- **Local**: L1 hijab+Arabic long-sleeve tee (200 verified; sleeves dropped —
  §31-class; text partially preserved; hijab intact), L2 hijab+one-piece
  dress (200 verified; complete incl. sleeves).
- **Global**: G1 white text tee (applied; text partially corrupted), G2 logo
  blazer (applied; inner-drop artifact), G3 dim-lighting blazer (applied;
  identity 0.9091).
- All 10 dynamic outputs ∉ the 89-hash pre-dynamic fixture set
  (`dynamic_validation_evidence.json` + `architecture_test_evidence.json`).

## D. STATIC FIXTURE RESULTS (separate — Phase 0.5, commit 503c8e1)

Fixture/benchmark results, reported separately per §51 (never mixed with C):
benchmark 54/54 @576×768; tests 47/47; §8 quality 20/40; onboarding 10/10;
§10/§12 OCR n=4 (g120 PRESERVED 2/2; g009 CORRUPTED; g121 DESTROYED;
auto-accept BLOCKED); §7 sleeve rotation 0° FULL / 45° partial / 90°
sleeveless; §5 clean-swap KB04 DETECTED / KB12 missed; VLM judge (38×2):
SINGLE 7.83/9.17/8.67, N2 8.00/8.67/8.67, N3 8.00/8.00/8.50. CONDITIONAL
PASS with Gate A (human calibration) BLOCKED.

## E. ROOT CAUSES (actual defects, MEASURED)

- **E-1 N=2 lower-slot-as-layer-2 worker-instance regression** (the only
  suite red). rt2+teal+olive succeeded 20:21/20:35 (verified, evidence saved),
  then failed 5/5 + every suite run with byte-identical metrics (l1 517,314 B
  verify PASS; l2 pixel_change 0.2172, color_shift 0.00149, stddev 48.08).
  Service side PROVEN byte-deterministic (wire payload has no seed; prep
  deterministic). Time-delayed retry +19 min: NO RECOVERY (same bytes).
  Generalization probe: DIFFERENT top (mustard, different L1 bytes) + chinos
  → same failure signature → on the current instance ANY bottom as layer 2 on
  a rendered top produces a near-identity output (no color transfer).
  Controls in the failing state: single chinos = verified; tee→blazer chain =
  verified. ⇒ the current Modal instance (device string flipped A10G→A10)
  systematically fails lower-slot layer 2; the earlier instance did not. Root
  cause of the instance-level difference: **UNRESOLVED** (no worker-side
  introspection); **worker redeploy BLOCKED** (Modal account credentials
  absent in this environment — `modal token info`: Token missing). Failure
  behavior is correct throughout (explicit 502 + code + metrics, never a fake
  image). Details: ARCHITECTURE_TEST_REPORT §4.1.
- **E-2 Sleeve drop-out class** (engine, geometry/pose-dependent): Phase 0.5
  §7 (0° FULL / 45° partial / 90° sleeveless) re-confirmed locally: L1
  long-sleeve tee rendered as crop with original sleeves visible (verify gate
  BLIND — it passed). One-piece dress sleeves render fine (L2). Production
  gate work: wire the calibrated structural probe (AT-16b) or refuse the
  category (§31).
- **E-3 Text corruption class** (engine): Arabic "القاهرة" distorted (L1),
  English "CONFIT" distorted (G1) — same family as Phase 0.5 g009/g121.
- **E-4 White-garment metric blind spot** (evaluation metric, not engine):
  color_coverage is structurally blind to near-white garments (achromatic +
  background exclusion); G1 documented with verify.PASS + visual record.
- **E-5 Inner-garment-drop under single-layer outerwear** (engine artifact):
  G2/G3 — a lone outerwear render replaces the upper body incl. the original
  inner garment. The production N=2 ordering (inner first, AT-15) avoids it.
- **E-6 Sandbox drops large binaries**: ArcFace w600k_r50.onnx (174 MB) lost
  twice in sandbox resets; restored from the verified InsightFace asset
  (sha256 4c06341c…e43 matches the recorded value exactly). Weights remain
  gitignored / EVAL-ONLY.

## F. MODEL / ENGINE RESULT (§46)

- **Current production engine: FASHN `fashn_vton-v1.5` (fork 7c0f10af),
  layered sequential composition** — live-verified for single garments,
  one-pieces, inner+outer N=2; honest explicit failures elsewhere.
- §46 comparison refresh (2026-09-15): no license-clean native multi-garment
  candidate beats FASHN layered composition — UniFit CC BY-NC-SA 4.0 + Flux
  Fill NC (commercial veto); MV-Fashion non-commercial; IDM/OOT/CatVTON
  CC-BY-NC-SA. Garments2Look (CVPR 2026) supports the absence of a
  license-clean native production-grade multi-garment model.
- **Selection: FASHN layered HOLDS on evidence** — conditional on E-1 being
  resolved (worker-side) and E-2 being gated (§31). If the worker instance
  issue proves unrecoverable AND no alternate engine passes the product bar:
  **NO-GO** (per §46/§52 — do not ship an inferior system).

## G. QUALITY GATES (actual validated gates)

- **Production per-layer gate**: `assert_layer_applied` — canonical
  single-source gate (contract C-06); invoked on every VTON path;
  PASS-is-True semantics; emits VTON_LAYER_NOT_APPLIED (502) with job +
  metrics. VERIFIED (contract + live E-1 behavior).
- **Calibrated structural sleeve probe** (eval→candidate production gate):
  AT-16b `_lower_arm_coverage`, threshold 0.35 (positive 0.77/0.64, negative
  0.16/0.16, ≥2× margins). MEASURED; NOT yet wired into production (work
  item with E-2).
- **Garment-application metric of record**: `color_coverage` (ΔE≤25,
  skin-excluded, torso band); applied 0.21–0.85; controls 0.0; threshold
  0.05. MEASURED + calibrated; known white-garment blind spot (E-4).
- **Eval-only, not gating**: ArcFace identity (LICENSE-GATED);
  `sleeve_metrics.arm_coverage` (false-positived on a verified long-sleeve
  render — demoted to reference per the no-ungrounded-hard-gates standard).
- **Human-calibrated thresholds**: **BLOCKED (Gate A)** — no threshold is
  frozen from this phase's measurements.

## H. HUMAN VALIDATION (§49)

**BLOCKED — HUMAN CALIBRATION PENDING.** No ≥3 genuine human raters available
in this environment. All "visual" verdicts in this phase are AGENT-level
visual inspection (recorded as such), explicitly NOT human calibration and
NOT ground truth (standing rule: VLM/agent judgments never substitute for
human raters). Sample frames for human rating exist: AT outputs +
`evaluation/results/outputs/dyn_*.png` (local/global cohorts incl. hijab,
long-sleeve, text, difficult-lighting cases).

## I. LOCAL VALIDATION

`docs/vton/LOCAL_DYNAMIC_VALIDATION_REPORT.md` — 2/2 dynamic renders verified;
hijab-safe (cos 0.92–0.95); one-piece modest dress complete; long-sleeve top
fails the §31 honest-render requirement (E-2); Arabic text partially
preserved. **CONDITIONAL** (blocked on the same gate work as §G).

## J. GLOBAL VALIDATION

`docs/vton/GLOBAL_DYNAMIC_VALIDATION_REPORT.md` — 3/3 dynamic renders
verified across diverse persons, difficult lighting (identity 0.9091), text
and logo garments; zero substitution; inner-drop artifact documented (E-5);
white-tee metric limitation documented (E-4). **GENERALIZES** on the measured
axes.

## K. SECURITY (§42)

| control | evidence | status |
|---|---|---|
| Authorization / ownership | AT-14: guest job poll without token 404, with token 200, wrong token 404, unknown job 404; C-07 status endpoint token-verified 200 vs 404 | VERIFIED |
| Tenant/visibility boundaries | catalog rows resolved server-side; unknown product 404 before worker (AT-13, C-03) | VERIFIED (core path) |
| SSRF | C-01 + C-05: metadata-service/loopback/private IPs rejected for person AND garment URLs, before any worker call; `is_safe_image_url` contract | VERIFIED |
| Image validation | check_person_bytes: type/size (10 KB–15 MB)/dimension (4096)/short-side (256)/aspect (4.0) — C-01 contracts | VERIFIED |
| Worker token protection | admin token env-only (`evaluation/.eval_env`, gitignored); C-05 headers; no token in any committed file | VERIFIED (audit) |
| Rate limits | `app/core/rate_limit.py` exists in production code | **NOT VERIFIED** in this phase (no load test) |
| No secret leakage | committed files scanned (no ak_/as_/tokens); logs carry no token values | VERIFIED (this phase's audit) |
| No image leakage on failures | C-08: every failure response classified, no image payload | VERIFIED |

## L. PRIVACY (§43)

| control | evidence | status |
|---|---|---|
| Person image retention | job row stores the person reference (input_person_image_url) — declared in the schema for provenance (hash-traced, C-07); no hidden persistence found in the VTON path | VERIFIED (declared scope) |
| No raw bytes in logs/status | C-07: status endpoint compact metadata, no base64; structured log fields only | VERIFIED |
| One-shot delivery | delivery_token_hash (sha256) persisted; token never re-served; result endpoint one-shot (404/410 without valid token, C-07/AT-14) | VERIFIED |
| Generated images not stored durably | no output_image_url on failed jobs; delivery backed by process-local TTL cache (vton_delivery) | VERIFIED (code + row audit) |
| URL replay protection | delivery URLs token-bound one-shot (AT-14) | VERIFIED |
| User deletion removes associated metadata | NOT tested in this phase (requires account flow) | **NOT VERIFIED** |
| Temp artifact cleanup | staging delivery TTL-deleted on claim | VERIFIED (code) |

## M. PERFORMANCE

- **p50/p95 per render (single layer, live, n=10 this phase)**: ~18.0–19.5 s
  (MEASURED, per-job logs: 18026–18188 ms execution; 19.2–20.5 s end-to-end
  worker latency). Cold-start not isolated (worker warm throughout —
  readiness OK attempt 0 on every call).
- **VRAM**: 1.83 GB allocated / 3.5 GB reserved on NVIDIA A10 (health payload
  22:28, MEASURED).
- **Cost per render**: **UNMEASURED** (no billing access from this
  environment).
- Determinism ⇒ no need for result caching in production (AT-06); delivery
  TTL cache only.

## N. LICENSE (exact evidence)

| item | license | status |
|---|---|---|
| FASHN engine (fashn_vton_segfee fork 7c0f10af) | Apache-2.0 (REPO-ATTESTED, Phase 0.5) | committable/deployable |
| ArcFace w600k_r50.onnx (174,383,860 B, sha256 4c06341c…e43 — re-verified 22:22) | trained on WebFace600K → commercial rights UNRESOLVED | **LICENSE-GATED — EVALUATION-ONLY**; never a production gate; never committed (gitignored) |
| InsightFace buffalo_l asset (288,621,354 B zip, zip-verified) | code Apache-2.0; weights per above | eval-only |
| AdaFace (weights lost; manifest only) | MS1MV2-derived → commercial UNRESOLVED | EVAL-ONLY history; not in this phase's runs |
| NotoNaskhArabic (available, not yet committed) | SIL OFL 1.1 | committable if needed for local text tooling |
| UniFit / MV-Fashion / IDM / OOT / CatVTON | CC BY-NC-SA 4.0 / non-commercial | commercial veto — excluded |
| Git tree | no license-restricted weights present (weights gitignored) | VERIFIED |

## O. PRODUCTION STATUS (exact)

- Branch `research/vton-phase05-calibration` (2 commits + this commit);
  `main` untouched; **no merge** (standing rule: no direct merge to main).
- `feat/vton-multigarment-layered-fashn` **NOT created** — §47 gates:
  architecture tests must pass (AT-04/AT-10 honest red on E-1) and validation
  gates must pass (Gate A BLOCKED). Gated, not started.
- Shadow/staging real-user test (§29): **NOT IMPLEMENTED** (post-gate).
- Frontend dynamic UI (§48): not implemented this phase (frontend shows the
  existing flow; no faking introduced, nothing verified beyond the API).
- Push to GitHub: **BLOCKED** (no PAT in env).

## P. REMAINING LIMITATIONS (no hidden limitations)

1. **N=2 top+bottom (lower slot as layer 2) fails on the current worker
   instance** (E-1) — honest 502; resolution requires worker-side action
   (redeploy/instance fix) — BLOCKED from here.
2. **Sleeve drop-out (E-2)**: production verify gate blind; calibrated
   structural probe exists but is not wired as a production gate; long-sleeve
   tops must be refused or gated per §31 before exposure.
3. **Text fidelity (E-3)**: Arabic and English garment text distorted
   (corruption class, n=2 dynamic + Phase 0.5 n=4 fixture).
4. **White-garment metric blind spot (E-4)** — evaluation metric only.
5. **Inner-garment-drop under single-layer outerwear (E-5)** — avoid via
   production N=2 ordering; standalone outerwear UX must be scoped.
6. **N=3 EVALUATION-ONLY** until N=2 is promoted (currently 502).
7. **Human calibration BLOCKED (Gate A)** — no frozen production thresholds.
8. **Production identity model LICENSE-GATED** — no commercially-cleared FR
   model obtained (HF unreachable; w600k/AdaFace eval-only).
9. Rate limits + user-deletion privacy flows NOT VERIFIED this phase.
10. Cost per render + isolated cold-start UNMEASURED (no billing/infra access).
11. Shadow/staging, frontend §48, production implementation §47 all pending
    the gates.
12. Sandbox binary persistence unreliable (weights lost twice; restored once
    with sha256 verification).

## Q. CLAIM AUDIT (every major claim)

| CLAIM | EVIDENCE | STATUS |
|---|---|---|
| CONFIT_A renders arbitrary unknown user images + runtime catalog garments through the real production path without substitution | AT-01/02/07/08/09/11/12/13/14 + AT-E2E + L/G renders; outputs ∉ 89-hash fixture set; input/output hashes recorded | **VERIFIED** (MEASURED) |
| Server-side authoritative catalog resolution; client metadata never truth | AT-13, C-02, C-03 (client slot lie rejected) | VERIFIED |
| Server-derived layer order, client-order independent | AT-15 (identical output both orders), C-04 | VERIFIED |
| One-shot delivery + provenance chain (request→output) | AT-05, C-07 (byte-identical person hash trace, token hash, model_used) | VERIFIED (enrichment gaps: garment image hashes, worker git revision on job, seed — documented §34) |
| Deterministic worker (identical inputs → identical bytes) | AT-06; 5 identical failure signatures; repeated renders byte-identical | VERIFIED |
| Failure handling is honest (explicit code, no fake image, no canned result) | AT-16/16b, C-06, C-08, E-1 behavior (502 VTON_LAYER_NOT_APPLIED with metrics) | VERIFIED |
| Fixture IDs never enter production decisions | code scan 10/10 (zero matches, production trees) | VERIFIED |
| **N=2 top+bottom reliability** | AT-04/AT-10 red; E-1 timeline + retry + generalization | **NOT VERIFIED — UNRESOLVED (worker-side); honest red** |
| Long-sleeve garments render with sleeves | AT-16b PASS (standard upright input) vs L1 local FAIL (crop re-fit) | **PARTIAL — geometry/pose-dependent; production gate not wired** |
| Identity preservation on dynamic outputs | ArcFace cos self 0.67–0.95 (eval-only) | MEASURED (LICENSE-GATED; not a production claim; human calibration BLOCKED) |
| Local market (hijab/modest/one-piece/Arabic) | L1/L2 renders | CONDITIONAL — one-piece + hijab PASS; long-sleeve top + text PARTIAL (E-2/E-3) |
| Global market generalization (body type/lighting/text/logo) | G1–G3 renders | MEASURED on the sampled axes; text PARTIAL; human rating pending |
| FASHN layered is the production engine | §15 refresh; no license-clean native multi-garment alternative | HOLDS on evidence (conditional on E-1/E-2) |
| Production-ready | §30 bar | **NOT MET — BLOCKED** (Gate A, E-1, LICENSE-GATED identity) |
| Human validation | — | **BLOCKED — HUMAN CALIBRATION PENDING** |

---

### Final statement (§52)

The system is proven DYNAMIC on the measured axes — real user images, real
catalog garments, real GPU, real gates, real provenance, zero fixture
substitution, honest explicit failures. It is **NOT production-ready**:
the N=2 lower-layer chain is broken on the live worker instance (honest red,
root cause unresolved, redeploy blocked), the sleeve limitation is not yet a
production gate, human calibration is pending, and a commercially-cleared
identity model is outstanding. Per the master prompt: where it cannot be
proven, this report says **NOT VERIFIED / BLOCKED** — and **BLOCKED is never
converted to GO**.
