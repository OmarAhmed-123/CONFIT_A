# VTON benchmark harness

Reproducible, offline-by-default evaluation of virtual try-on candidates against the
acceptance rubric in [`docs/tryon/00-research-plan.md`](../../../docs/tryon/00-research-plan.md).
**Not on the production request path** — nothing here is imported by the API or the
worker.

## Honesty invariants (enforced in code)

- The default run is a **dry run**: it exercises manifest → runner → report and
  produces **no** try-on image (`is_render=False`). The scorer refuses to emit quality
  scores for any non-render, so a dry run or a gated adapter can never look like a result.
- Real candidates are **gated**. A self-hosted model needs a real GPU
  (`VTON_BENCH_ENABLE_GPU=1`); a hosted API needs its key **and**
  `VTON_BENCH_ENABLE_PAID=1`. Enabling without the resource fails loudly — it never
  fabricates or echoes an image.
- A real run refuses cases that lack documented `consent_status`.

## Run (dry run — no GPU, no cost)

```bash
python services/vton-worker/benchmarks/run_benchmark.py
# writes results/results.json and results/report.md; renders=0 by design
```

## Run for real (needs the gates opened — approval/cost)

```bash
# self-hosted incumbent on a GPU host:
VTON_BENCH_ENABLE_GPU=1 python services/vton-worker/benchmarks/run_benchmark.py \
    --manifest datasets/<your-consented-set>.json --no-dry-run

# a hosted API (spends money):
FASHN_API_KEY=... VTON_BENCH_ENABLE_PAID=1 python services/vton-worker/benchmarks/run_benchmark.py --no-dry-run
```

## Layout

| Path | Purpose |
|---|---|
| `adapters/` | one adapter per candidate behind a stable interface (`base.py`); `dryrun.py` is the plumbing self-test; `fashn_segfee_local.py` (GPU-gated) and `hosted_api.py` (paid-gated) are the real ones |
| `harness/manifest.py` | load/validate the dataset manifest; consent + diversity reports |
| `harness/rubric.py` | load the rubric and score — refuses non-renders |
| `harness/metrics.py` | GPU detection; guarded SSIM/LPIPS (deps optional) |
| `harness/runner.py` | orchestrates adapters × cases; records env, seed, GPU |
| `run_benchmark.py` | CLI (dry-run default) |
| `rubric.json` | the acceptance thresholds (from the research plan §3) |
| `datasets/` | manifest schema + example (no image bytes); sourcing + consent guide |
| `tests/` | offline plumbing tests (no GPU, no network) |

## Reproducibility

Pinned seed, identical inputs per candidate, recorded GPU (or its absence), committed
raw outputs and scores, reported variance. See the research plan for the full method,
the licensing protocol, and the resource/approval gates.
