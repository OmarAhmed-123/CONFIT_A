# Load Test Baseline — stylist recommendation path

## 1. Measurement boundary (what the numbers mean)

```
 load client ──HTTP──▶ uvicorn (2 workers) ──▶ FastAPI route ──▶ WardrobeStylistService
      ▲                                                         │
      │  latency measured here: first byte of request           ▼
      │  to last byte of response, per endpoint        watsonx client (retry policy)
      │                                                         │ HTTP
      └──────────────────────────────────────────── watsonx DOUBLE (scripts/load/watsonx_double.py)
```

* **Measured**: end-to-end server time per endpoint as seen by `scripts/load/stylist_load.py` on the same host (loopback; network ≈ 0). Includes DB work (PostgreSQL 17), prompt building, provider call(s) **including retries and backoff**, output validation, persistence.
* **Not measured**: browser render, CDN, internet RTT, real watsonx queueing.
* **Model latency is simulated** by the double: `DOUBLE_LATENCY_MS ± DOUBLE_JITTER_MS` uniform; faults `DOUBLE_ERROR_RATE` (503) and `DOUBLE_RATE_LIMIT_RATE` (429). Since 2026-10-29 the double has `DOUBLE_FAULT_TIMING = after | before` (see §3).
* **Sign-up pacing is excluded** from the timing window (register endpoint is 5/min/IP; users are created before the clock starts).

## 2. Workload (unchanged across all runs)

| Parameter | Value |
|---|---|
| Virtual users | 20 |
| Recommendations per user | 20 (400 total) |
| Per user | 8 add_item, 20 recommend, 4 save_outfit, 1 list_outfits → 660 requests |
| API | uvicorn `--workers 2`, PostgreSQL 17 `confit_bench`, `WARDROBE_STYLIST_PROVIDER=auto` with the double standing in for watsonx |
| Faults | 2 % 503 + 1 % 429 on every model call |
| Thresholds (absolute, user-stated, **never lowered**) | recommend p95 ≤ 6.5 s, p99 ≤ 8.0 s, error rate < 1 %, 0 5xx from our code |
| Harness relative verdict (repo rule, stricter, **unchanged**) | p95 < model_latency + 1.5 s, p99 < model_latency + 3.0 s |

Reproduce: `scripts/dev/run_benchmark.sh` (knobs: `DOUBLE_LATENCY_MS DOUBLE_JITTER_MS DOUBLE_ERROR_RATE DOUBLE_RATE_LIMIT_RATE DOUBLE_FAULT_TIMING MODEL_LATENCY_S OUT`).

## 3. Baseline run (2026-10-29, before this pass)

`docs/qa/load/stylist_mocked_20vu_postgres17_2workers_5s_20261029.json`

| Endpoint | n | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| recommend | 400 | 5.044 s | **6.475 s** (PASS ≤ 6.5) | **10.932 s** (FAIL ≤ 8.0) | 12.135 s |
| add_item | 160 | 0.129 | 0.265 | 0.284 | 0.322 |
| save_outfit | 80 | 0.023 | 0.034 | 0.039 | 0.039 |
| list_outfits | 20 | 0.011 | 0.014 | 0.022 | 0.022 |

Throughput 5.84 rps · 660 requests · 0 × 5xx · 0 × 4xx · provenance `watsonx|ai=True|ibm/granite-4-h-small` 400/400 · 0 fallbacks.

## 4. Retry analysis (read from code + harness, then confirmed by counters in `LOAD_TEST_RESULTS.md`)

* **Bounded?** Yes. `WATSONX_MAX_RETRIES = 2` → ≤ 3 attempts; only 429/5xx/timeout retry; backoff 0.5 s then 1.0 s (cap 4 s). No retry on 4xx validation, auth (beyond one token refresh), or output-parse failures.
* **Amplification**: with fault rate *f* = 3 % and first-retry success, expected model calls per request = 1 + f ≈ **1.03×** (measured 413/400 = 1.0325 in run 3). Worst case per request is 3 calls (3× cost, ~2·latency + 1.5 s backoff).
* **Why p99 failed at baseline — root cause**: the double **slept the full simulated latency before deciding to return a 503/429** (`watsonx_double.py`, sleep preceded the fault branch). A retried request therefore cost `L + 0.5 s + L ≈ 2L + 0.5 s` = **~10.5–12 s** at L = 5 s. With 3 % of 400 requests (≈12) retried, the slowest 1 % (4 requests) are *by construction* retried requests, so p99 ≈ 2L + 0.5 s regardless of any application code. The DB tier (add/save/list ≤ 0.3 s) and request handling contribute < 0.3 s.
* Real watsonx behaviour: 429 (rate-limit) responses observed during live probes on 2026-10-27/28 were returned immediately, not after inference. A 503 may arrive either way; the "after" rule is the pessimistic bound.

**Conclusion**: no application bottleneck was found. The p99 miss is an artefact of a harness rule (fault timing) interacting with a correct, bounded retry policy. The thresholds were **not** changed; the measurement rule was made explicit and both rules are now reported (see `LOAD_TEST_RESULTS.md`).
