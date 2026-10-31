# Performance test report — stylist recommendation on PostgreSQL

**Latest run: 2026-10-29 11:08–11:13 UTC** — reproducible with one command:
`./scripts/dev/run_benchmark.sh` (≈ 6 min; needs local PostgreSQL, see
`local-development.md`). Raw report:
`docs/qa/load/stylist_mocked_20vu_postgres17_2workers_5s_20261029.json`.
Method history, bottleneck analysis and earlier runs: `docs/qa/LOAD_TEST_STYLIST.md`.

## Rig (identical to the 2026-10-27 "after fix" run)

* 2 vCPU / 2 GB sandbox; **PostgreSQL 17.11** (native, `confit_bench`, Alembic head 0048)
* API: uvicorn **2 workers**, `WARDROBE_STYLIST_PROVIDER=watsonx` pointed at the
  **watsonx double** (`scripts/load/watsonx_double.py`): IAM + `text/chat` emulation,
  **5.0 s ± 1.5 s** simulated inference, **2 % 503 + 1 % 429 injected**; answers cite
  real closet ids so the backend's id validation is exercised, not bypassed
* Workload (`scripts/load/stylist_load.py`): **20 VUs**, each a fresh user with an
  8-garment closet; **20 recommendations per VU** (rotating occasions,
  `previous_item_ids` chained), every 5th saved, one list at the end. Sign-up is
  paced to the 5/min limit and excluded from timing.
* The double is explicitly labelled a double in the rig; nothing here is presented
  as a live Granite measurement. Live Granite latency: eval 2026-10-28, p50 2.91 s, max 6.21 s.

## Results

| Metric | **2026-10-29** | 2026-10-27 (after fix) | 2026-10-27 (before) | Target |
|---|---|---|---|---|
| recommend p50 | **5.044 s** | 5.114 s | 5.931 s | — |
| recommend p95 | **6.475 s — PASS** | 6.483 s | 8.152 s | ≤ 6.5 s |
| recommend p99 | **10.932 s — FAIL** | 11.499 s | 11.557 s | ≤ 8.0 s |
| recommend mean / max | 5.19 / 12.14 s | 5.23 / 12.69 s | 6.03 / 12.41 s | — |
| add_item p95 | 0.265 s | — | — | — |
| save_outfit p50 / p95 | 0.023 / 0.034 s | 0.02 / 0.03 s | 0.50 / 1.55 s | — |
| list_outfits p95 | 0.014 s | 0.024 s | 0.211 s | — |
| requests / 5xx / 4xx | **660 / 0 / 0** | 660 / 0 / 0 | 660 / 0 / 0 | 0 × 5xx |
| throughput | 5.84 rps | 5.76 rps | 4.73 rps | — |
| wall (timed window) | 113.1 s | 114.7 s | 139.7 s | — |
| provenance | 400 × `watsonx / ibm/granite-4-h-small` | 400 | 400 | 100 % |
| fallbacks / rejected model refs | 0 / 0 | 0 / 0 | 0 / 0 | 0 |
| app overhead above the double's 5 s median (p50) | **≈ 0.04 s** | ≈ 0.11 s | ≈ 0.93 s | — |

## Reading

* **Reproducible.** Two independent runs two days apart on a rebuilt sandbox agree
  within 0.01 s at p50/p95 and within 0.6 s at p99. The benchmark is no longer a
  one-off.
* **p95 passes, narrowly, again** (6.475 vs 6.5). With the double's own p95 at
  ≈ 6.4 s (5 s + 1.5 s jitter, uniform) the application adds only tens of
  milliseconds at the median; there is no remaining application bottleneck at this
  concurrency.
* **p99 fails as written and will keep failing**: the 3 % injected faults are retried
  once with backoff, so the slowest 1 % of requests contain **two** model calls
  (≈ 5 s + 5 s + backoff ≈ 10.9–12 s). This is correct behaviour (no 5xx leaked, every
  answer labelled). The target is unattainable for any implementation that retries;
  it was **not relaxed**. Recommendation stands: define p99 as `2 × model latency + 2 s`
  if retries are meant to be inside it, or exclude retried requests from the p99 SLO.
* The double's fault rates are a conservative assumption, not a watsonx measurement.

## Not run (unchanged)

The same workload against the real staging/production runtime (Vercel Python
function + Neon) — blocked by Neon quota lock and Vercel 402 (`deployment-recovery.md`).
Soak (> 10 min) and > 20 VUs: not attempted on this 2 GB rig.
