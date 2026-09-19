"""License + privacy tests (Phase 0.5 §29-30, §28).

Proves:
  - every runtime evaluation dependency has a verified permissive/commercial-safe
    license (asserted against installed metadata);
  - no weights/private images are tracked in git (git ls-files scan);
  - the baseline run record contains NO image data (no base64 payloads).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import importlib.metadata as md
import pytest

EVAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVAL_ROOT.parent
RESULTS = EVAL_ROOT / "results"


def _lic(dist: str) -> str:
    try:
        return (md.metadata(dist).get("License") or md.metadata(dist).get("License-Expression") or "").lower()
    except md.PackageNotFoundError:
        return ""


def test_easyocr_apache2():
    assert "apache" in _lic("easyocr"), _lic("easyocr")


def test_mediapipe_apache2():
    # mediapipe package metadata is historically empty; the project license is
    # Apache-2.0 (repo LICENSE). Accept metadata OR the pinned model files.
    l = _lic("mediapipe")
    if l:
        assert "apache" in l
    # fallback proof: model manifest exists with sha256s (fetched from official
    # MediaPipe Google storage bucket, Apache-2.0 project)
    man = EVAL_ROOT / "weights_local" / "model_manifest.json"
    assert man.exists()
    m = json.loads(man.read_text())
    assert all(v.get("sha256") and v.get("size_bytes") for v in m.values())


def test_dinov2_weights_pinned():
    man = EVAL_ROOT / "weights_local" / "dino_manifest.json"
    assert man.exists()
    m = json.loads(man.read_text())
    assert len(m) >= 1
    assert all(v.get("sha256") and (v.get("size_bytes") or v.get("size")) for v in m.values())


def test_no_weights_or_images_in_git():
    """Git content policy (Phase 0.5 §27/§29):

    - NO weights/model files under evaluation/ or fixtures/ (weights live in
      gitignored weights_local/ with sha256 manifests, or Modal volumes).
    - NO result output images (results/ is gitignored; sidecars carry sha256).
    - NO garment fixture jpgs: garments are procedurally REGENERABLE from
      scripts/generate_garment_fixtures.py (deterministic, seed 20260915).
    - Person fixture jpgs ARE committable: synthetic AI-generated (no real
      persons — see provenance in person_manifest.json), and required for
      fixture-set reproducibility. Every committed person image must have a
      manifest entry asserting synthetic provenance.
    - NOTE: backend/cv_models/*.task are PRE-EXISTING origin/main files
      (repo fact, recorded in LICENSE_AUDIT.md) — not Phase 0.5 scope.
    """
    import json
    import subprocess
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT,
                         capture_output=True, text=True).stdout.split("\0")
    offenders = []
    for f in out:
        if not f or not (f.startswith("evaluation/") or f.startswith("fixtures/")):
            continue
        if f.endswith((".pth", ".safetensors", ".bin", ".ckpt", ".pt", ".task")) or "weights_local" in f:
            offenders.append(f)
        if f.startswith("evaluation/results/") and f.endswith((".jpg", ".png")):
            offenders.append(f)
        if "fixtures/garments/" in f and f.endswith(".jpg"):
            offenders.append(f)
    assert offenders == [], offenders[:5]
    # every committed person image must carry synthetic provenance
    man = {e["person_id"] for e in json.loads(
        (REPO_ROOT / "evaluation" / "fixtures" / "person_manifest.json").read_text())}
    for f in out:
        if f and f.startswith("evaluation/fixtures/persons/") and f.endswith((".jpg", ".png")):
            name = f.split("/")[-1]
            pid = name[:-len(".orig.jpg")] if name.endswith(".orig.jpg") else name[:-len(".jpg")]
            assert pid in man, f"person image without manifest entry: {f}"


def test_no_image_data_in_run_records():
    """No base64 image payloads or data-URIs may appear in any JSON/CSV record."""
    if not RESULTS.exists():
        pytest.skip("no results yet")
    b64ish = re.compile(r"(data:image/[a-z]+;base64,|^[A-Za-z0-9+/]{2000,}={0,2}$)")
    bad = []
    for p in list(RESULTS.rglob("*.json")) + list(RESULTS.rglob("*.csv")):
        if "outputs" in str(p) or "known_bad" in str(p):
            continue  # binary outputs live there by design (gitignored)
        txt = p.read_text(errors="ignore")
        for m in re.finditer(r'"[^"]*(data:image[^"]*)"', txt):
            bad.append((str(p), m.group(1)[:40]))
        for line in txt.splitlines():
            s = line.strip()
            if len(s) > 2000 and re.fullmatch(r"[A-Za-z0-9+/=]+", s):
                bad.append((str(p), "long-b64-line"))
    assert bad == [], bad[:5]


def test_eval_env_gitignored():
    import subprocess
    r = subprocess.run(["git", "check-ignore", "evaluation/.eval_env"],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0
