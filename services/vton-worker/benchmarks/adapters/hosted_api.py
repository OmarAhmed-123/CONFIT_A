"""Hosted try-on API adapter (paid-key-gated stub).

One class covers FASHN API / Kling / fal.ai / Gemini-image / Replicate: each is a
HostedApiAdapter with its own env key. Disabled unless the key is present AND paid
calls are explicitly opted into, because benchmarking a hosted model spends money.
"""

from __future__ import annotations

import os

from .base import RenderResult, VTONBenchmarkAdapter


class HostedApiAdapter(VTONBenchmarkAdapter):
    requires_paid_api = True

    def __init__(self, name: str, env_key: str, *, license: str = "commercial (vendor terms — verify)", version: str = "live-api") -> None:
        self.name = name
        self.env_key = env_key
        self.license = license
        self.version = version

    def available(self) -> tuple[bool, str]:
        if not os.environ.get(self.env_key):
            return (False, f"requires {self.env_key} (paid API; approval gate)")
        if os.environ.get("VTON_BENCH_ENABLE_PAID") != "1":
            return (False, "paid calls disabled; set VTON_BENCH_ENABLE_PAID=1 to allow (approval gate)")
        return (True, "paid adapter enabled")

    def render(self, case: dict, out_dir: str, seed: int) -> RenderResult:
        ok, reason = self.available()
        if not ok:
            return RenderResult(self.name, case["id"], is_render=False, error=f"GATED: {reason}")
        raise NotImplementedError(
            f"Implement the {self.name} vendor call once {self.env_key} is provisioned "
            "and paid calls are approved; record cost_usd per render."
        )
