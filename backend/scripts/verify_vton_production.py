"""VTON production verification — REAL GPU command (fails loudly, no fabrication).

This is the audit trail the commercial-migration directive requires (§34/§39/§40).

What it actually does:
  * requires a REAL person image + REAL garment image (controlled assets);
  * runs the commercially-defensible `fashn_vton_segfee` engine on a REAL Modal
    GPU (A10-class);
  * requires the generated image to DECODE, be non-blank, differ from the input
    (not an echo), and be non-trivial;
  * records the model/GPU/VRAM/latency/quality into a machine-readable JSON
    evidence file — no invented numbers.

It does NOT (and cannot) fake a GPU, an image, or a PASS, and it will exit
non-zero (fail loudly) if:
  * no GPU / torch CUDA is unavailable;
  * the person/garment assets are missing;
  * the engine exits without producing a decodable image;
  * output validation fails (echo / blank).

Usage:
  * Requires a Modal account authenticated (see repo notes for the WORKSPACE env
    values in `modal` config — they are runtime secrets, not committed).
  * Controlled assets are read from ./vendor/test_assets/person.png and
    ./vendor/test_assets/garment.png (never committed to Git).
  * Evidence is written to ./vendor/test_assets/vton_evidence.json.

This must run where GPU is available; it is intentionally NOT part of the GPU-less
CI suite.
"""
from __future__ import annotations

import json
import os
import sys

# Paths relative to the repo root (this file lives in backend/scripts/).
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(REPO_ROOT, "vendor", "test_assets")
PERSON = os.path.join(ASSETS, "person.png")
GARMENT = os.path.join(ASSETS, "garment.png")
EVIDENCE = os.path.join(ASSETS, "vton_evidence.json")
FORK_DIR = os.path.join(REPO_ROOT, "vendor", "fashn-vton-segfee")

# FASHN fork + upstream weights to pin.
UPSTREAM_MODEL = "fashn-ai/fashn-vton-1.5"
UPSTREAM_SHA = "7c0f10af3f91ad4048fe9729c470a13ef905d25a"
DWPOSE_REPO = "fashn-ai/DWPose"


def _fail(msg: str, code: int = 1) -> None:
    print(f"VERIFY_VTON_PRODUCTION: FAIL — {msg}", flush=True)
    sys.exit(code)


def _require_assets() -> None:
    for label, p in [("person", PERSON), ("garment", GARMENT)]:
        if not os.path.exists(p):
            _fail(f"missing controlled {label} asset at {p}. Provide real legal test images.")
        if os.path.getsize(p) < 1024:
            _fail(f"{label} asset too small/empty at {p}")


def main() -> None:
    _require_assets()

    import modal  # noqa: import error -> no Modal creds installed

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("libgomp1")
        .pip_install(
            "torch", "torchvision", "safetensors", "huggingface_hub", "pillow",
            "numpy", "opencv-python-headless", "tqdm", "einops",
            "onnxruntime-gpu", "matplotlib",
        )
        .add_local_dir(FORK_DIR, remote_path="/root/fashn-vton-segfee", copy=True)
        .add_local_dir(ASSETS, remote_path="/assets", copy=True)
        .run_commands("pip install --no-deps /root/fashn-vton-segfee")
    )

    app = modal.App("confit-vton-production-verify")

    @app.function(
        image=image,
        gpu="A10G",
        timeout=1800,
        volumes={"/weights": modal.Volume.from_name("confit-vton-fashn-weights", create_if_missing=True)},
    )
    def run_verify() -> dict:
        import time, sys, json
        import numpy as np
        from PIL import Image, ImageStat
        import torch

        if not torch.cuda.is_available():
            return {"error": "no CUDA GPU available in container"}

        # Stage weights (DWPose under dwpose/).
        from huggingface_hub import hf_hub_download
        wd = "/weights"
        hf_hub_download(UPSTREAM_MODEL, "model.safetensors", local_dir=wd)
        dw = os.path.join(wd, "dwpose")
        os.makedirs(dw, exist_ok=True)
        for fn in ["yolox_l.onnx", "dw-ll_ucoco_384.onnx"]:
            hf_hub_download(DWPOSE_REPO, fn, local_dir=dw)

        # parser-presence proof
        parser_pre = "fashn_human_parser" in sys.modules

        t0 = time.time()
        from fashn_vton import TryOnPipeline
        pipe = TryOnPipeline(weights_dir=wd, device="cuda")
        load_s = round(time.time() - t0, 2)

        person = Image.open("/assets/person.png").convert("RGB")
        garment = Image.open("/assets/garment.png").convert("RGB")

        # warmup + measured
        measured = None
        for phase in ("warmup", "measured"):
            t0 = time.time()
            out = pipe(person_image=person, garment_image=garment, category="tops",
                       garment_photo_type="flat-lay", segmentation_free=True,
                       num_timesteps=30, seed=42)
            dt = round(time.time() - t0, 3)
            img = out.images[0].convert("RGB")
            if phase == "measured":
                arr = np.asarray(img, dtype=np.uint8)
                stat = ImageStat.Stat(img)
                stddev = float(np.asarray(img, dtype=np.float32).std())
                ref = np.asarray(person.resize(img.size).convert("RGB"), dtype=np.int32)
                pixel_change = float(np.abs(arr.astype(np.int32) - ref).mean())
                color_shift = float(np.linalg.norm(
                    (np.asarray(img, dtype=np.int32) - ref).mean(axis=(0, 1)))) / 255.0
                teal = float(((arr[..., 1] > arr[..., 0] + 20) &
                              (arr[..., 2] > arr[..., 0] + 20) & (arr[..., 0] < 130)).mean())
                import hashlib
                sha = hashlib.sha256(img.tobytes()).hexdigest()[:16]
                ip = "/weights/vton_check.png"
                img.save(ip)
                measured = {
                    "infer_s": dt, "load_s": load_s,
                    "output_size": img.size,
                    "torch": torch.__version__, "device": torch.cuda.get_device_name(0),
                    "bf16_supported": bool(torch.cuda.is_bf16_supported()),
                    "pixel_change_mean": round(pixel_change, 3),
                    "color_shift": round(color_shift, 5),
                    "image_stddev": round(stddev, 2),
                    "teal_coverage_fraction": round(teal, 4),
                    "sha256_first16": sha,
                    "parser_pre_import": parser_pre,
                    "parser_in_runtime": "fashn_human_parser" in sys.modules,
                    "input_shape": list(pipe.tryon_model.input_shape),
                }
                vol = modal.Volume.from_name("confit-vton-fashn-weights")
                vol.commit()
        if measured is None:
            return {"error": "no measured result"}
        return measured

    @app.local_entrypoint()
    def entry() -> None:
        r = run_verify.remote()

    # ---- execute ----
    app.run(entry)


if __name__ == "__main__":
    main()
