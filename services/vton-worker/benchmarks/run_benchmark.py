#!/usr/bin/env python3
"""CONFIT VTON benchmark runner (CLI).

Dry-run by default — exercises the plumbing with NO GPU, NO paid calls and NO
rendered images. Enabling a real candidate requires its resource gate to be open
(see README.md): a GPU (`VTON_BENCH_ENABLE_GPU=1`) or a paid key plus
`VTON_BENCH_ENABLE_PAID=1`.

    python services/vton-worker/benchmarks/run_benchmark.py            # dry run
    python services/vton-worker/benchmarks/run_benchmark.py --no-dry-run  # real (needs gates)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # make `adapters` / `harness` importable standalone

from adapters import DryRunAdapter, FashnSegfeeLocalAdapter, HostedApiAdapter  # noqa: E402
from harness.manifest import consent_gaps, diversity_summary, load_manifest  # noqa: E402
from harness.runner import run  # noqa: E402


def build_adapters() -> list:
    """The candidate set. Real ones are gated; dryrun is the plumbing self-test."""
    return [
        DryRunAdapter(),
        FashnSegfeeLocalAdapter(),  # incumbent, GPU-gated
        HostedApiAdapter("fashn_api", "FASHN_API_KEY"),
        HostedApiAdapter("fal_fashn", "FAL_KEY"),
        HostedApiAdapter("kling", "KLING_API_KEY"),
        HostedApiAdapter("gemini_image", "GEMINI_API_KEY", license="Google terms — verify"),
    ]


def write_report(out_dir: Path, result: dict, manifest_data: dict) -> None:
    lines = ["# VTON benchmark run", ""]
    env = result["env"]
    lines += [
        f"- timestamp: {env['timestamp']}",
        f"- GPU: {env['gpu'].get('gpu') or 'none'} ({env['gpu'].get('detail')})",
        f"- dry_run: {env['dry_run']} · gpu_enabled: {env['gpu_enabled']} · paid_enabled: {env['paid_enabled']}",
        f"- cases: {result['summary']['cases']} · adapters: {result['summary']['adapters']}"
        f" · renders: {result['summary']['renders']} · non_renders: {result['summary']['non_renders']}",
        "",
        "## Adapters",
    ]
    for a in result["adapters"]:
        lines.append(f"- **{a['name']}** ({a['license']}) — available: {a['available']} — {a['reason']}")
    lines += ["", "## Diversity of the test set", "```json",
              json.dumps(diversity_summary(manifest_data), indent=2), "```", ""]
    if result["summary"]["renders"] == 0:
        lines += ["## Scores", "",
                  "No real renders were produced (dry run and/or gated adapters), so **no quality "
                  "scores are reported**. This is the honest-failure invariant, not a gap in the run."]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_benchmark")
    p.add_argument("--manifest", default=str(HERE / "datasets" / "manifest.example.json"))
    p.add_argument("--rubric", default=str(HERE / "rubric.json"))
    p.add_argument("--out", default=str(HERE / "results"))
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="attempt real renders (requires the resource gates)")
    p.set_defaults(dry_run=True)
    args = p.parse_args(argv)

    manifest_data = load_manifest(args.manifest)
    gaps = consent_gaps(manifest_data)
    if gaps:
        print(f"WARNING: {len(gaps)} case(s) have no documented consent_status: {gaps}", file=sys.stderr)
        if not args.dry_run:
            print("Refusing a real run over undocumented-consent cases.", file=sys.stderr)
            return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = run(build_adapters(), manifest_data, str(out_dir), seed=args.seed, dry_run=args.dry_run)
    (out_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_report(out_dir, result, manifest_data)
    print(f"wrote {out_dir / 'results.json'} and {out_dir / 'report.md'}")
    print(f"renders={result['summary']['renders']} non_renders={result['summary']['non_renders']} "
          f"(dry_run={args.dry_run})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
