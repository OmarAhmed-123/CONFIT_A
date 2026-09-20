"""Generic production sleeve-integrity gate (S31 repair, 2026-09-16).

WHY THIS EXISTS (measured defect, docs/vton/DYNAMIC_PHASE_FINAL_REPORT §31)
---------------------------------------------------------------------------
The FASHN engine can DROP the sleeves of a long-sleeve garment and still
return ``verify.PASS=True`` (the torso is re-textured, the arms are not).
The production verify gate (``assert_layer_applied``) is therefore
STRUCTURALLY BLIND to this defect class: it confirmed a render whose
sleeves were missing (LOCAL DYNAMIC case L1, 2026-09-15, saved output
``evaluation/results/outputs/dyn_L1_local_hijab_arabic_tee.png``).
Claiming success on such a render is the §31 violation: "never silently
render a known-risk garment and claim success".

DESIGN (generic only — no fixture/benchmark/garment IDs anywhere)
-----------------------------------------------------------------
1. SLEEVE EXPECTATION comes from AUTHORITATIVE CATALOG METADATA:
   ``Product.sleeve_length`` ("long" | "short" | "none" | NULL).
   The catalog is server-authoritative product data (AT-13 forbids the
   client from sending garment metadata). AT-19 (2026-09-15) required:
   "If you cannot reliably infer sleeve expectations from the actual
   catalog garments, the system must either require authoritative garment
   metadata or refuse the garment category. Never guess."

   NOTE: the image-geometry candidate detector
   (``evaluation/vton_metrics/sleeve_metrics.garment_sleeve_drop``) was
   measured 2026-09-16 to be MIS-CALIBRATED on real product photos
   (content box = full frame on gradient/shadow backgrounds; it flags
   short-sleeve tees and sleeveless chinos as "long-sleeve candidates"
   with near-constant ratios 0.85/0.85/0.85/0.71). It is NOT used by
   this gate; it remains an evaluation research tool only.

   v2.3 (2026-09-19) added two MONOTONE-SAFE anatomical integrity channels
   that run ONLY after the coverage probe reached its PASS line (they can
   only add REFUSE — never create a false positive). They close the two
   measured coverage-PASS failure modes on the 50-artifact matrix:
   (a) class E — the engine dropped the sleeves and coverage was carried
   by the white torso/short-sleeve region (best-arm 0.7062, FALSE-PASS
   under v2.2) while the exposed forearm showed newly appeared bare skin
   (arm-side new-skin 0.2965 vs <= 0.0903 on all 21 measured TPs — the
   largest TP reading, m1_light_trousers, is a deep-skin x windowpane-
   blazer composition; see residual limitations); (b) a partial drop over
   a garment-covered input (independently constructed 2026-09-19) —
   coverage 0.40 from torso/upper arm but no changed non-skin fabric at
   the wrist (wrist-reach 0.0 vs >= 0.1429 on all 21 measured TPs). Full
   provenance: evaluation/results/sleeve_signal_matrix.json + report
   Part 5.

2. SLEEVE PRESENCE is verified on the RENDERED OUTPUT by a calibrated
   CHANGED garment-color structural probe (v2.2, 2026-09-16): the
   fraction of each forearm band whose output pixel is (a) garment-
   colored (ΔE in CIE-Lab against the garment's dominant non-background
   color, radius 40) AND (b) actually changed relative to the LAYER
   INPUT (ΔE(output, input) > 20). "Garment color that appeared at the
   pixel" = sleeve applied; "the same appearance as before" (skin, the
   person's own clothing of ANY color family, background) = no verified
   sleeve.

   Calibration event 1 (MEASURED, 2026-09-16; absolute -> differential):
   the plain (absolute) probe version of this gate FALSE-PASSED the
   real L1 defect artifact (sleeves dropped): the person's own tan
   skirt in the render sits at ΔE≈38 (< 40) from the dark-olive
   garment, so 49.9% of one forearm band read as "garment-colored"
   with no sleeve present.

   Calibration event 2 (MEASURED, 2026-09-16; differential -> change
   probe): the differential probe ("garment-colored in the output but
   not already garment-colored in the input") was measured to
   FALSE-REFUSE correctly rendered, fully-sleeved, engine-verified
   DARK garments — the exact failure class of the product's flagship
   outerwear:
     * live contract C-07 (seed blazer on person rt4): the person's
       dark trousers/background at the forearm band were within ΔE 40
       of the dark-navy reference, annihilating the newness signal ->
       the gate read 0.2110 (NOT_VERIFIED -> REFUSE) on a good render
       whose own engine verify was PASS;
     * E-1 standalone blazer (raw person rt2): 0.0366/0.1077 (REFUSE)
       on a render with clearly present long sleeves.
   The change condition (ΔE(output, input) > 20) removes input-side
   contamination of ANY color family — dark trousers, the L1 tan
   skirt, a similar-colored previous layer — while still counting a
   real applied sleeve (garment-colored AND changed at the pixel).

   Calibration (MEASURED, best-arm of the two bands; exact per-arm
   values in the audit report):
     CHANGE probe v2.2, 2026-09-16:
       L1 defect (olive long-sleeve tee, sleeves DROPPED):
         left 0.0102 / right 0.0274 -> REFUSE (defect side: 5.5x below
         the 0.15 fail line, 12.8x below the 0.35 pass line)
       E-1 blazer (sleeves present, visually verified): 0.3524 -> PASS
         (THINNEST measured PASS case, 1.01x margin — see residual
         limitations)
       C-07 blazer (sleeves present, visually verified): 0.6022 -> PASS
         (1.72x)
       AT-16b (burgundy long-sleeve, sleeves present, visually
         verified to the wrist): 0.4725 -> PASS (1.35x)
       L2 (charcoal long-sleeve dress, sleeves present):
         0.9436 -> PASS (2.69x)
     Historical: DIFFERENTIAL v2.1 (2026-09-16): L1 0.0196/0.0635
     REFUSE; AT-16b 0.3729/0.3934 PASS; L2 0.8871/0.4240 PASS; plus
     the measured false refusals above (C-07 0.2110, E-1 0.1077).
     ABSOLUTE (2026-09-15, the original calibration that set the 0.35
     boundary): sleeves present 0.7758/0.6352; bare-forearm (short-
     sleeve negative control) 0.1648/0.1582.
   The 0.35 PASS / 0.15 FAIL boundaries are carried over from the
   absolute calibration. The [0.15, 0.35) band is NOT independently
   calibrated — it is treated as NOT VERIFIED, which REFUSES: the gate
   never passes a reading it cannot confidently call "sleeves present".

DECISION TABLE (per layer, fail-safe)
-------------------------------------
  slot not in {upper_inner, upper_outer, dress}  -> N/A (no gate)
  sleeve_length in {"short", "none"}             -> N/A (declared
      non-long-sleeve; the probe is inapplicable to short sleeves)
  sleeve_length is NULL / undeclared             -> REFUSE (NOT_VERIFIED:
      catalog has not declared sleeve construction; never guess)
  sleeve_length == "long":
      best-arm changed garment-color coverage <  0.15 -> REFUSE (FAIL:
          no changed sleeve-colored coverage)
      best-arm changed garment-color coverage in
      [0.15, 0.35)                                    -> REFUSE (NOT_VERIFIED)
      best-arm changed garment-color coverage >= 0.35 -> v2.3 anatomical
          integrity channels (monotone-safe: can only add REFUSE, never
          convert a REFUSE to a PASS):
            best-arm new-skin fraction (arm-side 65% of the band: output
            skin-colored AND changed vs the layer input) >= 0.10
                                                     -> REFUSE (the sleeve
            did not cover the forearm: it exposed bare skin — the measured
            class-E failure mode, reading 0.2965; all 21 measured TPs <=
            0.0903)
            best-arm wrist-reach (arm-side 65%, wrist zone = bottom 35%
            of the band: changed, non-skin fabric fraction) < 0.05
                                                     -> REFUSE (coverage
            came from the torso/upper arm, no sleeve reaches the wrist —
            the measured partial-drop-over-garment mode, reading 0.0; all
            21 measured TPs >= 0.1429)
            otherwise                                      -> PASS
      probe cannot run (undecodable images)       -> REFUSE (NOT_VERIFIED)

A REFUSE raises ``VTON_SLEEVES_NOT_VERIFIED`` in the render chain: the
job fails honestly (502 class) and NO image is delivered — the product
never claims a complete long-sleeve render it has not verified.

DOCUMENTED RESIDUAL LIMITATIONS (see the audit report)
------------------------------------------------------
* Dark / garment-colored input at the forearm band: the change
  condition (v2.2) handles the measured L1 tan-skirt and the C-07/E-1
  dark trousers/background cases (MEASURED 2026-09-16). Residual risk
  remains in multi-garment chains: if the layer INPUT already shows a
  previous layer's sleeve of a similar color at the band and the new
  layer's sleeve color is within ΔE 20 of it, the pixel-level change
  may read below the change threshold -> the gate over-refuses (safe
  direction, never a silent pass).
* Near-white long-sleeve garments on a light background: the dominant-
  color estimate can fail (white-on-white blind spot) -> the gate
  over-refuses (safe direction, never a silent pass).
* Garment color close to the wearer's skin tone within ΔE 40: the
  change condition still requires a pixel-level change, but a
  skin-toned sleeve on a bare-arm input is a small change and may read
  low -> over-refusal (safe direction).
* Garment color close to the input's clothing at the band (any color
  family) within ΔE 20 of the applied sleeve color: the change may read
  below threshold -> over-refusal (safe direction).
* The probe assumes a full-body front render (the production output
  aspect); unusual framing (cropped at the elbows, arms raised) can
  understate coverage -> over-refusal.
* THINNEST MEASURED MARGIN — the 0.35 PASS line cuts through the
  middle of the dark-blazer / arms-at-sides / dark-lower-body
  composition class, measured on BOTH sides (2026-09-16):
    - E-1 standalone blazer on raw person rt2: 0.3524 (1.01x ABOVE
      the line) -> PASS (thinnest measured PASS).
    - AT-15 N=2 inner+outer blazer on person rt1 (layer 2, product 1):
      0.3282 (0.94x, BELOW the line) -> REFUSE (NOT_VERIFIED). A
      captured render of this exact refusal (agent visual inspection,
      NOT human validation) shows the blazer WITH full long sleeves
      present — i.e. the gate over-refuses a visually-correct render
      here. This is a probe MARGIN limitation, NOT a sleeve-drop
      defect (contrast L1, where the sleeves are actually absent and
      the gate reads 0.0274).
  Consequence: within this composition class the gate cannot currently
  distinguish "sleeves present" from "sleeves present but thinly
  measured" with a robust margin; it fails closed (REFUSE) when the
  reading is < 0.35. That is the safe direction (no silent pass, no
  fake image) but it over-refuses some visually-acceptable renders.
  More calibration data is required before the margin can be treated
  as robust; the 0.35 boundary is NOT lowered to force these renders
  to pass (standing rule: no threshold change without statistical
  justification).
* A long-sleeve render with partial sleeve application (e.g. rolled
  cuffs, mid-forearm coverage) can land in NOT_VERIFIED ([0.15, 0.35))
  and be refused even if visually acceptable (safe direction).
* The calibration set is 5 measured artifacts (2026-09-16); the
  PASS-side margins on dark outerwear compositions are not yet
  statistically robust. The gate is a calibrated improvement over the
  differential v2.1 probe on every measured artifact, not a
  statistically proven production guarantee.
* Short-sleeve integrity (short sleeve dropped -> sleeveless crop) is
  OUT OF SCOPE of this gate; it is a lower-severity silhouette defect.
* v2.3 skin window (calibrated 2026-09-19 from the fair/tan/medium/deep
  evaluation cohort, CIE-Lab L* 25-85 / a* 7-25 / b* 7-31): a skin-toned
  GARMENT (tan/khaki-family) that falls inside the window on a dark input
  would read as "new skin" -> over-refusal (safe direction, never a false
  pass). Every measured catalog garment sits OUTSIDE the window:
  rendered rust a* 41.7-43.2 / b* 34-36 (a* AND b* out), terracotta /
  dark-rust a* 29-38 (a* out), burgundy a* 35.0 (a* out), brick a* 55.9
  (a* out), mustard b* 68.8 (b* out), purple b* -2.6 (b* out), beige /
  navy / gray / white a* ~0-3 (a* out), olive a* -17.9 (a* out), black
  L* 8.8 (L* out). Known conservative limitation (measured): the warmest
  hand/wrist highlight tail of a medium-deep person (J, a* up to 33.9)
  sits above the a* 25 cap — that is the hand, not the forearm (the
  anatomical target, measured a* 9.6-18.1 / b* 12.7-21.7, well inside),
  so at most a few wrist pixels are conservatively NOT counted as skin.
* v2.3 calibration set: 50 measured artifacts (Parts 3-5 of the audit
  report: 39 from 2026-09-16 + 11 new from 2026-09-19 incl. 8 fresh live
  renders and 3 hermetically constructed synthetic drops). Anatomy channel
  margins on this set (production probe grid): new-skin — drop side 3.0x
  (class E 0.2965 vs 0.10), TP side 1.11x (largest TP 0.0903, m1_light_
  trousers, deep-skin x windowpane composition); wrist-reach — 2.9x (smallest
  TP 0.1429 vs 0.05). The TP-side new-skin margin is THIN and composition-
  specific; it is calibration margin, not a statistical guarantee.
* v2.3 new-skin channel known false-positive tendency (measured): deep-skin
  persons wearing checked garments (white grid lines over a chromatic base)
  can accumulate small skin-colored-and-changed pixel fractions at the arm
  side (m1_light_trousers: 0.0903). The 0.10 threshold tolerates the
  measured maximum; a larger such reading would over-refuse (safe
  direction).
"""
from __future__ import annotations

import base64
import io
import math
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from backend.app.core.logging import logger

# ---------------------------------------------------------------------------
# Calibrated decision thresholds (provenance: see module docstring)
# ---------------------------------------------------------------------------
FOREARM_PASS_THRESHOLD = 0.35   # best-arm coverage >= 0.35 -> sleeves verified
FOREARM_FAIL_THRESHOLD = 0.15   # best-arm coverage <  0.15 -> sleeves absent
DELTA_E_RADIUS = 40.0           # CIE-Lab ΔE radius for "garment-colored"
# A forearm-band pixel counts as sleeve evidence only when the output is
# garment-colored AND its appearance actually CHANGED relative to the layer
# input (ΔE(output, input) > this). The change condition is what makes the
# probe immune to input-side contamination of ANY color family (the person's
# dark trousers/background, a similar-colored previous layer, the L1 tan
# skirt) — see the 2026-09-16 calibration events in the module docstring.
FOREARM_CHANGE_THRESHOLD = 20.0
# Forearm bands as normalized (x0, x1, y0, y1) rectangles of a full-body
# front 9:16 render — the exact calibrated boxes (2026-09-15).
FOREARM_BANDS = {
    "left": (0.52, 0.70, 0.40, 0.55),
    "right": (0.28, 0.46, 0.40, 0.55),
}
# Slots whose garments can carry (and drop) torso-adjacent sleeves.
SLEEVE_RELEVANT_SLOTS = {"upper_inner", "upper_outer", "dress"}
_NON_LONG_SLEEVE_VALUES = {"short", "none"}

# ---------------------------------------------------------------------------
# v2.3 anatomical integrity channels (calibrated 2026-09-19, n=50 artifacts;
# provenance + full measurement table: evaluation/results/sleeve_signal_matrix.json
# and docs/vton/REMEDIATION_FINAL_REPORT Part 5). Both channels are
# MONOTONE-SAFE: they only add REFUSE after the coverage probe already
# reached its PASS line — they can never turn a REFUSE into a PASS.
# ---------------------------------------------------------------------------
# Anatomical fact 1 (class E, measured 2026-09-16/19): when the engine drops
# a long sleeve over a forearm that the layer INPUT covered with a garment,
# the output exposes BARE SKIN at the forearm that was not skin in the input
# — "new skin at the arm side". Measured best-arm outer-65% new-skin
# fraction (50-artifact matrix, production probe grid): class E FP = 0.2965;
# a short-sleeve garment
# declared long = 0.1653; the 21 measured true positives = max 0.0903
# (m1_light_trousers — a deep-skin person x windowpane-blazer composition
# where a fraction of arm-side pixels read as skin-colored-and-changed; production
# grid 0.0903, harness step-2 grid 0.0882).
# Threshold 0.10 sits between the two populations: 3.0x below the class-E
# reading and 1.11x above the largest measured TP reading. The 1.13x TP-side
# margin is THIN and composition-specific (see residual limitations); the
# threshold is NOT raised to widen it because doing so would approach the
# short-sleeve-declared-long reading (0.1653) and erode the safety property.
ANATOMY_NEW_SKIN_REFUSE = 0.10
# Anatomical fact 2 (measured 2026-09-19): a genuinely applied long sleeve
# carries changed, non-skin fabric down to the wrist. In the wrist zone
# (bottom 35% of the forearm band, arm-side 65%), measured best-arm fraction
# of CHANGED (vs the layer input) AND non-skin output pixels: 21 measured
# TPs = min 0.1429 (2.9x above 0.05); every measured full drop and the
# measured partial drop (sleeve ends at mid-forearm, unchanged input garment
# shows below) = 0.0. A coverage reading >= 0.35 with no changed non-skin
# fabric at the wrist means the coverage came from the torso/upper-arm
# region, not from a sleeve reaching the arm -> REFUSE.
# Definition note: the channel deliberately does NOT require the wrist pixel
# to sit within DELTA_E_RADIUS of the garment's dominant color — checked /
# patterned garments (measured windowpane blazer, 2026-09-16 AT-15 study:
# white grid lines are not within the radius of the blue reference and
# annihilated a garment-radius wrist signal, readings 0.0/0.037 on two
# visually-verified TPs) must still count as "sleeve fabric at the wrist".
ANATOMY_WRIST_REACH_REFUSE = 0.05
# CIE-Lab window for human skin, calibrated 2026-09-19 from measured cohort
# pixels (fair/tan/medium/deep reference tones + J/L hand+forearm regions +
# the class-E exposed forearm): skin occupies L* 28.6-82.8, a* 8.0-19.4
# (reference tones; the warmest forearm a* 9.6-18.1), b* 18.2-28.9, with the
# warmest hand/wrist highlight tail reaching a* ~34. The window
# L* 25-85 / a* 7-25 / b* 7-31 includes every measured cohort skin tone and
# the class-E forearm, and EXCLUDES every measured catalog garment:
# rendered rust a* 41.7-43.2 / b* 34-36, terracotta / dark-rust a* 29-38,
# burgundy a* 35.0, brick a* 55.9, mustard b* 68.8, purple b* -2.6,
# beige / navy / gray / white a* ~0-3, olive a* -17.9, black L* 8.8.
# The a* 25 cap is the discriminating axis: it sits above the warmest
# measured FOREARM (18.1, 1.38x) and below the closest measured garment
# (dark-rust 29.3, 1.17x). Known conservative limitation: the warmest hand
# tail (a* > 25) is not counted as skin (hand, not forearm — safe direction).
SKIN_LAB_WINDOW = {"l": (25.0, 85.0), "a": (7.0, 25.0), "b": (7.0, 31.0)}
# Fraction of each band, on the arm side, that is the "outer" region used by
# both anatomy channels (excludes the torso edge that bleeds into the band).
ANATOMY_OUTER_FRACTION = 0.65
# Fraction of the band (from the bottom) that is the wrist zone for the
# wrist-reach channel.
ANATOMY_WRIST_FRACTION = 0.35
# ---------------------------------------------------------------------------
# v2.4 any-skin channel (measured 2026-09-19, Phase 6 P1-B adversarial
# composites on the cal_02 base — input wears a white TANK TOP, arms fully
# exposed; see evaluation/results/p6_sleeve_adversarial/ and
# evaluation/results/p6_sleeve_v24.json for the full table).
#
# Measured v2.3 structural defects closed by this channel:
#   * adv_onearm / adv_onearm_full (person's right sleeve fully dropped,
#     left arm intact) FALSE-PASSED v2.3: every v2.3 channel is aggregated
#     with max() (best arm) and S5 only counts skin that is NEW relative to
#     the layer input. On an input that already exposes the arm, a dropped
#     sleeve shows the person's OWN unchanged skin -> new_skin_outer was
#     measured at exactly 0.0 on the dropped arm; the intact arm carried
#     S1 (0.4608), S5 (0.0022) and S6 (0.2422) -> PASS on a render where
#     one arm has no sleeve at all.
#   * the same old-skin blindness applies to partial drops with the cuff
#     still present (exposed mid-forearm that is also present in the input).
#
# any_skin_outer = fraction of the outer forearm band that is
# human-skin-colored IN THE OUTPUT, whether or not new vs the input. A
# verified long sleeve leaves no skin in the outer band; an exposed forearm
# (old or new) fails the channel regardless of the input's sleeve state.
#
# Measured any-skin (best-arm) distribution, 57 artifacts (50-row matrix +
# 7 adversarial composites), production probe grid:
#   clean healthy renders (agent-verified full sleeves):  max 0.0892
#   borderline partial renders (thin forearm sliver; m1 carries 0.0936 NEW
#   skin — already a 0.0064-margin v2.3 coin-flip):       0.1070-0.1193
#   measured drop composites (crop/elbow/midgap/onearm/
#   onearm_full/wristgap):                                 min 0.1237
#   measured engine drops / short-declared-long rows:      0.2274-0.4225
#   (synthetic full drops over garment-covered inputs read 0.0000-0.0412 —
#   the band shows the unchanged covering garment, not skin; those are
#   caught by the wrist-reach channel, which is why the channels are kept
#   jointly rather than replaced.)
# Threshold 0.15 = midpoint of the measured gap between the highest clean
# healthy reading (m1_light_trousers_L2 0.1193 — a borderline partial render
# with a forearm skin sliver, 0.0936 of it NEW skin, i.e. already a 0.0064-
# margin v2.3 coin-flip; m5_dark_inner_L2 0.1070 is the next reading) and the
# lowest measured drop reading (adv_wristgap 0.1237; the asymmetric-drop
# false passes read 0.2350). It is 1.26x above the highest measured healthy
# reading and 1.57x below the measured asymmetric-drop false pass. Measured
# result (57 artifacts, v2.4 decision table): 22 PASS / 35 REFUSE — every
# agent-verified healthy render still PASSES (zero new over-refusals vs
# v2.3, which this channel was designed to preserve) and every measured drop
# (engine drops, synthetic drops, short-declared-long, all 6 adversarial
# composites incl. the two asymmetric false passes) is REFUSED. The root
# cause of the m1/m5 sliver (fixed band sampling the wrist/hand edge on some
# bodies) remains a documented P1-C limitation; with anatomical localization
# the threshold can be re-calibrated from a properly located band.
# ---------------------------------------------------------------------------
ANATOMY_ANY_SKIN_REFUSE = 0.15


class SleevesNotVerifiedError(RuntimeError):
    """Canonical sleeve-gate failure (raised into the render chain).

    Message starts with the canonical code so the existing error-taxonomy
    mappers (job path + controller) classify it as ``VTON_SLEEVES_NOT_VERIFIED``.
    """

    def __init__(self, detail: str):
        super().__init__(f"VTON_SLEEVES_NOT_VERIFIED: {detail}")


# ---------------------------------------------------------------------------
# Color helpers (pure-PIL ports of the AT-suite metrics — production code
# must not import from evaluation/)
# ---------------------------------------------------------------------------
def _rgb_to_lab(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    def _chan(c: float) -> float:
        c /= 255.0
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    r, g, b = (_chan(c) for c in rgb)
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883

    def _f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = _f(x), _f(y), _f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def garment_dominant_lab(garment_img: Image.Image) -> Tuple[float, float, float]:
    """Median Lab of the garment's non-background pixels (generic).

    Background pixels are those near-white (all channels > 235) — the
    studio flat-lay convention of the catalog. Returns (0, 0, 0) when no
    non-background pixels are found (e.g. a white garment on a white
    background — the white blind spot; the caller must treat a degenerate
    color as NOT VERIFIED, not as a measured color).
    """
    px = garment_img.convert("RGB").load()
    w, h = garment_img.size
    samples = []
    for yy in range(0, h, max(1, h // 40)):
        for xx in range(0, w, max(1, w // 40)):
            rgb = px[xx, yy]
            if min(rgb) > 235:
                continue
            samples.append(rgb)
    if not samples:
        return (0.0, 0.0, 0.0)
    lab = [_rgb_to_lab(s) for s in samples]
    return tuple(sorted(c)[len(c) // 2] for c in zip(*lab))


def forearm_garment_coverage(
    output_img: Image.Image,
    input_img: Image.Image,
    garment_lab: Tuple[float, float, float],
) -> Dict[str, float]:
    """CHANGED garment-color long-sleeve presence probe (calibrated 2026-09-16,
    superseding the differential v2.1 probe the same day).

    Fraction of each calibrated forearm band whose output pixel is
    garment-colored (ΔE in CIE-Lab against the garment's dominant color,
    radius ``DELTA_E_RADIUS``) AND has actually changed relative to the layer
    input (ΔE(output, input) > ``FOREARM_CHANGE_THRESHOLD``).

    Why the change condition (MEASURED calibration event, 2026-09-16): the
    differential v2.1 probe ("garment-colored in output but not already
    garment-colored in the input") was measured to FALSE-REFUSE correctly
    rendered, fully-sleeved, engine-verified dark garments:
      * live contract C-07 (seed blazer on person rt4): the person's dark
        trousers/background at the forearm band were within ΔE 40 of the
        dark-navy reference, so the newness signal was annihilated -> the
        gate read 0.2110 (NOT_VERIFIED -> REFUSE) on a good render.
      * E-1 standalone blazer (raw person rt2): 0.0366/0.1077 (REFUSE) on a
        render with clearly present long sleeves.
    A real applied sleeve is garment-colored AND changed vs the input;
    unchanged wearer clothing / background of any color family is NOT
    changed. The change condition therefore removes input-side contamination
    of ANY color family — including the L1 tan skirt (garment-colored but
    unchanged from the input) — without the differential probe's
    dark-input failure mode.

    Measured (2026-09-16, best-arm of the two bands):
      L1 defect (sleeves DROPPED):            0.0274  -> REFUSE (correct)
      E-1 blazer rt2 (sleeves present):       0.3524  -> PASS (thin 1.01x)
      C-07 blazer rt4 (sleeves present):      0.6022  -> PASS (1.72x)
      AT-16b burgundy rt1 (sleeves present):  0.4725  -> PASS (1.35x)
      L2 dress (sleeves present):             0.9436  -> PASS (2.69x)
    """
    out_w, out_h = output_img.size
    if input_img.size != (out_w, out_h):
        input_img = input_img.resize((out_w, out_h))
    px = output_img.convert("RGB").load()
    pi = input_img.convert("RGB").load()
    out: Dict[str, float] = {}
    for side, (fx0, fx1, fy0, fy1) in FOREARM_BANDS.items():
        n = close = 0
        for yy in range(int(out_h * fy0), int(out_h * fy1), 3):
            for xx in range(int(out_w * fx0), int(out_w * fx1), 3):
                out_lab = _rgb_to_lab(px[xx, yy])
                e_out = math.sqrt(sum((a - b) ** 2 for a, b in zip(out_lab, garment_lab)))
                if e_out > DELTA_E_RADIUS:
                    n += 1
                    continue
                in_lab = _rgb_to_lab(pi[xx, yy])
                e_change = math.sqrt(sum((a - b) ** 2 for a, b in zip(out_lab, in_lab)))
                n += 1
                if e_change > FOREARM_CHANGE_THRESHOLD:
                    close += 1
        out[side] = round(close / n, 4) if n else 0.0
    return out


def _is_skin_lab(lab: Tuple[float, float, float]) -> bool:
    """Is this CIE-Lab color inside the calibrated human-skin window?"""
    (l0, l1), (a0, a1), (b0, b1) = (
        SKIN_LAB_WINDOW["l"], SKIN_LAB_WINDOW["a"], SKIN_LAB_WINDOW["b"])
    return l0 <= lab[0] <= l1 and a0 <= lab[1] <= a1 and b0 <= lab[2] <= b1


def forearm_anatomy_probes(
    output_img: Image.Image,
    input_img: Image.Image,
    garment_lab: Tuple[float, float, float],
) -> Dict[str, Dict[str, float]]:
    """v2.3 anatomical integrity channels, per side (pure PIL, generic).

    ``new_skin_outer``: fraction of the arm-side (outer 65%) forearm-band
    pixels that are (a) human-skin-colored in the OUTPUT and (b) CHANGED
    relative to the layer input. High value = the sleeve that should cover
    the forearm instead exposed bare skin (the measured class-E mechanism).
    Pre-existing bare skin is UNCHANGED vs the input and does not count.

    ``wrist_reach``: fraction of the wrist-zone (bottom 35% of the band,
    arm-side 65%) pixels that are CHANGED relative to the layer input AND
    NOT skin-colored in the output — "sleeve fabric reached the wrist". A
    genuinely applied long sleeve reaches the wrist; coverage that does not
    reach the wrist at all (unchanged input garment / exposed skin /
    nothing) means the coverage came from the torso/upper-arm region.
    Deliberately NOT required to be within ``DELTA_E_RADIUS`` of the
    garment's dominant color: checked/patterned garments (measured
    windowpane blazer, 2026-09-16 AT-15 study) carry off-reference fabric
    (white grid lines) at the wrist that must still count as sleeve fabric.

    Both are measured exactly on the production probe grid (step 3) so the
    gate's decisions and the calibration tables are directly comparable.
    """
    out_w, out_h = output_img.size
    if input_img.size != (out_w, out_h):
        input_img = input_img.resize((out_w, out_h))
    px = output_img.convert("RGB").load()
    pi = input_img.convert("RGB").load()
    out: Dict[str, Dict[str, float]] = {}
    for side, (fx0, fx1, fy0, fy1) in FOREARM_BANDS.items():
        x0, x1 = int(out_w * fx0), int(out_w * fx1)
        y0, y1 = int(out_h * fy0), int(out_h * fy1)
        bw = x1 - x0
        xo = x0 + int(bw * (1 - ANATOMY_OUTER_FRACTION)) if side == "left" else x0
        x1o = x1 if side == "left" else x0 + int(bw * (1 - ANATOMY_OUTER_FRACTION))
        wy0 = y0 + int((y1 - y0) * (1 - ANATOMY_WRIST_FRACTION))
        n_ns = ns = n_wz = wz = nsa = sa = 0
        for yy in range(y0, y1, 3):
            for xx in range(xo, x1o, 3):
                if xx < x0 or xx >= x1 or yy < y0 or yy >= y1:
                    continue
                out_lab = _rgb_to_lab(px[xx, yy])
                in_lab = _rgb_to_lab(pi[xx, yy])
                e_change = math.sqrt(sum((a - b) ** 2 for a, b in zip(out_lab, in_lab)))
                changed = e_change > FOREARM_CHANGE_THRESHOLD
                n_ns += 1
                skin = _is_skin_lab(out_lab)
                if changed and skin:
                    ns += 1
                # v2.4: skin in the outer band regardless of newness vs the
                # input (closes the old-skin blindness of new_skin_outer —
                # see ANATOMY_ANY_SKIN_REFUSE for the measured provenance).
                if skin:
                    sa += 1
                if yy >= wy0:
                    n_wz += 1
                    # "sleeve fabric reached the wrist" = changed vs input AND
                    # not newly exposed skin (NOT required to be within
                    # DELTA_E_RADIUS of the dominant color — see docstring:
                    # checked/patterned garments carry off-reference fabric
                    # at the wrist that must still count).
                    if changed and not skin:
                        wz += 1
        out[side] = {
            "new_skin_outer": round(ns / n_ns, 4) if n_ns else 0.0,
            "any_skin_outer": round(sa / n_ns, 4) if n_ns else 0.0,
            "wrist_reach": round(wz / n_wz, 4) if n_wz else 0.0,
        }
    return out


# ---------------------------------------------------------------------------
# Gate decision (sync core — unit-testable without any I/O)
# ---------------------------------------------------------------------------
def evaluate_sleeves_sync(
    *,
    slot_type: str,
    sleeve_length: Optional[str],
    output_img: Image.Image,
    input_img: Image.Image,
    garment_img: Image.Image,
) -> Dict[str, Any]:
    """Decide the sleeve gate for ONE rendered layer.

    ``input_img`` is the layer's INPUT (the previous layer's output, or the
    uploaded person image for layer 1) — the change probe needs it to tell
    "garment color that changed at the pixel = applied sleeve" from "the
    same appearance as before" (the person's own clothing of any color
    family, background).

    Returns a dict with:
      status:  "N/A" | "PASS" | "REFUSE"
      reason:  human-readable (safe to store in job metrics)
      coverage: per-arm measured CHANGED garment-color coverage
                (only when the probe ran)
      sleeve_length: the catalog declaration that drove the decision

    REFUSE means the caller MUST fail the render with
    ``VTON_SLEEVES_NOT_VERIFIED`` and deliver no image.
    """
    base: Dict[str, Any] = {
        "status": None,
        "reason": None,
        "coverage": None,
        "sleeve_length": sleeve_length,
            "thresholds": {
                "pass": FOREARM_PASS_THRESHOLD,
                "fail": FOREARM_FAIL_THRESHOLD,
                "delta_e_radius": DELTA_E_RADIUS,
                "change": FOREARM_CHANGE_THRESHOLD,
                "anatomy_new_skin_refuse": ANATOMY_NEW_SKIN_REFUSE,
                "anatomy_any_skin_refuse": ANATOMY_ANY_SKIN_REFUSE,
                "anatomy_wrist_reach_refuse": ANATOMY_WRIST_REACH_REFUSE,
            },
    }
    if slot_type not in SLEEVE_RELEVANT_SLOTS:
        base.update(status="N/A", reason=f"slot '{slot_type}' has no long-sleeve construction to verify")
        return base
    if sleeve_length in _NON_LONG_SLEEVE_VALUES:
        base.update(status="N/A", reason=f"catalog declares sleeve_length='{sleeve_length}' — no long-sleeve expectation")
        return base
    if sleeve_length != "long":
        # Undeclared / unknown sleeve construction on an upper-slot garment:
        # never guess (AT-19). Safe explicit refusal.
        base.update(status="REFUSE", reason=(
            f"catalog has not declared sleeve construction (sleeve_length={sleeve_length!r}) "
            "for an upper garment; the system refuses to claim a verified long-sleeve "
            "render without authoritative metadata (AT-19: never guess)"
        ))
        return base

    # sleeve_length == "long" -> verify sleeves are actually in the output
    try:
        garment_lab = garment_dominant_lab(garment_img)
        if garment_lab == (0.0, 0.0, 0.0):
            # Degenerate: no non-background pixels found (e.g. a near-white
            # garment on a light background — the white blind spot). The
            # probe would run against an unmeasured color; refuse instead of
            # guessing (safe direction: over-refusal, never a silent pass).
            base.update(status="REFUSE", reason=(
                "the garment's dominant color could not be measured from its image "
                "(white-on-light blind spot); refusing to claim a verified "
                "long-sleeve render without a measurable reference color"
            ))
            return base
        coverage = forearm_garment_coverage(output_img, input_img, garment_lab)
    except Exception as e:  # noqa: BLE001 — fail-safe, never a silent pass
        base.update(status="REFUSE", reason=(
            f"probe could not run on the render/garment images ({type(e).__name__}: {str(e)[:120]}); "
            "refusing to claim an unverified long-sleeve render"
        ))
        logger.warn("sleeve_gate_probe_error", slot_type=slot_type, sleeve_length=sleeve_length, error=str(e)[:200])
        return base

    base["coverage"] = coverage
    best = max(coverage.values())
    if best >= FOREARM_PASS_THRESHOLD:
        # v2.3 anatomical integrity channels — run ONLY on the coverage-PASS
        # path. Both are monotone-safe (they can only add a REFUSE, never
        # convert a REFUSE to a PASS), so they cannot create a new false
        # positive; they close the two measured coverage-PASS failure modes:
        #   * class E (measured 2026-09-16/19): the engine dropped the
        #     sleeves and the coverage was carried by the white torso /
        #     short-sleeve region — best-arm 0.7062 -> the OLD gate
        #     FALSE-PASSED a sleeveless render. The dropped sleeve exposed
        #     bare skin at the arm side (new_skin_outer = 0.2965 vs max 0.0903
        #     on all 21 measured TPs) -> REFUSE.
        #   * partial drop over a garment-covered input (measured 2026-09-19,
        #     independently constructed): coverage >= 0.35 from the
        #     torso/upper arm, but NO changed non-skin fabric reaches the
        #     wrist (wrist_reach = 0.0 vs min 0.1429 on all 21 measured TPs)
        #     -> REFUSE.
        try:
            anatomy = forearm_anatomy_probes(output_img, input_img, garment_lab)
        except Exception as e:  # noqa: BLE001 — fail-safe, never a silent pass
            base.update(status="REFUSE", reason=(
                f"anatomical sleeve-integrity probe could not run "
                f"({type(e).__name__}: {str(e)[:120]}); refusing to claim a "
                "verified long-sleeve render"
            ))
            logger.warn("sleeve_gate_anatomy_probe_error",
                        slot_type=slot_type, error=str(e)[:200])
            return base
        base["anatomy"] = anatomy
        ns_best = max(a["new_skin_outer"] for a in anatomy.values())
        sa_best = max(a["any_skin_outer"] for a in anatomy.values())
        wz_best = max(a["wrist_reach"] for a in anatomy.values())
        if ns_best >= ANATOMY_NEW_SKIN_REFUSE:
            base.update(status="REFUSE", reason=(
                f"long sleeves NOT verifiably present: the arm side of the render shows "
                f"newly exposed bare skin (best-arm new-skin fraction {ns_best:.4f} >= "
                f"{ANATOMY_NEW_SKIN_REFUSE}) where a long sleeve should cover the forearm — "
                "the sleeve did not reach the arm (measured class-E failure mode: 0.2965; "
                "largest measured true positive: 0.0903)"
            ))
            return base
        if sa_best >= ANATOMY_ANY_SKIN_REFUSE:
            base.update(status="REFUSE", reason=(
                f"long sleeves NOT verifiably present: the arm side of the render shows "
                f"exposed forearm skin (best-arm any-skin fraction {sa_best:.4f} >= "
                f"{ANATOMY_ANY_SKIN_REFUSE}) where a long sleeve should cover the forearm — "
                "the skin counts whether or not it is new relative to the input, so a "
                "dropped sleeve cannot hide behind arm skin the input already exposed "
                "(measured asymmetric-drop false pass, Phase 6 P1-B: 0.2350 on a "
                "one-arm-drop render whose input tank top exposed the arm; clean healthy "
                "renders measured at most 0.0892)"
            ))
            return base
        if wz_best < ANATOMY_WRIST_REACH_REFUSE:
            base.update(status="REFUSE", reason=(
                f"long sleeves NOT verifiably present: no changed non-skin fabric reaches the "
                f"wrist (best-arm wrist-reach {wz_best:.4f} < {ANATOMY_WRIST_REACH_REFUSE}) — "
                "the coverage reading comes from the torso/upper-arm region, not from a "
                "sleeve reaching the arm (measured partial-drop mode: 0.0; smallest measured "
                "true positive: 0.1429)"
            ))
            return base
        base.update(status="PASS", reason=(
            f"long sleeves verified present (best-arm changed garment-color coverage {best:.4f} "
            f">= {FOREARM_PASS_THRESHOLD}; anatomical channels: new-skin {ns_best:.4f} < "
            f"{ANATOMY_NEW_SKIN_REFUSE}, wrist-reach {wz_best:.4f} >= {ANATOMY_WRIST_REACH_REFUSE})"
        ))
    elif best < FOREARM_FAIL_THRESHOLD:
        base.update(status="REFUSE", reason=(
            f"long sleeves NOT present in the render (best-arm changed garment-color coverage {best:.4f} "
            f"< {FOREARM_FAIL_THRESHOLD}; measured L1 defect artifact: 0.0274)"
        ))
    else:
        base.update(status="REFUSE", reason=(
            f"sleeve presence NOT VERIFIED (best-arm coverage {best:.4f} in [{FOREARM_FAIL_THRESHOLD}, "
            f"{FOREARM_PASS_THRESHOLD}) — indeterminate; refusing rather than claiming success"
        ))
    return base


def raise_if_refused(decision: Dict[str, Any], *, product_id: Optional[int] = None, layer: Optional[int] = None) -> None:
    """Raise the canonical VTON_SLEEVES_NOT_VERIFIED failure on REFUSE."""
    if decision.get("status") != "REFUSE":
        return
    raise SleevesNotVerifiedError(
        f"layer {layer} (product {product_id}): the long-sleeve construction of this garment "
        f"was not verifiably applied — {decision.get('reason')}. "
        "No complete, verified long-sleeve render exists; refusing delivery."
    )


# ---------------------------------------------------------------------------
# Async wrapper used by the render chains (decodes data URLs / fetches the
# garment image exactly as the worker would see it)
# ---------------------------------------------------------------------------
def _decode_data_url(data_url: str) -> bytes:
    if "," not in data_url:
        raise ValueError("not a data URL")
    return base64.b64decode(data_url.split(",", 1)[1])


def _open_image(raw: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(raw))
    img.load()
    return img


async def evaluate_layer_sleeves(
    *,
    slot_type: str,
    sleeve_length: Optional[str],
    output_data_url: str,
    input_data_url: str,
    garment_ref: str,
    product_id: Optional[int] = None,
    layer: Optional[int] = None,
) -> Dict[str, Any]:
    """Production entry point for one rendered layer.

    ``output_data_url``  — the layer's rendered output (data URL, already
                           validated by ``_call_gpu_worker``).
    ``input_data_url``   — the layer's INPUT image (the uploaded person for
                           layer 1, the previous layer's output otherwise).
                           The change probe needs it to distinguish
                           "garment color that changed at the pixel =
                           applied sleeve" from the person's own clothing
                           of any color family (including dark trousers /
                           backgrounds that match a dark garment).
    ``garment_ref``      — the garment image exactly as sent to the worker
                           (data URL preferred; http(s) URLs are fetched with
                           the same SSRF-protected path the service uses).

    Raises :class:`SleevesNotVerifiedError` on REFUSE (the caller's chain
    converts it to the job/API failure ``VTON_SLEEVES_NOT_VERIFIED``).
    Returns the decision dict on N/A / PASS (for layer metrics).
    """
    if slot_type not in SLEEVE_RELEVANT_SLOTS or sleeve_length in _NON_LONG_SLEEVE_VALUES:
        # Fast path: no probe needed — decide without touching any image.
        decision = evaluate_sleeves_sync(
            slot_type=slot_type,
            sleeve_length=sleeve_length,
            output_img=Image.new("RGB", (1, 1)),
            input_img=Image.new("RGB", (1, 1)),
            garment_img=Image.new("RGB", (1, 1)),
        )
        raise_if_refused(decision, product_id=product_id, layer=layer)
        return decision

    # Undeclared metadata on an upper slot -> refuse (no image needed).
    if sleeve_length != "long":
        decision = evaluate_sleeves_sync(
            slot_type=slot_type,
            sleeve_length=sleeve_length,
            output_img=Image.new("RGB", (1, 1)),
            input_img=Image.new("RGB", (1, 1)),
            garment_img=Image.new("RGB", (1, 1)),
        )
        raise_if_refused(decision, product_id=product_id, layer=layer)
        return decision

    # sleeve_length == "long": decode output + input + garment, run the probe.
    try:
        output_img = _open_image(_decode_data_url(output_data_url))
    except Exception as e:  # noqa: BLE001
        raise SleevesNotVerifiedError(
            f"layer {layer} (product {product_id}): the rendered output could not be decoded "
            f"for the sleeve-integrity probe ({type(e).__name__}); refusing to claim success."
        ) from e

    try:
        input_img = _open_image(_decode_data_url(input_data_url))
    except Exception as e:  # noqa: BLE001
        raise SleevesNotVerifiedError(
            f"layer {layer} (product {product_id}): the layer input image could not be decoded "
            f"for the sleeve-integrity probe ({type(e).__name__}); refusing to claim success."
        ) from e

    garment_raw: Optional[bytes] = None
    if isinstance(garment_ref, str) and garment_ref.startswith("data:image"):
        try:
            garment_raw = _decode_data_url(garment_ref)
        except Exception:  # noqa: BLE001
            garment_raw = None
    elif isinstance(garment_ref, str) and garment_ref.startswith("http"):
        try:
            from backend.app.core.security import is_safe_image_url

            if is_safe_image_url(garment_ref):
                import httpx

                resp = httpx.get(garment_ref, follow_redirects=True, timeout=15.0,
                                 headers={"User-Agent": "CONFIT-VTON/1.0"})
                if resp.status_code == 200 and len(resp.content) >= 100:
                    garment_raw = resp.content
        except Exception as e:  # noqa: BLE001
            logger.warn("sleeve_gate_garment_fetch_failed", product_id=product_id, error=str(e)[:150])
    if garment_raw is None:
        raise SleevesNotVerifiedError(
            f"layer {layer} (product {product_id}): the garment image is unavailable to the "
            "sleeve-integrity probe; refusing to claim a verified long-sleeve render."
        )

    try:
        garment_img = _open_image(garment_raw)
    except Exception as e:  # noqa: BLE001
        raise SleevesNotVerifiedError(
            f"layer {layer} (product {product_id}): the garment image could not be decoded "
            f"({type(e).__name__}); refusing to claim a verified long-sleeve render."
        ) from e

    decision = evaluate_sleeves_sync(
        slot_type=slot_type,
        sleeve_length=sleeve_length,
        output_img=output_img,
        input_img=input_img,
        garment_img=garment_img,
    )
    if decision["status"] == "REFUSE":
        logger.warn(
            "sleeve_gate_refused",
            layer=layer,
            product_id=product_id,
            slot_type=slot_type,
            sleeve_length=sleeve_length,
            coverage=decision.get("coverage"),
            anatomy=decision.get("anatomy"),
            reason=str(decision.get("reason"))[:200],
        )
    raise_if_refused(decision, product_id=product_id, layer=layer)
    return decision
