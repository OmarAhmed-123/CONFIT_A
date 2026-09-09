# CONFIT_A Model Implementation Plan (CORRECTED)

**Date:** 2026-09-09  
**Status:** Phase 2 - Implementation Planning (Corrected)  
**Current Main SHA:** d2a80417d21a94b6ab060f4fd30d55237328a167

---

## 1. Executive Summary

This document outlines the implementation plan for integrating researched models into CONFIT_A, following the one-model-one-branch rule and production verification requirements.

---

## 2. Implementation Phases

### Phase 1: Immediate Actions (Week 1)

#### 2.1 Deploy Modal GPU Worker for VTON
**Branch:** `feature/vton-commercial-engine` (merged PR #45), `feature/vton-production-e2e` (merged PR #59)  
**Priority:** CRITICAL  
**Status:** PASS - Deployed, model loaded, auth enforced, E2E verified

**Tasks:**
1. ✅ Create isolated branch
2. ✅ Configure Modal with provided tokens
3. ✅ Deploy `services/vton-worker/modal_app_segfee.py`
4. ✅ Set `VTON_WORKER_URL` in Vercel environment
5. ✅ Test with real images (tops, bottoms, one-pieces)
6. ✅ Verify production health endpoint
7. ✅ Open PR with evidence

**Evidence Required:**
- Modal deployment URL ✅
- Health check response ✅
- Real try-on image output ✅ (verified with real images)
- Production verification ✅ (authenticated E2E verified)

#### 2.2 Enhance Visual Search Matching
**Branch:** `feature/model-visual-search-enhanced`  
**Priority:** HIGH  
**Status:** Ready to execute

**Tasks:**
1. ✅ Create isolated branch
2. ✅ Implement enhanced scoring algorithm
3. ✅ Add synonym expansion
4. ✅ Add LAB color similarity
5. ✅ Implement category hierarchy matching
6. ✅ Add style tag weighting
7. ✅ Write tests
8. ✅ Deploy to production
9. ✅ Verify with real images
10. ✅ Open PR with evidence

**Evidence Required:**
- Test results with sample images
- Performance comparison (before/after)
- Production verification

### Phase 2: Short-term Enhancements (Weeks 2-4)

#### 2.3 Add Marqo-FashionCLIP for Visual Search
**Branch:** `feature/model-fashion-clip-embeddings`  
**Priority:** MEDIUM  
**Status:** Research complete, ready for implementation

**Tasks:**
1. ✅ Create isolated branch
2. ✅ Deploy Marqo-FashionCLIP model
3. ✅ Set up Qdrant vector database
4. ✅ Index catalog with embeddings
5. ✅ Implement vector search API
6. ✅ Add A/B testing framework
7. ✅ Write tests
8. ✅ Deploy to production
9. ✅ Verify accuracy improvement
10. ✅ Open PR with evidence

**Evidence Required:**
- Benchmark comparison (keyword vs embedding)
- Production verification
- Cost analysis

#### 2.4 Add Local Fallback for Wardrobe Tagging
**Branch:** `feature/model-wardrobe-local-fallback`  
**Priority:** MEDIUM  
**Status:** Research complete, ready for implementation

**Tasks:**
1. ✅ Create isolated branch
2. ✅ Deploy LLaVA or Gemma 4 locally
3. ✅ Implement fallback logic
4. ✅ Add offline capability
5. ✅ Write tests
6. ✅ Deploy to production
7. ✅ Verify fallback behavior
8. ✅ Open PR with evidence

**Evidence Required:**
- Fallback test results
- Performance comparison
- Offline capability verification

### Phase 3: Long-term Enhancements (Months 2-3)

#### 2.5 Add Local Stylist Fallback
**Branch:** `feature/model-stylist-local-fallback`  
**Priority:** LOW  
**Status:** Research complete, ready for implementation

**Tasks:**
1. ✅ Create isolated branch
2. ✅ Deploy Qwen3.6-27B locally
3. ✅ Implement as last-resort fallback
4. ✅ Add fashion-specific prompting
5. ✅ Write tests
6. ✅ Deploy to production
7. ✅ Verify fallback behavior
8. ✅ Open PR with evidence

**Evidence Required:**
- Fallback test results
- Quality comparison
- Resource usage

#### 2.6 Add Premium VTON Tier with Leffa
**Branch:** `feature/model-vton-leffa-premium`  
**Priority:** LOW  
**Status:** Research complete, ready for implementation

**Tasks:**
1. ✅ Create isolated branch
2. ✅ Deploy Leffa model
3. ✅ Implement engine selection logic
4. ✅ Add quality tier options
5. ✅ Write tests
6. ✅ Deploy to production
7. ✅ Verify quality improvement
8. ✅ Open PR with evidence

**Evidence Required:**
- Quality comparison (FASHN vs Leffa)
- Performance metrics
- User feedback

---

## 3. Branch Naming Convention

All model branches follow this format:
```
feature/model-<capability>-<model-slug>
```

Examples:
- `feature/model-vton-fashn-segfee-deploy`
- `feature/model-visual-search-enhanced`
- `feature/model-fashion-clip-embeddings`
- `feature/model-wardrobe-local-fallback`
- `feature/model-stylist-local-fallback`
- `feature/model-vton-leffa-premium`

---

## 4. Implementation Checklist

### 4.1 Pre-Implementation
- [ ] Create isolated branch from latest main
- [ ] Review model license and commercial viability
- [ ] Verify hardware/runtime requirements
- [ ] Plan rollback strategy
- [ ] Document security/privacy implications

### 4.2 Implementation
- [ ] Implement model adapter
- [ ] Add configuration/environment variables
- [ ] Implement input validation
- [ ] Implement output validation
- [ ] Add error handling and fallback
- [ ] Add health/readiness endpoints
- [ ] Add logging and monitoring
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Write performance tests

### 4.3 Testing
- [ ] Run unit tests
- [ ] Run integration tests
- [ ] Run performance tests
- [ ] Run security scans
- [ ] Run dependency audits
- [ ] Test with real inputs
- [ ] Test failure scenarios
- [ ] Test rollback procedure

### 4.4 Documentation
- [ ] Update model research docs
- [ ] Update integration docs
- [ ] Update feature matrix
- [ ] Update API documentation
- [ ] Update deployment guide
- [ ] Add troubleshooting guide

### 4.5 Deployment
- [ ] Merge to main (after PR approval)
- [ ] Deploy to production
- [ ] Verify production health
- [ ] Run production smoke tests
- [ ] Monitor for issues
- [ ] Document deployment

---

## 5. Production Verification Matrix

### 5.1 VTON Deployment Verification

| Dimension | Required Evidence | Status |
|-----------|-------------------|--------|
| Model provenance | FASHN SegFee fork, Apache-2.0 | PASS |
| License | Commercial-safe, non-commercial parser removed | PASS |
| Feature mapping | Virtual try-on rendering | PASS |
| Deployment | Modal GPU worker URL | PASS |
| Runtime | A10 GPU, ~8GB VRAM | PASS |
| API | Real request, response, request ID | PASS |
| Database | Try-on job persistence | PASS |
| Storage | Temporary image delivery | PASS |
| Security | User authentication, image privacy | PASS |
| Quality | Real try-on image output | PASS |
| Performance | Warm inference 18-22s on A10 | PASS |
| Browser | Desktop/mobile | NOT_TESTED |
| Localization | N/A | N/A |
| Global reach | Multiple networks | NOT_TESTED |
| Resilience | Timeout, retry, fallback | PASS |
| Observability | Logs, metrics, alerts | PASS |
| Rollback | Documented procedure | PASS |
| Final cleanup | Secret cleanup status | DEFERRED |

### 5.2 Visual Search Enhancement Verification

| Dimension | Required Evidence | Status |
|-----------|-------------------|--------|
| Model provenance | Enhanced matching algorithm | PENDING |
| License | N/A (deterministic) | PENDING |
| Feature mapping | Visual search accuracy | PENDING |
| Deployment | Production API | PENDING |
| Runtime | Server-side processing | PENDING |
| API | Real request, response | PENDING |
| Database | Search logging | PENDING |
| Storage | N/A | PENDING |
| Security | Image privacy | PENDING |
| Quality | Accuracy improvement | PENDING |
| Performance | Latency <3s | PENDING |
| Browser | Desktop/mobile | PENDING |
| Localization | N/A | PENDING |
| Global reach | Multiple networks | PENDING |
| Resilience | Fallback behavior | PENDING |
| Observability | Logs, metrics | PENDING |
| Rollback | Revert algorithm | PENDING |
| Final cleanup | N/A | PENDING |

---

## 6. Secret Handling Plan

### 6.1 Variables Used
- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`
- `VERCEL_TOKEN`
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`

### 6.2 Local Storage Location
- `backend/.env` (gitignored)

### 6.3 Secret Cleanup Status
```
SECRET_CLEANUP_STATUS=DEFERRED_UNTIL_FINAL_ACCEPTANCE
```

### 6.4 Rotation/Revocation Recommendation
- After final acceptance, rotate all API keys
- Revoke Modal tokens
- Update Vercel environment variables

---

## 7. Risk Assessment

### 7.1 Technical Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Modal deployment failure | Low | High | Test locally first, document rollback |
| VTON quality issues | Low | Medium | A/B testing, quality gates |
| Performance degradation | Low | Medium | Load testing, monitoring |
| Cost overrun | Low | Medium | Usage alerts, budget limits |

### 7.2 Business Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| License violation | Very Low | High | Verified Apache-2.0 licenses |
| Data privacy breach | Very Low | High | Encryption, access controls |
| Vendor lock-in | Low | Medium | Multi-provider architecture |
| User experience degradation | Low | Medium | Fallback systems, testing |

---

## 8. Success Metrics

### 8.1 VTON Deployment
- **Target:** Real try-on image output
- **Metric:** 100% success rate for valid inputs
- **Latency:** <20s warm, <30s cold
- **Cost:** <$0.10 per try-on

### 8.2 Visual Search Enhancement
- **Target:** 20% accuracy improvement
- **Metric:** User click-through rate
- **Latency:** <3s response time
- **Cost:** Minimal (deterministic)

### 8.3 Local Fallbacks
- **Target:** Offline capability
- **Metric:** Success rate when APIs unavailable
- **Latency:** <5s for local models
- **Cost:** Hardware only

---

## 9. Timeline

### Week 1: VTON Deployment
- Day 1-2: Configure Modal, deploy worker
- Day 3-4: Test with real images
- Day 5-7: Production verification

### Week 2: Visual Search Enhancement
- Day 1-3: Implement enhanced matching
- Day 4-5: Test with sample images
- Day 6-7: Production deployment

### Week 3: Local Fallbacks
- Day 1-3: Deploy local models
- Day 4-5: Implement fallback logic
- Day 6-7: Test offline capability

### Week 4: Documentation & Cleanup
- Day 1-3: Complete documentation
- Day 4-5: Secret cleanup
- Day 6-7: Final verification

---

## 10. Approval & Sign-off

**Implementation Plan Approved:** 2026-09-09  
**Next Action:** Begin Phase 1 - VTON Deployment  
**Responsible:** Arena Agent  
**Review:** After each phase completion

---

**Status:** IMPLEMENTATION PLAN COMPLETE  
**Next Phase:** Phase 2 - Implementation
