"""Production sleeve-integrity gate — recovered, re-engineered (2026-10-18).

WHAT THIS IS
------------
The FASHN-class engines can DROP the sleeves of a long-sleeve garment and
still return ``verify.PASS=True`` (the torso re-textures, the arms do not).
The canonical per-layer gate (``assert_layer_applied``) is structurally blind
to that defect class, so a render with missing sleeves could otherwise be
reported as a verified success. This module adds the missing check: for
catalog garments that DECLARE ``sleeve_length == "long"``, the rendered
output is probed for changed, garment-colored coverage of the forearm bands
plus anatomical integrity channels, and an unverified long-sleeve render is
NEVER presented as verified.

PROVENANCE (read before trusting any number here)
-------------------------------------------------
The probe design and the default thresholds were recovered from the
historical 2026-09-15..19 calibration line (audit report 2026-09-19,
n=57 measured artifacts incl. 3 synthetic composites; the historical
repo's own report states: "The calibration is an honest engineering
calibration on 2-3 measured artifacts, NOT a statistical guarantee" for
the v2.2 line, and the v2.3/v2.4 margins were "calibration margin, not a
statistical guarantee"). Those artifacts, their measurement table
(``sleeve_signal_matrix.json``) and the refusal/PASS readings are external
to this repository's current history. They are therefore treated as
HISTORICAL REFERENCE ONLY:

* the default constants below are the last MEASURED operating points, used
  for OBSERVE-mode logging and as the starting grid for recalibration —
  they are UNFROZEN and NOT a pass guarantee;
* ``enforce`` mode is REFUSED at startup unless a valid calibration
  manifest exists for the CURRENT engine build and the CURRENT
  ``SLEEVE_GATE_VERSION`` (see ``load_manifest`` / ``startup_check``);
  a missing / invalid / stale manifest means enforcement is NOT available
  — it never silently degrades to "pass";
* human review (three independent raters) is part of the manifest
  approval contract; a manifest without three distinct rater identities is
  invalid.

DESIGN RULES (inherited from the historical line, all fail-safe)
-----------------------------------------------------------------
1. Sleeve EXPECTATION comes from authoritative catalog metadata
   (``Product.sleeve_length`` ∈ {"long","short","none"} | NULL). Clients
   never supply it; the system NEVER guesses: an upper-body garment with
   NULL/unknown sleeve metadata is NOT_VERIFIED → refuse under enforce.
2. The probe measures CHANGED garment-color coverage of calibrated forearm
   bands (ΔE output-vs-garment-dominant within radius AND ΔE
   output-vs-layer-input above the change threshold). PASS additionally
   runs three monotone-safe anatomical channels (new-skin, any-skin,
   wrist-reach) that can only ADD a refusal, never convert a refusal.
3. Indeterminate is never pass: readings in [FAIL, PASS) refuse; any probe
   error (undecodable images, missing garment reference, degenerate
   dominant color) refuses.
4. The image-geometry candidate detector from the historical evaluation
   line was measured MIS-CALIBRATED on real product photos (flagged
   short-sleeve tees as long-sleeve candidates with near-constant ratios)
   and is deliberately NOT used here.

DECISION TABLE (per layer; identical semantics to the historical v2.4)
----------------------------------------------------------------------
  slot ∉ {upper_inner, upper_outer, dress}      -> N/A (no gate)
  sleeve_length ∈ {"short","none"}              -> N/A (declared non-long)
  sleeve_length NULL / undeclared               -> REFUSE (NOT_VERIFIED)
  sleeve_length == "long":
      coverage <  FAIL(0.15)                    -> REFUSE (sleeves absent)
      coverage ∈ [FAIL, PASS=0.35)              -> REFUSE (NOT VERIFIED)
      coverage >= PASS:
          new-skin  >= 0.10                     -> REFUSE
          any-skin  >= 0.15                     -> REFUSE
          wrist-reach <  0.05                   -> REFUSE
          else                                  -> PASS
      probe error / degenerate color            -> REFUSE (NOT VERIFIED)

Modes (settings.VTON_SLEEVE_GATE_MODE, default "off"):
  off     — no probe, no claims. Current production behaviour unchanged.
  observe — probe + record honest per-layer verdicts in job metrics; never
            blocks a render. For calibration data collection.
  enforce — probe; any REFUSE fails the job with the canonical
            VTON_SLEEVES_NOT_VERIFIED code and delivers no image. Refuses
            to start without a valid calibration manifest (below).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from backend.app.core.logging import logger

# Gate ALGORITHM version — bumped whenever the probe or decision semantics
# change. A calibration manifest is only valid for the gate version it was
# produced against (enforce refuses on mismatch).
SLEEVE_GATE_VERSION = "v3.0-recovered.1"

# ---------------------------------------------------------------------------
# OPERATING POINTS (historical measured reference values — UNFROZEN).
# Runtime decisions under ``enforce`` use the thresholds from the VALID
# calibration manifest; these constants define the observe-mode log baseline
# and the harness's starting grid. Do not retune them to change outcomes.
# ---------------------------------------------------------------------------
DEFAULT_FOREARM_PASS_THRESHOLD = 0.35
DEFAULT_FOREARM_FAIL_THRESHOLD = 0.15
DEFAULT_DELTA_E_RADIUS = 40.0
DEFAULT_CHANGE_THRESHOLD = 20.0
DEFAULT_NEW_SKIN_REFUSE = 0.10
DEFAULT_ANY_SKIN_REFUSE = 0.15
DEFAULT_WRIST_REACH_REFUSE = 0.05

# Calibrated forearm bands, normalized (x0,x1,y0,y1) of a full-body front
# 9:16 render (historical 2026-09-15 boxes; recalibration may propose new
# bands through the manifest, never by editing this constant ad hoc).
FOREARM_BANDS = {
    "left": (0.52, 0.70, 0.40, 0.55),
    "right": (0.28, 0.46, 0.40, 0.55),
}
SLEEVE_RELEVANT_SLOTS = {"upper_inner", "upper_outer", "dress"}
_NON_LONG_SLEEVE_VALUES = {"short", "none"}
# Catalog vocabulary that is accepted at write time (schema-level).
SLEEVE_LENGTH_VALUES = {"long", "short", "none"}

# Skin window in CIE-Lab (historical cohort calibration 2026-09-19;
# measured to include all cohort skin tones and exclude all measured
# catalog garments — the a* upper bound is the discriminating axis).
SKIN_LAB_WINDOW = {"l": (25.0, 85.0), "a": (7.0, 25.0), "b": (7.0, 31.0)}
ANATOMY_OUTER_FRACTION = 0.65
ANATOMY_WRIST_FRACTION = 0.35

# Sanity envelope for manifest thresholds (a manifest outside these bounds
# is INVALID — thresholds are chosen by the documented calibration method,
# not tuned to a target success rate).
_THRESHOLD_BOUNDS = {
    "forearm_pass": (0.25, 0.55),
    "forearm_fail": (0.05, 0.25),
    "delta_e_radius": (25.0, 60.0),
    "change": (10.0, 35.0),
    "new_skin_refuse": (0.05, 0.20),
    "any_skin_refuse": (0.10, 0.25),
    "wrist_reach_refuse": (0.02, 0.12),
}

MANIFEST_SCHEMA_VERSION = "sleeve-calibration/1"


class SleeveGateConfigError(RuntimeError):
    """Gate configuration / manifest problem (fail-closed, never a bypass)."""


class SleevesNotVerifiedError(RuntimeError):
    """Canonical sleeve-gate failure raised into the render chain.

    The message starts with the canonical code so the existing error
    taxonomies (async job classifier + controller mapper) classify it as
    ``VTON_SLEEVES_NOT_VERIFIED`` — an honest 502-class FAILED job with no
    image delivered.
    """

    def __init__(self, detail: str):
        super().__init__(f"VTON_SLEEVES_NOT_VERIFIED: {detail}")


# ---------------------------------------------------------------------------
# Mode + manifest resolution
# ---------------------------------------------------------------------------
VALID_MODES = {"off", "observe", "enforce"}


def resolve_mode(settings_obj: Any = None) -> str:
    """Resolve the configured mode; anything other than the exact valid
    values fails closed with an explicit error (a typo must NOT silently
    disable a safety gate)."""
    from backend.app.core.config import settings as _s

    settings_obj = settings_obj or _s
    mode = str(getattr(settings_obj, "VTON_SLEEVE_GATE_MODE", "off")).strip().lower()
    if mode not in VALID_MODES:
        raise SleeveGateConfigError(
            f"VTON_SLEEVE_GATE_MODE={mode!r} is not one of {sorted(VALID_MODES)}; "
            "refusing to run with an unrecognised safety-gate mode"
        )
    return mode


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(settings_obj: Any = None) -> Dict[str, Any]:
    """Load + validate the calibration manifest for the CURRENT engine build.

    Returns ``{"ok": bool, "reasons": [...], "manifest": dict|None,
    "path": str|None}``. NEVER raises for a missing manifest — callers map
    ``ok=False`` to their mode semantics (enforce → refuse; observe →
    record defaults).
    """
    from backend.app.core.config import settings as _s

    settings_obj = settings_obj or _s
    path = str(getattr(settings_obj, "VTON_SLEEVE_CALIBRATION_MANIFEST", "") or "").strip()
    engine = str(getattr(settings_obj, "VTON_ENGINE", "fashn_vton_segfee")).strip().lower()
    out: Dict[str, Any] = {"ok": False, "reasons": [], "manifest": None, "path": path or None}
    if not path:
        out["reasons"].append("VTON_SLEEVE_CALIBRATION_MANIFEST is not configured")
        return out
    if not os.path.isfile(path):
        out["reasons"].append(f"manifest file not found: {path}")
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            man = json.load(f)
    except Exception as e:  # noqa: BLE001
        out["reasons"].append(f"manifest is not valid JSON: {type(e).__name__}: {str(e)[:160]}")
        return out
    out["manifest"] = man
    reasons: List[str] = []

    if man.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        reasons.append(f"schema_version {man.get('schema_version')!r} != {MANIFEST_SCHEMA_VERSION!r}")
    if man.get("gate_version") != SLEEVE_GATE_VERSION:
        reasons.append(
            f"manifest was calibrated for gate_version {man.get('gate_version')!r}, "
            f"current gate is {SLEEVE_GATE_VERSION!r}"
        )
    bound_engine = str(man.get("engine", "")).strip().lower()
    if bound_engine != engine:
        reasons.append(f"manifest is bound to engine {bound_engine!r}, current VTON_ENGINE is {engine!r}")
    eb = man.get("engine_build") or {}
    for k in ("worker_git_sha", "model_used"):
        if not str(eb.get(k) or "").strip():
            reasons.append(f"manifest.engine_build.{k} missing — build not identified")

    th = man.get("thresholds") or {}
    for key, (lo, hi) in _THRESHOLD_BOUNDS.items():
        v = th.get(key)
        if not isinstance(v, (int, float)) or not (lo <= float(v) <= hi):
            reasons.append(f"thresholds.{key}={v!r} missing or outside the sane calibration envelope [{lo}, {hi}]")
    if isinstance(th.get("forearm_pass"), (int, float)) and isinstance(th.get("forearm_fail"), (int, float)):
        if not float(th["forearm_fail"]) < float(th["forearm_pass"]):
            reasons.append("thresholds.forearm_fail must be < forearm_pass")

    ds = man.get("dataset") or {}
    ds_dir = str(ds.get("dir") or "")
    ds_manifest = str(ds.get("manifest_sha256") or "")
    if not ds_dir or not os.path.isdir(ds_dir):
        reasons.append("dataset.dir is missing or not readable — calibration data cannot be re-verified")
    elif not ds_manifest:
        reasons.append("dataset.manifest_sha256 missing")
    else:
        approved = os.path.join(ds_dir, "approved.jsonl")
        if os.path.isfile(approved):
            actual = _sha256_file(approved)
            if actual != ds_manifest:
                reasons.append(f"dataset hash mismatch: manifest {ds_manifest[:16]}… vs recomputed {actual[:16]}… (dataset changed after calibration)")
        else:
            reasons.append("dataset.approved.jsonl not found next to the manifest — dataset cannot be re-verified")

    hr = man.get("human_review") or {}
    raters = hr.get("raters") or []
    names = sorted({str(r.get("name", "")).strip() for r in raters if isinstance(r, dict)})
    if len(raters) != 3 or len([n for n in names if n]) != 3:
        reasons.append("human_review.raters must be exactly 3 distinct human raters (AI/synthetic judgments are not sign-offs)")
    if not str(hr.get("agreement_report_sha256") or "").strip():
        reasons.append("human_review.agreement_report_sha256 missing (per-case agreement record required)")

    ev = man.get("evaluation") or {}
    for k in ("false_accept_rate", "false_reject_rate"):
        v = ev.get(k)
        if not isinstance(v, (int, float)) or v < 0 or v > 1:
            reasons.append(f"evaluation.{k} missing or not a rate in [0,1]")

    if man.get("revoked") is True:
        reasons.append("manifest has been revoked")

    if reasons:
        out["reasons"] = reasons
        return out
    out["ok"] = True
    return out


def active_thresholds(manifest: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Threshold set in force for decisions: manifest when valid, else the
    documented historical defaults (observe-mode only)."""
    if manifest:
        th = manifest.get("thresholds") or {}
        return {k: float(th[k]) for k in _THRESHOLD_BOUNDS}
    return {
        "forearm_pass": DEFAULT_FOREARM_PASS_THRESHOLD,
        "forearm_fail": DEFAULT_FOREARM_FAIL_THRESHOLD,
        "delta_e_radius": DEFAULT_DELTA_E_RADIUS,
        "change": DEFAULT_CHANGE_THRESHOLD,
        "new_skin_refuse": DEFAULT_NEW_SKIN_REFUSE,
        "any_skin_refuse": DEFAULT_ANY_SKIN_REFUSE,
        "wrist_reach_refuse": DEFAULT_WRIST_REACH_REFUSE,
    }


def startup_check(settings_obj: Any = None) -> Dict[str, Any]:
    """Fail-fast verification called at app startup.

    * invalid mode value → raise (never silently off);
    * enforce without a valid manifest → raise (refuse to initialize —
      explicit VTON_SLEEVES_NOT_VERIFIED-style refusal for the whole
      render path until calibration exists; off/observe are unaffected).
    Returns the resolved state dict for capability reporting.
    """
    mode = resolve_mode(settings_obj)
    state: Dict[str, Any] = {
        "mode": mode,
        "gate_version": SLEEVE_GATE_VERSION,
        "calibrated": False,
        "reasons": [],
    }
    if mode == "off":
        return state
    res = load_manifest(settings_obj)
    state["calibrated"] = bool(res["ok"])
    state["reasons"] = res["reasons"]
    state["manifest_path"] = res.get("path")
    if mode == "enforce" and not res["ok"]:
        raise SleeveGateConfigError(
            "VTON_SLEEVE_GATE_MODE=enforce refused to initialize: no valid calibration "
            "manifest for the current engine build — " + "; ".join(res["reasons"][:6]) +
            ". Complete the calibration protocol (scripts/vton_sleeve_calibration.md) "
            "and point VTON_SLEEVE_CALIBRATION_MANIFEST at the approved manifest; "
            "enforce NEVER falls back to defaults or to 'pass'."
        )
    if mode == "observe" and not res["ok"]:
        logger.warn(
            "sleeve_gate_observe_uncalibrated",
            reasons="; ".join(res["reasons"])[:400],
            note="observe-mode verdicts are advisory measurements against historical default thresholds; not a pass guarantee",
        )
    return state


# ---------------------------------------------------------------------------
# Color helpers (pure PIL; identical math to the calibrated v2.2-v2.4 line)
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
    """Median Lab of the garment's non-background pixels (studio flat-lay
    convention: near-white pixels are background). (0,0,0) means UNMEASURABLE
    (e.g. white-on-white) — callers must treat that as NOT_VERIFIED."""
    px = garment_img.convert("RGB").load()
    w, h = garment_img.size
    samples: List[Tuple[int, int, int]] = []
    for yy in range(0, h, max(1, h // 40)):
        for xx in range(0, w, max(1, w // 40)):
            rgb = px[xx, yy]
            if min(rgb) > 235:
                continue
            samples.append(rgb)
    if not samples:
        return (0.0, 0.0, 0.0)
    lab = [_rgb_to_lab(s) for s in samples]
    return tuple(sorted(c)[len(c) // 2] for c in zip(*lab))  # type: ignore[return-value]


def forearm_garment_coverage(
    output_img: Image.Image,
    input_img: Image.Image,
    garment_lab: Tuple[float, float, float],
    *,
    radius: float = DEFAULT_DELTA_E_RADIUS,
    change_threshold: float = DEFAULT_CHANGE_THRESHOLD,
) -> Dict[str, float]:
    """Changed garment-color coverage per forearm band (v2.2 semantics)."""
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
                if e_out > radius:
                    n += 1
                    continue
                in_lab = _rgb_to_lab(pi[xx, yy])
                e_change = math.sqrt(sum((a - b) ** 2 for a, b in zip(out_lab, in_lab)))
                n += 1
                if e_change > change_threshold:
                    close += 1
        out[side] = round(close / n, 4) if n else 0.0
    return out


def _is_skin_lab(lab: Tuple[float, float, float]) -> bool:
    (l0, l1), (a0, a1), (b0, b1) = (
        SKIN_LAB_WINDOW["l"], SKIN_LAB_WINDOW["a"], SKIN_LAB_WINDOW["b"])
    return l0 <= lab[0] <= l1 and a0 <= lab[1] <= a1 and b0 <= lab[2] <= b1


def forearm_anatomy_probes(
    output_img: Image.Image,
    input_img: Image.Image,
    *,
    change_threshold: float = DEFAULT_CHANGE_THRESHOLD,
) -> Dict[str, Dict[str, float]]:
    """Anatomical integrity channels per side (v2.3/v2.4 semantics):
    ``new_skin_outer`` (changed AND skin vs layer input), ``any_skin_outer``
    (skin in the outer band regardless of newness — closes the old-skin
    blindness), ``wrist_reach`` (changed non-skin fabric in the wrist zone).
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
        n_ns = ns = n_wz = wz = sa = 0
        for yy in range(y0, y1, 3):
            for xx in range(xo, x1o, 3):
                if xx < x0 or xx >= x1 or yy < y0 or yy >= y1:
                    continue
                out_lab = _rgb_to_lab(px[xx, yy])
                in_lab = _rgb_to_lab(pi[xx, yy])
                e_change = math.sqrt(sum((a - b) ** 2 for a, b in zip(out_lab, in_lab)))
                changed = e_change > change_threshold
                n_ns += 1
                skin = _is_skin_lab(out_lab)
                if changed and skin:
                    ns += 1
                if skin:
                    sa += 1
                if yy >= wy0:
                    n_wz += 1
                    if changed and not skin:
                        wz += 1
        out[side] = {
            "new_skin_outer": round(ns / n_ns, 4) if n_ns else 0.0,
            "any_skin_outer": round(sa / n_ns, 4) if n_ns else 0.0,
            "wrist_reach": round(wz / n_wz, 4) if n_wz else 0.0,
        }
    return out


# ---------------------------------------------------------------------------
# Pure decision core (unit-testable, no I/O)
# ---------------------------------------------------------------------------
def evaluate_sleeves_sync(
    *,
    slot_type: str,
    sleeve_length: Optional[str],
    output_img: Optional[Image.Image],
    input_img: Optional[Image.Image],
    garment_img: Optional[Image.Image],
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Decide the sleeve gate for ONE rendered layer.

    ``output_img`` — the layer's rendered output; ``input_img`` — the
    LAYER INPUT (previous verified render, or the person image for layer 1);
    ``garment_img`` — the catalog garment as sent to the engine.
    Pass ``None`` for images when the fast metadata path applies.

    Returns ``{"status": "N/A"|"PASS"|"REFUSE", "reason": str,
    "coverage": dict|None, "anatomy": dict|None, "sleeve_length": …,
    "thresholds": …, "decision_source": "manifest"|"historical-defaults"}``.
    """
    th = dict(thresholds or active_thresholds(None))
    base: Dict[str, Any] = {
        "status": None,
        "reason": None,
        "coverage": None,
        "sleeve_length": sleeve_length,
        "thresholds": dict(th),
        "decision_source": "manifest" if thresholds is not None else "historical-defaults",
    }
    if slot_type not in SLEEVE_RELEVANT_SLOTS:
        base.update(status="N/A", reason=f"slot '{slot_type}' has no long-sleeve construction to verify")
        return base
    if sleeve_length in _NON_LONG_SLEEVE_VALUES:
        base.update(status="N/A", reason=f"catalog declares sleeve_length='{sleeve_length}' — no long-sleeve expectation")
        return base
    if sleeve_length != "long":
        base.update(status="REFUSE", reason=(
            f"catalog has not declared sleeve construction (sleeve_length={sleeve_length!r}) "
            "for an upper garment; never guessed (refuse rather than claim a verified long-sleeve render)"
        ))
        return base

    if output_img is None or input_img is None or garment_img is None:
        base.update(status="REFUSE", reason=(
            "probe inputs unavailable (render, layer input, or garment image could not be obtained); "
            "missing verification is never a pass"
        ))
        return base
    try:
        garment_lab = garment_dominant_lab(garment_img)
        if garment_lab == (0.0, 0.0, 0.0):
            base.update(status="REFUSE", reason=(
                "the garment's dominant color could not be measured from its image (white-on-light "
                "blind spot); refusing to claim a verified long-sleeve render without a reference color"
            ))
            return base
        coverage = forearm_garment_coverage(
            output_img, input_img, garment_lab,
            radius=th["delta_e_radius"], change_threshold=th["change"])
    except Exception as e:  # noqa: BLE001 — fail-safe, never a silent pass
        base.update(status="REFUSE", reason=(
            f"probe could not run on the render/garment images ({type(e).__name__}: {str(e)[:120]}); "
            "refusing to claim an unverified long-sleeve render"
        ))
        logger.warn("sleeve_gate_probe_error", slot_type=slot_type,
                    sleeve_length=sleeve_length, error=str(e)[:200])
        return base

    base["coverage"] = coverage
    best = max(coverage.values())
    if best >= th["forearm_pass"]:
        try:
            anatomy = forearm_anatomy_probes(output_img, input_img,
                                             change_threshold=th["change"])
        except Exception as e:  # noqa: BLE001
            base.update(status="REFUSE", reason=(
                f"anatomical sleeve-integrity probe could not run "
                f"({type(e).__name__}: {str(e)[:120]}); refusing to claim a "
                "verified long-sleeve render"
            ))
            return base
        base["anatomy"] = anatomy
        ns_best = max(a["new_skin_outer"] for a in anatomy.values())
        sa_best = max(a["any_skin_outer"] for a in anatomy.values())
        wz_best = max(a["wrist_reach"] for a in anatomy.values())
        if ns_best >= th["new_skin_refuse"]:
            base.update(status="REFUSE", reason=(
                f"long sleeves NOT verifiably present: newly exposed bare skin at the arm side "
                f"(best-arm new-skin {ns_best:.4f} >= {th['new_skin_refuse']}) — coverage came from "
                "the torso/short-sleeve region while the forearm shows skin (measured class-E mode)"
            ))
            return base
        if sa_best >= th["any_skin_refuse"]:
            base.update(status="REFUSE", reason=(
                f"long sleeves NOT verifiably present: exposed forearm skin in the band "
                f"(best-arm any-skin {sa_best:.4f} >= {th['any_skin_refuse']}), whether or not new "
                "vs the input — a dropped sleeve cannot hide behind skin the input already exposed"
            ))
            return base
        if wz_best < th["wrist_reach_refuse"]:
            base.update(status="REFUSE", reason=(
                f"long sleeves NOT verifiably present: no changed non-skin fabric reaches the wrist "
                f"(best-arm wrist-reach {wz_best:.4f} < {th['wrist_reach_refuse']}) — coverage came "
                "from the torso/upper arm, not from a sleeve reaching the arm"
            ))
            return base
        base.update(status="PASS", reason=(
            f"long sleeves verified present (best-arm changed garment-color coverage {best:.4f} "
            f">= {th['forearm_pass']}; anatomy: new-skin {ns_best:.4f}, any-skin {sa_best:.4f}, "
            f"wrist-reach {wz_best:.4f})"
        ))
    elif best < th["forearm_fail"]:
        base.update(status="REFUSE", reason=(
            f"long sleeves NOT present in the render (best-arm changed garment-color coverage "
            f"{best:.4f} < {th['forearm_fail']})"
        ))
    else:
        base.update(status="REFUSE", reason=(
            f"sleeve presence NOT VERIFIED (best-arm coverage {best:.4f} in "
            f"[{th['forearm_fail']}, {th['forearm_pass']}) — indeterminate; refusing rather than "
            "claiming success"
        ))
    return base


# ---------------------------------------------------------------------------
# Image loading helpers for the production path
# ---------------------------------------------------------------------------
def _decode_data_url(data_url: str) -> bytes:
    if "," not in data_url:
        raise ValueError("not a data URL")
    return base64.b64decode(data_url.split(",", 1)[1])


def _open_image(raw: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(raw))
    img.load()
    return img


def load_image_from_ref(ref: Optional[str]) -> Optional[Image.Image]:
    """Load an image from a data URL (only). HTTP fetch for the gate was a
    historical feature (garment URLs sent to the worker); this build keeps
    data-URL handling — the service passes the SAME bytes it sent to the
    engine, so no new network surface is added here."""
    if not isinstance(ref, str) or not ref.startswith("data:image"):
        return None
    try:
        return _open_image(_decode_data_url(ref))
    except Exception:  # noqa: BLE001
        return None


def decide_layer(
    *,
    slot_type: Optional[str],
    sleeve_length: Optional[str],
    output_ref: Optional[str],
    input_ref: Optional[str],
    garment_ref: Optional[str],
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Decode the three refs and run the decision core. Decode failures map
    to REFUSE (NOT_VERIFIED) with the reason recorded — never to a pass."""
    output_img = load_image_from_ref(output_ref) if (slot_type in SLEEVE_RELEVANT_SLOTS and sleeve_length == "long") else None
    input_img = load_image_from_ref(input_ref) if output_img is not None else None
    garment_img = load_image_from_ref(garment_ref) if output_img is not None else None
    if slot_type in SLEEVE_RELEVANT_SLOTS and sleeve_length == "long":
        missing = [name for name, im in (("render", output_img), ("layer input", input_img), ("garment image", garment_img)) if im is None]
        if missing:
            return {
                "status": "REFUSE",
                "reason": "probe inputs could not be decoded for: " + ", ".join(missing) + " — missing verification is never a pass",
                "coverage": None,
                "sleeve_length": sleeve_length,
                "thresholds": dict(thresholds or active_thresholds(None)),
                "decision_source": "manifest" if thresholds is not None else "historical-defaults",
            }
    return evaluate_sleeves_sync(
        slot_type=slot_type or "",
        sleeve_length=sleeve_length,
        output_img=output_img,
        input_img=input_img,
        garment_img=garment_img,
        thresholds=thresholds,
    )


def aggregate_layer_decisions(decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Honest outfit-level aggregation (parallel to aggregate_layer_verification)."""
    relevant = [d for d in decisions if d.get("status") != "N/A"]
    refused = [d for d in relevant if d.get("status") == "REFUSE"]
    return {
        "layers_relevant": len(relevant),
        "layers_verified": sum(1 for d in relevant if d.get("status") == "PASS"),
        "layers_refused": len(refused),
        "all_sleeves_verified": bool(relevant) and not refused,
        "not_applicable_layers": sum(1 for d in decisions if d.get("status") == "N/A"),
    }
