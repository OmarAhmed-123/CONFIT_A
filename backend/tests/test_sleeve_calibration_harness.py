"""Calibration harness — refusal semantics + manifest round-trip proof.

Synthetic fixtures ONLY (the harness labels them as such); these tests
validate the tooling pipeline (freeze → split → scan → publish → the gate's
own manifest validator accepts it). They are NOT calibration evidence for
the live engine — the harness itself refuses to freeze anything marked
synthetic into a real approved dataset, which is exactly what the
zero-calibration-without-humans rule looks like in code.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import pytest
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HARNESS = os.path.join(REPO, "scripts", "vton_sleeve_calibration.py")
GRAY = (120, 110, 100)
RED = (180, 40, 40)


def _run(*args, expect_fail=False):
    p = subprocess.run([sys.executable, HARNESS, *args], capture_output=True, text=True,
                       cwd=REPO, env={**os.environ, "PYTHONPATH": REPO})
    if expect_fail:
        assert p.returncode != 0, f"expected refusal, got 0:\n{p.stdout}\n{p.stderr}"
        return p
    assert p.returncode == 0, f"harness failed:\n{p.stdout}\n{p.stderr}"
    return p


def _make_case(cdir: str, *, present: bool, raters: int = 3, synthetic: bool = False,
               expected: bool | None = None):
    os.makedirs(cdir, exist_ok=True)
    out = Image.new("RGB", (300, 512), color=GRAY)
    if present:
        px = out.load()
        for x0, x1 in ((156, 210), (84, 138)):
            for yy in range(204, 281):
                for xx in range(x0, x1):
                    px[xx, yy] = RED
    out.save(os.path.join(cdir, "output.png"))
    Image.new("RGB", (300, 512), color=GRAY).save(os.path.join(cdir, "input.png"))
    g = Image.new("RGB", (80, 80), color=(255, 255, 255))
    gx = g.load()
    for yy in range(15, 65):
        for xx in range(15, 65):
            gx[xx, yy] = RED
    g.save(os.path.join(cdir, "garment.png"))
    label = {
        "expected_sleeves": present if expected is None else expected,
        "garment_type": "blazer", "pose_class": "arms_down", "occlusion_class": "none",
        "quality_class": "studio", "sleeve_length_declared": "long",
        "raters": [{"name": f"H{i}", "verdict": "agree"} for i in range(raters)],
        "synthetic": synthetic, "source": "unit-test constructed fixture",
    }
    json.dump(label, open(os.path.join(cdir, "label.json"), "w"))


def _dataset(tmp_path, n_good=3, n_drop=3, raters=3):
    d = os.path.join(str(tmp_path), "dataset")
    os.makedirs(os.path.join(d, "cases"))
    for i in range(n_good):
        _make_case(os.path.join(d, "cases", f"good_{i}"), present=True, raters=raters)
    for i in range(n_drop):
        _make_case(os.path.join(d, "cases", f"drop_{i}"), present=False, raters=raters)
    return d


class TestSyntheticGuards:
    def test_make_synthetic_labels_every_case(self, tmp_path):
        out = str(tmp_path / "synth")
        _run("make-synthetic", "--out", out, "--n", "4")
        labels = [json.load(open(os.path.join(out, "cases", c, "label.json")))
                  for c in os.listdir(os.path.join(out, "cases"))]
        assert len(labels) == 4 and all(l["synthetic"] for l in labels)

    def test_freeze_refuses_synth_only_dataset(self, tmp_path):
        d = _dataset(tmp_path, n_good=0, n_drop=0)
        _make_case(os.path.join(d, "cases", "synth1"), present=True, synthetic=True)
        p = _run("freeze-dataset", "--dir", d, expect_fail=True)
        out = p.stdout + p.stderr
        assert "no real" in out.lower()
        # a mixed dir freezes ONLY the real cases (synthetic skipped, never entered)
        _make_case(os.path.join(d, "cases", "real1"), present=True)
        _run("freeze-dataset", "--dir", d, "--force")
        ids = [json.loads(l)["id"] for l in
                open(os.path.join(d, "approved.jsonl"), encoding="utf-8") if l.strip()]
        assert ids == ["real1"]

    def test_freeze_refuses_two_raters(self, tmp_path):
        d = _dataset(tmp_path, n_good=2, n_drop=1, raters=2)
        p = _run("freeze-dataset", "--dir", d, expect_fail=True)
        assert "3 distinct human raters" in (p.stdout + p.stderr)


class TestPipeline:
    def test_freeze_scan_publish_and_gate_accepts_manifest(self, tmp_path, monkeypatch):
        d = _dataset(tmp_path)
        _run("freeze-dataset", "--dir", d)
        approved = open(os.path.join(d, "approved.jsonl"), encoding="utf-8").read().splitlines()
        assert len(approved) == 6
        splits = json.load(open(os.path.join(d, "splits.json"), encoding="utf-8"))
        assert set(splits["calibration"]) | set(splits["evaluation"]) == {
            json.loads(a)["id"] for a in approved}
        # re-freeze without --force must refuse (immutability)
        _run("freeze-dataset", "--dir", d, expect_fail=True)

        rep = _run("run-benchmark", "--dataset", d, "--mode", "fixtures",
                   "--out", os.path.join(d, "report.json")).stdout
        assert "chosen forearm_pass" in rep
        report = json.load(open(os.path.join(d, "report.json"), encoding="utf-8"))
        assert report["chosen"]["calibration_metrics"]["false_accept_rate"] == 0.0

        approval = {
            "raters": [{"name": "Ann Rater", "verdict": "all cases agreed"},
                       {"name": "Ben Rater", "verdict": "all cases agreed"},
                       {"name": "Cid Rater", "verdict": "all cases agreed"}],
            "agreement": {"per_case": "see dataset labels", "disagreements": 0},
        }
        ap = os.path.join(str(tmp_path), "approval.json")
        json.dump(approval, open(ap, "w"))

        # two raters -> publish refuses
        bad = {"raters": approval["raters"][:2]}
        apbad = os.path.join(str(tmp_path), "approval_bad.json")
        json.dump(bad, open(apbad, "w"))
        p = _run("publish-manifest", "--dataset", d, "--report", os.path.join(d, "report.json"),
                 "--approval", apbad, "--engine-build-sha", "e" * 40,
                 "--model-used", "segfee-test", "--out", os.path.join(str(tmp_path), "m.json"),
                 expect_fail=True)
        assert "three distinct HUMAN" in (p.stdout + p.stderr)

        mpath = os.path.join(str(tmp_path), "manifest.json")
        _run("publish-manifest", "--dataset", d, "--report", os.path.join(d, "report.json"),
             "--approval", ap, "--engine-build-sha", "e" * 40, "--model-used", "segfee-test",
             "--out", mpath)
        man = json.load(open(mpath, encoding="utf-8"))
        # gate version/fields must line up with the runtime validator:
        man["gate_version"] = __import__("backend.app.services.vton_sleeve_gate",
                                         fromlist=["sg"]).SLEEVE_GATE_VERSION
        json.dump(man, open(mpath, "w"))

        from backend.app.services import vton_sleeve_gate as sg
        stub = type("S", (), {})()
        stub.VTON_SLEEVE_GATE_MODE = "enforce"
        stub.VTON_SLEEVE_CALIBRATION_MANIFEST = mpath
        stub.VTON_ENGINE = man["engine"]
        res = sg.load_manifest(stub)
        assert res["ok"] is True, res["reasons"]
        # enforce state with THIS manifest is accepted by the startup check
        state = sg.startup_check(stub)
        assert state["mode"] == "enforce" and state["calibrated"] is True

    def test_live_mode_refuses_without_worker_and_says_why(self, tmp_path):
        d = _dataset(tmp_path, n_good=2, n_drop=2)
        _run("freeze-dataset", "--dir", d)
        p = _run("run-benchmark", "--dataset", d, "--mode", "live", expect_fail=True)
        msg = (p.stdout + p.stderr).lower()
        assert "worker" in msg and ("will not fabricate" in msg or "never substitutes" in msg)
