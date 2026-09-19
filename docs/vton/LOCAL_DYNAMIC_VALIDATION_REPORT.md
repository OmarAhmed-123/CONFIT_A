# CONFIT_A — LOCAL MARKET DYNAMIC VALIDATION REPORT

Date: 2026-09-15
Scope: §26 + §41 — LOCAL market validation with **real dynamic runtime inputs** (new
persons + new garments rendered through the real production path on the live Modal
worker). NOT a fixture benchmark.

Status: **COMPLETE — 2/2 renders 200-verified; 1 §31-class sleeve defect found (L1)**

---

## 0. Input classes in this report (per §41)

| class | used here? | what it proves |
|---|---|---|
| Fixture evaluation | NO (Phase 0.5 report, separate) | calibration/regression only |
| **Dynamic runtime evaluation** | **YES — this report** | real-user generalization (the only class that can support a real-user claim) |
| Production-like evaluation | partially (real API + real GPU + real gates; shadow/staging pending §29) | pre-release rehearsal |

Every input below was generated 2026-09-15 for this run and is in
`evaluation/dyninputs/local/` (NOT in any fixture/benchmark/calibration corpus):

- **person_local_hijab.jpg** — Egyptian woman, white hijab, modest beige tunic,
  grey trousers; full-body studio. (hijab-compatible + modest-clothing case)
- **garment_local_arabic_tee.jpg** — olive long-sleeve tee, flat-lay, white Arabic
  text "القاهرة" on chest. (Arabic text + long sleeves + modest case)
- **garment_local_dress.jpg** — charcoal one-piece long-sleeve dress, flat-lay.
  (one-piece / modest case)

Engine: fashn-vton-v1.5 (fashn_vton_segfee, segmentation-free; fork 7c0f10af),
live Modal worker. Evidence: `evaluation/results/dynamic_validation_evidence.json`
+ output images `evaluation/results/outputs/dyn_L*.png`. Known-fixture-render
set = 89 pre-dynamic hashes (dynamic outputs excluded — self-contamination guard).

---

## 1. L1 — hijab person + olive long-sleeve Arabic tee

| field | value | status |
|---|---|---|
| Person | person_local_hijab.jpg (sha256 in evidence) | UNKNOWN runtime input |
| Garment | garment_local_arabic_tee.jpg → runtime catalog row, slot `upper_inner` | UNKNOWN runtime input |
| Result | 200, engine verify PASS (execution 18,026 ms) | MEASURED |
| Output | dyn_L1_local_hijab_arabic_tee.png (519,190 B, sha a932b400…9332) | NOT in 89-hash fixture set |
| Garment color coverage (runtime metric) | 0.3667 (applied, calibrated band) | MEASURED |
| Identity cosine self (ArcFace, eval-only) | 0.9484 | MEASURED |
| Hijab preserved | YES — white hijab fully intact in output | VISUALLY VERIFIED |
| Arabic text "القاهرة" | PARTIALLY PRESERVED — legible word, but letterforms distorted by the engine (text-corruption class, same as Phase 0.5 §10/§12: g120 preserved / g009 corrupted) | VISUALLY VERIFIED |
| **Long sleeves** | **NOT APPLIED — the engine re-fitted the garment as a CROP top; the person's original beige long sleeves remain visible on the arms** | **§31-CLASS DEFECT (MEASURED + visually verified)** |
| Sleeve probe (AT-16b `_lower_arm_coverage`) | n/a — forearm band shows original sleeves (not garment-colored) | MEASURED |

**Finding (L1):** the modest long-sleeve case — the core local-market requirement —
currently FAILS the §31 honest-render requirement on this worker instance: the
production verify gate passed (verify.PASS=True, color on the torso) while the
sleeves were dropped and the silhouette was re-fitted to a crop. This is the same
engine limitation family Phase 0.5 root-caused (geometry/pose-dependent sleeve
drop-out), observed here in a local-market modest context. Production must either
integrate the calibrated sleeve gate (AT-16b `_lower_arm_coverage`, threshold 0.35)
as a real gate or refuse long-sleeve garments with
`UNSUPPORTED_OR_UNVERIFIED_GARMENT_RENDER`. **This render must not be shipped as
"success" to a user expecting long sleeves.**

## 2. L2 — hijab person + charcoal one-piece dress

| field | value | status |
|---|---|---|
| Garment | garment_local_dress.jpg → runtime catalog row, slot `dress` (full_body) | UNKNOWN runtime input |
| Result | 200, engine verify PASS (execution 18,045 ms) | MEASURED |
| Output | dyn_L2_local_hijab_dress.png (480,362 B, sha d7664181…8497) | NOT in 89-hash fixture set |
| Garment color coverage (runtime metric) | 0.2119 (applied; dark fabric, shadow-lowered) | MEASURED |
| Identity cosine self | 0.9188 | MEASURED |
| One-piece applied | YES — full dress incl. long sleeves rendered on the arms | VISUALLY VERIFIED |
| Hijab preserved | YES | VISUALLY VERIFIED |
| Minor artifact | original trousers re-fitted/cropped at hem | VISUALLY VERIFIED (cosmetic) |

**Finding (L2):** the one-piece (full-body slot) modest case RENDERS COMPLETELY,
including long sleeves — contrasting with L1: sleeve drop-out is garment-geometry
dependent, not a uniform failure. One-piece modest dresses are currently a
reliable local-market path; separate long-sleeve tops are not (pending the sleeve
gate / worker fix).

---

## 3. Local-market verdict

| requirement (§26) | result |
|---|---|
| New authorized person image (runtime) | PASS (hijab person, unknown input) |
| Real/local catalog items (runtime rows) | PASS (2 new catalog rows, data-URL assets) |
| Real API request → real GPU render | PASS (2/2, 200 + verify PASS) |
| Arabic text | PARTIAL — "القاهرة" preserved but distorted (text-corruption class) |
| Modest clothing | one-piece dress PASS; long-sleeve top FAIL (sleeve drop-out, §31) |
| Long sleeves | FAIL on separate top (L1); PASS on one-piece dress (L2) |
| Hijab-compatible | PASS — hijab preserved in both renders, identity cos 0.92–0.95 |
| Provenance + no fixture substitution | PASS — both outputs ∉ 89-hash pre-dynamic fixture set; input/output hashes in evidence |

**Local dynamic status: CONDITIONAL — the pipeline is genuinely dynamic for the
local market (zero substitution, hijab-safe, one-piece modest path works); the
long-sleeve top path is blocked by the same sleeve limitation that blocks the
§31 gate work. Human rating of these outputs is still required (Gate A, BLOCKED).**

## 4. Claims audit (local)

| CLAIM | EVIDENCE | STATUS |
|---|---|---|
| Local renders are dynamic (no fixtures) | 89-hash set comparison; input hashes; new catalog rows | VERIFIED |
| Hijab preserved | visual inspection of both outputs | VISUALLY VERIFIED (agent; human rating pending) |
| One-piece dress renders completely | L2 output visual + verify + coverage | VERIFIED |
| Long-sleeve top drops sleeves on this instance | L1 output visual; §31-class | MEASURED |
| Arabic text preserved | L1 output: legible but distorted | PARTIAL — MEASURED |
| Identity preserved locally | ArcFace cos 0.9188–0.9484 (eval-only, LICENSE-GATED) | MEASURED (not a production claim) |
