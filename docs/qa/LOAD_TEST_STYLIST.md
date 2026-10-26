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

## Status and recommendation
* Correctness under load: **VERIFIED (mocked)** — no 5xx, no mislabelled
  provenance, no id leakage, retries work, saves persist.
* Latency targets: **PARTIALLY VERIFIED** — live single-user latency is what
  the model costs (~5.5 s); concurrency tails were measured on a rig that does
  not resemble production (Postgres, ≥2 workers, Redis limiter storage).
* **Before release sign-off:** re-run `stylist_load.py --mode mocked --vus 20`
  against a Postgres-backed staging API with ≥ 2 workers, and set the p99
  target to `2 × latency + 2 s` *explicitly* if retries are to be included in
  it (this document records that the original target did not account for them).
