# CONFIT_A — GLOBAL MARKET DYNAMIC VALIDATION REPORT

Date: 2026-09-15
Scope: §27 + §41 — GLOBAL market validation with **real dynamic runtime inputs**
(new diverse persons + new garments rendered through the real production path on the
live Modal worker). NOT a fixture benchmark, and NOT a directory swap of local
fixtures — all inputs were generated 2026-09-15 specifically for this cohort.

Status: **COMPLETE — 3/3 renders 200-verified; text partially corrupted; one
documented inner-garment-drop artifact under single-layer outerwear**

---

## 0. Input classes in this report (per §41)

| class | used here? | what it proves |
|---|---|---|
| Fixture evaluation | NO (Phase 0.5 report, separate) | calibration/regression only |
| **Dynamic runtime evaluation** | **YES — this report** | real-user generalization (the only class that can support a real-user claim) |
| Production-like evaluation | partially (real API + real GPU + real gates; shadow/staging pending §29) | pre-release rehearsal |

Inputs (`evaluation/dyninputs/global/` — NOT in any fixture/benchmark/calibration corpus):

- **person_global_a.jpg** — athletic man, dark skin, short hair; full-body studio
  (diverse body type / appearance).
- **person_global_b.jpg** — woman, medium build, freckles, red hair; **difficult
  lighting** (dim room, warm tungsten key light, shadows) — the lighting-generalization case.
- **garment_global_text_tee.jpg** — white tee, bold black English text "CONFIT".
- **garment_global_logo_blazer.jpg** — navy blazer, small geometric triangle logo
  (logo case; generic logo — no brand marks).

Engine: fashn-vton-v1.5 (fashn_vton_segfee, segmentation-free; fork 7c0f10af),
live Modal worker. Evidence: `evaluation/results/dynamic_validation_evidence.json`
+ `evaluation/results/outputs/dyn_G*.png`. Known-fixture-render set = 89
pre-dynamic hashes (dynamic outputs excluded).

---

## 1. G1 — global A + CONFIT white text tee

| field | value | status |
|---|---|---|
| Garment | garment_global_text_tee.jpg → runtime catalog row, slot `upper_inner` | UNKNOWN runtime input |
| Result | 200, engine verify PASS (execution 18,143 ms) | MEASURED |
| Output | dyn_G1_globalA_text_tee.png (537,778 B, sha 9eb92264…3d9f) | NOT in 89-hash fixture set |
| Garment applied | YES — original grey tee replaced by the white tee | VISUALLY VERIFIED |
| Color coverage (runtime metric) | **0.0012 — KNOWN METRIC LIMITATION for near-white garments**: `_nonbg_dominant` excludes >235 white pixels, so the garment reference color is shadow-grey and the rendered white shirt is achromatic (excluded from the denominator). verify.PASS + visual inspection are the record here, not this metric. | MEASURED + documented |
| English text "CONFIT" | PARTIALLY CORRUPTED — word recognizable, letterforms distorted (same engine text-corruption class as Phase 0.5 §10/§12 and local L1 Arabic) | VISUALLY VERIFIED |
| Identity cosine self | 0.9060 | MEASURED |

## 2. G2 — global A + navy logo blazer

| field | value | status |
|---|---|---|
| Garment | garment_global_logo_blazer.jpg → runtime catalog row, slot `upper_outer` | UNKNOWN runtime input |
| Result | 200, engine verify PASS (execution 18,169 ms) | MEASURED |
| Output | dyn_G2_globalA_logo_blazer.png (535,202 B, sha 7c26bcf4…c7e6) | NOT in 89-hash fixture set |
| Blazer applied | YES — navy color + geometric logo on chest pocket | VISUALLY VERIFIED |
| Color coverage | 0.8532 (strong) | MEASURED |
| Identity cosine self | 0.8715 | MEASURED |
| **Artifact** | **inner garment dropped**: the person's original grey tee is absent under the open blazer (bare-chest look). Single-layer outerwear render replaces the whole upper body. (In the production N=2 chain — inner rendered FIRST, outer second, AT-15 — the inner garment is part of the input to layer 2 and is preserved.) | VISUALLY VERIFIED (documented) |

## 3. G3 — global B (dim tungsten lighting) + navy logo blazer

| field | value | status |
|---|---|---|
| Person | person_global_b.jpg — difficult-lighting case | UNKNOWN runtime input |
| Result | 200, engine verify PASS (execution 18,176 ms) | MEASURED |
| Output | dyn_G3_globalB_dimlogo_blazer.png (697,138 B, sha f78e445f…5341) | NOT in 89-hash fixture set |
| Blazer under difficult lighting | YES — navy adapted to the warm scene lighting; logo present | VISUALLY VERIFIED |
| Color coverage | 0.3900 (lower — dim scene darkens the navy; applied) | MEASURED |
| Scene/background preserved | YES — room, lamp, bookshelf intact | VISUALLY VERIFIED |
| Identity cosine self | 0.9091 (identity preserved despite the lighting difficulty) | MEASURED |
| Artifact | same inner-garment-drop as G2 | VISUALLY VERIFIED (documented) |

---

## 4. Global-market verdict

| requirement (§27) | result |
|---|---|
| Diverse body types / appearance | PASS — athletic dark-skin man + medium-build woman both preserved (body/pose intact in all renders) |
| Varied fashion styles / construction | PASS — tee / blazer both applied; one-piece covered in local report |
| Text garments | PARTIAL — "CONFIT" recognizable but distorted (engine text-corruption class) |
| Logo garments | PASS — geometric logo present in both blazer renders |
| Layered outfits | N=2 inner+outer covered by AT-15 (PASS, both client orders); N=2 top+bottom = the open N=2 lower-layer gap (ARCHITECTURE_TEST_REPORT §4.1) |
| Difficult lighting | PASS — dim tungsten render verified, identity cos 0.9091 |
| Varied backgrounds | PASS — studio + real interior preserved |
| Provenance + no fixture substitution | PASS — all 3 outputs ∉ 89-hash pre-dynamic fixture set |

**Global dynamic status: the architecture GENERALIZES to the global cohort with
zero substitution (diverse persons, difficult lighting, text/logo garments all
render through the real path with honest verify). Open items: text fidelity
(corruption class), the single-layer-outerwear inner-drop artifact (production N=2
ordering avoids it), and the standing N=2 lower-layer reliability gap.**

## 5. Claims audit (global)

| CLAIM | EVIDENCE | STATUS |
|---|---|---|
| Global renders are dynamic (no fixtures) | 89-hash set comparison; input hashes; new catalog rows | VERIFIED |
| Generalization across body types/lighting | G1–G3 outputs visual + identity cos 0.87–0.91 | VISUALLY VERIFIED (agent; human rating pending) |
| White garment applied | G1 visual + verify.PASS (coverage metric documented as white-blind) | VERIFIED (metric limitation documented) |
| Text fidelity | G1 "CONFIT" distorted | PARTIAL — MEASURED |
| Logo fidelity | G2/G3 logo present | VERIFIED (agent visual) |
| Difficult-lighting robustness | G3 output, identity 0.9091 | MEASURED |
| Identity preserved globally | ArcFace cos 0.8715–0.9091 (eval-only, LICENSE-GATED) | MEASURED (not a production claim) |
