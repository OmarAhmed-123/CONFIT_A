# CHANGELOG — CONFIT Luxury Fashion Technology Platform

All notable changes, architectural transitions, and technical audits of this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.0] — August 2026

### 🚀 Replaced Fake Compositing With Real Virtual Try-On (VTON) Architecture

#### Added
- **VTON Model Research & Evaluation Report (`docs/vton-model-decision.md`):**  
  Documented empirical benchmarks (FID, SSIM, LPIPS, VRAM, Latency) comparing CatVTON, Leffa, IDM-VTON, OOTDiffusion, FitDiT, and Kling Kolors API. Identified **CatVTON / Leffa** (Apache 2.0, <8GB VRAM) as the commercially viable open-source self-hosted foundation.
- **GPU Inference Worker (`services/vton-worker/`):**  
  Implemented a containerized 5-stage VTON pipeline:
  1. *Human Parsing & Body Masking (`HumanParsingEngine`)*: SCHP semantic parsing separating person, limbs, and background.
  2. *Pose Estimation (`PoseEstimationEngine`)*: DWPose 18-keypoint body landmark conditioning to deform garments along actual shoulder slopes.
  3. *Garment Preprocessing (`GarmentPreprocessor`)*: Alpha mask extraction and background isolation via BiRefNet / Rembg.
  4. *Diffusion Inpainting Engine (`CatVTONDiffusionEngine`)*: Generative spatial-concatenation neural inpainting.
  5. *Lighting Harmonization & Quality Audit (`LightingHarmonizer`, `VTONQualityAuditor`)*: Poisson ambient lighting matching and SSIM verification.
  - Added Serverless GPU deployment manifests for Modal.com (`services/vton-worker/modal_app.py`) and RunPod.
- **Asynchronous Job Queue & Database Schema:**  
  - Created `tryon_jobs` table for non-blocking GPU job submission, stage tracking (`queued` $\rightarrow$ `parsing_person` $\rightarrow$ `warping_garment` $\rightarrow$ `diffusion_rendering` $\rightarrow$ `completed`), and polling.
  - Created `garment_assets` table for caching preprocessed transparent garment cutouts and masks.
  - Created `person_scan_cache` table for caching human parsing masks by image hash.
- **Async Job REST API Endpoints:**  
  - `POST /api/v1/try-on/jobs` (Enqueues async VTON job)
  - `GET /api/v1/try-on/jobs/{job_id}` (Polls live inference progress and metrics)
  - `POST /api/v1/try-on/jobs/{job_id}/cancel` (Cancels active job)
  - `GET /api/v1/try-on/garments/{product_id}/asset` (Returns cached garment cutout & mask)
- **Automated VTON Pipeline Test Suite (`backend/tests/test_vton_pipeline.py`):**  
  4 new integration tests verifying job lifecycle, garment asset caching, input validation, and cancellation.

#### Changed
- **Frontend Try-On State Machine & Studio (`VirtualTryOnModal.tsx`, `useTryOnViewModel.ts`):**  
  - Replaced naive rectangular CSS overlay boxes with the actual rendered VTON output image.
  - Replaced misleading "Motion Sequence / Animation Engine" claims with truthful **"Layer Assembly Sequence (Step-by-Step Dressing)"**.
  - Verified Before/After Split slider comparing the exact same subject photo against the styled garment drape without mismatched background cuts.
  - Implemented dynamic fit score calculation based on real product compatibility averages from the database.
- **PostgreSQL Database Fixes on Neon.tech:**  
  - Fixed `NOT NULL` constraint violation on `tryon_sessions.user_image_url` and converted all image URL columns to `TEXT` to prevent base64 truncation.
  - Added `outfit_id`, `body_shape`, and `calibration_method` columns to PostgreSQL tables.
- **Vercel Serverless Compatibility:**  
  - Resolved read-only filesystem crash (`OSError: [Errno 30]`) in `backend/app/core/database.py`.

#### Removed
- Removed fake toasts claiming "Live motion preview generated" or "Animation rendering verified" when no motion model was running.
- Removed hardcoded static fit values ("98% Fit", "Dressed with 2 Layers").
