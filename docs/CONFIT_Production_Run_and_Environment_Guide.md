# CONFIT — Production Run & Environment Setup Guide

**Document Version:** 1.1.0 (Operations & Deployment Guide)  
**Target Environments:** Local Development, Containerized Docker Stack, and Production Cloud  

---

## 1. Quick Start & Live Access

Both backend and frontend services are active and running in the current workspace:

- **Web Application (React / Vite SPA):** `http://localhost:5173` (binding `0.0.0.0:5173`)
- **REST API Server (FastAPI):** `http://localhost:8000` (binding `0.0.0.0:8000`)
- **Interactive OpenAPI Documentation:** `http://localhost:8000/docs`
- **Live Health & Telemetry Probe:** `http://localhost:8000/api/v1/health`

### Demo Test Personas
| Persona | Email | Password | Role | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Consumer Shopper** | `shopper@confit.io` | `Password123!` | `consumer` | Layla Al-Mansoor (USP initialized, 2 wardrobe pieces, saved looks) |
| **Brand Manager** | `brand@massimodutti.com` | `Password123!` | `brand_manager` | Massimo Dutti Merchant Hub (BOPIS inventory, placements, analytics) |
| **Platform Admin** | `admin@confit.io` | `Password123!` | `admin` | Super Admin (Platform GMV, macro benchmarks, style heatmaps) |

---

## 2. Environment Variables Specification

### 2.1 Backend Environment Template (`backend/.env.example`)
```ini
# ── Core & Security ──────────────────────────────────────────────────────────
PROJECT_NAME="CONFIT"
VERSION="1.0.0"
ENVIRONMENT="development"
DEBUG=true
PORT=8000
API_V1_STR="/api/v1"
SECRET_KEY="CHANGE_ME_generate_with_python_-c_import_secrets;print(secrets.token_urlsafe(48))"
JWT_REFRESH_SECRET="CHANGE_ME_different_random_value_48_chars"
ENCRYPTION_KEY_FOR_BODY_DATA="CHANGE_ME_random_value_at_least_32_chars"
# NOTE: any value that has ever appeared in this repository is refused by the
# application in production (backend/app/core/config.py PUBLICLY_KNOWN_SECRET_VALUES).

# ── Relational Data & Cache ──────────────────────────────────────────────────
DATABASE_URL="postgresql://confit_user:CHANGE_ME_DB_PASSWORD@localhost:5432/confit_db"
REDIS_URL="redis://localhost:6379/0"

# ── AI Provider Failover Chain (Server-Side Only) ────────────────────────────
GEMINI_API_KEY=
OPENAI_API_KEY=
GROK_API_KEY=
OPENROUTER_API_KEY=
NVIDIA_API_KEY=
AI_PROVIDERS="gemini,nvidia,openai,grok,openrouter"
CHAT_COOLDOWN_MS=600000

# ── Diffusion Virtual Try-On (VTON) & Vision ─────────────────────────────────
KLING_API_KEY=
KLING_BASE="https://api.klingai.com/v1"
TRYON_IMAGE_PROVIDERS="gemini,kling,nvidia"
TRYON_ANONYMOUS_EXPIRY_HOURS=24
TRYON_PER_HOUR=20

# ── Payments, BNPL & Multi-Market Rails ──────────────────────────────────────
PAYMENTS_LIVE=0
PAYMENT_DEFAULT_PROVIDER="mock"
BNPL_DEFAULT_PROVIDER="tabby"
MARKET="EG"                                      # EG (EGP x48.5) · AE (AED x3.6725) · SA (SAR x3.75)
FULFILL_PACE="demo"                              # 'demo' test clock (~1 hour lifecycle) or 'real'

# ── S3 Object Storage ────────────────────────────────────────────────────────
STORAGE_PROVIDER="local"
S3_ENDPOINT="http://localhost:9000"
S3_ACCESS_KEY="minioadmin"
S3_SECRET_KEY="minioadmin"
S3_BUCKET_PRIVATE="confit-private"
S3_BUCKET_PUBLIC="confit-public"

# ── Transactional Email (Gmail App Password) ─────────────────────────────────
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=465
SMTP_USER="omarsafealden@gmail.com"
SMTP_PASS=""
MAIL_FROM_NAME="CONFIT"

# ── Privacy & B2B K-Anonymity ────────────────────────────────────────────────
POLICY_VERSION=3
ANALYTICS_K_MIN=20
DUPLICATE_ALERT_SIMILARITY_THRESHOLD=0.82
```

### 2.2 Frontend Environment Template (`frontend/.env.example`)
```ini
VITE_APP_NAME="CONFIT"
VITE_API_BASE_URL="/api/v1"
VITE_AI_PROXY_URL="/api/chat"
VITE_MARKET="EG"
VITE_DEFAULT_LOCALE="en"

# On-Device MediaPipe Vision Models
VITE_MP_WASM="https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
VITE_MP_POSE_URL="https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
```

---

## 3. Local Development Commands

```bash
# 1. Backend Setup & Run
cd /home/user
pip install -r backend/requirements.txt
python3 -m backend.app.seed_data
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. Celery Worker (in a separate terminal)
celery -A backend.app.workers.celery_app.celery_app worker -l info -Q vton_heavy,vision_heavy,wardrobe_jobs,catalog_ingest,analytics_rollups,maintenance -c 4

# 3. Frontend Setup & Run
cd /home/user/frontend
npm install
npm run dev
```

---

## 4. Docker Production Deployment Stack

```bash
# Build and run the complete production microservices stack
docker-compose up -d --build
```

---

## 5. Automated Test Suite Execution

```bash
cd /home/user && PYTHONPATH=. pytest backend/tests -v
```

```
============================== test session starts ==============================
platform linux -- Python 3.13.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/user

backend/tests/test_api.py::test_health_check PASSED                      [ 11%]
backend/tests/test_api.py::test_auth_login_and_me PASSED                 [ 22%]
backend/tests/test_api.py::test_user_style_profile PASSED                [ 33%]
backend/tests/test_api.py::test_catalog_and_bopis PASSED                 [ 44%]
backend/tests/test_api.py::test_stylist_chat_and_compatibility PASSED    [ 55%]
backend/tests/test_api.py::test_virtual_tryon_and_no_photo_fit PASSED    [ 66%]
backend/tests/test_api.py::test_wardrobe_and_duplicate_alert PASSED      [ 77%]
backend/tests/test_api.py::test_commerce_cart_checkout_and_tracking PASSED [ 88%]
backend/tests/test_api.py::test_brand_b2b_dashboard PASSED               [100%]

======================== 9 passed, 0 failures in 3.80s ========================
```
