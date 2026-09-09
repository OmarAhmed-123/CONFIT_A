# PR: Deterministic visual search ranking enhancement

## Summary

This PR enhances the visual search ranking algorithm with deterministic improvements: synonym normalization, category hierarchy matching, LAB color similarity, and style weighting. No new ML models, embeddings, or vector databases are introduced.

## Scope

Deterministic search/ranking only. One canonical ranking path in `visual_search_service.py` with feature-flag integration.

## No New AI

No new model, embedding provider, or vector DB. FashionCLIP remains RESEARCH_ONLY.

## Implementation

- **Synonym normalization**: 50+ fashion term synonyms (tee→t-shirt, trousers→pants, trainers→sneakers)
- **Category hierarchy**: 6 top-level categories with children, exact/child/related matching
- **Color similarity**: RGB→LAB conversion, CIE76 ΔE* distance, 30+ color definitions
- **Style taxonomy**: 10 styles with related/opposite definitions
- **Scoring formula**: base=20, category=35, color=20, style=10, pattern=5

## Evaluation Dataset

110 queries (20 original + 90 expanded), distributed across tops, bottoms, dresses, outerwear, footwear, accessories. Development set: 90 queries. Holdout set: 20 queries (original, untouched during tuning).

## Results (110 queries)

| Metric | Baseline | Enhanced | Delta | Relative |
|--------|----------|----------|-------|----------|
| nDCG@5 | 0.8464 | 0.8918 | +0.0454 | +5.4% |
| nDCG@10 | 0.8976 | 0.9217 | +0.0240 | +2.7% |
| Precision@5 | 0.6891 | 0.7273 | +0.0382 | +5.5% |
| Precision@10 | 0.4582 | 0.4618 | +0.0036 | +0.8% |
| Recall@5 | 0.7388 | 0.7679 | +0.0290 | +3.9% |
| Recall@10 | 0.9300 | 0.9392 | +0.0092 | +1.0% |
| MRR | 0.9545 | 0.9659 | +0.0114 | +1.2% |

## Holdout (20 queries, untouched during tuning)

| Metric | Baseline | Enhanced | Delta | Relative |
|--------|----------|----------|-------|----------|
| nDCG@5 | 0.8352 | 0.8615 | +0.0264 | +3.2% |
| Precision@5 | 0.6900 | 0.7100 | +0.0200 | +2.9% |
| MRR | 0.9500 | 0.9500 | 0.0000 | 0.0% |

## Regression Analysis

**20 queries regressed. 49 queries improved. Net +29 improvements.**

Regressions are NOT zero. The evaluation criteria accepted the observed trade-off because:

1. No safety-critical category boundary was violated
2. Overall ranking metrics improved on both full dataset and holdout
3. Regressions are mostly minor ranking swaps (positions 2-3), not fundamental failures
4. Synonym and hierarchy improvements address the intended failure modes

### Major Regressions

| Query | Description | Baseline | Enhanced | Root Cause |
|-------|-------------|----------|----------|------------|
| EQ95 | "Green formal" | 1.000 | 0.770 | Style partial credit pushes formal items above color-matched items |
| EQ14 | "Black boots" | 0.910 | 0.764 | LAB color similarity gives partial credit to gray items |
| EQ38 | "Shorts for beach" | 0.956 | 0.818 | Minor ranking swap (positions 2-3) |
| EQ05 | "Red evening gown" | 1.000 | 0.899 | Enhanced prioritizes style over color |

## Feature Flag

```python
USE_ENHANCED_VISUAL_SEARCH_SCORING: bool = False  # default OFF
```

Environment-driven. No secret. Frontend cannot control. Rollback requires only disabling the flag.

## Rollback

Set `USE_ENHANCED_VISUAL_SEARCH_SCORING=false` and redeploy. No database migration required.

## Performance

| Metric | Baseline | Enhanced | Samples |
|--------|----------|----------|---------|
| Ranking latency (mean) | 0.073ms | 0.221ms | 110 |
| Ranking latency (P95) | 0.097ms | 0.292ms | 110 |

Vision API latency (~2-3 seconds) dominates. Enhanced ranking adds ~0.15ms, negligible in production.

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

**Visual Search Enhanced**: 41 passed, 0 failed

**VTON (unchanged)**: 28 passed, 5 skipped, 0 failed

## Production Status

**NOT YET PRODUCTION-VERIFIED**

- Feature flag defaults to OFF
- No real production request with enhanced scoring
- Rollback not yet tested in production

## Files Changed

| File | Change |
|------|--------|
| `backend/app/core/config.py` | Added `USE_ENHANCED_VISUAL_SEARCH_SCORING` flag |
| `backend/app/services/visual_search_enhanced.py` | Enhanced scoring algorithms |
| `backend/app/services/visual_search_service.py` | Feature-flag integration |
| `backend/tests/test_visual_search_enhanced.py` | 41 unit tests |
| `backend/tests/visual_search_benchmark.py` | Benchmark script |
| `backend/tests/visual_search_quality_gate.py` | Quality gate benchmark |
| `docs/visual-search-evaluation/` | Evaluation datasets and results |
| `docs/SEARCH_ENHANCEMENT_QUALITY_GATE_REPORT.md` | Quality gate report |

## Merge Conditions

- [x] CI passes
- [x] Security checks pass
- [x] No unintended files changed
- [x] Flag defaults OFF
- [x] Baseline behavior preserved
- [x] Documentation consistent

## Post-Merge Actions

1. Deploy reviewed commit
2. Verify production commit SHA
3. Verify feature flag state (OFF)
4. Test real visual-search request with baseline
5. Enable flag in controlled environment
6. Test real visual-search request with enhanced
7. Verify rollback
8. Record evidence

## FashionCLIP

**RESEARCH_ONLY** — not included in this PR.
