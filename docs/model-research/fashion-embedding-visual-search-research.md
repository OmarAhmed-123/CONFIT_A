# Fashion Embedding & Visual Search Model Research Report

**Date:** 2026-09-09  
**Feature:** Visual Search & Fashion Embeddings  
**Status:** Research Phase  

---

## 1. Executive Summary

This research evaluates embedding and vision models for CONFIT_A's visual search feature, which analyzes uploaded fashion images and matches them to catalog products. Currently uses Gemini Flash Lite for vision analysis.

---

## 2. Current Implementation Analysis

### 2.1 Current Architecture
- **Vision Analysis:** Gemini Flash Lite (gemini-flash-lite-latest)
- **Analysis Output:** Category, color, pattern, style detection
- **Matching Algorithm:** Token-based scoring against catalog
- **Fallback:** Honest degradation when no vision model available

### 2.2 Current Limitations
1. **No True Embeddings:** Uses keyword matching, not vector similarity
2. **Limited Fashion Understanding:** Generic vision model
3. **No Semantic Search:** Can't understand "bohemian summer dress"

---

## 3. Candidate Models Evaluation

### 3.1 Fashion-Specific Embedding Models

#### 3.1.1 Marqo-FashionCLIP
- **Model ID:** `Marqo/marqo-fashionCLIP`
- **License:** Apache 2.0
- **Commercial Use:** ✅ YES
- **Parameters:** 150M
- **Embedding Dimensions:** 512
- **Strengths:**
  - SOTA on fashion benchmarks (+57% over FashionCLIP 2.0)
  - Apache 2.0 license
  - Fast inference (10% faster than alternatives)
  - Optimized for fashion attributes (color, texture, pattern)
- **Weaknesses:**
  - Requires vector database infrastructure
  - Needs catalog re-indexing
- **Fashion Suitability:** EXCELLENT

#### 3.1.2 Marqo-FashionSigLIP
- **Model ID:** `Marqo/marqo-fashionSigLIP`
- **License:** Apache 2.0
- **Commercial Use:** ✅ YES
- **Parameters:** 150M
- **Strengths:**
  - Same as FashionCLIP but with SigLIP optimization
  - Better zero-shot performance
- **Weaknesses:**
  - Newer, less production-proven
- **Fashion Suitability:** EXCELLENT

#### 3.1.3 OpenFashionCLIP
- **Model ID:** `aimagelab/open-fashion-clip`
- **License:** Apache 2.0
- **Commercial Use:** ✅ YES
- **Strengths:**
  - Open-source fashion data training
  - Good generalization
- **Weaknesses:**
  - Lower benchmark scores than Marqo models
- **Fashion Suitability:** GOOD

### 3.2 General Vision Models (Current)

#### 3.2.1 Gemini Flash Lite (Current)
- **Model ID:** `gemini-flash-lite-latest`
- **License:** Proprietary (Google)
- **Commercial Use:** ✅ YES (with API key)
- **Strengths:**
  - Fast inference (~2-3s)
  - Good multimodal understanding
  - Already integrated
- **Weaknesses:**
  - Not fashion-specific
  - Higher cost than self-hosted
- **Fashion Suitability:** GOOD

### 3.3 Vector Database Options

#### 3.3.1 ChromaDB (Lightweight)
- **License:** Apache 2.0
- **Best For:** Small-medium catalogs (<100K items)
- **Strengths:** Easy setup, Python-native
- **Weaknesses:** Limited scalability

#### 3.3.2 Qdrant (Production-Grade)
- **License:** Apache 2.0
- **Best For:** Large catalogs, production use
- **Strengths:** High performance, filtering, cloud option
- **Weaknesses:** More complex setup

#### 3.3.3 Weaviate (Feature-Rich)
- **License:** BSD-3
- **Best For:** Complex queries, hybrid search
- **Strengths:** Built-in vectorization, GraphQL
- **Weaknesses:** Higher resource requirements

---

## 4. Recommendation

### 4.1 Phase 1: Enhance Current System (Immediate)
**Keep Gemini Flash Lite for vision analysis, improve matching algorithm**

**Rationale:**
1. **Production-Proven:** Already working
2. **No Infrastructure Changes:** No vector DB needed
3. **Cost-Effective:** Pay-per-use
4. **Fast Implementation:** Days, not weeks

**Implementation:**
1. Enhance token matching with synonym expansion
2. Add color similarity scoring (LAB color space)
3. Implement category hierarchy matching
4. Add style tag weighting

### 4.2 Phase 2: Add Fashion Embeddings (Future)
**Deploy Marqo-FashionCLIP with Qdrant**

**Rationale:**
1. **Superior Accuracy:** +57% over alternatives
2. **Semantic Search:** Understands "bohemian summer dress"
3. **Apache 2.0:** Clean commercial license
4. **Production-Ready:** Qdrant handles scale

**Implementation Plan:**
1. Deploy Marqo-FashionCLIP model
2. Index catalog with embeddings
3. Implement vector search API
4. A/B test against current system

---

## 5. Implementation Details

### 5.1 Enhanced Matching Algorithm (Phase 1)

```python
# Enhanced scoring with synonym expansion
def enhanced_score(product, detected_attributes):
    score = 50.0  # base
    
    # Category matching with hierarchy
    category_score = match_category_hierarchy(
        product.category, 
        detected_attributes['category']
    )
    score += category_score * 30.0
    
    # Color similarity in LAB space
    color_score = lab_color_similarity(
        product.color_family,
        detected_attributes['color']
    )
    score += color_score * 15.0
    
    # Style tag matching with synonyms
    style_score = synonym_aware_matching(
        product.style_tags,
        detected_attributes['style']
    )
    score += style_score * 8.0
    
    return min(98.0, score)
```

### 5.2 Vector Search Architecture (Phase 2)

```
User Image → Marqo-FashionCLIP → 512-dim embedding
                                    ↓
                              Qdrant Vector DB
                                    ↓
                            Similar Products (cosine distance)
                                    ↓
                            Re-rank with business rules
```

---

## 6. Evidence Links

- **Marqo-FashionCLIP:** https://github.com/marqo-ai/marqo-FashionCLIP
- **FashionCLIP Paper:** https://arxiv.org/pdf/2309.05551
- **Qdrant:** https://qdrant.tech/
- **ChromaDB:** https://www.trychroma.com/
- **Gemini Flash Lite:** Verified in production (2026-09-04)

---

**Status:** RESEARCH COMPLETE  
**Decision:** PHASE 1 - ENHANCE CURRENT SYSTEM  
**Next Action:** Implement enhanced matching algorithm
