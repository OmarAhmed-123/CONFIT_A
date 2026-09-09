# Deterministic visual search ranking enhancement

## Summary

This PR enhances the visual search ranking algorithm with deterministic improvements: synonym normalization, category hierarchy matching, LAB color similarity, and style weighting. The enhanced scoring is gated behind a feature flag (`USE_ENHANCED_VISUAL_SEARCH_SCORING`) that defaults to OFF.

## Scope

Deterministic search/ranking engineering only. One canonical ranking path in `visual_search_service.py`. No new AI models, embeddings, vector databases, or providers.

## No New AI

No new model, embedding provider, or vector DB. FashionCLIP remains RESEARCH_ONLY.

## Implementation

- **Synonym normalization**: 50+ fashion term synonyms (tee→t-shirt, trousers→pants, trainers→sneakers)
- **Category hierarchy**: 6 top-level categories with children, exact/child/related matching
- **Color similarity**: RGB→LAB conversion, CIE76 ΔE* distance, 30+ color definitions
- **Style taxonomy**: 10 styles with related/opposite definitions
- **Scoring formula**: base=20, category=35, color=20, style=10, pattern=5
- **Feature flag**: `USE_ENHANCED_VISUAL_SEARCH_SCORING: bool = False`

## Evaluation Dataset

110 queries (20 original + 90 expanded), distributed across tops, bottoms, dresses, outerwear, footwear, accessories. Development set: 90 queries. Holdout set: 20 queries (original, untouched during tuning).

**Limitation**: The evaluation uses manually labeled queries from a relatively small dataset and does not establish statistically representative production-wide performance.

## Offline Quality Results (110 queries)

| Metric | Baseline | Enhanced | Delta | Relative |
|--------|-------:|-------:|------:|---------|
| nDCG@5 | 0.8464 | 0.8918 | +0.0454 | +5.4% |
| nDCG@10 | 0.8976 | 0.9217 | +0.0240 | +2.7% |
| Precision@5 | 0.6891 | 0.7273 | +0.0382 | +5.5% |
| Precision@10 | 0.4582 | 0.4618 | +0.0036 | +0.8% |
| Recall@5 | 0.7388 | 0.7679 | +0.0290 | +3.9% |
| Recall@10 | 0.9300 | 0.9392 | +0.0092 | +1.0% |
| MRR | 0.9545 | 0.9659 | +0.0114 | +1.2% |

## Holdout Results (20 queries, untouched during tuning)

| Metric | Baseline | Enhanced | Delta | Relative |
|--------|-------:|-------:|------:|---------|
| nDCG@5 | 0.8352 | 0.8615 | +0.0264 | +3.2% |
| Precision@5 | 0.6900 | 0.7100 | +0.0200 | +2.9% |
| MRR | 0.9500 | 0.9500 | 0.0000 | 0.0% |

## Regression Analysis

**49 queries improved. 20 queries regressed.**

Most regressions are small rank-order changes, with a limited number of larger metric regressions including EQ95 (−0.230), EQ14 (−0.147), EQ38 (−0.139), and EQ05 (−0.101). Root causes were identified and documented.

| Query | Baseline nDCG@5 | Enhanced nDCG@5 | Root Cause |
|-------|----------------:|----------------:|------------|
| EQ95 | 1.000 | 0.770 | Style partial credit pushes formal items above color-matched items |
| EQ14 | 0.910 | 0.764 | LAB color similarity gives partial credit to gray items |
| EQ38 | 0.956 | 0.818 | Minor rank-order swap (positions 2-3) |
| EQ05 | 1.000 | 0.899 | Enhanced prioritizes style (formal) over color (red) |

**Acceptance rationale**: No safety-critical category boundary was violated. Overall ranking metrics improved on both the full dataset and the holdout set. The regressions are concentrated in edge cases where style and color signals conflict.

## Feature Flag

```python
USE_ENHANCED_VISUAL_SEARCH_SCORING: bool = False  # default OFF
```

Environment-driven. No secret. Frontend cannot control. OFF reproduces baseline ranking exactly. ON activates enhanced scorer.

## Rollback

Set `USE_ENHANCED_VISUAL_SEARCH_SCORING=false` and redeploy. No database migration required. No cache invalidation needed.

## Performance

| Metric | Baseline | Enhanced | Samples |
|--------|-------:|-------:|--------:|
| Ranking latency (mean) | 0.073 ms | 0.221 ms | 110 |
| Ranking latency (P95) | 0.097 ms | 0.292 ms | 110 |

These are ranking-only measurements from the evaluation harness.

## Security

- No new secrets
- No new external network calls
- No raw image persistence
- No authentication change
- No authorization change
- No ownership change
- No SSRF weakening
- No unsafe dependency added
- No dynamic code execution

## Testing

**Visual Search Enhanced**: 41 passed, 0 failed, 0 skipped

**VTON (unchanged)**: 28 passed, 0 failed, 5 skipped (5 skipped tests require vendor source files at `services/vendor/` — pre-existing path issue, not introduced by this PR)

## Production Status

**NOT YET PRODUCTION-VERIFIED**

- Feature flag defaults to OFF
- No real production request with enhanced scoring
- Rollback not yet tested in production
- Offline quality gate PASS; production verification pending

## Files Changed

| File | Change |
|------|--------|
| `backend/app/core/config.py` | Added `USE_ENHANCED_VISUAL_SEARCH_SCORING` flag |
| `backend/app/services/visual_search_enhanced.py` | Enhanced scoring algorithms (NEW) |
| `backend/app/services/visual_search_service.py` | Feature-flag integration into production path |
| `backend/tests/test_visual_search_enhanced.py` | 41 unit tests (NEW) |
| `backend/tests/visual_search_benchmark.py` | Benchmark script (NEW) |
| `backend/tests/visual_search_quality_gate.py` | Quality gate benchmark (NEW) |
| `docs/visual-search-evaluation/` | Evaluation datasets and results (NEW) |
| `docs/SEARCH_ENHANCEMENT_QUALITY_GATE_REPORT.md` | Quality gate report (NEW) |

## FashionCLIP

**RESEARCH_ONLY** — not included in this PR.
