"""Environment capture and optional image metrics.

Importing this module must NOT require torch/skimage/lpips — those are needed only
to score real renders on a GPU host (see requirements-bench.txt). Each metric
returns a reason string instead of raising when its dependency is absent, so the
scaffold runs offline with nothing installed.
"""

from __future__ import annotations

import shutil
import subprocess


def detect_gpu() -> dict:
    """Report the GPU via nvidia-smi, or say plainly there is none."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"gpu": None, "detail": "nvidia-smi not found (no NVIDIA GPU visible)"}
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        return {"gpu": (out.stdout.strip() or None), "detail": "nvidia-smi"}
    except Exception as exc:  # noqa: BLE001
        return {"gpu": None, "detail": f"nvidia-smi failed: {type(exc).__name__}"}


def ssim(a_path: str, b_path: str) -> dict:
    try:
        import numpy as np
        from PIL import Image
        from skimage.metrics import structural_similarity as _ssim
    except Exception as exc:  # noqa: BLE001
        return {"value": None, "reason": f"metric deps absent: {type(exc).__name__} (see requirements-bench.txt)"}
    try:
        a = np.asarray(Image.open(a_path).convert("L"))
        b = np.asarray(Image.open(b_path).convert("L"))
        return {"value": float(_ssim(a, b))}
    except Exception as exc:  # noqa: BLE001
        return {"value": None, "reason": f"ssim failed: {type(exc).__name__}: {exc}"}


def lpips_score(a_path: str, b_path: str) -> dict:
    try:
        import lpips  # noqa: F401
        import torch  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return {"value": None, "reason": f"lpips/torch absent: {type(exc).__name__} (see requirements-bench.txt)"}
    # Deliberately not implemented in the scaffold: wiring LPIPS belongs on the
    # GPU host where the models actually run.
    return {"value": None, "reason": "lpips scoring is implemented on the GPU host, not in the scaffold"}
