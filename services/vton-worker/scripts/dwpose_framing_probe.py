"""One-off DWPose probe for the person-framing gate. NOT deployed.

Runs the *real* DWPose model from the vendored fork over a folder of test
uploads and reports, per image, what the framing gate decides and which
keypoints the detector actually saw. `modal run` makes this an ephemeral app:
it starts containers, returns the data, and shuts down — the deployed
`confit-vton-worker` app is untouched.

Why a GPU job at all: DWPose is an ONNX model with weights that only exist in
the worker image and the `confit-vton-fashn-weights` volume. There is no way to
produce honest keypoints locally, and inventing them would defeat the point of
the gate.

Usage
-----
    set -a; . .secrets/deploy.env; set +a          # MODAL_TOKEN_ID / SECRET
    CORPUS_DIR=$HOME/vton_evidence/framing_corpus \\
        modal run --detach services/vton-worker/scripts/dwpose_framing_probe.py

Writes `framing_probe.json` (verdicts + keypoints) and `framing_overlays/*.png`
(skeleton drawn on the input) next to the corpus directory.
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path

import modal

def _find_repo_root(start: Path) -> Path:
    """Locate the repo when running locally.

    This module is ALSO imported inside the container (Modal mounts the script
    at /root/), where the repo layout does not exist. Only the local client ever
    uses these paths — image build steps run client-side — so a harmless
    fallback is enough and must never raise.
    """
    for candidate in (start, *start.parents):
        if (candidate / "vendor" / "fashn-vton-segfee").is_dir():
            return candidate
    return Path("/root")


_REPO = _find_repo_root(Path(__file__).resolve())
_FORK = _REPO / "vendor" / "fashn-vton-segfee"
_WORKER = _REPO / "services" / "vton-worker"
CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", Path.home() / "vton_evidence" / "framing_corpus"))

app = modal.App("confit-framing-probe")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgomp1", "libgl1-mesa-glx", "libglib2.0-0")
    # CPU-only on purpose: DWPose is ONNX, so the keypoints do not need a GPU.
    # (Ephemeral GPU functions are payment-gated on this workspace; the deployed
    # worker's A10G is unaffected.) torch is required by the fork's imports even
    # though DWPose itself only needs onnxruntime — install the CPU wheel.
    .pip_install(
        "torch", "torchvision", "safetensors", "huggingface_hub", "pillow",
        "numpy", "opencv-python-headless", "tqdm", "einops", "onnxruntime",
        "matplotlib",
        index_url="https://download.pytorch.org/whl/cpu",
        extra_index_url="https://pypi.org/simple",
    )
    .add_local_dir(str(_FORK), remote_path="/root/fashn-vton-segfee", copy=True)
    .add_local_file(str(_WORKER / "vton_framing.py"), remote_path="/root/vton-worker/vton_framing.py", copy=True)
    .add_local_dir(str(CORPUS_DIR), remote_path="/corpus", copy=True)
    .run_commands("pip install --no-deps /root/fashn-vton-segfee")
    .env({"PYTHONPATH": "/root/fashn-vton-segfee:/root/vton-worker"})
)


@app.function(
    image=image,
    cpu=4,
    timeout=900,
    volumes={"/weights": modal.Volume.from_name("confit-vton-fashn-weights")},
)
def probe() -> dict:
    import sys
    import time

    import numpy as np
    from PIL import Image, ImageDraw

    from fashn_vton.dwpose import DWposeDetector, draw_pose
    from vton_framing import assess_person_framing

    t0 = time.time()
    detector = DWposeDetector(checkpoints_dir="/weights/dwpose", device="cpu")
    load_seconds = round(time.time() - t0, 2)

    results = {}
    for path in sorted(Path("/corpus").iterdir()):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        image_pil = Image.open(path).convert("RGB")

        t1 = time.time()
        pose = detector(np.array(image_pil)[..., ::-1])   # BGR, as pipeline.py does
        detect_seconds = round(time.time() - t1, 3)

        verdict = assess_person_framing(pose)

        # Labelled overlay: index printed next to every point the fork keeps.
        # The fork returns `subset` as sentinel indices (int(18*i+j), or -1), not
        # confidences, and remaps keypoint order — so the only trustworthy way to
        # know which index means what is to look at where it landed.
        labelled = image_pil.copy()
        labelled.thumbnail((900, 900))
        draw_canvas = ImageDraw.Draw(labelled)
        _b = np.asarray(pose["bodies"]["candidate"], dtype=np.float32)
        _b = _b.reshape(-1, 18, 2)[0]
        for _i in range(18):
            _x, _y = float(_b[_i, 0]), float(_b[_i, 1])
            if _x < 0 or _y < 0:
                continue
            px, py = _x * labelled.width, _y * labelled.height
            draw_canvas.ellipse([px - 4, py - 4, px + 4, py + 4], outline=(255, 0, 0), width=2)
            draw_canvas.text((px + 5, py - 5), str(_i), fill=(255, 220, 0))
        small = io.BytesIO()
        labelled.save(small, format="PNG")

        # Skeleton overlay: the visual proof of what was detected.
        overlay = draw_pose(pose, image_pil.height, image_pil.width, grayscale=False)
        overlay = Image.fromarray(overlay.astype(np.uint8)).convert("RGB")
        overlay.thumbnail((640, 640))
        buf = io.BytesIO()
        overlay.save(buf, format="PNG")

        bodies = pose["bodies"]
        cand_arr = np.asarray(bodies["candidate"], dtype=np.float32)
        score_arr = np.asarray(bodies["subset"], dtype=np.float32)
        # DWPose's shapes vary with how many people it kept: (N,18,2) or a
        # single (18,2), and empty arrays when nobody is in frame. Flatten to a
        # 2-D (n,2) view so every case reports the same way.
        if cand_arr.ndim == 3:
            n_cand = int(cand_arr.shape[0])
            cand = cand_arr[0] if n_cand else np.full((18, 2), -1.0)
            score = score_arr[0] if score_arr.ndim == 2 and score_arr.size else np.full((18,), -1.0)
        elif cand_arr.ndim == 2 and cand_arr.shape[0]:
            n_cand = 1
            cand = cand_arr
            score = score_arr if score_arr.ndim == 1 else score_arr.reshape(-1)[:18]
        else:
            n_cand = 0
            cand = np.full((18, 2), -1.0)
            score = np.full((18,), -1.0)

        results[path.name] = {
            "size": list(image_pil.size),
            "detect_seconds": detect_seconds,
            "full_body": verdict["full_body"],
            "code": verdict["code"],
            "evidence": verdict["evidence"],
            "candidates_detected": n_cand,
            # Every one of the 18, including the ones DWPose left at -1: the
            # scores are the evidence for whether a leg keypoint is real.
            "keypoints": {
                str(i): [round(float(cand[i, 0]), 4), round(float(cand[i, 1]), 4),
                         round(float(score[i]), 4)]
                for i in range(min(18, cand.shape[0]))
            },
            "overlay_png_b64": base64.b64encode(buf.getvalue()).decode(),
            "labelled_png_b64": base64.b64encode(small.getvalue()).decode(),
        }

    return {
        "model_load_seconds": load_seconds,
        "compute": "cpu:4",
        "images": results,
    }


@app.local_entrypoint()
def main(out_dir: str = ""):
    payload = probe.remote()
    out = Path(out_dir) if out_dir else CORPUS_DIR.parent
    out.mkdir(parents=True, exist_ok=True)

    overlays = out / "framing_overlays"
    overlays.mkdir(exist_ok=True)

    summary = {"model_load_seconds": payload["model_load_seconds"], "images": {}}
    for name, row in payload["images"].items():
        b64 = row.pop("overlay_png_b64")
        (overlays / f"{Path(name).stem}_pose.png").write_bytes(base64.b64decode(b64))
        (overlays / f"{Path(name).stem}_labelled.png").write_bytes(
            base64.b64decode(row.pop("labelled_png_b64")))
        summary["images"][name] = row
        print(f"{name:42s} full_body={row['full_body']!s:5s} code={row['code']} "
              f"lowest={row['evidence'].get('lowest_region')} t={row['detect_seconds']}s")

    (out / "framing_probe.json").write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {out / 'framing_probe.json'} and {overlays}/")
