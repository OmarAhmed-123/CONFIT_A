"""Incumbent self-hosted engine adapter (GPU-gated stub).

Wraps the production engine (services/vton-worker/engine FashnSegfeeVTONEngine).
Left unimplemented in the no-GPU scaffold ON PURPOSE: wiring it to the real
pipeline requires a GPU host, which is an approval/cost gate. Enabling it without
a GPU must fail loudly, never silently echo an input as if it were a render.
"""

from __future__ import annotations

import os

from .base import RenderResult, VTONBenchmarkAdapter


class FashnSegfeeLocalAdapter(VTONBenchmarkAdapter):
    name = "fashn_vton_segfee"
    version = "7c0f10af (vendored fork)"
    license = "Apache-2.0 (segmentation-free fork; non-commercial parser removed)"
    requires_gpu = True

    def available(self) -> tuple[bool, str]:
        if os.environ.get("VTON_BENCH_ENABLE_GPU") != "1":
            return (
                False,
                "requires a real GPU; provision one and set VTON_BENCH_ENABLE_GPU=1 "
                "(approval/cost gate)",
            )
        return (True, "gpu adapter enabled")

    def render(self, case: dict, out_dir: str, seed: int) -> RenderResult:
        ok, reason = self.available()
        if not ok:
            return RenderResult(self.name, case["id"], is_render=False, error=f"GATED: {reason}")
        # Intentionally not implemented in the scaffold: the real call binds to
        # services/vton-worker/engine on a GPU host. Fail loudly rather than fake.
        raise NotImplementedError(
            "Wire to services/vton-worker/engine on a GPU host before enabling; "
            "the no-GPU scaffold must not fabricate a render."
        )
