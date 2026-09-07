"""Deterministic acquisition + integrity validation of the Qwen2.5-VL weights.

Produces a complete, reproducible local copy of the *pinned* model into a target
directory (e.g. a Modal Volume mount). Idempotent. Fails honestly (raises
:class:`WeightsError`) if the download is incomplete or a file is missing.

Production flow (no laptop, no untracked cache, no /tmp):

1. Populate a Modal Volume (``confit-qwen25vl-weights``) by running
   ``bootstrap_weights.py`` once (an authenticated one-off run, or a Modal job), OR
2. Mount an already-populated volume at ``WEIGHTS_DIR``.
"""
from __future__ import annotations

import hashlib
import os
from typing import Dict, List

from model_spec import (
    EXPECTED_TOTAL_BYTES,
    MIN_TOTAL_BYTES,
    MODEL_REVISION,
    MODEL_REPO_ID,
    REQUIRED_FILES,
)


class WeightsError(RuntimeError):
    """Weights are missing, incomplete, or corrupt."""


def download_weights(target_dir: str) -> str:
    """Deterministically download the pinned model into ``target_dir`` (idempotent)."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover
        raise WeightsError("huggingface_hub is required to acquire weights (see requirements.txt)") from exc

    os.makedirs(target_dir, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_REPO_ID,
        revision=MODEL_REVISION,
        local_dir=target_dir,
    )
    problems = validate_weights(target_dir)
    if problems:
        raise WeightsError("weight acquisition incomplete: " + "; ".join(problems))
    return target_dir


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_weights(target_dir: str) -> List[str]:
    """Return a list of problems (empty == OK). Never raises on a missing file."""
    problems: List[str] = []
    if not os.path.isdir(target_dir):
        return [f"weights dir missing: {target_dir}"]
    total = 0
    for name in REQUIRED_FILES:
        p = os.path.join(target_dir, name)
        if not os.path.isfile(p):
            problems.append(f"missing file: {name}")
            continue
        total += os.path.getsize(p)
    if not problems and total < MIN_TOTAL_BYTES:
        problems.append(
            f"total size {total} bytes < expected ~{EXPECTED_TOTAL_BYTES} bytes (truncated download?)"
        )
    return problems


def manifest(target_dir: str) -> Dict[str, str]:
    """SHA256 manifest of the acquired weights (for audit / integrity checks)."""
    out: Dict[str, str] = {}
    for name in REQUIRED_FILES:
        p = os.path.join(target_dir, name)
        if os.path.isfile(p):
            out[name] = _sha256(p)
    return out
