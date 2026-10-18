"""Sleeve-integrity gate — decision core + calibration-manifest unit tests.

Zero GPU, zero network. The gate's honesty contract is what these tests pin:
missing verification is NEVER a pass, metadata is never guessed, enforce is
locked behind a valid calibration manifest, and every fail-safe branch
refuses instead of succeeding quietly.

Thresholds exercised here are the HISTORICAL DEFAULTS (unfrozen, observe
semantics) unless a test supplies a manifest — see the module docstring of
backend/app/services/vton_sleeve_gate.py.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import types

import pytest
from PIL import Image

from backend.app.services import vton_sleeve_gate as sg


# --------------------------------------------------------------------- image helpers
def _solid(rgb, w=300, h=512) -> Image.Image:
    return Image.new("RGB", (w, h), color=rgb)


def _with_band(img: Image.Image, side: str, rows_frac: float, color, y0f=0.40, y1f=0.55) -> Image.Image:
    """Paint the given fraction of one forearm band's rows with `color`."""
    img = img.copy()
    px = img.load()
    fx0, fx1, fy0, fy1 = sg.FOREARM_BANDS[side]
    x0, x1 = int(img.width * fx0), int(img.width * fx1)
    y0, y1 = int(img.height * fy0), int(img.height * fy1)
    ymid = y0 + int((y1 - y0) * rows_frac)
    for yy in range(y0, ymid):
        for xx in range(x0, x1):
            px[xx, yy] = color
    return img


def _data_url(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


GRAY = (120, 110, 100)
RED = (180, 40, 40)
SKIN = (200, 150, 120)  # inside the calibrated skin window (fair/tan family)
GARMENT = Image.new("RGB", (60, 60), color=RED)  # dominant red on white bg


def _decide(out: Image.Image, inp: Image.Image, gar: Image.Image = GARMENT, *,
            slot="upper_outer", sleeve="long", th=None):
    return sg.evaluate_sleeves_sync(
        slot_type=slot, sleeve_length=sleeve,
        output_img=out, input_img=inp, garment_img=gar, thresholds=th)


# ---------------------------------------------------------------- decision table
class TestMetadataFastPaths:
    def test_irrelevant_slot_is_na(self):
        d = _decide(_solid(RED), _solid(GRAY), slot="footwear")
        assert d["status"] == "N/A"

    def test_declared_short_or_none_is_na(self):
        for v in ("short", "none"):
            d = _decide(_solid(GRAY), _solid(GRAY), sleeve=v)
            assert d["status"] == "N/A"

    def test_undeclared_long_slot_refuses_never_guesses(self):
        for v in (None, "", "unknown"):
            d = _decide(_solid(RED), _solid(GRAY), sleeve=v)
            assert d["status"] == "REFUSE"
            assert "never guessed" in d["reason"] or "not declared" in d["reason"]

    def test_undeclared_metadata_needs_no_images(self):
        d = sg.evaluate_sleeves_sync(
            slot_type="upper_inner", sleeve_length=None,
            output_img=None, input_img=None, garment_img=None)
        assert d["status"] == "REFUSE"  # metadata path fires before probes


class TestProbe:
    def test_sleeves_absent_refuses(self):
        d = _decide(_solid(GRAY), _solid(GRAY))
        assert d["status"] == "REFUSE"
        assert d["coverage"] is not None
        assert max(d["coverage"].values()) < sg.DEFAULT_FOREARM_FAIL_THRESHOLD

    def test_full_changed_garment_color_passes(self):
        # Whole render in garment color vs gray input: coverage 1.0, wrist
        # fabric reaches (changed non-skin), no skin channels fire.
        d = _decide(_solid(RED), _solid(GRAY))
        assert d["status"] == "PASS", d["reason"]
        assert d["decision_source"] == "historical-defaults"

    def test_indeterminate_band_refuses_not_verified(self):
        # ~25% of band rows garment-colored -> inside [0.15, 0.35)
        out = _with_band(_solid(GRAY), "left", 0.25, RED)
        d = _decide(out, _solid(GRAY))
        assert d["status"] == "REFUSE"
        assert "NOT VERIFIED" in d["reason"]

    def test_class_e_new_skin_channel_refuses(self):
        # Right arm fully garment-colored (coverage passes), left arm's outer
        # band shows NEWLY EXPOSED SKIN -> best-arm new-skin fires -> REFUSE.
        # (Channels aggregate with max() across arms: skin on EITHER arm where
        # a long sleeve should be blocks the whole layer.)
        out = _solid(RED)
        img = out.load()
        fx0, fx1, fy0, fy1 = sg.FOREARM_BANDS["left"]
        x0, x1 = int(300 * fx0), int(300 * fx1)
        bw = x1 - x0
        xo = x0 + int(bw * (1 - sg.ANATOMY_OUTER_FRACTION))
        for yy in range(int(512 * fy0), int(512 * fy1)):
            for xx in range(xo, x1):
                img[xx, yy] = SKIN
        d = _decide(out, _solid(GRAY))
        assert d["status"] == "REFUSE"
        assert "new-skin" in d["reason"] or "bare skin" in d["reason"]
        assert d["anatomy"]["left"]["new_skin_outer"] > sg.DEFAULT_NEW_SKIN_REFUSE

    def test_class_e_full_arm_drop_refuses(self):
        # BOTH arms' outer skin exposed with unchanged red inner coverage low ->
        # construct: bands = skin everywhere (coverage 0 -> refuse absent)
        d = _decide(_solid(SKIN), _solid(GRAY))
        assert d["status"] == "REFUSE"

    def test_partial_drop_no_wrist_fabric_refuses(self):
        # Left+right band: top 60% garment color (coverage ~0.6 >= 0.35),
        # wrist zone (bottom 35%) left identical to the input (no changed
        # fabric at the wrist) -> wrist-reach channel must refuse.
        base_in = _solid(GRAY)
        out = _solid(GRAY)
        for side in ("left", "right"):
            out = _with_band(out, side, 0.60, RED, y0f=0.40, y1f=0.487)
            # ^ paint only the UPPER ~60% of the band rows [0.40..0.487]
        d = _decide(out, base_in)
        assert d["status"] == "REFUSE"
        assert "wrist" in d["reason"]

    def test_old_skin_blindness_closed_by_any_skin(self):
        # Input ALREADY shows skin at the band; output keeps it (unchanged)
        # while a red sliver passes coverage -> new-skin=0 but any-skin high.
        inp = _with_band(_solid(GRAY), "left", 0.55, SKIN, y0f=0.40, y1f=0.55)
        inp = _with_band(inp, "right", 0.55, SKIN)
        out = inp.copy()
        # right band top 45%: garment red changed vs input -> coverage .45+
        out = _with_band(out, "right", 0.45, RED, y0f=0.40, y1f=0.4675)
        d = _decide(out, inp)
        assert d["status"] == "REFUSE"
        assert "any-skin" in d["reason"] or "exposed forearm skin" in d["reason"]

    def test_white_on_light_garment_refuses_degenerate(self):
        white = Image.new("RGB", (60, 60), color=(250, 250, 250))
        d = _decide(_solid(RED), _solid(GRAY), gar=white)
        assert d["status"] == "REFUSE"
        assert "dominant color" in d["reason"]

    def test_undecodable_inputs_refuse_via_decide_layer(self):
        d = sg.decide_layer(
            slot_type="upper_outer", sleeve_length="long",
            output_ref="not-a-data-url", input_ref=None, garment_ref=None)
        assert d["status"] == "REFUSE"
        assert "never a pass" in d["reason"]


class TestThresholdBinding:
    def test_manifest_thresholds_change_the_decision(self):
        # Coverage ~0.37 (upper rows + wrist-zone rows so the wrist channel
        # stays quiet) -> PASS under the 0.35 default, REFUSE under a
        # manifest whose pass line is 0.45: the manifest, not the module,
        # decides production enforcement.
        out = _solid(GRAY)
        for side in ("left", "right"):
            out = _with_band(out, side, 0.26, RED)
            fx0, fx1, fy0, fy1 = sg.FOREARM_BANDS[side]
            x0, x1 = int(300 * fx0), int(300 * fx1)
            y0, y1 = int(512 * fy0), int(512 * fy1)
            px = out.load()
            for yy in range(y1 - 9, y1 - 1):    # wrist-zone strip (~8 rows)
                for xx in range(x0, x1):
                    px[xx, yy] = RED
        d1 = _decide(out, _solid(GRAY))
        assert d1["status"] == "PASS", d1
        th = dict(sg.active_thresholds(None))
        th["forearm_pass"] = 0.45
        d2 = _decide(out, _solid(GRAY), th=th)
        assert d2["status"] == "REFUSE"  # same render, stricter manifest
        assert "NOT VERIFIED" in d2["reason"]
        assert d2["decision_source"] == "manifest"

    def test_aggregate_counts_relevant_layers(self):
        agg = sg.aggregate_layer_decisions([
            {"status": "PASS"}, {"status": "REFUSE"}, {"status": "N/A"},
        ])
        assert agg["layers_relevant"] == 2
        assert agg["all_sleeves_verified"] is False
        agg2 = sg.aggregate_layer_decisions([{"status": "N/A"}])
        assert agg2["layers_relevant"] == 0 and agg2["all_sleeves_verified"] is False


# ----------------------------------------------------------------- mode resolution
def _stub(**kw):
    base = dict(VTON_SLEEVE_GATE_MODE="off", VTON_SLEEVE_CALIBRATION_MANIFEST="",
                VTON_ENGINE="fashn_vton_segfee")
    base.update(kw)
    return types.SimpleNamespace(**base)


class TestModeResolution:
    def test_default_off(self):
        assert sg.resolve_mode(_stub()) == "off"

    def test_invalid_mode_fails_closed(self):
        with pytest.raises(sg.SleeveGateConfigError):
            sg.resolve_mode(_stub(VTON_SLEEVE_GATE_MODE="EnforceTheGate"))
        with pytest.raises(sg.SleeveGateConfigError):
            sg.resolve_mode(_stub(VTON_SLEEVE_GATE_MODE=""))


# -------------------------------------------------------------- manifest validity
def _write_valid_manifest(tmp_path, *, gate_version=None, engine="fashn_vton_segfee"):
    ds = tmp_path / "dataset"
    ds.mkdir(exist_ok=True)
    approved = ds / "approved.jsonl"
    approved.write_text(json.dumps({"id": "x", "synthetic": True}) + "\n", encoding="utf-8")
    man = {
        "schema_version": sg.MANIFEST_SCHEMA_VERSION,
        "gate_version": gate_version or sg.SLEEVE_GATE_VERSION,
        "engine": engine,
        "engine_build": {"worker_git_sha": "a" * 40, "model_used": "segfee-2026-10"},
        "thresholds": dict(sg.active_thresholds(None)),
        "dataset": {
            "dir": str(ds),
            "manifest_sha256": hashlib.sha256(approved.read_bytes()).hexdigest(),
            "counts": {"calibration": 1, "evaluation": 0},
        },
        "human_review": {
            "raters": [{"name": "R. One"}, {"name": "T. Two"}, {"name": "U. Three"}],
            "agreement_report_sha256": "b" * 64,
        },
        "evaluation": {"false_accept_rate": 0.0, "false_reject_rate": 0.1},
        "issued_at": "2026-10-18T00:00:00Z",
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(man), encoding="utf-8")
    return p, man


class TestManifestValidation:
    def test_no_manifest_configured(self, tmp_path):
        res = sg.load_manifest(_stub())
        assert res["ok"] is False and any("not configured" in r for r in res["reasons"])

    def test_missing_file(self, tmp_path):
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(tmp_path / "nope.json")))
        assert not res["ok"] and any("not found" in r for r in res["reasons"])

    def test_valid_manifest_ok(self, tmp_path):
        p, _ = _write_valid_manifest(tmp_path)
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert res["ok"] is True, res["reasons"]

    def test_engine_mismatch_invalidates(self, tmp_path):
        p, man = _write_valid_manifest(tmp_path)
        res = sg.load_manifest(_stub(VTON_ENGINE="catvton",
                                     VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"] and any("engine" in r for r in res["reasons"])

    def test_gate_version_mismatch_invalidates(self, tmp_path):
        p, _ = _write_valid_manifest(tmp_path, gate_version="v0.0-ancient")
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"] and any("gate_version" in r for r in res["reasons"])

    def test_dataset_tampering_invalidates(self, tmp_path):
        p, _ = _write_valid_manifest(tmp_path)
        with open(tmp_path / "dataset" / "approved.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": "injected"}) + "\n")  # dataset changed after freeze
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"] and any("hash mismatch" in r or "changed" in r for r in res["reasons"])

    def test_two_raters_invalid(self, tmp_path):
        p, man = _write_valid_manifest(tmp_path)
        man["human_review"]["raters"] = man["human_review"]["raters"][:2]
        p.write_text(json.dumps(man), encoding="utf-8")
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"] and any("3 distinct human" in r for r in res["reasons"])

    def test_duplicate_rater_names_invalid(self, tmp_path):
        p, man = _write_valid_manifest(tmp_path)
        man["human_review"]["raters"][1]["name"] = "R. One"
        p.write_text(json.dumps(man), encoding="utf-8")
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"] and any("3 distinct" in r for r in res["reasons"])

    def test_out_of_envelope_threshold_invalid(self, tmp_path):
        p, man = _write_valid_manifest(tmp_path)
        man["thresholds"]["forearm_pass"] = 0.02  # tuned to "pass" everything
        p.write_text(json.dumps(man), encoding="utf-8")
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"] and any("forearm_pass" in r for r in res["reasons"])

    def test_inverted_bands_invalid(self, tmp_path):
        p, man = _write_valid_manifest(tmp_path)
        man["thresholds"]["forearm_fail"] = 0.5
        p.write_text(json.dumps(man), encoding="utf-8")
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"]

    def test_revoked_manifest_invalid(self, tmp_path):
        p, man = _write_valid_manifest(tmp_path)
        man["revoked"] = True
        p.write_text(json.dumps(man), encoding="utf-8")
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"] and any("revoked" in r for r in res["reasons"])

    def test_broken_json_invalid_not_crash(self, tmp_path):
        p = tmp_path / "manifest.json"
        p.write_text("{not json", encoding="utf-8")
        res = sg.load_manifest(_stub(VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert not res["ok"] and any("JSON" in r for r in res["reasons"])


class TestStartupCheck:
    def test_off_boots_without_manifest(self, tmp_path):
        state = sg.startup_check(_stub())
        assert state["mode"] == "off" and state["calibrated"] is False

    def test_enforce_without_manifest_refuses_initialization(self, tmp_path):
        with pytest.raises(sg.SleeveGateConfigError) as ei:
            sg.startup_check(_stub(VTON_SLEEVE_GATE_MODE="enforce"))
        msg = str(ei.value)
        assert "refused to initialize" in msg and "calibration" in msg

    def test_enforce_with_invalid_manifest_refuses(self, tmp_path):
        p, man = _write_valid_manifest(tmp_path)
        man["gate_version"] = "stale"
        p.write_text(json.dumps(man), encoding="utf-8")
        with pytest.raises(sg.SleeveGateConfigError):
            sg.startup_check(_stub(VTON_SLEEVE_GATE_MODE="enforce",
                                   VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))

    def test_enforce_with_valid_manifest_boots(self, tmp_path):
        p, _ = _write_valid_manifest(tmp_path)
        state = sg.startup_check(_stub(VTON_SLEEVE_GATE_MODE="enforce",
                                       VTON_SLEEVE_CALIBRATION_MANIFEST=str(p)))
        assert state["mode"] == "enforce" and state["calibrated"] is True

    def test_observe_without_manifest_boots_advisory(self, tmp_path):
        state = sg.startup_check(_stub(VTON_SLEEVE_GATE_MODE="observe"))
        assert state["mode"] == "observe" and state["calibrated"] is False
        assert state["reasons"]  # advisory reason recorded, not raised

    def test_invalid_mode_fails_startup(self, tmp_path):
        with pytest.raises(sg.SleeveGateConfigError):
            sg.startup_check(_stub(VTON_SLEEVE_GATE_MODE="yes"))
