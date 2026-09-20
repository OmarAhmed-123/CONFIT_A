# CONFIT_A VTON — REMEDIATION FINAL REPORT, PHASE 6 (2026-09-19)

**Phase 6 mandate:** corrective verification + hardening. Not a restart.
No production-readiness declarations. No reinterpreting prior failures as
solved.

**Single release state: `BLOCKED`** (see §S). No GO transition was made
or attempted.

Format: every major statement is given as **CLAIM → EVIDENCE → STATUS**.
Statuses: VERIFIED / MEASURED / BLOCKED / LICENSE-GATED / UNKNOWN /
SUPERSEDED / DISCOVERED / NOT MEASURED.

---

## A. Repository state

**CLAIM A1.** Phase 6 was performed on the Phase-5 tree (sleeve gate
v2.3, N=2 controlled matrix, MCP audit) and is delivered as sleeve gate
**v2.4** + Phase 6 probes/results/human-calibration package, committed as
`49ef942` on branch `vton-evidence-reconciliation-2026-09-16` (author
OmarAhmed-123; main untouched; no push — no PAT).
→ EVIDENCE: git log; `backend/app/services/vton_sleeve_gate.py` (v2.4);
`evaluation/probes/p6_*.py`; `evaluation/results/p6_*/`;
`evaluation/human_calibration/`; suite 1322P/33S/0F at commit time.
→ STATUS: VERIFIED.

**CLAIM A2.** The sandbox was rebuilt between phases; the rebuild reset
site-packages **and destroyed local git history** (branch + commits
382237d/c5d6207/aa0649d absent; `git cat-file` fails; no remote in this
environment). Working-tree files (code, tests, docs, artifacts)
persisted. A second, lighter reset (site-packages only) occurred
mid-Phase-6-session and was restored the same turn
(`pip install -r backend/requirements.txt` + CPU torch stack).
→ EVIDENCE: git state inspection (this report §A1 note + Phase-6
commit message); restore commands re-ran green (suite 1322P/33S/0F).
→ STATUS: VERIFIED (environment incidents; see Appendix T).

**CLAIM A3.** Evaluation-only dependencies restored: torch 2.14.0+cpu,
torchvision 0.29.0+cpu, easyocr 1.7.1 (Apache-2.0, asserted by the
license suite). No **production** dependency was added: mediapipe was
already in `backend/requirements.txt`; its pose model is used
evaluation-only this phase (§E.6/P1-C).
→ STATUS: VERIFIED.

**Note on commit references (added by the 2026-09-19 compliance audit;
extended by the 2026-09-19 post-audit remediation).**
The `49ef942` SHA in §A1 is the Phase-6 commit **as made**
(HISTORICAL — it no longer exists as a Git object). Environment resets
#3–#6 (post-dating this report; documented in the Phase-7 report §A1,
in recommit messages, and in the compliance audit §2) each replaced
`.git` with a fresh clone. As of this remediation (2026-09-19 ~12:05
UTC) none of `49ef942`, `713694da`, `ec04a13`, `d886c77`, or `c472bfd`
exists in the repository (`git cat-file` fails for all; 0 dangling
objects), and reset #6 left the entire Phase 5/6/7 tree **UNCOMMITTED**
on a fresh clone of `main` (928e615). The post-audit remediation
re-established branch `vton-evidence-reconciliation-2026-09-16` with a
verbatim evidence-snapshot commit (tag
`evidence-snapshot-pre-remediation-2026-09-19`) followed by the
remediation commit of record — see the branch log and the audit's
"Current Git Ground Truth" section. A 7th reset (same day) repeated
the pattern: `.git` was re-cloned and the snapshot + remediation
commits (`d5f6ca8`, `1975778`) were lost; the reconciled tree was
re-committed as a single commit directly on `main` (audit §2
addendum). An 8th reset (same day) repeated the pattern again (the
commit of record `92f6513` was also lost); the reconciled tree was
re-committed, and — once the owner provided a GitHub PAT in-session —
the branch was pushed to origin as
`vton-evidence-reconciliation-2026-09-16` (remote `main` untouched;
audit §2 addendum). Exact historical identity of any
re-commit with `49ef942`/`713694da` is **UNVERIFIED** (original
objects unrecoverable); content preservation is supported by
file-level comparison. See
`docs/vton/COMPLIANCE_AUDIT_PHASE6_2026-09-19.md`.

## B. Low-contrast N=2 investigation

**CLAIM B1 (matrix).** All seven controlled compositions rendered live
(direct worker calls; exact L1 bytes fed as L2 input; `lower` slot):

| case | composition (input → target bottom) | L2 verify | pixel_change | color_shift | lower-region changed px (>8/255) | max diff |
|---|---|---|---|---|---|---|
| A-E | I (navy joggers) → navy wool trousers | False | 0.2915 | 0.00206 | 0.000% | 2–3/255 |
| B | I (navy joggers) → charcoal trousers | False | 0.2774 | 0.001972 | 0.000% | ≤3/255 |
| C | I (navy joggers) → beige chinos | True | 14.2964 | 0.098462 | 37.8% | ~210/255 |
| D | C (cream chinos) → navy wool trousers | True | 15.7698 | 0.107406 | 29.7% | ~210/255 |
| F | I (navy joggers) → navy patterned trousers | False | 0.2814 | 0.002005 | 0.000% | ≤3/255 |
| G | K (gray wide chinos) → navy slim (wool) trousers | True | 8.9892 | 0.061063 | 23.9% | ~210/255 |
| H | A (denim) → navy skirt | True | 2.9688 | 0.020183 | 8.9% (skirt rows 434–546) | ~210/255 |

→ EVIDENCE: `evaluation/results/p6_lowcontrast/` (results.json = hashes +
verify; raw L1/L2 PNGs; signals.json); agent visual confirmation of the
comparison sheet (A-E/B/F: unchanged navy joggers, drawstring visible;
C: beige chinos applied). Lower region = bottom 55% × center 60%.
→ STATUS: MEASURED (raw bytes + metrics + rendered images per case).

**CLAIM B2 (engine pattern, MEASURED).** The engine applies the lower
garment when the target differs in luminance family (C, D, G) or changes
silhouette (H), and **no-ops** when the target is in the same dark color
family as the existing bottom — including charcoal (perceptually distinct
from navy, still no-op). Product question carried forward, no decision
this phase: honest refusal (current) vs engine-side fix for dark-on-dark.
→ STATUS: MEASURED / product question OPEN (reported, §S).

## C. Engine-vs-verifier classification

**CLAIM C1.** Each case was classified from raw evidence, never from the
verify label alone (P0-A):

| case | classification | raw evidence |
|---|---|---|
| A-E | **ENGINE DID NOT APPLY** | L1↔L2 max diff 2–3/255 across the whole lower region; 0.000% changed px; visually identical joggers + drawstring |
| B | **ENGINE DID NOT APPLY** | same (≤3/255, 0.000%) |
| F | **ENGINE DID NOT APPLY** | same (≤3/255, 0.000%) |
| C, D, G, H | APPLIED | 8.9–37.8% changed px, max ~210/255; visually replaced garment |

No case required the UNKNOWN bucket; no `VTON_LAYER_NOT_APPLIED` was
auto-classified as engine non-application.
→ STATUS: MEASURED.

**CLAIM C2 (the Phase-5 navy-on-navy REFUSE).** pxchg 0.2915 / cs
0.00206 = L1≈L2 to ≤3/255 → a **correct honest rejection of a genuine
engine no-op, not a verifier limitation**.
→ STATUS: VERIFIED (C1).

**CLAIM C3 (orthogonal signals, P0-B).** Measured on the 7 cases:

| case | s1 lower changed-px | s2 Sobel edge-Δ | s3 texture (Bhattacharyya) | s4 k=3 Lab cluster Δ vs garment ref |
|---|---|---|---|---|
| A-E | 0.00000 | 0.237 | 0.0000 | +0.03 |
| B | 0.00000 | 0.229 | 0.0000 | −0.02 |
| C | 0.37824 | 2.753 | 0.0111 | +0.01 |
| D | 0.29707 | 2.598 | 0.0404 | −0.08 |
| F | 0.00000 | 0.232 | 0.0000 | −0.01 |
| G | 0.23852 | 2.648 | 0.0062 | −0.82 |
| H | 0.08943 | 1.322 | 0.0078 | −0.04 |

- s1 separates perfectly on the observed range (0.00000 vs ≥ 0.08943);
  s2 separates cleanly (0.229–0.237 vs ≥ 1.322).
- s3 (texture) and s4 (multi-cluster vs garment reference) are **NOT
  discriminative** (tiny magnitudes, mixed signs; s4 contaminated by
  background/feet in the region).
- s5 (localized embedding / DINOv2) = **ENVIRONMENT-BLOCKED** (pinned
  weights lost in the rebuild; HF proxy 401) — recorded, not skipped.
→ EVIDENCE: `evaluation/probes/p6_lowcontrast_signals.py`.
→ STATUS: MEASURED. **No signal adopted**: the pixel-diff family already
separates applied (≥2.97 pxchg / 0.0202 cs) from not-applied (≤0.2915 /
0.00206) with a ≥10× margin on the observed range; no threshold changed
(P0-C satisfied).

**CLAIM C4 (residual regime).** "Applied-but-invisible" (engine applied
the garment with per-pixel difference below the metric's sensitivity) was
**never produced** in the ~27 L2 renders measured across Phases 3/5/6 →
UNKNOWN, not claimed impossible. If it ever occurs, an orthogonal signal
(measured candidates: s2 edge-Δ) would be required; none is in production
today.
→ STATUS: UNKNOWN (documented).

**CLAIM C5 (negative controls, P0-D).** (a) A-E/B/F are natural
requested-but-not-applied controls → all REFUSED ✓ (same-color navy,
near-color charcoal, same-color patterned — three distinct no-application
controls). (b) (L1, L1) twin reads not-applied ✓. No metric was accepted
on positive improvement alone.
→ STATUS: VERIFIED.

## D. New lower-garment verification design

**CLAIM D1.** The lower-garment verifier is **unchanged by design** in
Phase 6: the calibrated changed-garment-color + changed-px gate
(`assert_layer_applied`, `tryon_service.py`). Evidence: the existing
signal separates applied from not-applied with ≥10× margin on every
observed case (C3); lowering `pixel_change` to "fix" 0.2915 would turn
genuine no-ops into false PASSes (P0-C) and was NOT done.
→ STATUS: VERIFIED (no change, for evidence-based reasons).

**CLAIM D2 (acceptance property, P0-E).** On the measured set the
verifier: rejects genuine non-application (A-E/B/F) ✓; accepts genuine
application (C/D/G/H) ✓; does not pass similar-color unchanged inputs
(A-E/B/F REFUSED) ✓; is generic (region + color-change rule; no fixture
IDs, no garment/person exceptions, no fake output) ✓. Where distinction
is unreliable (C3), the honest behavior is the explicit refusal it
already performs.
→ STATUS: VERIFIED on the measured set; residual regime UNKNOWN (C4).

## E. Sleeve v2.3 adversarial validation

**CLAIM E1 (attack protocol).** v2.3 was attacked with FRESH cases not
used to create the fix, before any replacement: 6 adversarial composites
on the `cal_02` base (input = white tank top — arms exposed in the input;
render = burgundy LS, gate PASS S1 0.4608 / S5 0.0019 / S6 0.2294),
covering: long→crop, long→elbow, partial mid-forearm gap (cuff present),
one-arm drop (elbow-length), full one-arm drop (shoulder→hand bare),
cuff/wrist-only gap. Agent-labeled — NOT human ground truth.
→ EVIDENCE: `evaluation/results/p6_sleeve_adversarial/` (contact sheet +
per-case gate traces).
→ STATUS: MEASURED.

**CLAIM E2 (NEW FAILURE CLASS FOUND — not hidden).** v2.3
**FALSE-PASSES a visibly incomplete long-sleeve render**: an asymmetric
sleeve drop on a person whose input already exposes the forearms.

| composite | defect (agent-verified) | v2.3 verdict | channel trace |
|---|---|---|---|
| adv_crop | sleeves end at bicep | REFUSE | S1 0.049/0.028 |
| adv_elbow | sleeves end at elbow | REFUSE | S1 0.049/0.028 |
| adv_midgap | upper sleeve + cuff, bare mid-forearm gap | REFUSE | S1 0.20/0.151 |
| **adv_onearm** | right sleeve to elbow, left intact | **PASS (FP)** | S1 max 0.4608; S5 max 0.0022 (dropped-arm `new_skin_outer` = **0.0** — skin NOT new vs tank-top input); S6 max 0.2422 (intact arm's cuff) |
| **adv_onearm_full** | right arm fully bare shoulder→hand | **PASS (FP)** | same trace; any-skin 0.2350 |
| adv_wristgap | cuff/wrist bare, both arms | REFUSE | S6 0.040/0.030 |

Mechanism (two structural defects, both measured): (1) **max-arm
aggregation** — every channel aggregated with max(); one intact arm
carries the verdict. (2) **S5 "new-skin" blindness** — S5 counts only
skin NEW vs the input; on an input that already exposes the arm, a
dropped sleeve shows the person's own unchanged skin → measured
`new_skin_outer` = exactly 0.0 on the dropped arm.
→ STATUS: MEASURED. Also measured live in the same session: a declared
long-sleeve garment rendered as a **short sleeve** (engine defect, person
I + white LS) → correctly REFUSED (coverage 0.095); the defective output
is instance-cached (subsequent identical calls returned identical bytes;
gate refuses every time) — documented, §T.6.

**CLAIM E3 (generic redesign, v2.4).** One channel added:
**`any_skin_outer`** — fraction of the outer forearm band that is
human-skin-colored in the output, **whether or not new vs the input**
(max-arm, threshold **0.15**). A verified long sleeve leaves no skin in
the outer band; an exposed forearm (old or new) fails it regardless of
the input's sleeve state. No fixture/garment/person exceptions.
→ EVIDENCE: `backend/app/services/vton_sleeve_gate.py`
(`ANATOMY_ANY_SKIN_REFUSE`, `any_skin_outer` in `forearm_anatomy_probes`,
verdict path). Threshold = midpoint of the measured gap (57 artifacts,
`evaluation/results/p6_sleeve_v24.json`): clean healthy max **0.1193**
(m1 — a borderline partial, 0.0936 of it NEW skin, already a 0.0064-margin
v2.3 coin-flip); drop readings **≥ 0.1237**; measured FPs **0.2350**
(1.57× margin). Alternatives measured and rejected (documented):
per-arm AND of S1/S6 (closes FPs but over-refuses 11/22 healthy rows);
τ=0.10 (over-refuses 2 borderline healthy rows for no extra safety).
→ STATUS: MEASURED + IMPLEMENTED.

**CLAIM E4 (verification).** v2.4 decision table:
- 50-row matrix: **21 P / 29 R — identical to v2.3** (zero new
  over-refusals; class-E + all synthetic drops still refused).
- 7 adversarial composites: base PASS; **all 6 drops REFUSED**
  (adv_onearm / adv_onearm_full now refused via any-skin 0.2350 ≥ 0.15;
  reason string names the mechanism).
- Suite: **1322P/33S/0F** (security included — re-run after the
  instrumentation change, P8).
- Regression-pinned: `test_v24_refuse_asymmetric_drop_on_exposed_arm_input`
  (hermetic) + `test_replay_p1b_asymmetric_drop_composite_refused`
  (real artifacts; both assert the any-skin mechanism).
- One pre-existing test was corrected, documented:
  `test_gate_pass_low_margin_positive` had modeled its "low-margin
  positive" as bare forearms — v2.4 correctly refuses that image (a
  one-arm render, the very P1-B class); the test now models the measured
  E-1 composition (background bleed into the band, both arms fully
  sleeved) so it pins its stated intent (the S1 0.35 boundary). No other
  assertion was changed; nothing was changed to force a pass.
→ STATUS: VERIFIED (suite green at commit time).

**CLAIM E5 (hard safety property).** Every measured dropped-sleeve
render — engine drops (class-E, L1 defect), synthetic drops (3),
short-declared-long (2), adversarial composites (6 incl. both
asymmetric FPs) — is REFUSED by v2.4 and regression-pinned. No KNOWN
dropped-sleeve render may PASS/ship: satisfied on the measured set.
→ STATUS: VERIFIED on the measured set (human barrier still open, §O).

**CLAIM E6 (P1-C anatomical validity — existing dependency).** MediaPipe
pose landmarks (elbow 13/14, wrist 15/16) are available through an
**existing** runtime dependency (`mediapipe>=1.0.0` in
`backend/requirements.txt`; Apache-2.0, asserted by the license suite)
with a 5.8MB float16 CPU model (Apache-2.0, gitignored). Measured on 9
renders/composites (`evaluation/results/p6_sleeve_p1c_localization.json`):
latency **30.6–32.7 ms/image** CPU; pose-shifted rows fixed (cal_04
fixed-band any-skin 0.163 → 0.017 landmark; m3_arms_raised arm located,
S1 0.488/0.548); wrist/hand-edge slivers reduced (m5 0.104→0.062,
m1 0.112→0.095); drop signals amplified (adv_onearm_full 0.240→0.566,
dropped-arm S1 0.000). Dependency review: license Apache-2.0 ✓, weights
5.8MB CPU hash-pinnable ✓, runtime (already a backend dependency) ✓,
privacy (offline, no egress) ✓, security (local file) ✓, performance
(~31 ms) ✓.
→ STATUS: MEASURED (evaluation-only this phase; NOT integrated). Fixed
band is the released state (v2.4); landmark bands = v2.5 candidate
requiring a full re-calibration pass. Fixed-band limitation stands
documented: pose-shifted wrists cause **over-refusal, not over-pass**.

## F. Sleeve confusion matrix

**CLAIM F1 (channel ablation, corrected truth mapping; truth ∈
present / dropped / dropped_synth / short_declared_long, all three
refuse-labels = should-REFUSE):**

| rule | TP | TN | FP | FN | TPR | FNR | TNR | FPR | precision | recall |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 alone | 22 | 7 | **2** | 19 | 0.537 | 0.463 | 0.778 | 0.222 | 0.917 | 0.537 |
| S1+S5 | 22 | 8 | **1** | 19 | 0.537 | 0.463 | 0.889 | 0.111 | 0.957 | 0.537 |
| S1+S6 | 22 | 8 | **1** | 19 | 0.537 | 0.463 | 0.889 | 0.111 | 0.957 | 0.537 |
| S1+S5+S6 (v2.3) | 22 | 9 | **0** | 19 | 0.537 | 0.463 | 1.0 | 0.0 | 1.0 | 0.537 |

- S1-alone FPs = {class-E `p4_j_arabic2_L1`, `p0c_synth_partial_krust_L1`}.
- **S5 and S6 are each individually necessary and complementary** (S5
  alone leaves the partial-drop FP; S6 alone leaves class-E).
- FN = 19 over-refusals **identical across all four rules** (S1-driven:
  thin margins / pose / band geometry); S5/S6 add zero new over-refusals
  (TP stable at 22).
- v2.3 margin notes: thinnest TP margins cal_01 S1 +0.0064, cal_05 S6
  +0.0985; thinnest drop rejections sc_crop_B S6 +0.050, sc_tank_C S6
  +0.0412, p4_j_arabic2 S5 +0.2078.

**CLAIM F2 (v2.4 on the extended 57-artifact set):** 0 FP, TNR 1.0, 22
healthy PASS (unchanged vs v2.3), 35 REFUSE — the two asymmetric FPs
close at 0.2350 (1.57×) and no healthy row flips (highest healthy
0.1193 < 0.15).
→ EVIDENCE: `evaluation/probes/p6_sleeve_channel_ablation.py` →
`evaluation/results/p6_sleeve_ablation.json` (first run invalid —
truth-mapping bug, fixed and re-run; file overwritten);
`evaluation/probes/p6_sleeve_v24_measure.py` →
`evaluation/results/p6_sleeve_v24.json`.
Boundary-row note (audit 2026-09-19; clarified by the post-audit
remediation 2026-09-19):
- **HISTORICAL CACHED MEASUREMENT (the ablation replay table above).**
  It replays Phase-5 cached S1 values; one present row (`m0_repro_L2`,
  S1 0.3511 cached) sits just above the 0.35 boundary → PASS in the
  replay, giving TP=22. This table is a historical replay of cached
  measurements, **not** a current measurement.
- **CURRENT LIVE MEASUREMENT (authoritative for current production).**
  The live production-gate re-execution (frozen v2.4, 56/56 rows,
  `evaluation/results/p7_v24_full_matrix.json`) re-measures
  `m0_repro_L2` at S1 0.3451 → REFUSE under the frozen 0.35 boundary;
  the frozen 50-row table is 21 PASS / 29 REFUSE — which is what §E4
  states and what the production gate currently returns. The current
  live frozen-gate matrix is **21 TP / 20 FN**.
- The 22-TP (historical cached replay) and 21-TP (current live)
  results are two different measurements of one boundary-straddling
  row; they are **not** simultaneously "the current" result. Every
  defect-safety number (FP=0, TN=9, TNR=1.0, precision 1.0) is
  identical in both, so the safety conclusions for the measured
  defect cohort are unchanged. No threshold was moved to reconcile
  the two runs; the boundary row is documented, not "fixed".
→ STATUS: MEASURED (agent labels = engineering calibration, NOT human
validation).

## G. Remaining sleeve limitations (documented, not hidden)

**CLAIM G1.** Every known sleeve-gate limitation is documented here
(and in §E6), not hidden; the 20/41 healthy over-refusals are
enumerated individually in
`evaluation/results/p7_v24_full_matrix.json`.

The limitations:

1. **Fixed band geometry** (no pose tracking): pose/size misalignment →
   over-refusal (measured: the 19-row FN set; m3/cal_04 examples).
   E6 shows the existing-dependency fix path (~31 ms); not integrated
   this phase.
2. **Residual unmeasured regime**: a very small sleeve gap above the
   wrist zone that keeps coverage ≥ 0.35, wrist fabric present, and
   any-skin < 0.15 (e.g. a ~10% band-height gap on a high-coverage base)
   was not measured — no such engine output was observed in ~27 renders.
   UNKNOWN, not claimed closed.
3. **Skin window**: the warmest hand-highlight tail (a* > 25) is not
   counted as skin — safe direction (hand, not forearm).
4. **Stochastic engine drops persist** at the engine level (measured
   short-sleeve render of a declared long sleeve, §E2); the gate's role
   is to refuse them, which is regression-pinned — the engine itself is
   not fixed.
5. **Agent labels ≠ human ground truth** — barrier §O.

→ EVIDENCE: the five items above;
`evaluation/results/p7_v24_full_matrix.json` (`valid_render_acceptance`:
41 present rows, 20 over-refused, each with `reason_kind`);
`evaluation/results/p7_v24_confusion_matrix.json` (TPR 0.5122
documented as the usability side of the same gate). No limitation was
removed or softened by the post-audit remediation.
→ STATUS: DOCUMENTED (presence of all five in the cited artifacts
VERIFIED by the 2026-09-19 audit + post-audit remediation).

## H. MCP Market reconciliation

**CLAIM H1.** The Phase-5 "WeShop NOT FOUND" findings are **SUPERSEDED BY
RECONCILIATION** (preserved verbatim in the audit doc, not deleted): all
5 known WeShop skills **plus** `ai-outfit-generator` are LIVE Agent
Skills at direct slug URLs (fetched live 2026-09-19):
`/tools/skills/{weshop-ai-virtual-try-on, ai-clothes-changer,
ai-bikini-virtual-try-on, bikini-virtual-try-on, weshop-ai-visual-studio,
ai-outfit-generator}`.
→ EVIDENCE: `docs/vton/MCP_MARKET_TRYON_AUDIT_2026-09-19.md`
(§C rows preserved + SUPERSEDED marker) + RECONCILIATION ADDENDUM
(appended this phase); official repos `github.com/weshopai/skills` (MIT)
+ `weshopai/weshop-skill-package` (official npm CLI).
→ STATUS: VERIFIED (direct fetches; no credentials requested).

**CLAIM H2 (why the old search missed — exact cause).** (1) Phase-5
scanned the MCP **Server** surface (`/search?q=`: top-20 only,
client-side Load More, no server-side pagination — `&page=N` 404); the
WeShop items are **Agent Skills** (`/tools/skills`), which have **no
server-side search at all**. (2) The e-commerce skills category page 1
was scanned, but the WeShop skills don't rank there (5,232 skills / 100
pages; also present in other categories). (3) **Direct slug URLs work**
— the skills were slug-discoverable all along; the search surface simply
never exposes them.
→ STATUS: VERIFIED (mechanics measured 2026-09-19).

**CLAIM H3.** "Exhaustive searched" withdrawn; the discovery claim is
**REACHABLE-SURFACE DISCOVERY** with documented limits (server surface =
top-20 only; skills surface = slug + deep pagination only; 48,857
servers / 358,558 skills). Existence = **DISCOVERED**, never PRODUCTION
CANDIDATE (P2-C). Nothing was installed (P2-C/P16).
→ STATUS: VERIFIED (wording corrected in the audit doc).

## I. MCP Server vs Agent Skill distinction

**CLAIM I1.** Three distinct surfaces documented and used: MCP Server
(`/search`, `/server/<slug>`), Agent Skills (`/tools/skills`,
`/tools/skills/categories/<slug>` — paginated category lists only, no
search), direct skill detail pages (`/tools/skills/<slug>` — render
fully). The Phase-5 miss was a surface conflation (Server search used to
look for Skills).
→ EVIDENCE: measured page mechanics + the addendum.
→ STATUS: VERIFIED.

## J. WeShop/fal/other candidate matrix

| candidate | access/creds | privacy understood | evaluated | state |
|---|---|---|---|---|
| WeShop AI Virtual Try-On (+5 sibling skills) | DISCOVERED; no authorized key; none requested | NO (undocumented) | NO | **BLOCKED (P3-B)** / DISCOVERED |
| fal-tryon (fal.ai) | needs FAL_KEY (none authorized) | partial | NO — stale listing (skill folder removed from upstream main) | RESEARCH (stale) |
| Vybe | public Replicate | n/a | engine 404 (dead) | REJECTED |
| HeyBeauty / TryOnfy / GenPark / ComfyUI wrappers | no legitimate access | unknown | NO | RESEARCH |
| Rembg-1 | public | n/a | weights license-gated | RESEARCH |
| CLO3D | commercial | unknown | NO | REJECTED |
| Face/identity candidates | weights license-gated | n/a | NO | LICENSE-GATED |

**CLAIM J1 (WeShop 6-facet audit, P2-B).** All 6 WeShop skills are thin
wrappers over the **WeShop OpenAPI** (`openapi.weshop.ai`; key sent only
to that domain — verified in the official package). Identity: official
repos, MIT skill code. Capability: VTO agent `virtualtryon` v1.0 —
`originalImage` (garment URL, required) + optional `fashionModelImage`
("will resemble this person" — **approximate identity, NOT preservation**)
+ optional `locationImage`; **single garment per run — NO native
multi-garment/layering**; `batchCount` 1–16; async polling
(Pending/Segmenting/Running/Success/Failed); engines weshopFlash /
weshopPro (aspectRatio) / bananaPro (1K–4K, identity unverified). Engine:
proprietary hosted, not inspectable. Commercial: vendor-tier pricing
(not publicly documented); **no public statements on uploaded/
generated-image retention, model-training usage, deletion, data
residency, or DPA** (weshop.ai/privacy = standard template). Security:
`WESHOP_API_KEY` env-only, egress only to openapi.weshop.ai, no command
execution in the skill, official-repo supply chain. Skill code license
(MIT) **≠ underlying model/API terms** (P3-C).
→ STATUS: DISCOVERED; EXTERNAL VTO INTEGRATION = BLOCKED (P3-B).
No real user images sent to discover policy; no credentials requested,
found, or used.

## K. Actual candidate evaluations

**CLAIM K1.** **No external candidate was evaluated this phase** — none
has legitimate access + authorized credentials + understood privacy
(P18). WeShop/fal require keys that were not authorized (none requested);
WeShop privacy is undocumented (K1/J1); fal-tryon is a stale listing;
Vybe's engine is dead. No marketing claim was used as evidence.
→ STATUS: VERIFIED (process) / NO EVALUATIONS PERFORMED (honest).

**CLAIM K2 (P3-A vs FASHN).** A fresh-dynamic-input comparison vs FASHN
is **BLOCKED (infrastructure)**: the Modal GPU worker workspace was
disabled mid-session (§T.1); all live render endpoints 404; no redeploy
credentials in the workspace. No partial FASHN-fresh results exist this
phase. FASHN baseline **HOLDS** (P4: no replacement; no candidate even
reaches SECONDARY EVALUATION ENGINE because none could be tested).
→ STATUS: BLOCKED / VERIFIED (baseline holds by default of evidence).

## L. Legal/privacy/security status

**CLAIM L1 (licenses).** Re-verified by the license suite (green at
commit): FASHN Apache-2.0 (fork 7c0f10af); mediapipe Apache-2.0; EasyOCR
Apache-2.0 (eval-only); DINOv2/SAM2 Apache-2.0 (eval-only; DINOv2
weights currently unavailable, §T.5); UniFit CC BY-NC-SA veto;
MV-Fashion NC; AdaFace MS1MV2 unresolved; IDM/OOT/CatVTON
CC-BY-NC-SA; FastFit NOASSERTION-NC. No NC/unclear-license code or
weights in production; no license-restricted weights committed
(gitignored + git-ls-files scan).
→ STATUS: VERIFIED.

**CLAIM L2 (privacy).** No user images left this environment except to
the local/eval FASHN worker (authorized evaluation path); no real user
images sent to any vendor; no credentials stored in the workspace
(`.eval_env`/`.eval_urls` gitignored). WeShop privacy gap → BLOCKED (J1).
→ STATUS: VERIFIED (process) / BLOCKED (external).

**CLAIM L3 (security, P8).** Security suite re-run after the v2.4
instrumentation change: full backend + evaluation **1326P/29S/0F**
(incl. `test_group1_security_hardening.py`,
`test_deployment_security_headers.py`,
`test_measurement_session_security.py`;
`evaluation/tests/test_licenses_and_secrets.py` 6P). Persisted records = hashes /
metadata / metrics / status only (no base64 payloads, no raw user
images, no worker tokens — verified by `test_licenses_and_secrets.py`);
the human-calibration manifest is paths + sha256 only.
→ STATUS: VERIFIED.

## M. Fresh local validation

**CLAIM M1.** Fresh local dynamic validation = **BLOCKED
(infrastructure)** — same Modal workspace disablement as K2. Delivered
and re-runnable: NEW runtime inputs (`evaluation/dyninputs_p5/`,
generated 2026-09-19, never used before): hijab/modest (p5l_hijab),
Arabic-text (p5l_arabic), deep-skin (p5l_deep), fair-skin (p5l_fair);
case design L1–L6 (modest tunic LS, one-piece dress, Arabic-text tee
[EasyOCR], rust LS, white LS, patterned LS), N=2 each, in
`evaluation/probes/p6_p5_dynamic_fresh.py`. The probe executed and
recorded the deterministic 404 evidence per render
(`evaluation/results/p5_dynamic_fresh/results.json`,
`VTON_WORKSPACE_DISABLED`; re-checked 2026-09-19 ~07:45 UTC, still
disabled).
→ STATUS: BLOCKED (ready to re-run; no local metric claimed).

## N. Fresh global validation

**CLAIM N1.** Fresh global dynamic validation = **BLOCKED (same
infrastructure)**. Delivered and re-runnable: NEW runtime inputs
p5g_plus (body type), p5g_darkbg (difficult lighting/dark bg),
p5g_tank (exposed arms — the live old-skin condition); cases G1–G5
(black LS, dark-on-dark, text tee [EasyOCR], L1 tee → L2 logo blazer
inner+outer chain, tee+joggers in ONE call = true multi-garment), N=2
each. EasyOCR restored and verified single-language ("CONFIT" detected
on the text tee); dual-language load OOMs the 2 GB sandbox —
subprocess single-language readers with error capture are in place
(§T.3). Identity on P5 renders will be reported NOT MEASURED (not
proxied) — §P.
→ STATUS: BLOCKED (ready to re-run; no global metric claimed).

## O. Human calibration

**CLAIM O1.** `HUMAN CALIBRATION = BLOCKED`: no ≥3 real independent
raters available; no VLM/agent relabeling performed or permitted.
→ STATUS: BLOCKED (barrier open).

**CLAIM O2 (package prepared, executable as-is).**
`evaluation/human_calibration/`: `RUBRIC.md` (Type-S sleeve integrity
FULL/PARTIAL/ABSENT/UNSURE + Type-L lower application
APPLIED/NOT_APPLIED/PARTIAL/UNSURE; low-contrast honesty rule; no AI
assistance), `RUN_INSTRUCTIONS.md` (≥3 independent raters, blinding,
fixed-seed display order, core set 21 items vs full set 63, Fleiss'
kappa + consensus adjudication, gate-vs-human disagreements = defect
reports, closure criteria), `ARTIFACT_MANIFEST.json` (63 items = 56
sleeve artifacts incl. all 6 adversarial composites + 7 low-contrast
cases; paths + sha256 + agent labels + v2.3/v2.4 verdicts; P8: no image
payloads), `LABELING_SHEET_rater{1,2,3}.csv`, `UNBLINDING_SHEET.csv`
(not shown to raters), `build_manifest.py` (reproducible).
→ STATUS: PREPARED (barrier closure requires raters, per the package's
closure criteria).

**Scope note (post-audit remediation 2026-09-19).** The manifest was
extended in Phase 7 to 73 items = the Phase-6 core 63 (56 sleeve + 7
low-contrast) + 10 Phase-7 P1-D base renders. The Phase-6 core is the
authoritative Phase-6 set: **63/63 paths resolve and 189/189 SHA-256
values reproduce** (re-verified 2026-09-19). The 10 Phase-7 items are
tracked separately in the manifest (top-level `phase_scope` block;
per-item `phase` field): their source images were lost in environment
reset #5, so each is
`HASH RECORDED, SOURCE ARTIFACT CURRENTLY UNVERIFIABLE` — the rater
procedure's ITEM_ERROR rule covers them. The 10 missing Phase-7 images
are not presented as verified and do not contaminate the Phase-6-core
completeness claim. The directory holds **9 files** on disk (README,
RUBRIC, RUN_INSTRUCTIONS, ARTIFACT_MANIFEST.json, 3 labeling sheets,
UNBLINDING_SHEET.csv, build_manifest.py). No human raters have
performed labeling: **PACKAGE PREPARED; HUMAN CALIBRATION = BLOCKED**
(the two facts are distinct and both hold).

## P. Production identity licensing

**CLAIM P1.** `PRODUCTION IDENTITY = LICENSE-GATED` (unchanged):
ArcFace/WebFace600K evaluation-only, rights unresolved; DINOv2
(Apache-2.0) weights currently unavailable in this environment (lost in
rebuild; HF proxy 401). **No identity metric is claimed anywhere in this
phase** — P5 identity will be reported NOT MEASURED, not proxied.
→ STATUS: LICENSE-GATED.

## Q. Regression suite

**CLAIM Q1.** Full suite: **1326 passed / 29 skipped / 0 failed**
(232.59 s, post-audit remediation re-run 2026-09-19; the Phase-6
commit-time run read 1322P/33S/0F — HISTORICAL). Sleeve-specific
(fresh raw re-run 2026-09-19): `test_sleeve_gate_regression.py` =
**42 passed / 1 skipped** (43 tests collected; the skip is the
gitignored synthetic partial-drop replay artifact — skip by design;
includes both v2.4 pinning tests); `test_sleeve_v23_matrix.py` =
**52 passed** (v2.4 decision table on the 50-row matrix + P1-B
composites refused); `evaluation/tests/test_licenses_and_secrets.py` =
**6 passed**. All 29 full-suite skips explained in the audit §7.
→ EVIDENCE: raw pytest output of the post-audit remediation
(2026-09-19, after the documented environment restore).
→ STATUS: VERIFIED (fresh raw re-run; the one corrected line is
disclosed below).

**Correction note (post-audit remediation 2026-09-19).** The sleeve-
regression count originally recorded here (44P/1S) does not reproduce:
the current raw output is **42P/1S** (43 tests collected). No test was
removed, added, or modified by this remediation; the earlier figure is
superseded and disclosed, not hidden.

**CLAIM Q2.** No test was changed to force a pass — the single test
edit is documented in E4 with its rationale (the old version asserted a
one-arm render should PASS — the exact v2.3 defect).
→ STATUS: VERIFIED (audit trail in E4).

## R. Claim audit

**CLAIM R1.** Banned words appear only in negated context; no
"production-ready/solved/robust/best/reliable" claim is made without
evidence. No threshold was moved to change PASS/REFUSE counts: the only
threshold added (`ANATOMY_ANY_SKIN_REFUSE = 0.15`) is a NEW channel
calibrated from the measured gap (E3), and the 50-row table is
bit-identical to v2.3. No fixture/garment/person exceptions; no
retry-until-success; no cached/unrelated images; no silent fallback; no
failure-label swaps without raw bytes.
→ STATUS: VERIFIED (self-audit against the do-not-game list).

**CLAIM R2.** The Phase-5 "FPR-0" claim for the sleeve gate is
**INVALID as stated** (superseded): v2.3 had a measured FP (E2). The
v2.4 statement is scoped precisely: **0 FPs on the 57-artifact measured
set** — a measured claim, not a universal guarantee.
→ STATUS: SUPERSEDED (v2.3 claim) / MEASURED (v2.4 scope).

## S. Final release decision

**CLAIM S1.** The overall release state is exactly one:
**`RELEASE = BLOCKED`** — no GO transition was made or attempted, and
no competing overall state (READY / STABLE / CONDITIONAL-GO) is
asserted anywhere in this report. Individual defect families are
closed at their measured scope (barriers 1–2) without changing the
overall state.

Barrier table:

| # | barrier | state | evidence |
|---|---|---|---|
| 1 | Sleeve — no known dropped-sleeve render may PASS/ship | **CLOSED at measurement level** | E4/E5: every measured drop (engine/synthetic/composite) refused + regression-pinned; residuals documented (G); human calibration still open under barrier 3 |
| 2 | N=2 — evidence-backed low-contrast application verifier | **CLOSED at behavior level** | §B/C: gate separates applied (≥2.97) from not-applied (≤0.29) on raw bytes; honest refusal of engine no-op verified; no threshold changed; "applied-but-invisible" regime = UNKNOWN, documented (C4) |
| 3 | Human calibration (≥3 independent raters) | **BLOCKED** (package prepared, O2) | §O |
| 4 | Production identity licensing | **LICENSE-GATED** | §P |
| 5 | Fresh dynamic local + global batch | **BLOCKED (infrastructure)** | §M/N (worker workspace disabled; re-run ready) |
| 6 | MCP — no third-party VTO without technical + privacy + licensing + security approval | **BLOCKED** | §J/K (WeShop privacy undocumented; no other candidate accessible) |

Product question carried forward (no decision this phase): the engine's
dark-on-dark lower-garment no-op (B2) — honest refusal (current) vs
engine-side fix; classified in the compliance audit §12 as a residual
engineering/product limitation (the refusal contract is settled and
enforced), not a separate release barrier.

→ EVIDENCE: the barrier table above (barrier evidence pointers §E4/§E5,
§B/§C, §O, §P, §M/§N, §J/§K); §R1/§R2 claim audit; the Phase-7 report
§U (consistent single state).
→ STATUS: **BLOCKED** (exactly one overall release state).

---

## Appendix T — Environment & infrastructure incidents (this phase)

1. **T.1 Modal GPU worker workspace disabled mid-session** — all eval
   URLs + 3 older eval deployments → `404 workspace
   ac-io3nXB7Q2nuaHHl8mVkeLH is disabled`; legacy production URL →
   `invalid function call` (function removed). Worker served live
   renders successfully earlier the same day (P0 matrix, P1 base
   render); re-checked 2026-09-19 ~07:45 UTC — still disabled. No Modal
   credentials in the workspace to re-enable/redeploy. **Blocks P5/P3-A
   live rendering.**
2. **T.2 Site-packages resets** — twice: at the phase boundary (git
   refs also destroyed; A2) and mid-session (restored with
   `pip install -r backend/requirements.txt` + CPU torch/torchvision +
   easyocr 1.7.1; suite re-ran green).
3. **T.3 EasyOCR memory limit** — 2 GB sandbox: dual-language Reader
   SIGKILL (137); single-language subprocess readers fit (verified
   "CONFIT" on the English text tee).
4. **T.4 Git history destroyed by the rebuild** — branch
   `vton-evidence-reconciliation-2026-09-16` + commits 382237d/c5d6207/
   aa0649d absent (objects gone; no remote in this environment). Working
   tree persisted. Branch recreated; Phase 6 committed there (`49ef942`);
   main untouched; no push (no PAT).
5. **T.5 DINOv2 weights lost** — `evaluation/weights_local/dino/` empty
   after rebuild (gitignored by design); HF proxy 401 → re-download
   impossible. P0-B s5 channel ENVIRONMENT-BLOCKED, recorded, not
   skipped.
6. **T.6 Instance-cache persistence of a defective render** — the
   short-sleeve render of a declared long-sleeve garment (E2) returned
   bit-identically on subsequent identical calls (same sha); the gate
   refuses it every time. Documented; worker internals closed.

## Appendix U — Artifact index (paths; hashes in the JSONs, P8)

- P0: `evaluation/probes/p6_lowcontrast_{matrix,signals}.py`,
  `evaluation/results/p6_lowcontrast/{results.json,signals.json,raw_*.png}`
- P1-A: `evaluation/probes/p6_sleeve_channel_ablation.py`,
  `evaluation/results/p6_sleeve_ablation.json`
- P1-B/v2.4: `evaluation/probes/p6_sleeve_{adversarial,v24_measure}.py`,
  `evaluation/results/p6_sleeve_{adversarial/,v24.json}`,
  `backend/app/services/vton_sleeve_gate.py`,
  `backend/tests/test_sleeve_gate_regression.py`
- P1-C: `evaluation/probes/p6_sleeve_p1c_localization.py`,
  `evaluation/results/p6_sleeve_p1c_localization.json`,
  weights (gitignored) `evaluation/weights_local/mediapipe/`
- P5: `evaluation/probes/p6_p5_dynamic_fresh.py`,
  `evaluation/dyninputs_p5/`, `evaluation/results/p5_dynamic_fresh/`
- P6: `evaluation/human_calibration/` (README, RUBRIC,
  RUN_INSTRUCTIONS, ARTIFACT_MANIFEST.json, 3 labeling sheets,
  unblinding sheet, build_manifest.py)
- MCP: `docs/vton/MCP_MARKET_TRYON_AUDIT_2026-09-19.md` (+ RECONCILIATION
  ADDENDUM)
- Prior: `docs/vton/REMEDIATION_FINAL_REPORT_PART5_2026-09-19.md`

## Appendix V — Re-run procedures

- **P5 (after worker restore):** `python3
  evaluation/probes/p6_p5_dynamic_fresh.py` (deterministic case list;
  N=2 per case; OCR single-language subprocesses).
- **Sleeve matrix replay:** `python3 -m pytest
  backend/tests/test_sleeve_gate_regression.py
  evaluation/tests/test_sleeve_v23_matrix.py -q`
- **v2.4 measurement:** `python3 evaluation/probes/p6_sleeve_v24_measure.py`
- **P1-C localization:** `python3
  evaluation/probes/p6_sleeve_p1c_localization.py`
- **Human calibration (once ≥3 raters exist):** follow
  `evaluation/human_calibration/RUN_INSTRUCTIONS.md`.

---
*Every status above is MEASURED (raw bytes/metrics on disk at the cited
paths), VERIFIED (re-executed this session), BLOCKED, LICENSE-GATED,
UNKNOWN, SUPERSEDED, or PREPARED — with the evidence pointer inline. No
claim was made without its evidence; no fabricated PASS exists in this
phase's results. What was fixed (v2.4 any-skin channel; MCP
reconciliation; P5 tooling; human package), what is engine limitation
(dark-on-dark no-op; stochastic drops; short-sleeve render), what is
verifier limitation (fixed bands; unobservable low-diff regime UNKNOWN),
what is worker/runtime limitation (Modal workspace disabled; 2 GB RAM;
lost weights), what was found vs listed vs tested (found: 6 WeShop
skills + outfit generator; tested: none — none testable under the
access/privacy constraints), what was integrated (v2.4 gate,
regression-pinned), what was rejected (Vybe, CLO3D, face candidates —
with reasons, §J), and what remains externally blocked (WeShop privacy,
Modal workspace, raters, identity rights) — is stated in the sections
above, without roundabout language.*
