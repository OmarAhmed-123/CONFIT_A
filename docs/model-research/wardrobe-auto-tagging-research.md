# Wardrobe Auto-Tagging Model Research Report

**Date:** 2026-09-09  
**Feature:** Wardrobe Item Classification & Auto-Tagging  
**Status:** Research Phase  

---

## 1. Executive Summary

This research evaluates models for CONFIT_A's wardrobe auto-tagging feature, which analyzes user-uploaded clothing images and extracts structured attributes (category, color, style, pattern, etc.). Currently uses Gemini Flash Lite.

---

## 2. Current Implementation Analysis

### 2.1 Current Architecture
- **Vision Model:** Gemini Flash Lite (gemini-flash-lite-latest)
- **Analysis Output:** Structured JSON with 12+ attributes
- **Prompt:** WARDROBE_TAG_PROMPT with fashion taxonomy
- **Fallback:** Honest degradation when model unavailable

### 2.2 Current Capabilities
1. **Category Detection:** Tops, Bottoms, Outerwear, Footwear, Accessories, Dresses
2. **Color Extraction:** Primary color + hex, secondary colors
3. **Style Analysis:** Style description + tags
4. **Pattern Detection:** Solid, Striped, Checked, Floral, etc.
5. **Occasion Suitability:** 10 occasion categories
6. **Seasonality:** All-Season, Spring, Summer, Autumn, Winter
7. **Confidence Score:** 0.0-1.0

### 2.3 Current Limitations
1. **API Dependency:** Requires Gemini API key
2. **Cost:** Pay-per-use
3. **Latency:** ~2-3s per image
4. **No Local Option:** Can't work offline

---

## 3. Candidate Models Evaluation

### 3.1 Fashion-Specific Vision Models

#### 3.1.1 Marqo-FashionCLIP (Embedding Model)
- **Model ID:** `Marqo/marqo-fashionCLIP`
- **License:** Apache 2.0
- **Commercial Use:** ✅ YES
- **Use Case:** Can be used for classification via embedding similarity
- **Strengths:**
  - Fashion-optimized
  - Fast inference
  - Apache 2.0 license
- **Weaknesses:**
  - Not designed for detailed attribute extraction
  - Requires custom classification head
- **Fashion Suitability:** GOOD (for classification)

#### 3.1.2 Fashion-MNIST Classifiers
- **Models:** Various CNN architectures
- **License:** Varies
- **Use Case:** Category classification only
- **Strengths:**
  - Fast inference
  - Lightweight
- **Weaknesses:**
  - Limited to category classification
  - No attribute extraction
- **Fashion Suitability:** LIMITED

### 3.2 General Vision Models

#### 3.2.1 Gemini Flash Lite (Current)
- **Model ID:** `gemini-flash-lite-latest`
- **License:** Proprietary (Google)
- **Commercial Use:** ✅ YES
- **Strengths:**
  - Excellent attribute extraction
  - Structured JSON output
  - Fast inference
  - Already integrated
- **Weaknesses:**
  - API dependency
  - Cost per request
- **Fashion Suitability:** EXCELLENT

#### 3.2.2 GPT-4 Vision
- **Model ID:** `gpt-4-vision-preview`
- **License:** Proprietary (OpenAI)
- **Commercial Use:** ✅ YES
- **Strengths:**
  - High accuracy
  - Good attribute extraction
- **Weaknesses:**
  - Higher cost than Gemini
  - Slower inference
- **Fashion Suitability:** EXCELLENT

### 3.3 Local/Open Source Models

#### 3.3.1 LLaVA (Large Language and Vision Assistant)
- **Model ID:** `liuhaotian/llava-v1.6-34b`
- **License:** Apache 2.0
- **Commercial Use:** ✅ YES
- **VRAM:** ~20GB
- **Strengths:**
  - Open source
  - Good multimodal understanding
  - Can run locally
- **Weaknesses:**
  - High VRAM requirements
  - Slower than specialized models
  - Not fashion-optimized
- **Fashion Suitability:** GOOD

#### 3.3.2 Gemma 4 (Vision Capable)
- **Model ID:** `google/gemma-4-26b-a4b`
- **License:** Apache 2.0
- **Commercial Use:** ✅ YES
- **VRAM:** ~15GB (3.8B active)
- **Strengths:**
  - Apache 2.0 license
  - Edge-optimized
  - Vision capability
- **Weaknesses:**
  - Smaller active parameters
  - May need fine-tuning for fashion
- **Fashion Suitability:** MODERATE

---

## 4. Recommendation

### 4.1 Primary Recommendation: Keep Gemini Flash Lite

**Rationale:**
1. **Production-Proven:** Already working well
2. **Excellent Accuracy:** Best attribute extraction
3. **Structured Output:** JSON format matches schema
4. **Fast Inference:** ~2-3s acceptable for UX
5. **Cost-Effective:** Pay-per-use reasonable

### 4.2 Enhancement Opportunities

#### 4.2.1 Add Local Fallback (Future)
- Deploy LLaVA or Gemma 4 as local fallback
- Use when Gemini API unavailable
- Provides offline capability

#### 4.2.2 Add Fashion-Specific Fine-Tuning (Future)
- Fine-tune Gemma 4 on fashion dataset
- Improve attribute extraction accuracy
- Reduce API dependency

---

## 5. Implementation Details

### 5.1 Current Prompt Structure
```python
WARDROBE_TAG_PROMPT = (
    "Analyze this photo of a clothing item the user owns. Respond with STRICT JSON only, "
    "no prose, with exactly these keys: "
    "category (one of: Tops, Bottoms, Outerwear, Footwear, Accessories, Dresses), "
    "item_type (specific subcategory, e.g. 'Oversized Blazer', 'Pleated Trousers'), "
    "primary_color (simple color family name), "
    "primary_color_hex (approximate hex like #1B1F3B), "
    "secondary_colors (list of secondary color families, may be empty), "
    "style (short style description, e.g. 'Smart Casual', 'Minimalist', 'Streetwear'), "
    "style_tags (list of up to 6 short attribute tags, e.g. 'Tailored', 'Wool Blend'), "
    "pattern (e.g. Solid, Striped, Checked, Floral), "
    "occasion_suitability (list chosen from: Casual, Smart Casual, Work & Business, "
    "Business Formal, Cocktail, Formal, Black Tie, Active, Lounge, Evening), "
    "seasonality (one of: All-Season, Spring, Summer, Autumn, Winter), "
    "confidence (float 0.0-1.0 for how certain the analysis is). "
    "If the image does not show a clothing or fashion accessory item, set category to null."
)
```

### 5.2 Local Fallback Implementation (Future)
```python
async def analyze_wardrobe_image_local(image_base64: str) -> Dict[str, Any]:
    """Local fallback using LLaVA or Gemma 4."""
    try:
        # Try local model first
        result = await local_vision_model.analyze(image_base64)
        return normalize_to_taxonomy(result)
    except Exception:
        # Fall back to Gemini
        return await analyze_wardrobe_image_gemini(image_base64)
```

---

## 6. Evidence Links

- **Gemini Flash Lite:** Verified in production (2026-09-04)
- **Marqo-FashionCLIP:** https://github.com/marqo-ai/marqo-FashionCLIP
- **LLaVA:** https://github.com/haotian-liu/LLaVA
- **Gemma 4:** https://huggingface.co/google/gemma-4-26b-a4b

---

**Status:** RESEARCH COMPLETE  
**Decision:** KEEP GEMINI FLASH LITE  
**Next Action:** Implement local fallback for offline capability
