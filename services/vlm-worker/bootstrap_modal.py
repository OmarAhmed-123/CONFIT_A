"""One-off, DETERMINISTIC population of the Qwen2.5-VL-7B weights into the Modal
Volume `confit-qwen25vl-weights`.

This is a CPU job (no GPU) and downloads in Modal's infrastructure, so no multi-GB
weights ever touch git or a developer laptop. Idempotent: snapshot_download caches
by the pinned revision, so re-running skips already-present files.

Run:
    modal run services/vlm-worker/bootstrap_modal.py

Self-contained (inlines the pinned spec) so `modal run` has no import-path issues.
"""
import os

import modal

# --- Pinned model spec (single source of truth: see model_spec.py) ----------
MODEL_REPO_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
MODEL_REVISION = "cc594898137f460bfe9f0759e9844b3ce807cfb5"  # Apache-2.0
MIN_TOTAL_BYTES = 16_000_000_000  # ~16 GB (BF16); fail if smaller
# The repo has no root LICENSE file (Apache-2.0 is the model-card tag); these 14
# files are exactly what from_pretrained + the processor need.
REQUIRED_FILES = (
    "config.json",
    "generation_config.json",
    "chat_template.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "model-00001-of-00005.safetensors",
    "model-00002-of-00005.safetensors",
    "model-00003-of-00005.safetensors",
    "model-00004-of-00005.safetensors",
    "model-00005-of-00005.safetensors",
    "model.safetensors.index.json",
)

app = modal.App("confit-vlm-bootstrap")
vol = modal.Volume.from_name("confit-qwen25vl-weights", create_if_missing=True)
image = modal.Image.debian_slim(python_version="3.11").pip_install("huggingface_hub>=0.24.0")


@app.function(image=image, volumes={"/weights": vol}, timeout=1800)
def populate():
    from huggingface_hub import snapshot_download

    print(f"[bootstrap] volume space: {os.popen('df -h /weights 2>/dev/null | tail -1').read().strip()}", flush=True)
    print(f"[bootstrap] downloading {MODEL_REPO_ID} @ {MODEL_REVISION} -> /weights", flush=True)
    snapshot_download(repo_id=MODEL_REPO_ID, revision=MODEL_REVISION, local_dir="/weights")

    missing = [n for n in REQUIRED_FILES if not os.path.isfile(os.path.join("/weights", n))]
    total = sum(
        os.path.getsize(os.path.join("/weights", f))
        for f in os.listdir("/weights")
        if os.path.isfile(os.path.join("/weights", f))
    )
    print(f"[bootstrap] total_bytes={total} ({total / 1024**3:.2f} GB)", flush=True)
    if missing:
        print(f"[bootstrap] MISSING FILES: {missing}", flush=True)
        raise SystemExit(1)
    if total < MIN_TOTAL_BYTES:
        print(f"[bootstrap] TOTAL TOO SMALL (expected >~{MIN_TOTAL_BYTES / 1024**3:.0f} GB)", flush=True)
        raise SystemExit(1)
    print("[bootstrap] WEIGHTS COMPLETE", flush=True)
