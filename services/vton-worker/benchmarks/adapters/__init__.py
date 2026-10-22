"""Benchmark candidate adapters.

Each adapter wraps one try-on candidate behind a stable interface so the runner
treats a self-hosted model and a hosted API identically. Real adapters are GATED
(disabled unless a GPU / paid key is provisioned and explicitly opted into); the
DryRunAdapter exists only to exercise the harness plumbing without any inference.
"""

from .base import RenderResult, VTONBenchmarkAdapter
from .dryrun import DryRunAdapter
from .fashn_segfee_local import FashnSegfeeLocalAdapter
from .hosted_api import HostedApiAdapter

__all__ = [
    "RenderResult",
    "VTONBenchmarkAdapter",
    "DryRunAdapter",
    "FashnSegfeeLocalAdapter",
    "HostedApiAdapter",
]
