"""Adapter contract shared by every try-on candidate."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RenderResult:
    """One candidate's attempt at one test case.

    ``is_render`` is the honesty flag: it is True ONLY when a real try-on image
    was produced by a real model. A dry run, a gated adapter, or an error all
    yield ``is_render=False`` with a reason in ``error``. The scorer refuses to
    score a set that contains any non-render.
    """

    candidate: str
    case_id: str
    is_render: bool
    output_path: Optional[str] = None
    latency_s: Optional[float] = None
    cold_start_s: Optional[float] = None
    vram_gib: Optional[float] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None
    meta: dict = field(default_factory=dict)


class VTONBenchmarkAdapter(abc.ABC):
    """A benchmark candidate. Subclasses declare identity + resource needs and
    implement ``render``; ``available()`` decides whether the gate is open."""

    name: str = "base"
    version: str = "unset"
    license: str = "unset"
    requires_gpu: bool = False
    requires_paid_api: bool = False

    def available(self) -> tuple[bool, str]:
        """(enabled, reason). Default: disabled — real candidates must opt in."""
        return (False, "not enabled in scaffold")

    def warmup(self) -> None:
        """Optional: load weights / open a warm container. No-op by default."""
        return None

    @abc.abstractmethod
    def render(self, case: dict, out_dir: str, seed: int) -> RenderResult:
        """Produce a try-on image for one case, or an honest non-render result."""
        raise NotImplementedError
