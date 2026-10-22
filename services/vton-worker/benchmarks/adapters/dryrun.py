"""Dry-run adapter: plumbing self-test only, never a renderer."""

from __future__ import annotations

from .base import RenderResult, VTONBenchmarkAdapter


class DryRunAdapter(VTONBenchmarkAdapter):
    """Exercises manifest -> runner -> report WITHOUT a GPU, a paid call, or a
    fabricated render. It deliberately produces NO image (is_render=False) so the
    harness can be validated offline and a dry run can never be read as a result.
    """

    name = "dryrun"
    version = "0"
    license = "n/a (no model invoked)"

    def available(self) -> tuple[bool, str]:
        return (True, "plumbing self-test; not a renderer")

    def render(self, case: dict, out_dir: str, seed: int) -> RenderResult:
        return RenderResult(
            candidate=self.name,
            case_id=case["id"],
            is_render=False,
            error="DRY RUN: no model invoked (plumbing self-test)",
            meta={"seed": seed, "category": case.get("category")},
        )
