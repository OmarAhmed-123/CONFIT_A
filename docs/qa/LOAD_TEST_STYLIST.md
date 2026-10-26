# Load test — wardrobe stylist (P5)

Harness: `scripts/load/stylist_load.py` (driver) + `scripts/load/watsonx_double.py`
(local IAM + `text/chat` double; configurable latency/jitter/503/429 injection).
Results: `docs/qa/load/*.json`. No uncontrolled traffic reached IBM: the live
mode is capped **in code** at 12 requests / 2 VUs.

## Pre-defined targets (set before running)

| Mode | Error rate (5xx) | p95 recommend | p99 recommend | Other |
|---|---|---|---|---|
| mocked | < 1 % | < model latency + 1.5 s | < model latency + 3 s | 0 × 5xx from our code; every answer labelled with its real source |
| live | 0 % | < 15 s | < 20 s | provenance `watsonx` / `ibm/granite-4-h-small` on every answer |

Model latency for the double was set to **5.0 s ± 1.5 s** after the live probe
measured ~5.5 s median for `granite-4-h-small` (the 0.9 s originally assumed
was wrong — recorded here deliberately).

## Rig

Single sandbox (2 vCPU): uvicorn **1 worker**, **SQLite** dev database,
in-memory rate-limit storage, double on the same host. Each VU is a freshly
registered user (own 40/hour stylist budget, as in production) with an
8-garment closet; per VU: 20 × `POST /wardrobe/outfit-recommendation`
(rotating occasions, `previous_item_ids` chained), every 5th answer saved via
`POST /wardrobe/outfits`, final `GET /wardrobe/outfits`. Registration is paced
to the app's 5/min sign-up limit and excluded from the timing window.

## Results

### Mocked — 20 VUs × 20 requests (`stylist_mocked_20vu.json`, idle machine)

| Metric | Value |
|---|---|
| Requests (measured window) | 660 in 151 s → **4.36 req/s** (400 recommendations ≈ 2.6 rec/s with a 5 s model) |
| 5xx from our code | **0** · 4xx **0** |
| Provenance | 400/400 `source=watsonx, ai_generated=true, model_id=ibm/granite-4-h-small`; 0 fallbacks |
| Model references rejected by id validation | 0 |
| Injected upstream faults (double) | 503s + 429s ≈ 3 % of chat calls → **all recovered by one retry**; 0 surfaced to users (410 chat calls for 400 answers) |
| `recommend` | p50 **6.35 s** · p95 **9.26 s** · p99 **12.40 s** · max 13.4 s |
| `save_outfit` | p50 1.18 s · p95 3.00 s · p99 3.96 s (all 201) |
| `list_outfits` | p50 9 ms · p95 1.14 s |
| `add_item` | p50 119 ms · p99 3.75 s |

**Verdict against targets: p95 (9.26 > 6.5) and p99 (12.40 > 8.0) MISSED; error-rate and 0×5xx PASSED.**

### Mocked — 1 VU baseline (`stylist_mocked_1vu_baseline.json`)

`recommend` p50 **4.63 s** (double alone: 5 ± 1.5 s) · `save_outfit` 15 ms ·
`list_outfits` 17 ms · `add_item` 7 ms → per-request overhead of our code path
(auth, closet load, prompt build, validation, persistence) is in the tens of ms.

### Attribution of the p95/p99 miss
* Retries: a 503/429 costs model latency + backoff, so ~3 % of answers
  legitimately land at ≈ 2 × latency; this alone explains the p99 band
  (12–13 s) and is correct behaviour.
* Concurrency: at 20 in-flight requests the *cheap* endpoints degrade from
  ~15 ms to seconds (`save_outfit` p50 1.2 s, `list_outfits` p95 1.1 s). That
  signature is the rig — one worker and SQLite's single writer — not the stylist
  code. It inflates recommend p50 by ~1.3 s as well.
* A contended earlier run (browser audits + build in parallel) is kept as
  `stylist_mocked_20vu_contended.json` for comparison; numbers were similar,
  confirming the bottleneck is structural to the rig.

### Live — 2 VUs × 4 requests (`stylist_live_probe.json`, real watsonx.ai eu-de)

| Metric | Value |
|---|---|
| Requests | 28 (8 recommendations, 2 saves, 16 items, 2 lists) |
| Errors | **0** (0×4xx, 0×5xx), 0 fallbacks, 0 rejected references |
| Provenance | 8/8 `ibm/granite-4-h-small`, `ai_generated=true` |
| `recommend` | p50 **5.47 s** · p95 **8.02 s** · max 8.02 s |
| Verdict | **PASS** (all live targets) |

## Re-validation pass (2026-10-26, later the same day) — production-like rig

Rig: **PostgreSQL 16** (local, UTF8, Alembic head 0048), uvicorn **2 workers**,
per-process (memory) rate-limit storage — the app's documented fallback when
no external Redis is configured, so limits are per worker; a shared store was
not required for these scenarios because every VU is its own user and
registration is paced — same host, idle machine, same harness, **unchanged
targets**.

### Mocked — 20 VUs × 20 requests (`stylist_mocked_20vu_postgres_2workers.json`)

Double at its defaults (0.9 s ± 0.4 s model latency, 2 % injected 503) → targets
derived by the harness: p95 < 2.4 s, p99 < 3.9 s.

| Metric | SQLite / 1 worker (earlier run, 5 s model) | **PostgreSQL / 2 workers (0.9 s model)** |
|---|---|---|
| Requests (window) | 660 in 151 s → 4.36 req/s | 660 in **29.7 s → 22.2 req/s** |
| 5xx / 4xx from our code | 0 / 0 | **0 / 0** |
| Provenance | 400/400 Granite-labelled | **400/400** `watsonx · ai=true · ibm/granite-4-h-small`, 0 fallbacks |
| `recommend` p50 / p95 / p99 | 6.35 / 9.26 / 12.40 s | **1.23 / 1.69 / 2.01 s** (max 3.14 s) |
| `save_outfit` p50 / p95 | 1.18 / 3.00 s | **0.24 / 0.55 s** |
| `list_outfits` p50 / p95 | 9 ms / 1.14 s | **11 ms / 0.34 s** |
| `add_item` p50 / p99 | 119 ms / 3.75 s | **157 ms / 0.30 s** |
| Verdict | p95/p99 MISSED | **PASS — VERIFIED** (p95 1.69 < 2.4; p99 2.01 < 3.9; error rate 0; no 5xx) |

Reading: application overhead above model latency at p95 is ≈ **0.8 s** with 20
concurrent users (vs. ≈ 2.8 s on the SQLite/1-worker rig). The earlier miss is
therefore confirmed as rig attribution, not stylist code. Note the model
latencies differ between the two runs (the comparison that matters is overhead
above the model, which the harness's targets are expressed in).

### Mocked, like-for-like — 20 VUs × 20, double at **5 s ± 1.5 s**, 2 % 503 + 1 % 429 injected (`stylist_mocked_20vu_postgres_2workers_5s.json`)

| Metric | SQLite / 1 worker | **PostgreSQL / 2 workers** | Double alone (simulated from its own parameters, 200k draws) |
|---|---|---|---|
| Requests / throughput | 660 in 151 s → 4.36 req/s | 660 in **139 s → 4.75 req/s** | — |
| 5xx / 4xx | 0 / 0 | **0 / 0** | — |
| Provenance | 400/400 Granite | **400/400** Granite, 0 fallbacks | — |
| `recommend` p50 / p95 / p99 | 6.35 / 9.26 / 12.40 s | **5.96 / 8.25 / 9.52 s** (max 12.98 s) | 5.05 / 6.44 / ≈ 11.0 s |
| Verdict vs. 6.5 / 8.0 | MISSED | **MISSED** (p95 8.25 > 6.5; p99 9.52 > 8.0) | the targets are below the double's own p95 + 0.1 s and far below its p99 |

Reading, stated plainly:
* The pre-defined targets were written as *mean model latency + 1.5 s / + 3 s*.
  With ±1.5 s jitter and 3 % retried calls the double **by itself** has p95 ≈
  6.44 s and p99 ≈ 11 s, so an application overhead of more than ~0.06 s fails
  p95 and p99 cannot pass at all. **The targets are not relaxed here**; the
  owner must decide whether to restate them against the model's *measured
  percentiles* (e.g. p95 ≤ model-p95 + 1.5 s, p99 counted with retries as
  `2 × latency + 2 s`). This document already flagged the retry omission.
* What the application adds at 20 concurrent users, 2 workers: ≈ **0.9 s at
  p50** and ≈ **1.8 s at p95** (measured minus double-alone). The 0.9 s-model
  run above puts the same overhead at ≈ 0.3 s / 0.8 s; i.e. overhead grows
  with the number of requests simultaneously in flight per worker (≈ 10 here).
  Candidates, unverified: synchronous SQLAlchemy work inside the `async`
  recommendation handler blocking the event loop while other requests await
  the model, and CPU contention on a 2-vCPU host that also runs the double,
  PostgreSQL and the load driver. **Next action (Engineering):** profile one
  worker under 10 concurrent recommendations; if the event loop is the cause,
  move the DB/prompt phase to a threadpool or raise the worker count; re-run.
* Correctness, isolation and provenance under load: clean in every run.
* Side observation: registration throttling was reached after 4 → 9 → 14 → 19
  users instead of every 5 — the per-process (`memory://`) limiter with two
  workers lets roughly double the configured rate through. Expected and
  documented; set `REDIS_URL` for global limits in multi-worker deployments.

### Live — 2 VUs × 4 requests on the same PostgreSQL / 2-worker rig (`stylist_live_probe_postgres_2workers.json`)

| Metric | Value |
|---|---|
| Requests | 8 recommendations (+ items, 2 saves, 2 lists) |
| Errors | **0** (0×4xx, 0×5xx), 0 fallbacks, 0 rejected references |
| Provenance | **8/8** `ibm/granite-4-h-small`, `ai_generated=true` (server log: `POST https://eu-de.ml.cloud.ibm.com/ml/v1/text/chat` → 200, `wardrobe_outfit_saved … source=watsonx`) |
| `recommend` | p50 **3.51 s** · p95 **6.10 s** (n = 8; bounded probe, not a load test) |
| Verdict | **PASS** against the master-prompt targets (p95 ≤ 6.5 s, p99 ≤ 8 s) — *for this sample size*; the live cap of 12 requests is deliberate |

### Found while building the rig (fixed in this pass)
On a **fresh PostgreSQL** database the API never finished starting: the
lifespan held the catalogue-probe session open while `seed_database()` ran
`DROP TABLE` on a second connection — a self-deadlock PostgreSQL cannot detect
(the holder is idle, not waiting). Fixed in `backend/app/main.py`; regression
test `backend/tests/test_startup_seed_no_open_session.py`. Non-production
only (production never seeds), but it would have blocked any Postgres-backed
staging on first boot.

## Status and recommendation
* Correctness under load: **VERIFIED (mocked)** — no 5xx, no mislabelled
  provenance, no id leakage, retries work, saves persist.
* Latency targets: **PARTIAL.** On the production-like rig (PostgreSQL,
  2 workers) the 0.9 s-model run passes its derived targets and the live
  bounded probe passes (p95 6.10 s ≤ 6.5 s), but the like-for-like 5 s-model
  run still misses 6.5 / 8.0 (p95 8.25 / p99 9.52). Targets were **not**
  relaxed; see the reading above for why they cannot be met as written with a
  jittered, fault-injecting double, and for the measured application overhead
  that *is* ours to reduce (≈ 0.9 s p50 / 1.8 s p95 at 20 concurrent).
* Still outstanding (**NOT RUN**): the same run against the real staging
  deployment (Neon + Vercel function runtime) — blocked by the Neon quota lock
  and the Vercel 402. Vercel's Python function is single-process per
  invocation, so worker-count behaviour there is a platform property; re-run
  the live probe and a short mocked soak once staging exists.
* Retry accounting: unchanged recommendation — if retries are to be inside
  the p99 budget, state the target as `2 × latency + 2 s` explicitly.
