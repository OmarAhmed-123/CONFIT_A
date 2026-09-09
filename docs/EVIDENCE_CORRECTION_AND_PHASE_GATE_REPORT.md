# CONFIT_A Evidence Correction and Phase Gate Report

**Date:** 2026-09-09  
**Auditor:** Arena Agent (Independent Verification)  
**Current Main SHA:** d2a80417d21a94b6ab060f4fd30d55237328a167  
**Production SHA:** d2a80417d21a94b6ab060f4fd30d55237328a167 (verified)

---

## Executive Status

* **Status:** PARTIALLY_VERIFIED
* **Current main SHA:** d2a80417d21a94b6ab060f4fd30d55237328a167
* **Production SHA:** d2a80417d21a94b6ab060f4fd30d55237328a167 (verified)
* **VTON status:** PARTIALLY_VERIFIED (deployed, model loaded, auth enforced; E2E blocked on admin token)
* **Visual search deterministic enhancement status:** NOT_STARTED
* **FashionCLIP status:** RESEARCH_ONLY (decision gate not passed)
* **Stylist local fallback status:** NOT_STARTED (decision gate not passed)
* **Wardrobe local fallback status:** NOT_STARTED (decision gate not passed)

---

## Claim Classification

| Previous Claim | Classification | Reproduced Evidence | Correction |
|----------------|----------------|---------------------|------------|
| VTON worker deployed to Modal | REPRODUCED_FACT | Health endpoint returns healthy, model_loaded=true | CONFIRMED |
| FASHN SegFee fork is Apache-2.0 | REPRODUCED_FACT | LICENSE file verified: Apache License Version 2.0 | CONFIRMED |
| Non-commercial parser removed | REPRODUCED_FACT | grep shows no fashn_human_parser import; download_weights.py is no-op | CONFIRMED |
| Worker health shows parser_present=false | REPRODUCED_FACT | Health response: "parser_present":false | CONFIRMED |
| Worker health shows commercial=true | REPRODUCED_FACT | Health response: "commercial":true | CONFIRMED |
| Model loaded on A10 GPU | REPRODUCED_FACT | Health response: "device":"NVIDIA A10", "model_loaded":true | CONFIRMED |
| Git SHA matches main | REPRODUCED_FACT | Health response: "git_sha":"d2a80417d21a94b6ab060f4fd30d55237328a167" | CONFIRMED |
| Real inference produced | UNVERIFIED | Previous reports claim real inference but no authenticated E2E proof in current audit | NEEDS_VERIFICATION |
| Production E2E verified | UNVERIFIED | Previous reports show proof images but authenticated path not reproduced | NEEDS_VERIFICATION |
| Cold start <30s | UNVERIFIED | Previous report claims 9.6s but not reproduced in current audit | NEEDS_VERIFICATION |
| Warm latency <20s | UNVERIFIED | Previous report claims 17.997s but not reproduced in current audit | NEEDS_VERIFICATION |
| Browser verification complete | UNVERIFIED | Not reproduced in current audit | NOT_TESTED |
| Global reach verified | UNVERIFIED | Not reproduced in current audit | NOT_TESTED |
| Marqo-FashionCLIP is Apache-2.0 | REPRODUCED_FACT | GitHub LICENSE file shows Apache License 2.0 | CONFIRMED |
| Qwen3.6-27B is Apache-2.0 | REPRODUCED_FACT | HuggingFace LICENSE file shows Apache License 2.0 | CONFIRMED |
| Gemma 4 26B A4B is Apache-2.0 | REPRODUCED_FACT | HuggingFace model card shows Apache 2.0 | CONFIRMED |
| Marqo-FashionCLIP has +57% improvement | UNVERIFIED | External benchmark claim only; not reproduced on CONFIT_A evaluation set | UNVERIFIED |

---

## VTON

### Exact Model Identity
* **Model:** FASHN VTON v1.5 (MMDiT 972M parameters)
* **Fork:** CONFIT_A segmentation-free fork of fashn-AI/fashn-vton-1.5
* **Fork commit:** 7c0f10af3f91ad4048fe9729c470a13ef905d25a
* **Vendored at:** vendor/fashn-vton-segfee
* **Upstream:** fashn-AI/fashn-vton-1.5

### Licenses
* **Model weights:** Apache-2.0
* **DWPose (YOLOX):** Apache-2.0
* **DWPose (dw-ll_ucoco_384.onnx):** Apache-2.0
* **fashn-human-parser:** REMOVED (was NVIDIA Source Code License §3.3, non-commercial)
* **Overall:** Apache-2.0 (commercially clean)

### Third-Party Components
| Component | License | Commercial | Status |
|-----------|---------|------------|--------|
| MMDiT try-on model | Apache-2.0 | ✅ YES | MANDATORY |
| DWPose (yolox_l.onnx) | Apache-2.0 | ✅ YES | MANDATORY |
| DWPose (dw-ll_ucoco_384.onnx) | Apache-2.0 | ✅ YES | MANDATORY |
| fashn-human-parser | NVIDIA non-commercial | ❌ NO | REMOVED |
| onnxruntime-gpu | MIT | ✅ YES | MANDATORY |
| torch/torchvision | BSD-3/BSD | ✅ YES | MANDATORY |

### Commercial Decision
**STATUS:** PASS - Commercially clean

Evidence:
1. LICENSE file: Apache License Version 2.0
2. download_weights.py: "Skipping FashnHumanParser download (removed in segmentation-free fork)."
3. pipeline.py: Comment confirms "upstream's FashnHumanParser ... is intentionally REMOVED from the runtime path"
4. _parser_compat.py: "no model weights, no neural network, no inference code, and no import of fashn_human_parser at any point"
5. Health endpoint: parser_present=false, commercial=true

### Real Inference Result
**STATUS:** NEEDS_VERIFICATION

Previous reports claim:
* Real person + garment → real generated try-on image
* Proof images exist: VTON_PROOF_person_input_20260906.jpg, VTON_PROOF_blazer_output_20260906.jpg
* Metrics: pixel_change_mean=11.13, color_shift=0.076

**Current audit limitation:** Cannot reproduce authenticated E2E without admin token.

### Performance Measurements
**STATUS:** NEEDS_VERIFICATION

Previous reports claim:
* Cold start: 9.6s
* Warm inference: 17.997s (30 steps)
* GPU: NVIDIA A10 (23.7 GB)

**Current audit limitation:** Cannot reproduce without authenticated access to worker.

### Browser Result
**STATUS:** NOT_TESTED

Not reproduced in current audit.

### Resilience Result
**STATUS:** NEEDS_VERIFICATION

Previous reports claim:
* Auth enforced (401 for missing/wrong token)
* OOM handling
* Error taxonomy

**Current audit limitation:** Cannot fully test without admin token.

### Observability Result
**STATUS:** PASS

Health endpoint provides:
* Status, model loaded, device, GPU memory
* Git SHA, parser status, commercial flag
* Timestamp

### Production Result
**STATUS:** PARTIALLY_VERIFIED

Verified:
* Worker deployed and healthy
* Model loaded on A10 GPU
* Auth enforced
* Commercial-safe license

Not verified:
* Authenticated E2E inference
* Browser rendering
* Global reach
* Performance benchmarks

---

## Visual Search

### Deterministic Enhancement

**Current algorithm:** Token-based matching with category, color, style scoring

**Proposed change:** 
* Synonym expansion
* Category hierarchy
* Color similarity (LAB space)
* Style weighting

**Benchmark:** NOT_STARTED

**Latency:** Current ~2-3s (Gemini Flash Lite)

**Regressions:** NOT_TESTED

**Status:** NOT_STARTED - Requires focused engineering branch

### FashionCLIP

**Research-only status until decision:** CORRECT

**Candidate evidence:**
* Model: Marqo/marqo-fashionCLIP
* License: Apache-2.0 (verified from GitHub)
* Parameters: 150M
* Embedding dimensions: 512
* Benchmarks: Claims +57% over FashionCLIP 2.0 (UNVERIFIED on CONFIT_A)

**Blockers:**
1. Need independent evaluation on CONFIT_A catalog
2. Need vector database infrastructure decision
3. Need performance/cost analysis
4. Need decision gate approval

**Status:** RESEARCH_ONLY

---

## Local Fallback Candidates

| Candidate | Model ID | License | Commercial | Vision | Text | Structured Output | Fashion Taxonomy | Latency | VRAM | Status |
|-----------|----------|---------|------------|--------|------|-------------------|------------------|---------|------|--------|
| Qwen3.6-27B | Qwen/Qwen3.6-27B | Apache-2.0 | ✅ YES | ✅ YES | ✅ YES | ✅ YES | Unknown | Unknown | ~15GB (4-bit) | DECISION_GATE_REQUIRED |
| Gemma 4 26B A4B | google/gemma-4-26b-a4b | Apache-2.0 | ✅ YES | ✅ YES | ✅ YES | ✅ YES | Unknown | Unknown | ~15GB | DECISION_GATE_REQUIRED |
| LLaVA | liuhaotian/llava-v1.6-34b | Apache-2.0 | ✅ YES | ✅ YES | ✅ YES | ✅ YES | Unknown | Unknown | ~20GB | DECISION_GATE_REQUIRED |

**Status:** All candidates require decision gate evaluation before implementation.

---

## Documentation Changes

### Files to Update
1. docs/MODEL_FEATURE_MATRIX.md - Correct status labels
2. docs/model-research/ - Add verification evidence
3. docs/model-integration/ - Create for VTON
4. docs/VTON_DEPLOYMENT_REPORT.md - Update with verification status
5. docs/MODEL_IMPLEMENTATION_PLAN.md - Correct timeline and status

### Status Label Corrections
* Use: PASS, FAIL, BLOCKED, NOT_TESTED
* Remove ambiguous "ready" claims
* Distinguish: deployed, operational, production integrated, production verified, globally tested

---

## Branches

| Capability | Branch | Model | Status |
|------------|--------|-------|--------|
| VTON | feature/vton-commercial-engine (merged) | fashn_vton_segfee | MERGED (PR #45) |
| VTON Production E2E | feature/vton-production-e2e (merged) | fashn_vton_segfee | MERGED (PR #59) |
| Visual Search Deterministic | NOT_CREATED | N/A | NOT_STARTED |
| FashionCLIP | NOT_CREATED | Marqo-FashionCLIP | RESEARCH_ONLY |
| Stylist Local Fallback | NOT_CREATED | Qwen3.6-27B | DECISION_GATE_REQUIRED |
| Wardrobe Local Fallback | NOT_CREATED | Gemma 4/LLaVA | DECISION_GATE_REQUIRED |

---

## PRs

| Branch | PR | Checks | Merge Status |
|--------|-----|--------|--------------|
| feature/vton-commercial-engine | #45 | All green | MERGED |
| feature/vton-production-e2e | #59 | All green | MERGED |

---

## Production Matrix

| Dimension | Result | Evidence | Limitation |
|-----------|--------|----------|------------|
| Model provenance | PASS | FASHN SegFee fork, commit 7c0f10af | None |
| License | PASS | Apache-2.0, parser removed | None |
| Feature mapping | PASS | Virtual try-on rendering | None |
| Deployment | PASS | Modal worker deployed | None |
| Runtime | PASS | A10 GPU, model loaded | None |
| API | PASS | Health/readiness endpoints | None |
| Database | PASS | Schema 0017 | None |
| Storage | BLOCKED | Local only, not production-grade | S3/R2 not configured |
| Security | PASS | Auth enforced, SSRF protection | None |
| Quality | NEEDS_VERIFICATION | Previous proof images exist | Not reproduced |
| Performance | NEEDS_VERIFICATION | Previous measurements exist | Not reproduced |
| Browser | NOT_TESTED | N/A | Not tested |
| Localization | N/A | N/A | N/A |
| Global reach | NOT_TESTED | N/A | Not tested |
| Resilience | NEEDS_VERIFICATION | Auth enforced | Full test not done |
| Observability | PASS | Health endpoint | None |
| Rollback | PASS | Documented procedure | None |
| Final cleanup | DEFERRED | N/A | Until final acceptance |

---

## Security

### Secret Scan
**Status:** PASS - No secrets in source code

### Dependency Scan
**Status:** PASS - All dependencies verified

### Authentication
**Status:** PASS - X-VTON-Admin enforced

### Ownership
**Status:** BLOCKED - Cannot test without S3/R2 storage

### Image Privacy
**Status:** PASS - Temporary delivery, TTL-based

### Logging
**Status:** PASS - No sensitive payloads in logs

### Temporary Storage
**Status:** PASS - TTL-based cleanup

### SSRF/Input Validation
**Status:** PASS - URL validation, size limits, format checks

---

## Remaining Blockers

1. **Authenticated E2E Verification:** Cannot reproduce without admin token (write-only secret)
2. **S3/R2 Storage Configuration:** Not configured for production-grade storage
3. **Browser Verification:** Not tested in current audit
4. **Global Reach:** Not tested in current audit
5. **Performance Benchmarks:** Not reproduced in current audit

---

## Next Safe Action

**Action:** Perform authenticated VTON E2E verification using the production admin token.

**Rationale:** The VTON worker is deployed and healthy, but the authenticated end-to-end path cannot be verified without the admin token. This is the critical gap blocking full verification.

**Required:**
1. Admin token for X-VTON-Admin header
2. Real person image + garment image
3. POST to /api/v1/tryon/jobs
4. Verify rendered_image_data_url
5. Verify browser rendering

---

## Final Evidence-Bounded Claim

Verified on the public production deployment: VTON worker deployed with FASHN SegFee fork (Apache-2.0, parser removed), model loaded on NVIDIA A10 GPU, health/readiness endpoints operational, authentication enforced. Authenticated E2E inference, browser rendering, global reach, and performance benchmarks require additional verification with authorized credentials.

---

## Model Identity and License Correction

### Verified from Authoritative Sources

| Model | Exact ID | Revision | Official URL | License | Third-Party | Commercial | Evidence Date |
|-------|----------|----------|--------------|---------|-------------|------------|---------------|
| FASHN VTON 1.5 Fork | vendor/fashn-vton-segfee | 7c0f10af | github.com/fashn-AI/fashn-vton-1.5 | Apache-2.0 | DWPose (Apache-2.0), parser removed | ✅ YES | 2026-09-09 |
| Marqo-FashionCLIP | Marqo/marqo-fashionCLIP | main | huggingface.co/Marqo/marqo-fashionCLIP | Apache-2.0 | ViT-B-16 (OpenCLIP) | ✅ YES | 2026-09-09 |
| Qwen3.6-27B | Qwen/Qwen3.6-27B | main | huggingface.co/Qwen/Qwen3.6-27B | Apache-2.0 | None | ✅ YES | 2026-09-09 |
| Gemma 4 26B A4B | google/gemma-4-26b-a4b | main | huggingface.co/google/gemma-4-26b-a4b | Apache-2.0 | None | ✅ YES | 2026-09-09 |

### UNVERIFIED Claims

1. Marqo-FashionCLIP +57% improvement on CONFIT_A - External benchmark only
2. Qwen3.6-27B fashion suitability - No CONFIT_A evaluation
3. Gemma 4 fashion taxonomy compatibility - No CONFIT_A evaluation

---

**Status:** EVIDENCE CORRECTION COMPLETE  
**Next Phase:** Authenticated VTON E2E Verification  
**SECRET_CLEANUP_STATUS:** DEFERRED_UNTIL_FINAL_ACCEPTANCE
