#!/usr/bin/env python3
"""One-off, deterministic population of the Qwen2.5-VL-7B weights into a directory.

Usage:
    python bootstrap_weights.py <target_dir>

Downloads the PINNED revision (model_spec.MODEL_REVISION), verifies the file set
+ total size, and prints a SHA256 manifest for audit. Idempotent. Fails loudly if
the acquisition is incomplete — it never leaves a partial set.

Requires huggingface_hub. The model is NOT gated (no HF token required).
"""
from __future__ import annotations

import os
import sys

from acquire import WeightsError, download_weights, manifest


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python bootstrap_weights.py <target_dir>", file=sys.stderr)
        return 2
    target = os.path.abspath(sys.argv[1])
    print(f"[bootstrap] downloading pinned Qwen2.5-VL-7B -> {target}", flush=True)
    try:
        download_weights(target)
    except WeightsError as exc:
        print(f"[bootstrap] FAILED: {exc}", file=sys.stderr)
        return 1
    print("[bootstrap] weights complete. SHA256 manifest:", flush=True)
    for name, digest in sorted(manifest(target).items()):
        print(f"  {name}: {digest}", flush=True)
    print("[bootstrap] OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
