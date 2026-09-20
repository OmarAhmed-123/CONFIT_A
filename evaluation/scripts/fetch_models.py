"""Fetch pinned evaluation models to evaluation/weights_local/ (gitignored).

Downloads + records sha256 + size for each artifact. All Apache-2.0:
  - MediaPipe Face Landmarker (478 lm) — model file Apache-2.0 (MediaPipe repo)
  - MediaPipe Pose Landmarker (lite)  — model file Apache-2.0 (MediaPipe repo)
  - DINOv2 ViT-B/14 (facebook/dinov2-base @ refs/pr/10) — Apache-2.0 (repo README)

EasyOCR models are fetched lazily on first EasyOCR use into ~/.EasyOCR
(recorded in LICENSE_AUDIT.md with sizes + sha256 at first run).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

WEIGHTS = Path(__file__).resolve().parent.parent / "weights_local"

MODELS = {
    "face_landmarker.task":
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "pose_landmarker_lite.task":
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
}


def main():
    WEIGHTS.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in MODELS.items():
        p = WEIGHTS / name
        if p.exists():
            print(f"skip (exists): {name}")
        else:
            print(f"downloading {name} ...")
            urllib.request.urlretrieve(url, p)
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest[name] = {"url": url, "sha256": h, "size_bytes": p.stat().st_size}
        print(f"  {name}: {p.stat().st_size} bytes sha256={h[:16]}...")
    (WEIGHTS / "model_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("wrote", WEIGHTS / "model_manifest.json")


if __name__ == "__main__":
    main()
