# CONFIT_A VTON — REMEDIATION FINAL REPORT, PHASE 7 (2026-09-19)

**Phase-7 mandate:** verification and closure. No broad redesign. No
reopening settled questions without contradictory observation. The
repository is left in one of two honest states: release-grade evidence
with all gates closed, or a precise BLOCKED/CONDITIONAL state. It is the
latter.

**Single release state: `BLOCKED`** (§U). No GO transition made or
attempted.

Format: **CLAIM → EVIDENCE → STATUS**. States used only where
evidence-supported: VERIFIED / MEASURED / IMPLEMENTED / TESTED /
CONDITIONALLY VERIFIED / PARTIAL / NOT VERIFIED / BLOCKED / UNRESOLVED /
UNSUPPORTED / LICENSE-GATED / NO-GO.

---

## A. Exact repository state

**A1.** Phase 7 executed on the Phase-6 tree (v2.4 gate, P0 matrix,
MCP reconciliation, human package). Environment reset #4 occurred at
phase start (`.git` replaced by a fresh clone — Phase-6 commit `713694d`
lost, 0 dangling objects; site-packages wiped; **working tree intact**).
Environment restored per the documented procedure (P8-A):
`pip install -r backend/requirements.txt` + CPU torch/torchvision +
easyocr 1.7.1; all Phase-7 work re-committed on branch
`vton-evidence-reconciliation-2026-09-16` (re-created from main 928e615).
→ EVIDENCE: reflog ("clone: from …"), `git fsck` (0 dangling), restore
commands, full suite green after restore (§S).
→ STATUS: VERIFIED.

**A2.** No accidental main commit; main = 928e615 (unchanged); all Phase-7
work committed on the reconciliation branch only. Secret scan of the
staged diff: clean (only `modal_` identifier/doc references). No user
images or model weights tracked (results/ + weights_local/ + raw PNGs
gitignored; the 73-item human manifest stores paths + sha256 only).
→ STATUS: VERIFIED (P9 checklist, §S).

**A3.** New Phase-7 artifacts: frozen spec
(`docs/vton/SLEEVE_GATE_V24_FROZEN_SPEC_2026-09-19.md`), full-matrix
probe + JSON (`p7_v24_full_matrix`), confusion-matrix JSON
(`p7_v24_confusion_matrix`), P1-D fresh adversarial set (10 bases +
20 composites + `results.json`), MCP audit Phase-7 verification section,
human package upgraded (73 items, blinded), P5 probe records gate
fingerprint.
→ STATUS: IMPLEMENTED.

## B. v2.4 final implementation

**B1 (frozen state).** The gate was frozen before any change (P0):
`SLEEVE_GATE_V24_FROZEN_SPEC_2026-09-19.md` records the exact constants
(S1 pass 0.35 / fail 0.15; ΔE radius 40.0; change 20.0; S5 0.10; S6
0.05; **S5b `ANATOMY_ANY_SKIN_REFUSE = 0.15` at line 372**; skin window
l 25–85 / a 7–25 / b 7–31; bands left (0.52,0.70,0.40,0.55), right
(0.28,0.46,0.40,0.55); outer 0.65; wrist 0.35), the exact decision
order (N/A → N/A → AT-19 REFUSE → degenerate-color REFUSE → probe-error
REFUSE → coverage → S5 → S5b → S6 → PASS), the exact status/reason
strings, and the exact regression tests.
→ STATUS: VERIFIED (code inspection, line numbers recorded).

**B2 (purity).** `0.15` is the production constant; no experimental
alternatives in production code (per-arm AND, τ 0.10/0.20,
mediapipe/landmark variants exist only in evaluation probes); no
probe-specific monkeypatch in the service/controller path (grep +
inspection of `tryon_service.py` call site). v2.4 = v2.3 + S5b only;
S1/S5/S6 byte-identical to v2.3.
→ STATUS: VERIFIED.

**B3 (wiring).** REFUSE → `SleevesNotVerifiedError` →
`VTON_SLEEVES_NOT_VERIFIED` → HTTP 502 on both try-on endpoints, no
image staged/delivered. No new public error code introduced in v2.4.
→ STATUS: VERIFIED.

## C. Sleeve confusion matrix (authoritative, frozen v2.4)

Full-matrix run of the frozen production gate on the entire calibrated
cohort (50 matrix rows + 6 adversarial composites = **56 unique
artifacts**; `BASE_cal02` duplicate entry removed):

**C1 (table match).** All 56 rows reproduce the frozen decision table —
0 mismatches, 0 missing files, 0 errors.
→ EVIDENCE: `evaluation/results/p7_v24_full_matrix.json`.
→ STATUS: VERIFIED.

**C2 (authoritative matrix, τ = 0.15):**

| | PASS | REFUSE | total |
|---|---|---|---|
| truth = present (41) | **TP = 21** | **FN = 20** (over-refusal) | 41 |
| truth = dropped / dropped_synth / short_declared_long (15) | **FP = 0** | **TN = 15** | 15 |

TPR 0.5122 · FNR 0.4878 · TNR 1.0 · FPR 0.0 · precision (PASS verdicts)
1.0 · recall (defect detection) 1.0.
→ STATUS: MEASURED (agent labels — engineering calibration, NOT human
ground truth).

**C3 (defect safety vs valid-render acceptance, separated as
mandated).**
- **Defect safety:** 15/15 defect rows REFUSED — no actually-incomplete
  sleeve render PASSES.
- **Valid-render acceptance:** 20/41 present rows REFUSED — each listed
  with its refusing channel (S1 coverage thin-margin / pose / band
  geometry; S5/S6 anatomy): cal_03, cal_04, cal_07, sc_white, sc_gray_D,
  loc_arabic2_F, sc_black_I, io_gray_I, m0_repro, p5_m_blazer, p5_m_io,
  p0c_k_white, p0c_f_white, p0c_m_black, p0c_e_rust, p0c_a_pattern,
  io_1, io_3, m3_arms_raised, m4_diff_person. **Not hidden**: this is
  the gate's measured usability cost (over-refusal in the safe
  direction), fixed-band geometry (P1-C of Phase 6: landmark fix is
  feasible, ~31 ms, evaluation-only).
→ STATUS: MEASURED.

**C4 (threshold proof, P1-B).** Swept τ ∈ {0.05, 0.10, 0.15, 0.20}
(evaluation-only, from the measured s5b values — no code changed):

| τ | TP | TN | FP | FN | flips vs v2.3 | verdict |
|---|---|---|---|---|---|---|
| 0.05 | 14 | 15 | 0 | 28 | 9 | REJECTED — 7 healthy v2.3-PASS rows newly over-refused (cal_01, cal_02, cal_09, sc_rust_I, p4_k_rust, m1, m5) |
| 0.10 | 20 | 15 | 0 | 22 | 4 | REJECTED — 2 borderline healthy rows over-refused (m1 0.1193, m5 0.1070), no added safety |
| **0.15** | **21** | **15** | **0** | **20** | **2** | **RETAINED — zero baseline flips; closes both asymmetric FPs** |
| 0.20 | 21 | 15 | 0 | 20 | 2 | dominated by 0.15 (identical table; defect margin 1.175× vs 1.57×) |

Decision-relevant boundaries (S5b has authority only on v2.3-PASS rows):
highest healthy 0.1193 (m1); lowest defect 0.2350 (both asymmetric
composites; the 4 other composites are already refused by v2.3's own
channels — e.g. adv_wristgap s5b 0.1237 but v23=REFUSE, not an S5b
hole). τ=0.15 sits between them: 1.26× / 1.57× margins. Selected from
the flip table, not because it "looks balanced".
→ EVIDENCE: `evaluation/results/p7_v24_confusion_matrix.json`.
→ STATUS: MEASURED.

## D. Sleeve adversarial results

**D1 (frozen-gate adversarial set).** All 6 Phase-6 composites REFUSED
on the frozen gate (part of C1's 56-row run): crop, elbow, midgap,
onearm, onearm_full (s5b 0.2350 → REFUSE), wristgap.
→ STATUS: VERIFIED.

**D2 (P1-D fresh cases — not used to tune the rule).** 10 freshly
generated bases (new persons; dark/light/medium skin; white/black/
burgundy/gray/beige/stripe/multicolor garments; light & dark
backgrounds; hijab/modest; plus-size; arms-raised) × 3 constructions
(healthy vs exposed-arm input, one-arm drop, bilateral crop):
- **20/20 defect composites REFUSED** — every one-arm composite
  measured s1 = 0.54–0.99 (S1 alone would have PASSED every one) and
  s5b = 1.0: the v2.3 false-pass class reproduced on 10 fresh arms, all
  closed by S5b.
- 8/10 healthy renders PASSED. The 2 "healthy" REFUSEs were visually
  re-labeled by agent inspection: the generator produced **3/4-sleeve
  renders** (sleeves ending above the wrist; forearms exposed) — i.e.,
  two further genuine `long → 3/4-sleeve` defect renders, correctly
  refused (s5b 0.356 / 0.326). **Net: 0 safety violations, 0 unjustified
  refusals.**
→ EVIDENCE: `evaluation/results/p7_adversarial/` (bases, composites,
`results.json` with per-channel measurements + visual notes).
→ STATUS: MEASURED (AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH).

**D3 (P1-C ten required classes — all REFUSED):**

| # | required class | measured artifact(s) | result |
|---|---|---|---|
| 1 | one-arm full sleeve drop | adv_onearm_full; 10× p7d onearm | REFUSE (s5b 0.2350 / 1.0) |
| 2 | one-arm partial sleeve drop | adv_onearm (elbow-length) | REFUSE (s5b 0.2350) |
| 3 | bilateral sleeve drop | cal_06 (L1 defect); p4_j_arabic2 (class-E); 10× p7d bilateral | REFUSE |
| 4 | long→short conversion | live white-LS render (s1 0.095); 2× p7d 3/4-sleeve renders; p0c_g_short; cal_10; sc_tank_C; sc_crop_B | REFUSE |
| 5 | long→elbow conversion | adv_elbow; p7d onearm paint (elbow-down) | REFUSE |
| 6 | sleeve missing, garment body present | class-E (white torso, sleeves dropped); adv_midgap | REFUSE |
| 7 | inner garment visible where outer sleeve should be | p0c_synth_full ×3 | REFUSE |
| 8 | asymmetric failure on exposed-arm input | adv_onearm/onearm_full; 10× p7d (exposed-arm inputs) | REFUSE (s5b) |
| 9 | class-E color-block failure | p4_j_arabic2_L1 | REFUSE (S5 0.2965) |
| 10 | patterned/multicolor, sleeve not to wrist | adv_wristgap (S6); p7d stripe + multicolor fresh renders & their defect composites | REFUSE |

No genuine defect PASSES in any measured set. No test weakened.
→ STATUS: VERIFIED on the measured set (human barrier, §Q).

## E. Sleeve safety conclusion

**E1.** `SLEEVE GATE v2.4 = SAFE AT MEASUREMENT LEVEL`: every measured
incomplete-sleeve render (engine drops, synthetic drops, 3/4-sleeve
renders, all composites incl. the asymmetric FP class on 12 different
arms) is REFUSED and regression-pinned; 0 FPs across 56+30 evaluated
artifacts; no threshold moved without the flip-table evidence (C4).
→ STATUS: VERIFIED (measured set) — **human calibration remains open**
(§Q); "universal safety" is NOT claimed.

**E2.** Measured limitations (not hidden): 20/41 healthy renders
over-refused (fixed bands; P1-C landmark path feasible, ~31 ms,
evaluation-only); very-small-gap-above-wrist regime unmeasured (no such
engine output observed); engine stochastic drops persist at the engine
level (gate refuses, engine not fixed).
→ STATUS: DOCUMENTED.

## F. N=2 low-contrast engine truth

**F1 (settled — raw-output evidence).** The P0 matrix (7 live renders,
exact L1 bytes as L2 input) measured: navy-on-navy (A-E, pxchg 0.2915),
navy→charcoal (B, 0.2774), navy→navy-patterned (F, 0.2814) =
**ENGINE DID NOT APPLY** (max diff 2–3/255 over the whole lower region;
0.000% changed px; original joggers + drawstring visible in the raw
render). Beige (C 14.30), reverse navy (D 15.77), wide→slim (G 8.99),
pants→skirt (H 2.97) = APPLIED (8.9–37.8% changed px, max ~210/255).
→ STATUS: VERIFIED (raw bytes + metrics + rendered images on disk,
Phase-6 §B/C). Not reopened — no contradictory observation exists.

**F2 (engine pattern, MEASURED).** The engine applies the lower garment
when the target differs in luminance family or silhouette, and no-ops on
same dark-color-family targets (including charcoal). Engine limitation,
documented; not a verifier limitation.
→ STATUS: MEASURED.

## G. N=2 verifier truth

**G1.** The change-based lower-garment verifier separates applied
(≥2.97 pxchg / 0.0202 cs) from not-applied (≤0.2915 / 0.0021) with a
≥10× margin on the observed range; orthogonal signals measured (s1
changed-px and s2 Sobel edge-Δ separate cleanly; s3/s4 not
discriminative; s5 DINOv2 ENVIRONMENT-BLOCKED, recorded not skipped);
**no signal adopted, no threshold changed**; negative controls (three
distinct no-application controls) all REFUSED. "Applied-but-invisible"
regime = UNKNOWN (never produced in ~27 renders), documented; honest
refusal is the verifier's behavior where distinction is unreliable.
→ STATUS: MEASURED (Phase-6 §B–D; no change).

**G2 (product decision, P2-A).** Contract decision recorded: a
composition is **supported only when engine evidence confirms actual
application**; when the engine cannot apply/verify the target garment
(incl. low-contrast no-op), the system **refuses with the existing
canonical `VTON_LAYER_NOT_APPLIED` (502, no image delivered)**.
No new public error code is introduced: the existing code already
encodes the product semantics ("the requested garment layer was not
applied"), and the five required checks confirm it — existing taxonomy
✓, API compatibility ✓ (502 + code field on both endpoints), frontend
handling ✓ (`useTryOnViewModel.ts:178`), telemetry ✓
(`vton_layer_not_applied` event with verify metrics), regression
coverage ✓ (`test_vton_layer_not_applied.py`). A `LOW_CONTRAST`-flavored
variant would fragment the taxonomy without changing the
user-facing fact.
→ STATUS: IMPLEMENTED (decision; behavior pre-existing and verified).

## H. N=2 composition matrix

**H1 (measured, per class — existing evidence, explicitly NOT
aggregated into one percentage):**

| class | measured evidence | status |
|---|---|---|
| Single top | sleeve cohort L1 renders (50+ rows, multiple persons/garments) + P5-design L-cases (pending live) | MEASURED (large) / fresh-this-phase: NOT RUN (infra) |
| Single bottom | P0 matrix (7 live, raw bytes, persons I/C/A/K) | MEASURED |
| Single dress/tunic | cohort (loc_tunic_F, p4_j_tunic, sc_dress_G) | MEASURED (sleeve context) |
| Single outerwear | cohort (E-1, C-07, cal_13, p5_m_blazer, m-rows) | MEASURED (sleeve context) |
| N=2 top+bottom | Phase-5 controlled matrix: 18/20 PASS (persons A/C/I × 3 bottoms, N repeats, byte-identical within instance; 2/20 = person-I navy-on-navy engine no-op REFUSE) | MEASURED |
| N=2 inner+outer | cohort L2 rows (m0_repro, io_1, io_3, m5) + G4 design (pending live) | MEASURED (partial) / fresh-this-phase: NOT RUN (infra) |

**H2 (gap, stated).** The Phase-7 requirement "fresh person 1/2/3 × ≥2
garments × repeated attempts per class" requires live worker runs:
**BLOCKED (infrastructure)** — Modal workspace disabled (re-pinged this
phase, still `404 … is disabled`); no redeploy credentials. The P5 probe
(11 cases × N=2, new runtime inputs) covers the local + global designs
and records the frozen gate version/commit at run time; re-run =
`python3 evaluation/probes/p6_p5_dynamic_fresh.py`. No stale pre-v2.4
result is used as current verification; no partial percentage claimed.
→ STATUS: BLOCKED (infrastructure) / MEASURED where stated.

## I. Retry assessment

**I1.** Production path = **single-attempt inference, no render retry**:
`tryon_service.py` performs one `POST /vton/process`; every error branch
(401/403/422/503/other) raises its canonical error immediately. The
only retry loop in the file is the pre-render **health/readiness probe**
(`VTON_WORKER_MAX_RETRIES=3`, exponential backoff — waiting for the GPU
to come up, not re-rolling a render). Measured retry ineffectiveness
stands (Phase 4: first-attempt 13.3% / within-5 30.8%; Phase 5:
byte-identical person-I repeats). No retry-until-success, no
previous-image/stale-image/fixture fallback, no alternate-engine silent
fallback exists or was added.
→ STATUS: VERIFIED (code inspection + prior measurements).

## J. MCP Market reconciliation (closure)

**J1.** Phase-6 reconciliation stands: 6 WeShop-ecosystem skills LIVE at
direct slug URLs; old "NOT FOUND" preserved + `SUPERSEDED BY RECONCILIATION`;
miss cause documented (server `/search` top-20 only; skills surface has
no server-side search; direct slugs work); "exhaustive" withdrawn →
`REACHABLE-SURFACE DISCOVERY`.
→ STATUS: VERIFIED (Phase-6 addendum, preserved in the audit doc).

**J2 (Phase-7 verification).** Two further skills named in the Phase-7
directive were fetched live 2026-09-19 and added to the audit
(§7.1): **WeShop AI Studio — Image & Video** (`weshop-ai-image-video-studio`,
LIVE: VTO + ghost mannequin + model/background swap + pose + canvas +
video, asset upload + async polling) and **WeShop AI Model Generator**
(`weshop-ai-model-generator`, LIVE: portrait → stylized-model imagery/
video, batch ≤16). Both = same class: Agent Skills wrapping the WeShop
OpenAPI. **Total: 8 WeShop-ecosystem skills, all LIVE, all DISCOVERED.**
→ STATUS: VERIFIED (direct fetches; listing text recorded as evidence).

## K. Agent Skills vs MCP Server distinction

**K1.** For every audited item the four layers are recorded separately:
MCP Server / Agent Skill / Underlying API / Underlying engine. **None
of the 8 WeShop items is an MCP Server** (all Agent Skills); the
underlying API = WeShop OpenAPI (proprietary); the underlying engines =
proprietary hosted (weshopFlash/weshopPro/bananaPro + unnamed video
engines) — not open, weights not auditable. Calling an Agent Skill "an
MCP server", the wrapper "an AI model", or the WeShop API "an open VTON
model" is forbidden and not done anywhere in the audit.
→ STATUS: VERIFIED (audit §7.2 table).

## L. WeShop audit (final)

**L1 (license separation, P3-B).** For all 8 skills: skill code = MIT;
CLI = official npm package; API terms = WeShop commercial ToS; model
rights = **unknown** (proprietary hosted, no weights, no license
statement). MIT wrapper grants NO rights to the engines.
→ STATUS: VERIFIED (official repos, Phase-6 §3 + Phase-7 §7.3).

**L2 (identity, P3-C — the critical one).**
- **WeShop AI Model Generator = identity SUBSTITUTION by design**
  ("converts portrait photos into … model visuals") → classified
  **`NOT SUITABLE AS A CONFIT REAL-USER IDENTITY-PRESERVING VTON
  ENGINE`** (product requirement = preservation; the service replaces).
  Not hidden behind "model reference".
- VTO skill `fashionModelImage` = "will resemble this person" =
  approximate identity, not verified preservation.
- Studio "model swapping" = catalog-model composition (product-photo
  workflow), not real-user identity rendering.
→ STATUS: VERIFIED (listing text + OpenAPI contract as evidence).

**L3 (multi-garment, P3-D).** `batchCount` 1–16 = 16 outputs from one
input set (variations/angles), **NOT** multiple garments in one
composition. The VTO contract takes exactly one garment per run. **No
WeShop skill or endpoint demonstrates native multi-garment/layered
composition or deterministic layer order.** Batch ≠ multi-garment,
explicitly stated.
→ STATUS: VERIFIED (OpenAPI contract).

**L4 (privacy).** No documented retention/training-usage/deletion/
residency/DPA for any WeShop endpoint (privacy page = standard
template). → **EXTERNAL VTO INTEGRATION = BLOCKED**;
**EXTERNAL LIVE EVALUATION = BLOCKED** (no authorized credentials — none
requested/invented; no real user images sent to any vendor, no synthetic
upload without terms permitting it).
→ STATUS: BLOCKED.

## M. Other external candidates

| candidate | state | why |
|---|---|---|
| fal-tryon (fal.ai skill) | RESEARCH (stale) | needs FAL_KEY (none authorized); upstream skill folder removed from main — stale listing; engine per call dynamic/unpinned |
| Vybe | REJECTED | Replicate model 404 (engine gone) |
| HeyBeauty / TryOnfy / GenPark / ComfyUI wrappers | RESEARCH | proprietary link/redirect surfaces or generic substrate; no VTO engine access |
| CLO3D | REJECTED | 3D CAD, wrong domain |
| Rembg-1 | RESEARCH | software Apache-2.0 but weights license-gated (u2net family) |
| Face/identity candidates | LICENSE-GATED | deepfake-adjacent, rights unresolved |

**No external candidate was evaluated this phase** — none satisfies
access + terms + authorized credentials + understood privacy (P3/P4).
No marketing claim was used as evidence.
→ STATUS: VERIFIED (process) / NO EVALUATIONS PERFORMED (honest).

## N. Privacy / legal / security decision

**N1 (privacy).** No real user images left this environment except to
the local/eval FASHN worker (authorized evaluation path, now blocked by
infrastructure). No vendor upload of any kind. WeShop privacy gap →
BLOCKED (L4).
→ STATUS: VERIFIED (process) / BLOCKED (external).

**N2 (legal).** License suite green at commit (FASHN Apache-2.0 fork
7c0f10af; mediapipe/EasyOCR Apache-2.0 eval-only; UniFit CC BY-NC-SA
veto; MV-Fashion NC; AdaFace MS1MV2 unresolved; IDM/OOT/CatVTON
CC-BY-NC-SA; FastFit NOASSERTION-NC; NotoNaskh OFL). No
NC/unclear-license code or weights in production; no license-restricted
weights tracked (gitignored + scan).
→ STATUS: VERIFIED.

**N3 (security, P8).** Full suite green after every instrumentation
change this phase (§S). Persisted records = hashes/metadata/metrics/
statuses only; the 73-item human manifest and all probe JSONs audited
for payloads (none); no credentials/tokens in tracked files
(`.eval_env`/`.eval_urls` gitignored; secret scan clean).
→ STATUS: VERIFIED.

## O. Fresh local dynamic validation

**O1.** `BLOCKED (infrastructure)` — Modal workspace disabled (re-pinged
this phase; no redeploy credentials). Delivered and re-runnable: NEW
runtime inputs (`evaluation/dyninputs_p5/`: hijab/modest, Arabic-text,
deep-skin, fair-skin, plus-size, dark-bg, tank/exposed-arms) + L1–L6
local design (modest tunic LS, one-piece dress, Arabic-text tee
[EasyOCR], rust LS, white LS, patterned LS), N=2 each; the probe now
records the frozen gate version + commit + constants in its output
(gate fingerprint verified this phase: S1 0.35/0.15, S5 0.10, S5b 0.15,
S6 0.05 — matching the frozen spec exactly). EasyOCR 1.7.1 restored,
single-language subprocess (2 GB OOM constraint documented). Identity
on P5 renders = NOT MEASURED, NOT VERIFIED, no proxy.
→ STATUS: BLOCKED (ready to re-run; no local metric claimed).

## P. Fresh global dynamic validation

**P1.** `BLOCKED (same infrastructure)`. Delivered and re-runnable:
G1–G5 global design (plus-size black LS over tank input = live
old-skin condition, dark-on-dark, text tee [EasyOCR], tee → logo blazer
inner+outer chain, tee+joggers in ONE call = true multi-garment), N=2
each, new inputs. Same gate-fingerprint recording. No global metric
claimed.
→ STATUS: BLOCKED (ready to re-run).

## Q. Human calibration

**Q1.** `HUMAN CALIBRATION = BLOCKED` — no ≥3 real independent raters
available; no VLM/agent relabeling (agent labels explicitly
`AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH` everywhere).
→ STATUS: BLOCKED.

**Q2 (package — executable as-is, upgraded this phase).**
`evaluation/human_calibration/`: 73-item blinded set (66 sleeve — incl.
all 6 Phase-6 composites + 10 fresh Phase-7 P1-D bases, the two
3/4-sleeve renders among them — + 7 low-contrast); **opaque `blind_id`
presentation** (raters see item-01…item-73 + type only; case/person/
garment identity + verdicts in `UNBLINDING_SHEET.csv`, never shown);
rubric (FULL/PARTIAL/ABSENT/UNSURE; APPLIED/NOT_APPLIED/PARTIAL/UNSURE;
low-contrast honesty rule; no-AI rule); run instructions (≥3
independent raters, fixed-seed order, core set 23, Fleiss' kappa +
consensus, gate-vs-human disagreements = defect reports, closure
criteria); reproducible builder (paths + sha256 only, P8).
→ STATUS: PREPARED (barrier closure requires raters).

## R. Production identity

**R1.** `PRODUCTION IDENTITY = LICENSE-GATED` (unchanged, per mandate):
ArcFace/WebFace600K evaluation-only, rights unresolved; no identity
metric claimed anywhere this phase; P5 identity will be reported NOT
MEASURED, not proxied.
→ STATUS: LICENSE-GATED.

## S. Full regression / security suites

**S1.** After environment restore, the complete authoritative suite:
**backend + evaluation = 1326 passed / 29 skipped / 0 failed** (216 s).
All 29 skips explained:
- 26 × "live GPU worker not configured" (opt-in
  `CONFIT_AT_LIVE_WORKER=1`; the worker is disabled — §O/P; the
  architecture tests are live-worker tests, not product regressions);
- 1 × PostgreSQL-only schema-drift test (no PG URL in this environment);
- 1 × synthetic partial-drop replay — gitignored PNG absent (skip by
  design);
- 1 × rembg model path disabled (license-gated, disabled by default).
No test removed or weakened.
→ STATUS: VERIFIED.

**S2 (P9 git reconciliation).** Before commit: HEAD/branch/main
verified; exact diff inspected; secret scan clean (only `modal_`
identifiers/doc references, no values); no user images/weights tracked;
raw-bytes probe artifacts excluded (results/ gitignored); commit made
only with intended work; SHA verified after commit (recorded in the
commit message of record — see branch log); no push/PR (no PAT; not
claimed).
→ STATUS: VERIFIED.

## T. Claim audit

**T1 (banned-word / no-gaming).** No threshold moved to change
PASS/REFUSE counts (S5b 0.15 = the only v2.4 constant, retained by
flip-table evidence C4, zero baseline flips); no FP/FN hidden (20
over-refusals listed individually, C3); no failure-label swaps without
raw bytes (F1); no fixture/garment/person exceptions anywhere in the
gate (B2); no install-because-exists (J2: DISCOVERED only); no
description-as-proof-of-backend (all WeShop claims tied to the OpenAPI
contract or listing text, labeled as such); no privacy-safe/commercial-
rights claims without evidence (L4); no retry-until-success (I1); no
cached/unrelated images (worker cache = same-composition re-read,
documented Phase 5; no cross-composition reuse); no silent engine
fallback (I1).
→ STATUS: VERIFIED (self-audit against the do-not-game list).

**T2 (superseded claims, preserved).** Phase-5 "FPR-0" for the sleeve
gate = INVALID as stated (superseded by the measured v2.3 FP class);
the v2.4 statement is scoped: **0 FPs on the 56+30 measured artifacts**.
WeShop "NOT FOUND" = SUPERSEDED BY RECONCILIATION (6+2 skills LIVE).
"Exhaustive searched" = withdrawn (REACHABLE-SURFACE DISCOVERY).
→ STATUS: SUPERSEDED (documented in place).

## U. Final release decision

**RELEASE = BLOCKED.** One state; no GO transitions.

| barrier | state | evidence |
|---|---|---|
| Sleeve safety (no known dropped-sleeve render may PASS/ship) | **CLOSED at measurement level** — 0 FPs on 56+30 measured artifacts, all classes D3 refused + regression-pinned; human calibration still open under barrier 5 | §C–E |
| N=2 engine (reliably applies requested garment) | **OPEN — engine limitation**: same-dark-family lower-garment no-op measured (F2); engine not fixed; product contract = support only on confirmed application (G2) | §F |
| N=2 verification (distinguish applied from not) | **CLOSED at behavior level** (≥10× margin on observed range; honest refusal on the no-op; no threshold moved; applied-but-invisible = UNKNOWN documented) | §G |
| Human calibration (≥3 real raters) | **BLOCKED** (package prepared, blinded, 73 items) | §Q |
| Identity licensing | **LICENSE-GATED** | §R |
| MCP integration (technical+privacy+licensing+security) | **BLOCKED** (WeShop privacy undocumented + identity substitution + no multi-garment; no other candidate accessible; nothing installed) | §J–L, §M |
| Fresh dynamic local + global batch | **BLOCKED (infrastructure)** (Modal workspace disabled; re-runnable; gate fingerprint recorded) | §O/P |

Product question carried forward (no decision this phase beyond G2):
engine-side fix vs continued honest refusal for the dark-on-dark lower-
garment no-op — the refusal contract (G2) is settled; the engine fix is
an engineering task, not a verifier change.

### What this phase fixed / found / left (final standard)

- **Fixed/integrated:** v2.4 frozen + proven (0.15 retained by evidence);
  full 56-row frozen-gate matrix green; fresh 30-artifact adversarial
  sweep all safe; 3/4-sleeve defect class newly caught; MCP audit closed
  (8 skills, 2 newly verified); human package blinded + expanded; P5
  probe records gate version; Phase-6 report restructured; suites green.
- **Engine limitations (not verifier):** dark-on-dark lower-garment
  no-op; stochastic sleeve drops; 3/4-sleeve renders (generator/engine
  variance).
- **Verifier limitations:** fixed-band geometry → 20/41 healthy
  over-refusals (landmark fix feasible, evaluation-only);
  applied-but-invisible regime UNKNOWN (never observed).
- **Reliability limitations:** worker instance-cache determinism
  (same composition re-reads the same outcome); Modal workspace disabled
  (infrastructure); 2 GB sandbox RAM (dual-language OCR OOM); DINOv2
  weights lost (HF 401).
- **MCP actually found:** 8 WeShop-ecosystem Agent Skills (LIVE) +
  fal-tryon (stale) + 4 RESEARCH + 3 REJECTED — listed vs tested:
  **none of the external candidates was tested** (none accessible under
  the constraints).
- **Rejected:** Vybe (engine dead), CLO3D (wrong domain),
  Model-Generator class (identity substitution), WeShop production
  integration (privacy/identity/multi-garment).
- **Externally blocked:** WeShop credentials+privacy, Modal workspace,
  ≥3 human raters, ArcFace/WebFace600K rights.
- **Production state: BLOCKED.**

---
*Every status above is MEASURED (raw bytes/metrics at the cited paths),
VERIFIED (re-executed this session), BLOCKED, LICENSE-GATED, UNKNOWN,
SUPERSEDED, PREPARED, or DOCUMENTED — evidence pointer inline. No
fabricated PASS exists in this phase's results.*
