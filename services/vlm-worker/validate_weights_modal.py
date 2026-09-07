"""Lightweight validate-only check of the Qwen weights in the Modal Volume
(no download). Confirms all 14 inference files are present + total size.

Run:  modal run services/vlm-worker/validate_weights_modal.py
"""
import os

import modal

REQUIRED = (
    "config.json",
    "generation_config.json",
    "chat_template.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "model.safetensors.index.json",
    "model-00001-of-00005.safetensors",
    "model-00002-of-00005.safetensors",
    "model-00003-of-00005.safetensors",
    "model-00004-of-00005.safetensors",
    "model-00005-of-00005.safetensors",
)

app = modal.App("confit-vlm-validate")
vol = modal.Volume.from_name("confit-qwen25vl-weights")
image = modal.Image.debian_slim(python_version="3.11")


@app.function(image=image, volumes={"/weights": vol}, timeout=300)
def validate():
    missing = [n for n in REQUIRED if not os.path.isfile(os.path.join("/weights", n))]
    total = sum(
        os.path.getsize(os.path.join("/weights", f))
        for f in os.listdir("/weights")
        if os.path.isfile(os.path.join("/weights", f))
    )
    print(f"[validate] total_bytes={total} ({total / 1024**3:.2f} GiB)", flush=True)
    for n in REQUIRED:
        p = os.path.join("/weights", n)
        print(f"[validate]   {n}: {'MISSING' if not os.path.isfile(p) else os.path.getsize(p)}", flush=True)
    print(f"[validate] MISSING: {missing or 'none'}", flush=True)
    if missing:
        raise SystemExit(1)
    print("[validate] ALL 14 INFERENCE FILES PRESENT", flush=True)
