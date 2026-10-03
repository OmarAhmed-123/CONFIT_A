# ==============================================================================
# CONFIT VTON WORKER — BASETEN SHELL (feature 03, multi-garment)
#
# Serves the SHARED HTTP layer (server_core.py) on Baseten as a custom Docker
# container (no-build mode): uvicorn starts this app, Baseten's router maps
#
#     https://model-<id>.api.baseten.co/environments/production/sync/health
#     https://model-<id>.api.baseten.co/environments/production/sync/readiness
#     https://model-<id>.api.baseten.co/environments/production/sync/process
#
# 1:1 onto this app's routes. The API service derives exactly those paths from
# VTON_WORKER_URL=<...>/sync (see TryOnService._derive_worker_urls), so the
# cutover is a URL change, not a code change.
#
# Engine lifecycle mirrors modal_app_v15.py @modal.enter: load once at boot on
# cuda; a failed load leaves the app UP and honestly degraded (health reports
# model_loaded=false + load_error; readiness 503s) — never a fake success.
#
# The X-VTON-Admin token is read from the env or from the Baseten secrets file
# mount (/secrets/confit-worker-admin-token/...); it is NEVER baked into the
# image and NEVER logged.
# ==============================================================================

from __future__ import annotations

import os
import sys

# Make the engine adapter importable (baked at /app/vton-worker) and point the
# engine at the vendored pristine upstream (baked at /app/vendor/fashn-vton-1.5).
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, "/app/vton-worker", "/app/vendor/fashn-vton-1.5"):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("FASHN_V15_VENDOR_DIR", "/app/vendor/fashn-vton-1.5")

WEIGHTS_DIR = os.environ.get("VTON_WEIGHTS_DIR", "/app/weights")

import server_core  # noqa: E402  (path set above)


class _BasetenEngineHolder:
    """Owns the loaded engine — the same duck-typed surface the Modal class
    exposes (engine / model_loaded / load_error / device_name)."""

    def __init__(self) -> None:
        self.engine = None
        self.model_loaded = False
        self.load_error = None
        self.device_name = None

    def load(self) -> None:
        try:
            import torch

            from engine import get_engine

            engine_cls = get_engine("fashn_v15")
            if engine_cls is None:
                raise RuntimeError("fashn_v15 engine is not registered")
            engine = engine_cls(weights_dir=WEIGHTS_DIR, device="cuda")
            engine.load()
            self.engine = engine
            self.device_name = (
                torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
            )
            self.model_loaded = True
            print(f"[load] fashn_v15 loaded on {self.device_name}", flush=True)
            if torch.cuda.is_available():
                print(
                    f"[load] GPU memory allocated={torch.cuda.memory_allocated()/1024**3:.2f}GB "
                    f"reserved={torch.cuda.memory_reserved()/1024**3:.2f}GB",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001 — honest degradation, never crash
            import traceback as _tb

            self.engine = None
            self.model_loaded = False
            self.load_error = f"{type(exc).__name__}: {exc}"
            _tb.print_exc()
            print(f"[load] MODEL LOAD FAILED: {self.load_error}", flush=True)


_holder = _BasetenEngineHolder()
_holder.load()  # at boot: one load per replica, never per request

app = server_core.create_app(_holder)
