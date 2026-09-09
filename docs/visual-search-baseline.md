# Visual Search Baseline Documentation

**Date:** 2026-09-09  
**Branch:** feature/search-visual-deterministic-enhancement  
**Starting SHA:** d2a80417d21a94b6ab060f4fd30d55237328a167

---

## Current Pipeline

### 1. Vision Model
- **Provider:** Gemini Flash Lite (gemini-flash-lite-latest)
- **Input:** Image URL or base64
- **Output:** JSON with detected_category, detected_color, detected_pattern, detected_style, detected_attributes

### 2. Attribute Extraction
- **Category:** Outerwear, Tops, Bottoms, Dresses, Footwear, Accessories
- **Color:** Simple color family (e.g., "navy", "black")
- **Pattern:** Solid, Striped, Checked, Floral, etc.
- **Style:** Style description (e.g., "Smart Casual", "Minimalist")

### 3. Tokenization
```python
cat_tokens = [t for t in (detected_cat or "").lower().replace("&", " ").split() if len(t) > 2]
col_tokens = [t for t in (detected_col or "").lower().split() if len(t) > 2]
sty_tokens = [t.replace(" ", "_") for t in (detected_sty or "").lower().split("/") if t.strip()]
```

### 4. Current Scoring Algorithm
```python
score = 50.0  # neutral base

# Category match: detected category words against product category/title
if any(t in p_cat or t in p_title for t in cat_tokens):
    score += 30.0

# Color family match
if any(t in p_color for t in col_tokens):
    score += 15.0

# Style tag match
if any(t in p_tags for t in sty_tokens):
    score += 8.0

score = min(98.0, round(score, 1))
```

### 5. Match Type Classification
- **Exact Match:** score >= 95
- **Silhouette Match:** score >= 88
- **Complementary Alternative:** score < 88

### 6. Fallback Behavior
- When no vision model configured: analysis_available=False
- All products get base score 50.0
- No fabricated detections

---

## Current Limitations

1. **No Synonym Handling:** "t-shirt" won't match "tee"
2. **No Category Hierarchy:** "top" won't match "shirt" or "blouse"
3. **No Color Similarity:** "navy" won't match "dark blue"
4. **Arbitrary Weights:** 30/15/8 not evidence-based
5. **Token Matching Only:** No semantic understanding
6. **No Tie-Breaking:** Products with same score have arbitrary order

---

## Baseline Metrics (To Be Measured)

| Metric | Baseline |
|--------|----------|
| Precision@5 | TBD |
| Precision@10 | TBD |
| Recall@5 | TBD |
| Recall@10 | TBD |
| MRR | TBD |
| nDCG@5 | TBD |
| nDCG@10 | TBD |
| Category Accuracy | TBD |
| Color Match Accuracy | TBD |
| Synonym Hit Rate | TBD |
| Zero Result Rate | TBD |
| Avg Latency (ranking only) | TBD |

---

## Evaluation Dataset

See: `docs/visual-search-evaluation/evaluation-dataset.json`

---

## Enhancement Plan

### A. Synonym Normalization
- Controlled taxonomy mapping
- Examples: tee → t-shirt, trousers → pants, sneakers → trainers

### B. Category Hierarchy
- Parent-child relationships
- Related category matching with weighted scores

### C. Color Similarity
- LAB color space conversion
- Perceptual distance calculation
- Threshold-based matching

### D. Style/Tag Weighting
- Controlled weighting for style, pattern, material
- Category priority over secondary attributes

### E. Scoring Formula
Evidence-based weights after baseline measurement.
