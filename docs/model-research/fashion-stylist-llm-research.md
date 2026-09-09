# Fashion Stylist LLM Research Report

**Date:** 2026-09-09  
**Feature:** AI Stylist (Fashion Advice & Recommendations)  
**Status:** Research Phase  

---

## 1. Executive Summary

This research evaluates the best LLM models for CONFIT_A's AI Stylist feature, which provides personalized fashion advice grounded in real catalog products. The current implementation uses a multi-provider failover system with Groq, Gemini, and OpenAI.

---

## 2. Current Implementation Analysis

### 2.1 Current Architecture
- **Multi-Provider Orchestrator:** Live failover across NVIDIA, Groq, Gemini, OpenAI
- **Grounding Verification:** Ensures AI responses reference real catalog products
- **Deterministic Fallback:** StylingEngine when no AI providers available
- **Response Validation:** Empty response detection and quarantine system

### 2.2 Current Models in Use
1. **Groq:** `openai/gpt-oss-120b` (~0.5s latency)
2. **Gemini:** `gemini-flash-latest` (~3s latency)
3. **OpenAI:** `gpt-4o-mini` (~1.5s latency)

---

## 3. Candidate Models Evaluation

### 3.1 Open Source Models (Self-Hosted)

#### 3.1.1 Llama 3.3 70B
- **Model ID:** `meta-llama/Llama-3.3-70B-Instruct`
- **License:** Llama 3.3 Community License
- **Commercial Use:** ✅ YES (below 700M MAU)
- **VRAM:** ~40GB (70B dense)
- **Latency:** Depends on hardware
- **Strengths:** 
  - Best overall local chat model
  - Strong instruction following
  - Reduced hallucination vs 3.1
- **Weaknesses:**
  - Requires significant GPU resources
  - Not optimized for fashion domain
- **Fashion Suitability:** Good general-purpose, may need fine-tuning

#### 3.1.2 Qwen3.6-27B
- **Model ID:** `Qwen/Qwen3.6-27B`
- **License:** Apache 2.0
- **Commercial Use:** ✅ YES
- **VRAM:** ~15GB (4-bit quantization)
- **Latency:** Low (optimized for local deployment)
- **Strengths:**
  - Apache 2.0 license (clean commercial)
  - Good multilingual support
  - Strong tool calling
- **Weaknesses:**
  - Smaller model may have less nuanced fashion knowledge
- **Fashion Suitability:** Good for multilingual fashion advice

#### 3.1.3 Gemma 4 26B A4B
- **Model ID:** `google/gemma-4-26b-a4b`
- **License:** Apache 2.0
- **Commercial Use:** ✅ YES
- **VRAM:** ~15GB (3.8B active parameters)
- **Latency:** Very fast (edge-optimized)
- **Strengths:**
  - Apache 2.0 license
  - 140+ language support
  - Edge deployment ready
- **Weaknesses:**
  - Smaller active parameters
- **Fashion Suitability:** Good for multilingual, fast responses

### 3.2 Hosted API Models

#### 3.2.1 Groq (Current)
- **Model:** `openai/gpt-oss-120b`
- **Latency:** ~0.5s (fastest)
- **Cost:** Pay-per-use
- **Strengths:** Ultra-low latency, reasoning model
- **Weaknesses:** Can produce empty responses (mitigated)

#### 3.2.2 Gemini Flash (Current)
- **Model:** `gemini-flash-latest`
- **Latency:** ~3s
- **Cost:** Pay-per-use
- **Strengths:** Good multimodal, fast
- **Weaknesses:** 503s under load

#### 3.2.3 OpenAI GPT-4o-mini (Current)
- **Model:** `gpt-4o-mini`
- **Latency:** ~1.5s
- **Cost:** Pay-per-use
- **Strengths:** Reliable, good quality
- **Weaknesses:** Higher cost than Groq

---

## 4. Recommendation

### 4.1 Primary Recommendation: Keep Current Multi-Provider Architecture

**Rationale:**
1. **Production-Proven:** Already deployed and working
2. **Resilience:** Live failover with quarantine system
3. **Cost-Effective:** Pay-per-use model
4. **Low Latency:** Groq provides sub-second responses
5. **Grounding:** Already implements catalog verification

### 4.2 Enhancement Opportunities

#### 4.2.1 Add Fashion-Specific Fine-Tuning (Future)
- Fine-tune Llama 3.3 70B on fashion styling datasets
- Use Polyvore or DeepFashion datasets
- Implement LoRA for efficient adaptation

#### 4.2.2 Add Local Fallback Model
- Deploy Qwen3.6-27B as local fallback
- Use when all hosted providers fail
- Provides offline capability

---

## 5. Implementation Plan

### Phase 1: Optimize Current System (Immediate)
1. ✅ Keep multi-provider failover
2. ✅ Enhance grounding verification
3. ✅ Improve empty response handling

### Phase 2: Add Local Fallback (Future)
1. Deploy Qwen3.6-27B locally
2. Implement as last-resort fallback
3. Add fashion-specific prompting

### Phase 3: Fine-Tuning (Future)
1. Collect fashion styling dataset
2. Fine-tune Llama 3.3 70B with LoRA
3. Deploy as primary model

---

## 6. Evidence Links

- **Llama 3.3:** https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct
- **Qwen3.6:** https://huggingface.co/Qwen/Qwen3.6-27B
- **Gemma 4:** https://huggingface.co/google/gemma-4-26b-a4b
- **Groq Performance:** Verified in production (2026-09-04)
- **Fashion Fine-Tuning Research:** https://arxiv.org/html/2409.12150v1

---

**Status:** RESEARCH COMPLETE  
**Decision:** KEEP CURRENT MULTI-PROVIDER ARCHITECTURE  
**Next Action:** Implement local fallback with Qwen3.6-27B
