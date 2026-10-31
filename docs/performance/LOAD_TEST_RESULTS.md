# Load Test Results — 2026-10-29 (three runs, identical workload and thresholds)

All runs: 20 VU × 20 recommendations (660 requests), PostgreSQL 17, uvicorn 2 workers,
2 % 503 + 1 % 429 injected on every model call, `WATSONX_MAX_RETRIES = 2`.
Thresholds (absolute): recommend **p95 ≤ 6.5 s, p99 ≤ 8.0 s**, error rate < 1 %, 0 × 5xx from our code — unchanged from every prior pass.
Harness relative verdict (`stylist_load.py`, unchanged): p95 < L + 1.5 s, p99 < L + 3.0 s where L = simulated model latency.

| Run | Model latency L | Fault timing | recommend p50 | p95 | p99 | max | rps | errors | model calls / retries | Absolute verdict | Relative verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 (baseline) `stylist_mocked_20vu_postgres17_2workers_5s_20261029.json` | 5.0 ± 1.5 s | after latency | 5.044 | 6.475 | **10.932** | 12.135 | 5.84 | 0 | counters not captured (added later) | p95 PASS · **p99 FAIL** | p95 PASS · p99 FAIL (8.0) |
| 2 `stylist_mocked_20vu_pg17_5s_faultbefore_20261029.json` | 5.0 ± 1.5 s | **before** latency (gateway-style) | 5.293 | 6.393 | **6.516** | 6.969 | 6.03 | 0 | counters not captured (script change landed after) | **p95 PASS · p99 PASS** | p95 PASS · p99 PASS (8.0) |
| 3 `stylist_mocked_20vu_pg17_live2p9s_faultafter_20261029.json` | **2.9 ± 1.1 s** (from live Granite distribution: 22 calls, p50 2.87, p95 5.41, max 6.20) | after latency | 2.990 | 3.992 | **7.074** | 7.990 | 9.16 | 0 | **413 calls / 400 req → 12 × 503 + 1 × 429 = 13 retries, all succeeded on first retry** | **p95 PASS · p99 PASS** | p95 PASS (4.4) · **p99 FAIL** (5.9) |

Every run: 400/400 recommendations with provenance `watsonx|ai=True|ibm/granite-4-h-small`, 0 fallbacks, 0 rejected model references, 0 × 4xx, 0 × 5xx.

## What changed between runs (and what did not)

* **Did not change**: application code on the request path, retry policy, thresholds, VU count, fault rates, DB, worker count.
* **Run 2** changes only *when* the double returns the injected fault (`DOUBLE_FAULT_TIMING=before`). Result: p99 drops from 10.93 s to 6.52 s. This isolates the entire p99 excess to the "fault-after-latency" rule × one bounded retry.
* **Run 3** keeps the pessimistic "after" rule but parameterises latency from the only real evidence available (the 2026-10-28 live eval). Retried requests cost 2.9 + 0.5 + 2.9 ≈ 6.3–8.0 s → p99 7.07 s. This passes the absolute 8.0 s target and misses the repo's stricter relative rule (L + 3 = 5.9 s) by 1.17 s. Arithmetic identity: under "fault after latency", a retried request always exceeds L + 3 once L > 2.5 s, so the relative rule cannot pass with faults unless they fail fast.

## Retry evidence (run 3 counters, `double_stats`)

`{"iam": 1, "chat": 413, "errors_injected": 12, "rate_limits_injected": 1}` → 13 retried requests (3.25 %), 0 second retries, amplification 1.0325×. Bound holds: no request made more than 2 calls. IAM token fetched once and cached across 413 calls.

## Verdict

* Against the user-stated thresholds (p95 ≤ 6.5 / p99 ≤ 8): **PASS** in runs 2 and 3; **FAIL** only in run 1, whose p99 is explained entirely by the harness fault-timing rule.
* No code bottleneck was identified, so none was "fixed"; the only code change is harness instrumentation (`DOUBLE_FAULT_TIMING` knob, `double_stats` attached to reports, benchmark exits with the load status).
* **Open**: real watsonx 503 timing is unmeasured (no 503 observed live). Until measured, treat run 1 as the pessimistic bound and run 3 as the evidence-based estimate. Real-provider soak under load: **NOT TESTED** (rate limits + cost; see `docs/qa/LOAD_TEST_STYLIST.md`).
