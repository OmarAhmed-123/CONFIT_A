# CONFIT_A — Phase 6 Post-Audit Reconciliation & Final Truthful Closure (2026-09-19)

**Type:** post-audit reconciliation and truthfulness pass over the actual
workspace (evidence-only; not an implementation cycle).
**Audited:** `docs/vton/REMEDIATION_FINAL_REPORT_PHASE6_2026-09-19.md`
(A–S + Appendices T/U/V), `docs/vton/REMEDIATION_FINAL_REPORT_PHASE7_2026-09-19.md`,
`docs/vton/MCP_MARKET_TRYON_AUDIT_2026-09-19.md`, and every cited artifact
against the files and measurements that actually exist right now.
**Governing principle:** the repository, committed files, reproducible
artifacts, raw test output, and externally observable runtime evidence are
authoritative; narrative claims are not evidence by themselves.
**Supersedes:** the 2026-09-19 compliance audit of the same name
(reported `COMPLIANT — PHASE 6 CLOSED AS BLOCKED` at commit `c472bfd`).
That audit's conclusion was NOT treated as automatically authoritative:
this pass independently re-verified every load-bearing fact, found that
the Git state recorded there was itself obsolete (a further environment
reset), and corrected the documentation to match reality.

**Hard rules applied (unchanged from the mandate):** no VTON redesign; no
threshold change; no new provider; no FASHN change; no N=2 verifier
weakening; no fabricated artifacts; no recreation of lost AI-generated
images as the originals; no silent conversion of historical measurements
into current ones; no claim that human calibration happened (it did not);
no claim that a Git object exists when it does not; absence of evidence ≠
PASS.

---

## 1. Executive Result

`COMPLIANT — PHASE 6 CLOSED AS BLOCKED`

After the corrections listed in §10, every Phase-6 claim in the report
matches the files and measurements that actually exist; the A–S
structure is intact with exactly 19 sections whose status arithmetic
reconciles (15 VERIFIED + 3 BLOCKED + 1 LICENSE-GATED = 19, §3); the
human-calibration accounting is split into the four distinct facts the
mandate requires (§4); the 22-TP (historical cached replay) and 21-TP
(current live) results are explicitly separated (§6); the release state
is exactly one: `RELEASE = BLOCKED` (§14).

This pass found and corrected genuine documentation gaps (the pre-pass
state was therefore not yet fully truthful): a 6th environment reset that
destroyed the Git state the previous audit had recorded, a package file
count stated as 7 (actual: 9), a 63-vs-73 manifest scope conflation, a
stale test count (44P/1S → current raw 42P/1S), and two sections
(§G/§S of the Phase-6 report) lacking the literal CLAIM → EVIDENCE →
STATUS form. All corrections are listed in §10 with their evidence. None
of them changed a threshold, a test, a verdict, or the release state.

## 2. Current Git Ground Truth

Independently verified at remediation start (2026-09-19 ~12:05 UTC),
before any edit:

| item | result |
|---|---|
| branch at start | `main` (fresh clone; reconciliation branch absent) |
| HEAD at start | `928e615110640c00df0db80ef1a93f92ff353870` = `main` (verified `git rev-parse main`) |
| parent of HEAD | `8f23cb0` (upstream history intact) |
| tree at start | **22 dirty entries** (10 modified + 12 untracked paths) — the ENTIRE Phase 5/6/7 body of work was **UNCOMMITTED** |
| `c472bfd` (previous audit commit) | **ABSENT** — `git cat-file` fails |
| `d886c77` (previous pre-audit recommit) | **ABSENT** |
| `ec04a13` (Phase-7 recommit) | **ABSENT** |
| `713694da` (Phase-6 recommit) | **ABSENT** |
| `49ef942` (Phase-6 as-made commit) | **ABSENT** |
| reflog | single entry: `928e615 HEAD@{0}: clone: from https://github.com/OmarAhmed-123/CONFIT_A.git` |
| `git fsck --full --no-reflogs --unreachable` | **0 unreachable objects** — nothing recoverable |
| reachable refs at start | local `main` only; remote-tracking `origin/*` refs present (fresh clone); no local PAT/credentials |

**Finding (new incident, 6th reset).** Between the previous audit
(commit `c472bfd`) and this remediation, the environment reset `.git`
**again** (6th occurrence): `.git` was replaced by a fresh clone of
`main` (928e615). The reconciliation branch and ALL its commits
(`c472bfd`, `d886c77`, and everything before them) were lost; the
working tree survived intact (all Phase-5/6/7 files present —
inventory in §13), but **uncommitted**. The reset also wiped
site-packages (7th environment incident); the documented restore
procedure was applied (`pip install -r backend/requirements.txt` +
torch 2.14.0+cpu + torchvision 0.29.0+cpu + easyocr 1.7.1) and every
suite re-ran with identical results (§7). This irreproducibility is
recorded as an incident, not treated as harmless.

**Protected snapshot and remediation (this pass, no destructive action):**

1. Branch `vton-evidence-reconciliation-2026-09-16` re-created from
   `main` 928e615 (no reset, no `.git` replacement, no history rewrite).
2. **Evidence-snapshot commit `d5f6ca8`** (tag
   `evidence-snapshot-pre-remediation-2026-09-19`): the entire
   pre-remediation tree committed verbatim — 232 files changed,
   +25,975/−79. Cross-check: previous `d886c77` was 231 files,
   +25,598/−79; the delta is exactly the previous audit's own
   additions (audit report + probe fix + regenerated ablation JSON +
   two disclosure notes) plus the fresh P5 re-check line (§5).
3. **Remediation commit of record:** the single commit on this branch
   immediately after `d5f6ca8` (see `git log`); it contains exactly the
   files listed in the appendix "Files changed by the remediation
   commit of record" at the end of this report. This report is part of
   it.
4. `main` remains **928e615, untouched** (verified after the commit).
5. Push/PR: **BLOCKED — external Git operation unavailable** at the time
   of this report's original writing (no PAT in the workspace; not
   attempted, not claimed). **SUPERSEDED:** a GitHub PAT was provided
   in-session on 2026-09-19 by the repository owner, and the
   reconciliation branch was pushed to origin (see the §2 addendum).
   Remote `main` remains 928e615, untouched; no merge to main.

**Identity wording (unchanged, required):** for every re-commit chain,
**CONTENT PRESERVATION SUPPORTED, EXACT HISTORICAL IDENTITY UNVERIFIED**
(original objects `49ef942`/`713694da`/`ec04a13`/`d886c77`/`c472bfd`
unrecoverable; preservation supported by file-level verification and
diffstat continuity).

**Addendum (second verification pass, 2026-09-19 ~13:10 UTC).** A 7th
environment reset occurred after the remediation commit of record:
`.git` was again replaced by a fresh clone of `main` (928e615; reflog
single `clone:` entry; `git fsck` 0 unreachable objects), and the
snapshot commit (`d5f6ca8`) and remediation commit (`1975778`) were
lost. The working tree survived intact — already containing the fully
reconciled documentation — so no documentation re-work was required;
only a fresh independent re-verification was performed (raw re-runs:
1326P/29S/0F; 42P/1S; 52P; 6P; ablation JSON byte-identical; 189/189
SHA reproduction on the Phase-6 core; P5 corroboration ping 13:15 UTC
→ both URLs 404 workspace-disabled). site-packages had been wiped
again (8th environment incident) and was restored by the documented
procedure before the re-runs. The reconciliation was then re-committed
as a **single** focused commit on branch
`vton-evidence-reconciliation-2026-09-16` directly on `main` 928e615
(snapshot and remediation merged, because the tree was already in its
reconciled state at pass start). The identity wording above applies
unchanged to `d5f6ca8`/`1975778` as well.

**Addendum (third verification pass, 2026-09-19 ~13:50 UTC).** An 8th
environment reset occurred after the previous commit (`92f6513` was
destroyed along with all others; `.git` re-cloned at `main` 928e615;
reflog single `clone:` entry; `fsck` 0 unreachable). The working tree
survived intact, still in its reconciled state. site-packages was
wiped again (9th environment incident) and restored by the documented
procedure. All evidence was independently re-verified with fresh raw
output: 1326P/29S/0F (219.03 s); 42P/1S; 52P; 6P; ablation JSON
byte-identical; 189/189 SHA reproduction; 30/30 p7d source files still
missing; v2.4 constants unchanged; P5 ping 13:56 UTC → both URLs 404
workspace-disabled (`BLOCKED-INFRA` holds). The reconciliation was
re-committed as the single focused commit of record on branch
`vton-evidence-reconciliation-2026-09-16` directly on `main` 928e615.
**Git operation unblocked:** the owner provided a GitHub PAT in-session
(2026-09-19) and confirmed the required commit identity
(`OmarAhmed-123` / `omarsafealden@gmail.com` — used for all commits).
The branch was then pushed to origin as
`vton-evidence-reconciliation-2026-09-16` (new remote branch; remote
`main` verified still 928e615; no merge to main; the PAT itself was
never written to `.git/config` or any file). This makes the reconciled
evidence externally verifiable: `git ls-remote origin
vton-evidence-reconciliation-2026-09-16` resolves to the commit of
record. Modal credentials were also provided in-session; per the task
scope (no VTON investigation restart, no re-runs of external work),
no workspace re-enable or P5 re-run was performed — P5 remains
`BLOCKED-INFRA` on the observed runtime evidence.

## 3. Exact A–S Matrix (19 rows)

Statuses per mandate: VERIFIED / IMPLEMENTED / TESTED / BLOCKED / NO-GO /
GAP / UNVERIFIED / NOT APPLICABLE. One status per section. All evidence
re-verified this pass (2026-09-19).

| Section | Requirement (abridged) | Evidence (re-verified this pass) | Status |
|---|---|---|---|
| A. Repository state | exact commit/branch/env facts | git state above; §A1 + commit-reference note (extended this pass to cover reset #6); content intact file-by-file | VERIFIED |
| B. Low-contrast N=2 investigation | 7-case matrix, exact bytes + metrics | `p6_lowcontrast/results.json` + 14 raw PNGs on disk; all 7 metrics (pxchg/cs/sha) match report §B1 | VERIFIED |
| C. Engine-vs-verifier classification | ENGINE-DID-NOT-APPLY / APPLIED / UNKNOWN from raw evidence | A-E/B/F = not-applied (max diff 2–3/255, 0.000% changed px); C/D/G/H = applied (2.97–15.77 pxchg); negative twin (L1,L1) per row; DINOv2 ENVIRONMENT-BLOCKED recorded | VERIFIED |
| D. New lower-garment verification design | generic verifier; no blind threshold change | `tryon_service.py` L759 `pixel_change < 0.5` unchanged; no new signal adopted | VERIFIED |
| E. Sleeve v2.3 adversarial validation | fresh cases; FP class found; generic redesign | `p6_sleeve_adversarial/` (10 PNGs + results.json); asymmetric FP measured (any-skin 0.2350); all 6 composites REFUSED under frozen v2.4 (56/56 live matrix) | VERIFIED |
| F. Sleeve confusion matrix | ablation + authoritative matrix | fixed probe re-run live: no crash, output written, on-disk JSON byte-identical to fresh run; **22 TP = HISTORICAL CACHED replay; 21 TP = CURRENT LIVE (authoritative)**; defect safety identical (FP 0, TN 9, TNR 1.0) | VERIFIED |
| G. Remaining sleeve limitations | documented, not hidden | §G now literal CLAIM G1 → EVIDENCE → STATUS (this pass); 5 limitations present; 20/41 over-refusals enumerated in `p7_v24_full_matrix.json` | VERIFIED |
| H. MCP Market reconciliation | old findings preserved + SUPERSEDED | `MCP_MARKET_TRYON_AUDIT_2026-09-19.md`: NOT-FOUND×8 preserved, 3× SUPERSEDED markers, 8 skills verified LIVE at discovery (Phase 6 + 7) | VERIFIED |
| I. MCP Server vs Agent Skill distinction | surfaces separated | server/skill/detail-page mechanics measured; Phase-7 four-layer table (server/skill/API/engine) | VERIFIED |
| J. WeShop/fal/other candidate matrix | 6-facet audit; DISCOVERED only | matrix consistent; WeShop = DISCOVERED; fal-tryon RESEARCH (stale); Vybe REJECTED (engine 404); no marketing used as evidence | VERIFIED |
| K. Actual candidate evaluations | none without access/terms/creds/privacy | no external candidate was evaluated; stated honestly | VERIFIED |
| L. Legal/privacy/security status | license suite + P8 hygiene | 6P fresh raw run (§7); 0 tracked files under results/weights; no base64 payloads in tracked JSONs; secret scan clean. **Clean scan ≠ privacy compliance** (classified separately) | VERIFIED |
| M. Fresh local validation | new runtime inputs + re-runnable probe | probe + `dyninputs_p5/` (7 persons) + `p5_dynamic_fresh/results.json` (fresh 404 re-check 2026-09-19 12:11 UTC, §5); gate fingerprint recorded at run time | BLOCKED (infrastructure) |
| N. Fresh global validation | same, global design | same probe, cases G1–G5 | BLOCKED (infrastructure) |
| O. Human calibration | package prepared; status not downgraded | 9 files on disk (§4); Phase-6 core 63/63 + 189/189 SHA reproducible (fresh); 10 Phase-7 items = HASH RECORDED, SOURCE ARTIFACT CURRENTLY UNVERIFIABLE; zero human labels (sheets are empty templates); report status BLOCKED not downgraded | BLOCKED (calibration) / PREPARED (package) |
| P. Production identity licensing | LICENSE-GATED, no promotion | ArcFace/WebFace600K eval-only; no rights evidence anywhere; no identity metric claimed | LICENSE-GATED |
| Q. Regression suite | fresh counts | fresh raw output this pass (§7): 1326P/29S/0F; 42P/1S; 52P; 6P — all match; stale 44P/1S line corrected in §Q1 with disclosure | VERIFIED |
| R. Claim audit | no banned words; no gaming | sweeps this pass (§18 of mandate): banned words only in negated/banned-list context; only threshold added (S5b 0.15) has flip-table evidence + zero baseline flips; no fixture/person/garment exceptions in code | VERIFIED |
| S. Final release decision | exactly one state | §S now literal CLAIM S1 → EVIDENCE → STATUS (this pass); `RELEASE = BLOCKED`, single state, barrier table intact | VERIFIED |

**A–S arithmetic: 15 VERIFIED + 3 BLOCKED (M, N, O) + 1 LICENSE-GATED
(P) = 19.** The summary arithmetic reconciles exactly. (The "18 VERIFIED
+ 2 BLOCKED + 1 LICENSE-GATED" line quoted in the remediation mandate
does not appear anywhere in the report — sweep-verified — and would not
reconcile with 19 sections; the strict table above supersedes any such
compressed summary.)

**Appendices (separate table, not mixed into the A–S count):**

| Appendix | Requirement | Evidence | Status |
|---|---|---|---|
| T. Environment incidents | incidents documented, not hidden | T.1–T.6 present; reset #5 + `p7_adversarial` loss recorded by the previous audit; reset #6 + site-packages wipe (7th incident) recorded in §2 of this report | VERIFIED |
| U. Artifact index | paths resolve | 13/13 expanded paths exist (checked this pass) | VERIFIED |
| V. Re-run procedures | procedures exist and run | all referenced probes exist; local ones executed green this pass (§7) | VERIFIED |

**Appendix arithmetic: 3 VERIFIED = 3.**

## 4. Human Calibration Accounting

Four distinct facts, kept separate (the mandate prohibits merging them):

**4.1 Package files — actual count on disk: 9** (counted directly from
`evaluation/human_calibration/` this pass):
`README.md`, `RUBRIC.md`, `RUN_INSTRUCTIONS.md`,
`ARTIFACT_MANIFEST.json`, `LABELING_SHEET_rater1.csv`,
`LABELING_SHEET_rater2.csv`, `LABELING_SHEET_rater3.csv`,
`UNBLINDING_SHEET.csv`, `build_manifest.py`.
(The previous audit's "Files present (7)" was a miscount — corrected in
§10.2. The 3 labeling sheets are **empty templates** — 73 rows each,
all label cells blank — and are NOT evidence that "three raters exist.")

**4.2 Phase-6 core (authoritative Phase-6 set): 63 items**
(56 sleeve incl. all 6 adversarial composites + 7 low-contrast).
Re-verified this pass: **63/63 paths resolve; 189/189 SHA-256 values
reproduce** (render + input + garment_ref per item). The 6 composites
are present and refused under v2.4.

**4.3 Phase-7 extension: 10 items** (`S_p7_p7d_*` base renders added in
Phase 7; current manifest n=73 = 66 sleeve + 7 low-contrast). All **30
source files of the 10 items are MISSING** (10/10 render, 10/10 input,
10/10 garment_ref — lost in reset #5; AI-generated, never
byte-reproducible). Their SHA-256 values were computed at build time and
remain in the manifest. Status per item, now explicit in the manifest
(top-level `phase_scope` block + per-item `phase`/`artifact_status`
fields, added this pass):
`HASH RECORDED, SOURCE ARTIFACT CURRENTLY UNVERIFIABLE`. No replacement
images were generated; no recovery is claimed. The rater procedure's
ITEM_ERROR rule covers missing images. **The 10 missing items do not
contaminate the Phase-6-core completeness claim (4.2).**

**4.4 Human execution: NONE.** Zero real independent raters have
performed labeling. The labeling sheets contain no labels; the rubric,
manifest, builder script, and agent labels (explicitly
`AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH`) do not constitute
calibration.

**Result (two separate statuses, both true):**
`PACKAGE PREPARED` (executable as-is once ≥3 raters exist) and
`HUMAN CALIBRATION = BLOCKED` (no qualified raters exist).

## 5. P5 Status

**Fresh infrastructure evidence (this pass, 2026-09-19 12:11 UTC):**
both current eval URLs re-pinged with a **real render payload**
(person `p5l_fair` + black-joggers lower garment):

- `…confit-vton-worker-segfee-eval-fashninfer-7ad942.modal.run` →
  **404** `modal-http: workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled`
  (5.3 s)
- `…confit-vton-worker-segfee-eval-fashninfer-737de2.modal.run` →
  **404** identical (5.3 s)

Responses + timestamp recorded in
`evaluation/results/p5_dynamic_fresh/results.json`
(`blocker.rechecked`). Prior re-checks in the same artifact: 11:21 UTC
(previous audit) and ~07:45 UTC. The artifact's per-case records show
all 11 cases × N=2 = 22 renders as 404 (`VTON_WORKSPACE_DISABLED`); the
worker served live renders earlier the same day — the disablement is
mid-session **infrastructure** state, not an application or algorithm
failure, and no claim is made about worker/model health in either
direction. No Modal credentials exist in the workspace → no redeploy
possible. The re-run procedure is ready (probe records gate
version + commit + constants at run time) **without pretending it has
succeeded**.

**`P5 = BLOCKED-INFRA`** — infrastructure-bounded, re-checkable,
re-runnable.

## 6. VTON Evidence Reconciliation

**6.1 Sleeve — v2.4 remains exactly frozen.** Code-verified this pass
(`backend/app/services/vton_sleeve_gate.py`, unmodified by this
remediation): `FOREARM_PASS_THRESHOLD = 0.35` (L241),
`ANATOMY_NEW_SKIN_REFUSE = 0.10` (L283, S5),
`ANATOMY_ANY_SKIN_REFUSE = 0.15` (L372, S5b),
`ANATOMY_WRIST_REACH_REFUSE = 0.05` (L299, S6). Decision order
(L659→L725): coverage → S5 → **S5b** → S6; every channel aggregated
`max()` across both arms (**max-arm**); probe-error paths REFUSE
(fail-safe, never silent pass). Active production logic is exactly
**`v2.4 = v2.3 AND max(S5b) < 0.15`**. No per-arm variant is active
(per-arm appears only in comments/docstrings); no hidden fallback; no
client-side authority; no threshold was changed by this remediation.
Authoritative live matrix (`p7_v24_full_matrix.json`, 56/56 unique
rows, frozen-gate version recorded): `matched_frozen_table = 56`,
`mismatches = []`, defect safety `VERDICT: SAFE` (15 defect rows, 0
passing). Confusion matrix at τ 0.15 (`p7_v24_confusion_matrix.json`):
TP 21 / TN 15 / FP 0 / FN 20; TPR 0.5122; TNR 1.0; FPR 0.0; precision
1.0; recall-defect 1.0; 20/41 healthy over-refused (safe direction,
each enumerated). τ sweep: 0.05/0.10 REJECTED, **0.15 RETAINED** (zero
baseline flips; decision-relevant gap 0.1193 vs 0.2350), 0.20 dominated.

**6.2 The §F1 boundary row — explicitly separated (mandate §6).**
- **HISTORICAL CACHED MEASUREMENT:** the ablation replay table (Phase-6
  report §F1; `p6_sleeve_ablation.json`) replays Phase-5 **cached** S1
  values. `m0_repro_L2` = S1 0.3511 cached → above the 0.35 boundary →
  PASS in the replay → **22 TP / 19 FN** for rule V4 (= v2.3).
- **CURRENT LIVE MEASUREMENT (authoritative for current production):**
  the live production-gate re-execution (frozen v2.4, 56/56 rows)
  re-measures `m0_repro_L2` at S1 0.3451 → REFUSE → the frozen 50-row
  table is **21 PASS / 29 REFUSE** (21 TP / 20 FN), which is what
  production returns today.
- Bounded statement: *The 22-TP result belongs to the historical
  cached-S1 replay; the current live frozen-gate matrix is 21 TP / 20
  FN. The safety conclusions relevant to FP/TN remain unchanged for the
  measured defect cohort (FP 0, TN 9, TNR 1.0, precision 1.0 in both).*
  No threshold was moved to reconcile the two runs; the boundary row is
  documented, not "fixed".

**6.3 Ablation probe re-check (mandate §7).** `p6_sleeve_channel_ablation.py`
executed live this pass: **no crash** (the `KeyError: 'dropped_refuse'`
defect, fixed by the previous audit, does not recur); **the output file
is written**; `diff` between the pre-run on-disk JSON and the fresh
output: **byte-identical** — the on-disk JSON is the corrected run's
output; the docstring correctly distinguishes the probe's best-arm
replay from production's max-arm aggregation. V1 22/7/2/19
(FP {`p4_j_arabic2_L1`, `p0c_synth_partial_krust_L1`}, P 0.9167);
V2 22/8/1/19; V3 22/8/1/19; V4 22/9/0/19 (TNR 1.0, P 1.0) — exactly the
Phase-6 report §F1 table. The probe's algorithm was not changed.

**6.4 Low-contrast N=2 (mandate §10).** The three-way distinction
holds on raw bytes: **ENGINE DID NOT APPLY** {A-E, B, F} (pxchg
0.2774–0.2915; max per-pixel diff 2–3/255; 0.000% changed px in the
lower region — the engine returned essentially the input); **ENGINE
APPLIED** {C, D, G, H} (pxchg 2.97–15.77; max diff ~210/255). 14 raw
L1/L2 PNGs on disk; `VTON_LAYER_NOT_APPLIED` is the correct
evidence-bounded classification for the **measured** non-application
cases; no verifier threshold was changed to convert no-ops into PASS;
the result is **not generalized** to future low-contrast inputs
("applied-but-invisible" regime remains UNKNOWN, never observed in ~27
measured renders). DINOv2 (s5 channel) = ENVIRONMENT-BLOCKED (weights
lost; HF 401) — recorded, not skipped.

**6.5 Sleeve claim boundary (mandate §9).** The supported claim is
`MEASUREMENT-LEVEL CLOSURE FOR THE TESTED DEFECT FAMILY` (every measured
drop — engine/synthetic/short-declared/asymmetric — REFUSED +
regression-pinned; 0 FP on the 56+30 measured artifacts). Sweep result:
"universal" appears in `docs/vton/` **only in negated context**
(Phase-6 §R2 "not a universal guarantee"; Phase-7 §E "universal safety
is NOT claimed"); "fully solved" — 0 hits; no over-broad claim found
that required downgrading.

## 7. Test Evidence (fresh raw output, this pass)

After the documented environment restore (§2), raw pytest output
(2026-09-19):

| suite | raw result | matches report |
|---|---|---|
| backend + evaluation full | **1326 passed, 29 skipped, 0 failed** (232.59 s) | ✓ (report 1326P/29S/0F) |
| `test_sleeve_gate_regression.py` | **42 passed, 1 skipped** (43 collected) | ✓ current value; the stale "44P/1S" line in Phase-6 §Q1 corrected with disclosure (§10.4) |
| `test_sleeve_v23_matrix.py` | **52 passed** | ✓ |
| `test_licenses_and_secrets.py` | **6 passed** | ✓ |

All 29 full-suite skips explained (raw `-rs` output): 26 = live-GPU-
worker opt-in (`CONFIT_AT_LIVE_WORKER=1`; worker workspace disabled —
§5); 1 = PostgreSQL-only schema-drift test (no PG URL in environment);
1 = gitignored synthetic partial-drop replay artifact absent (skip by
design); 1 = rembg model path disabled (license-gated, disabled by
default). No test was removed, weakened, or changed to pass. The
environment incident (7th) is recorded separately (§2) and is NOT
described as harmless merely because the suite passed.

## 8. MCP / External Integration

The five-layer distinction is maintained throughout (MCP Server / Agent
Skill / wrapper-package / vendor API / underlying model-engine):

- **8 WeShop-ecosystem Agent Skills** = DISCOVERED → SCREENED (all LIVE
  at direct slugs at discovery; thin wrappers over the WeShop OpenAPI
  `openapi.weshop.ai`). None is an MCP server. Model Generator =
  identity **substitution** → NOT SUITABLE for identity preservation.
  `batchCount` 1–16 = 16 outputs from ONE input ≠ multi-garment.
- **Nothing installed or called, re-verified this pass:** no `weshop`
  CLI on PATH, 0 matching pip packages, 0 `WESHOP_*`/`FAL_*`/
  `REPLICATE_*` environment variables.
- **No real user image was uploaded to any external provider**; no
  credentials were requested, found, or used; no marketing claim was
  used as evidence; a wrapper's MIT license ≠ vendor model/API terms.
- **States:** `EXTERNAL VTO INTEGRATION = BLOCKED` and `EXTERNAL LIVE
  EVALUATION = BLOCKED` (privacy/retention/training/residency/DPA
  undocumented; no authorized credentials; no candidate evaluated).
  **FASHN HOLDS** (P4: not replaced; no candidate reached secondary
  evaluation).

## 9. Licensing

`PRODUCTION IDENTITY = LICENSE-GATED` (unchanged): ArcFace/WebFace600K
evaluation-only, rights unresolved; no documented production/commercial
rights evidence exists; no identity metric is claimed anywhere (P5
identity = NOT MEASURED, not proxied). "Technically works" was not
converted into "production licensed"; no model-popularity or
wrapper-license (MIT/Apache) argument was substituted for missing
rights evidence. License suite: 6P fresh raw run (§7) — FASHN
Apache-2.0, mediapipe/EasyOCR Apache-2.0 (eval-only), NC vetoes held
(UniFit CC BY-NC-SA; MV-Fashion NC; AdaFace MS1MV2 unresolved;
IDM/OOT/CatVTON CC-BY-NC-SA; FastFit NOASSERTION-NC); no
license-restricted weights tracked or committed. Security: clean secret
scan is classified as **security evidence only** — it is NOT privacy
compliance, which remains BLOCKED on external evidence (§8).

## 10. Contradictions Found and Corrected

Only genuine findings (each verified against raw evidence this pass):

1. **(FIXED) Stale Git state — 6th environment reset.** The previous
   audit recorded `c472bfd`/`d886c77` on branch
   `vton-evidence-reconciliation-2026-09-16` as the current state.
   Reset #6 replaced `.git` with a fresh clone at `main` 928e615; all
   those objects are absent (0 dangling). The entire Phase 5/6/7 tree
   was left uncommitted. Corrective action (non-destructive): branch
   re-created; verbatim evidence-snapshot commit `d5f6ca8` + tag;
   Phase-6 report §A1 note extended; this report §2 written from fresh
   `git` inspection.
2. **(FIXED) Package file count.** Previous audit §5: "Files present
   (7)" while listing 9 filenames. Actual count on disk: **9**
   (counted directly). Corrected here (§4.1) and in the Phase-6 report
   §O2 scope note.
3. **(FIXED) 63-vs-73 manifest scope conflation.** The 73-item manifest
   mixes the 63-item Phase-6 core with 10 Phase-7 items whose source
   images are missing; the previous audit verified the 63 but did not
   split the manifest by scope. Corrective action: manifest annotated
   with top-level `phase_scope` + per-item `phase`/`artifact_status`
   (10/10 p7d = `HASH RECORDED, SOURCE ARTIFACT CURRENTLY UNVERIFIABLE`);
   Phase-6 report §O2 scope note added. No fabricated replacements; no
   recovery claimed.
4. **(FIXED) Stale sleeve-regression count.** Phase-6 §Q1 recorded
   `test_sleeve_gate_regression.py` = 44P/1S; current raw output =
   **42P/1S** (43 tests collected). No test was removed, added, or
   modified by this remediation. Corrected in §Q1 with an explicit
   correction note (the earlier figure is superseded and disclosed, not
   hidden).
5. **(VERIFIED FIXED, from previous audit) Ablation probe crash.**
   Re-executed live: no `KeyError`; output written; on-disk JSON
   byte-identical to the fresh corrected run; docstring honest about
   best-arm replay vs production max-arm (§6.3).
6. **(CLARIFIED, from previous audit) §F1 boundary row (22 TP vs 21
   TP).** The Phase-6 report note now explicitly labels the two
   measurements (HISTORICAL CACHED replay = 22 TP; CURRENT LIVE frozen
   gate = 21 TP, authoritative) with the bounded statement of §6.2; no
   threshold moved.
7. **(FIXED) CLAIM → EVIDENCE → STATUS literal form.** Phase-6 report
   §G and §S used list/table forms without the explicit fields.
   Normalized to `CLAIM G1`/`CLAIM S1` → `EVIDENCE` → `STATUS` (and
   §Q1 given explicit EVIDENCE) — presentation only; no technical
   meaning changed; historical evidence not rewritten.
8. **(NOT A REPORT DEFECT — noted) A–S summary arithmetic.** The
   "18× VERIFIED, 2× BLOCKED, 1× LICENSE-GATED" summary cited in the
   mandate does not appear in any report (sweep-verified) and would not
   reconcile with 19 sections. The previous audit's 19-row matrix
   reconciled correctly (15+3+1=19). The strict 19-row A–S table +
   separate 3-row appendix table are given in §3; the arithmetic is
   exact.
9. **(CLASSIFIED) Phase-7 §U "OPEN — engine limitation" barrier row vs
   Phase-6 §S "product question carried forward".** Same underlying
   fact (dark-on-dark lower-garment no-op), two framings. This audit
   classifies it as a **residual engineering limitation** (§12), not a
   release blocker, because the truthful-refusal/containment contract
   (support only on confirmed application; `VTON_LAYER_NOT_APPLIED`
   otherwise) is settled and enforced. Both framings keep the overall
   state `BLOCKED`; neither report is rewritten.
10. **(SELF-DISCLOSED) Malformed P5 re-check attempt.** The first P5
    re-ping this pass (12:09 UTC) mis-parsed `.eval_urls` (three URLs on
    one line) and wrote an invalid `rechecked` entry (http 0,
    InvalidURL). It was immediately re-run correctly (12:11 UTC, §5)
    and the invalid entry **overwritten before any commit** — no
    malformed data reached Git. Disclosed per the no-hiding rule.

## 11. Remaining Release Blockers

Exactly **4** release blockers — conditions that currently prevent the
requested release state. Counted separately; no inflation, no hiding:

1. **Human calibration** — no ≥3 real independent raters exist.
   Closure: execute `evaluation/human_calibration/RUN_INSTRUCTIONS.md`
   (package prepared, blinded, re-runnable; §4).
2. **Production identity licensing** — LICENSE-GATED
   (ArcFace/WebFace600K rights unresolved, or an alternative with
   evidenced production rights; §9).
3. **Fresh dynamic local + global batch** — BLOCKED-INFRA (Modal
   workspace disabled, confirmed by fresh pings through 13:56 UTC;
   credentials now available in-session (provided 2026-09-19) but
   re-enable/redeploy was out of scope for this pass; re-runnable
   probe with gate fingerprint; §5).
4. **External VTO integration (WeShop)** — BLOCKED (privacy/retention/
   training/residency/DPA undocumented; no authorized credentials; no
   candidate evaluated; §8). FASHN HOLDS.

## 12. Residual Engineering Limitations

Known issues / future work that are **not** separate release blockers
(the system already carries a truthful refusal/containment contract for
them). Exactly **7**, kept separate from §11:

1. **Engine-side dark-on-dark lower-garment no-op** — product/engine
   task; the refusal contract is settled and enforced
   (`VTON_LAYER_NOT_APPLIED` on confirmed non-application). (Phase-7 §U
   lists it conservatively as an open barrier row — see §10.9.)
2. **Fixed-band sleeve geometry** (no pose tracking) → 20/41 healthy
   over-refusals — safe direction; landmark-based fix feasible
   (existing dependency, ~31 ms, evaluation-only, not integrated).
3. **"Applied-but-invisible" residual regime** — UNKNOWN, never
   observed in ~27 measured renders; no orthogonal signal is in
   production; not claimed closed.
4. **Stochastic engine sleeve drops** persist at the engine level
   (measured short-sleeve render of a declared long sleeve); the gate
   refuses them (regression-pinned); the engine itself is not fixed.
5. **Worker instance-cache determinism** — the same composition
   re-reads the same cached outcome (measured; documented, worker
   internals closed).
6. **2 GB sandbox RAM** — dual-language EasyOCR load OOMs
   (single-language subprocess readers in place).
7. **DINOv2 weights lost** — HF proxy 401; s5 channel
   ENVIRONMENT-BLOCKED (eval-only).

## 13. Final Claim Audit & Evidence Accounting

Classification of every high-value claim as of 2026-09-19:

- **VERIFIED (re-executed this pass):** v2.4 = `v2.3 AND max(S5b) <
  0.15` (code + 56/56 live matrix); 0 FP on the 56+30 measured sleeve
  artifacts; P0 low-contrast engine truth (raw bytes); P5
  BLOCKED-INFRA (12:11 UTC 404s); HUMAN CALIBRATION = BLOCKED /
  PACKAGE PREPARED; PRODUCTION IDENTITY = LICENSE-GATED; MCP
  DISCOVERED/BLOCKED, nothing installed; suite counts 1326P/29S/0F,
  42P/1S, 52P, 6P; single release state `RELEASE = BLOCKED`; Phase-6
  core 63/63 + 189/189 SHA.
- **HISTORICAL (true when made; not current state; preserved, not
  rewritten):** `49ef942`/`713694da` as "the commit"; `ec04a13`/
  `d886c77`/`c472bfd` as current refs (all objects now absent); the
  22-TP cached-replay table; "file overwritten" (ablation) — TRUE as of
  the previous audit and re-verified byte-identical this pass; Phase-6
  commit-time suite 1322P/33S/0F; sleeve-regression 44P/1S
  (superseded by 42P/1S, disclosed).
- **UNVERIFIED (evidence insufficient):** exact historical identity of
  any re-commit with the original commits (required wording: CONTENT
  PRESERVATION SUPPORTED, EXACT HISTORICAL IDENTITY UNVERIFIED);
  worker/model-level health in either direction (only the observed 404
  infrastructure condition is claimed).
- **LOST (artifact gone; recorded values stand where documented):**
  `evaluation/results/p7_adversarial/` (10 AI-generated bases + 20
  composites + results.json — reset #5; measured values remain in the
  Phase-7 report body and manifest verdicts); the 10 Phase-7 p7d
  manifest source images (HASH RECORDED, SOURCE ARTIFACT CURRENTLY
  UNVERIFIABLE); DINOv2 weights; original Git objects of all five
  historical commits.
- **BLOCKED (requirement unsatisfied, externally):** human raters;
  identity rights; Modal workspace; WeShop privacy/credentials.

**Evidence accounting table** (Exists / Byte-Hash Verifiable /
Current status, all re-checked this pass):

| Artifact / claim | Scope | Exists | Byte/hash verifiable | Current status |
|---|---|---|---|---|
| Phase-6 63-item human package (189 files) | Phase 6 core | yes | 189/189 SHA-256 reproduce (fresh) | PRESENT_AND_VERIFIABLE |
| Phase-7 10-item extension (30 source files) | Phase 7 | manifest entries yes; source images no | hashes recorded at build time; sources missing (reset #5) | HASH RECORDED, SOURCE ARTIFACT CURRENTLY UNVERIFIABLE (10/10) |
| Calibration package files (9) | Phase 6/7 | yes | n/a (documents; builder reproducible) | PRESENT_AND_VERIFIABLE (count corrected to 9) |
| P5 dynamic evidence (11 cases × N=2) | Phase 6 P5 | yes | 404 responses captured; fresh re-check 12:11 UTC in artifact | BLOCKED-INFRA (re-runnable) |
| Low-contrast matrix (7 cases, 14 raw PNGs, signals) | Phase 6 P0 | yes | results.json + 14 PNGs on disk; hashes in JSON | PRESENT_AND_VERIFIABLE |
| Sleeve v2.4 evidence (57 artifacts / 56 unique) | Phase 6/7 | yes | 56/56 frozen-table match; defect safety SAFE | PRESENT_AND_VERIFIABLE |
| Ablation JSON | Phase 6 P1-A | yes | byte-identical to fresh corrected-probe run (diff-verified) | PRESENT_AND_VERIFIABLE (crash fixed, previous audit) |
| Full suite evidence | current | yes | raw output this pass: 1326P/29S/0F | VERIFIED (fresh) |
| Sleeve regression / matrix / license suites | current | yes | 42P/1S; 52P; 6P (raw, this pass) | VERIFIED (fresh) |
| Security/secret scan | Phase 6 P8 | yes | 6P fresh; clean scan ≠ privacy compliance | VERIFIED (security) / BLOCKED (external privacy) |
| MCP audit (8 skills; 5-layer distinction) | Phase 6/7 P3 | yes | URLs verified live at discovery; no install (re-verified) | PRESENT_AND_VERIFIABLE (discovery) / BLOCKED (integration) |
| Final reports (Phase-6, Phase-7, this audit) | — | yes | in the remediation commit of record; also on `origin/vton-evidence-reconciliation-2026-09-16` after the 2026-09-19 push (§2 addendum) | PRESENT (local + remote) |
| Appendices T/U/V referenced paths | Phase 6 | 13/13 + all probes | all resolve (checked) | PRESENT_AND_VERIFIABLE |
| P1-D adversarial images (30) + results.json | Phase 7 P1-D | no | measured values recorded in Phase-7 report + manifest verdicts | LOST (values HISTORICAL) |
| DINOv2 weights | eval-only | no (dir empty) | — | LOST / ENVIRONMENT-BLOCKED |
| Historical commits `49ef942`/`713694da`/`ec04a13`/`d886c77`/`c472bfd`/`d5f6ca8`/`1975778`/`92f6513` | git | no (0 dangling; resets #3–#8) | content preservation supported by file-level verification + diffstat continuity; reconciled content additionally hosted on `origin/vton-evidence-reconciliation-2026-09-16` (pushed 2026-09-19, §2 addendum) | LOST (local objects); CONTENT PRESERVATION SUPPORTED, EXACT HISTORICAL IDENTITY UNVERIFIED |

## 14. Final Release State

`RELEASE = BLOCKED`

Exactly one overall release state; no READY / STABLE / CONDITIONAL-GO /
PRODUCTION-VERIFIED language exists anywhere in the Phase-6/7 reports
or this audit (sweep-verified). Permitted scope closures, which do not
change the overall state:

- Sleeve: **MEASUREMENT-LEVEL CLOSURE FOR THE TESTED DEFECT FAMILY**
  (every measured drop refused + regression-pinned; 0 FP on the
  measured cohort; residuals documented, §12.2–4).
- N=2 verification: **CLOSED at behavior level** on the measured set
  (≥10× margin observed range; honest refusal on the no-op; no
  threshold moved; residual regime UNKNOWN).

The release remains BLOCKED by the four blockers of §11 until they are
genuinely closed.

---

## Truthfulness Statement

Truthful `FAIL` / `BLOCKED` / `UNRESOLVED` / `UNVERIFIED` / `LOST`
findings are valid, useful engineering outcomes — this pass was not a
grading exercise, and nothing was hidden to obtain a PASS. Specifically
not hidden: the 6th reset that destroyed the Git state the previous
audit recorded (§2); the 7th reset that destroyed the snapshot +
remediation commits (`d5f6ca8`, `1975778`) after they were made (§2
addendum) — with the associated site-packages wipe (8th environment
incident; documented restore + identical re-run, recorded as an
incident, not called harmless); the 8th reset that destroyed the
re-commit (`92f6513`) and the 9th site-packages wipe (§2 addendum,
third pass); the package file-count miscount
(§10.2); the stale
44P/1S count (§10.4); the malformed 12:09 UTC P5 re-check attempt
(§10.10, overwritten before any commit); the lost P1-D and p7d images
(no replacement generated, no recovery claimed); the unresolved
ArcFace/WebFace600K rights; the disabled Modal workspace and missing
credentials; and the absence of any real human rater. A fabricated PASS
would contaminate the audit trail and mis-target remediation; the
actual state is: Phase-6 evidence intact and reproducible at the
measured scope, documentation now reconciled to the files that exist,
and the release correctly `BLOCKED` until the four external blockers
(§11) are genuinely closed.

---

## Appendix — Files changed by the remediation commit of record

(One focused remediation commit on branch
`vton-evidence-reconciliation-2026-09-16`; `main` 928e615 untouched
locally and on origin; tree clean. Per the §2 addendum: after resets
#7–#8 this commit sits directly on `main` — snapshot and remediation
merged into the single commit, because the tree was already in its
reconciled state at pass start. Push: initially BLOCKED (no PAT);
unblocked 2026-09-19 when the owner provided a PAT in-session — the
branch was pushed to origin and remote `main` verified untouched.)

1. `docs/vton/COMPLIANCE_AUDIT_PHASE6_2026-09-19.md` — rewritten to the
   mandated 14-section post-audit structure (this file).
2. `docs/vton/REMEDIATION_FINAL_REPORT_PHASE6_2026-09-19.md` — §A1
   commit-reference note extended (reset #6); §F2 boundary note
   clarified (HISTORICAL CACHED vs CURRENT LIVE, authoritative
   stated); §G and §S normalized to literal CLAIM → EVIDENCE → STATUS;
   §O2 scope note added (9 files; 63 core vs 10 Phase-7 extension;
   HASH RECORDED / UNVERIFIABLE); §Q1 count corrected (42P/1S) with
   disclosure. No other technical content changed.
3. `evaluation/human_calibration/ARTIFACT_MANIFEST.json` — top-level
   `phase_scope` block + per-item `phase`/`artifact_status` fields
   (phase/scope split; no hash, path, or verdict changed).
4. `evaluation/results/p5_dynamic_fresh/results.json` — fresh
   `blocker.rechecked` entry (2026-09-19 12:11 UTC) [included in the
   snapshot commit `d5f6ca8`, listed here for completeness].

Verification commands (all re-run green this pass):

```
git log --oneline -3                       # d5f6ca8 snapshot; remediation commit; 928e615 main
git status --porcelain=v1                  # empty (clean tree)
git rev-parse main                         # 928e615… unchanged
python3 -m pytest backend/tests evaluation/tests -q
python3 -m pytest backend/tests/test_sleeve_gate_regression.py -q
python3 -m pytest evaluation/tests/test_sleeve_v23_matrix.py -q
python3 -m pytest evaluation/tests/test_licenses_and_secrets.py -q
python3 evaluation/probes/p6_sleeve_channel_ablation.py
```
