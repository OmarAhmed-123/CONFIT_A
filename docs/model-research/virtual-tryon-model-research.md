# Virtual Try-On (VTON) Model Research Report

**Date:** 2026-09-09  
**Feature:** Virtual Try-On Rendering  
**Status:** Research Phase  

---

## 1. Executive Summary

This research evaluates virtual try-on models for CONFIT_A's VTON feature. Currently, the code is complete but awaiting GPU worker deployment. The production engine is FASHN SegFee (segmentation-free commercial fork).

---

## 2. Current Implementation Analysis

### 2.1 Current Architecture
- **Engine:** FASHN SegFee (segmentation-free fork)
- **License:** Apache-2.0 (commercially clean)
- **VRAM:** ~8GB
- **Status:** Code complete, awaiting Modal GPU deployment
- **Fallback:** Honest 503 when worker unavailable

### 2.2 Current Limitations
1. **Not Deployed:** Requires Modal GPU worker
2. **Cold Start:** GPU initialization time
3. **Cost:** Pay-per-use GPU compute

---

## 3. Candidate Models Evaluation

### 3.1 Commercial-Safe Models

#### 3.1.1 FASHN VTON v1.5 (Current Choice)
- **Model ID:** `fashn-ai/fashn-vton-1.5`
- **License:** Apache-2.0
- **Commercial Use:** ✅ YES
- **Parameters:** 972M (MMDiT architecture)
- **VRAM:** ~8GB minimum
- **Latency:** ~5s on H100
- **Strengths:**
  - Apache-2.0 license (fully permissive)
  - Consumer GPU compatible (RTX 30xx/40xx)
  - Maskless operation (no segmentation required)
  - Production-proven API
- **Weaknesses:**
  - Single garment at a time
  - Limited category support
- **Fashion Suitability:** EXCELLENT

#### 3.1.2 FASHN SegFee Fork (Current Production)
- **Model ID:** `CONFIT_A fork of fashn-AI/fashn-vton-1.5`
- **License:** Apache-2.0 (non-commercial parser removed)
- **Commercial Use:** ✅ YES
- **VRAM:** ~8GB
- **Strengths:**
  - Commercially clean (non-commercial parser removed)
  - Verified on real A10 GPU
  - Real try-on image produced
- **Weaknesses:**
  - Custom fork maintenance
- **Fashion Suitability:** EXCELLENT

#### 3.1.3 Leffa (High-Fidelity)
- **Model ID:** `francis-rings/leffa`
- **License:** Apache-2.0
- **Commercial Use:** ✅ YES
- **VRAM:** ~12-16GB
- **Latency:** 6.8-12s on A10G
- **Strengths:**
  - Best quality for complex poses
  - Flow-guided attention
  - Apache-2.0 license
- **Weaknesses:**
  - Higher VRAM requirements
  - Slower inference
- **Fashion Suitability:** EXCELLENT (high-end)

### 3.2 Non-Commercial Models (Research Only)

#### 3.2.1 CatVTON
- **Model ID:** `Zheng-Chong/CatVTON`
- **License:** CC BY-NC-SA 4.0
- **Commercial Use:** ❌ NO
- **Strengths:**
  - Low VRAM (~8GB)
  - Good quality
- **Weaknesses:**
  - Non-commercial license
- **Fashion Suitability:** RESEARCH ONLY

#### 3.2.2 IDM-VTON
- **License:** CC BY-NC-SA 4.0
- **Commercial Use:** ❌ NO
- **Strengths:**
  - High quality
- **Weaknesses:**
  - High VRAM (18-24GB)
  - Non-commercial
- **Fashion Suitability:** RESEARCH ONLY

### 3.3 Cloud APIs

#### 3.3.1 FASHN API (Managed)
- **Pricing:** $0.075/credit
- **Strengths:**
  - No infrastructure management
  - Production-ready
  - Multiple modes (fast/balanced/quality)
- **Weaknesses:**
  - Higher cost than self-hosted
  - Vendor lock-in
- **Fashion Suitability:** EXCELLENT

#### 3.3.2 Kling Kolors VTON API
- **License:** Commercial API
- **Strengths:**
  - Enterprise-grade
  - High quality (SSIM: 0.935)
- **Weaknesses:**
  - Higher cost
  - External dependency
- **Fashion Suitability:** EXCELLENT

---

## 4. Recommendation

### 4.1 Primary Recommendation: Deploy FASHN SegFee Fork

**Rationale:**
1. **Commercially Clean:** Apache-2.0 with non-commercial components removed
2. **Production-Verified:** Real A10 GPU run with real output
3. **Cost-Effective:** ~8GB VRAM, consumer GPU compatible
4. **Already Integrated:** Code complete in CONFIT_A

### 4.2 Implementation Plan

#### Phase 1: Deploy Modal GPU Worker (Immediate)
1. Configure Modal account with provided tokens
2. Deploy `services/vton-worker/modal_app.py`
3. Set `VTON_WORKER_URL` in environment
4. Test with real images

#### Phase 2: Add Leffa as High-End Option (Future)
1. Deploy Leffa for complex poses
2. Implement engine selection logic
3. Offer quality tiers to users

#### Phase 3: Add Cloud Fallback (Future)
1. Integrate FASHN API as fallback
2. Use when self-hosted unavailable
3. Implement cost controls

---

## 5. Implementation Details

### 5.1 Modal Deployment Command
```bash
# Install Modal CLI
pip install modal

# Authenticate with provided token
modal token set --token-id [REDACTED] --token-secret [REDACTED]

# Deploy worker
cd services/vton-worker
modal deploy modal_app.py

# Set environment variable
export VTON_WORKER_URL=<deployed_url>
```

### 5.2 Engine Selection Logic
```python
def select_vton_engine(pose_complexity, quality_tier):
    if quality_tier == "premium" and pose_complexity > 0.7:
        return "leffa"  # High-quality for complex poses
    else:
        return "fashn_vton_segfee"  # Default commercial engine
```

---

## 6. Evidence Links

- **FASHN VTON v1.5:** https://huggingface.co/fashn-ai/fashn-vton-1.5
- **FASHN VTON Reddit:** https://www.reddit.com/r/LocalLLaMA/comments/1qpdn1t/fashn_vton_v15_apache20_virtual_tryon_model_runs/
- **Leffa:** https://github.com/francis-rings/leffa
- **CatVTON:** https://github.com/Zheng-Chong/CatVTON
- **CONFIT VTON Decision:** docs/vton-model-decision.md

---

**Status:** RESEARCH COMPLETE  
**Decision:** DEPLOY FASHN SEGFEE FORK  
**Next Action:** Deploy Modal GPU worker with provided tokens
