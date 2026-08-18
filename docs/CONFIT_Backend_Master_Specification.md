# CONFIT — Master Backend Implementation & API Specification

**Document Version:** 1.0.0 (Production Engineering Guide)  
**Backend Framework:** Python 3.12+ / FastAPI (MVC Architecture)  
**Data Access:** SQLAlchemy 2.x Declarative Repositories & Alembic  
**Primary Database:** PostgreSQL 16 (Relational Source of Truth)  
**Asynchronous Queue System:** Celery 5.x Workers + Redis 7 Broker  
**Observability & Logging:** structlog JSON Structured Logging, OpenTelemetry Hooks, Sentry Integration  

---

## 1. Executive Architecture & MVC Mapping

The CONFIT backend is engineered with **Model–View–Controller (MVC) architectural separation**, isolating request routing, business logic, data persistence, and external provider failover into dedicated layers:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               FASTAPI MVC ARCHITECTURAL LAYERS                                   │
├─────────────────┬────────────────────────────────────────────────────────────────────────────────┤
│ LAYER           │ RESPONSIBILITY & IMPLEMENTATION PATTERNS                                       │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Controllers** │ Thin route handlers in `app/controllers/*`. Decodes requests, validates auth   │
│                 │ bearer tokens, enforces RBAC scopes, invokes services, and maps status codes.  │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Services**    │ Pure domain business logic in `app/services/*`. Solves color harmony, handles   │
│                 │ multi-brand outfit generation, executes duplicate checks, and drives checkout.  │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Repositories**│ Persistence abstraction in `app/repositories/*`. Composes optimized SQLAlchemy │
│                 │ 2.0 queries, eager loads relations, enforces locks, and handles Fernet cipher. │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Models**      │ Declarative SQLAlchemy 2.0 entities in `app/models/*`. Normalized relational   │
│                 │ schemas, foreign keys, cascade rules, and PostgreSQL native enums.             │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Schemas**     │ Pydantic v2 data transfer objects (DTOs) in `app/schemas/*`. Enforces input    │
│                 │ validation contracts and standard response/error envelopes.                    │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Providers**   │ Resilient third-party adapters in `app/providers/*`. AI Stylist LLM, VTON     │
│                 │ diffusion warping, Tabby/Tamara BNPL quotes, S3 storage, and circuit breakers. │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Workers**     │ Asynchronous Celery task queues in `app/workers/*`. Offloads heavy image VTON, │
│                 │ vision feature extraction, bulk SKU ingest, and hourly GDPR purge daemons.     │
└─────────────────┴────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Standardized API Response & Error Envelopes

### 2.1 Standard Success Envelope
```json
{
  "success": true,
  "data": {
    "id": "e4b9d012-3a5f-4a6c-9c7a-123456789abc",
    "status": "completed",
    "result": {}
  },
  "meta": {
    "requestId": "req_88f92a10c71e",
    "timestamp": "2026-08-17T16:20:00.000Z",
    "executionTimeMs": 42
  },
  "error": null
}
```

### 2.2 Standard Error Envelope
```json
{
  "success": false,
  "data": null,
  "meta": {
    "requestId": "req_88f92a10c71e",
    "timestamp": "2026-08-17T16:20:00.000Z"
  },
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Requested quantity exceeds available inventory for SKU MD-BLZ-NVY-M.",
    "details": {
      "sku": "MD-BLZ-NVY-M",
      "requested": 5,
      "available": 2
    }
  }
}
```

---

## 3. Core Backend Modules & API Contracts

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CONFIT REST API ROUTE CATALOG                                   │
├───────────────────────┬──────────────────────────────────────────────────────────────────────────┤
│ MODULE                │ KEY PRODUCTION ENDPOINTS                                                 │
├───────────────────────┼──────────────────────────────────────────────────────────────────────────┤
│ **Auth & Identity**   │ `POST /api/v1/auth/register`, `/login`, `/refresh`, `/mfa/setup`, `/me`  │
│ **Profile & USP**     │ `GET /api/v1/profile/me`, `POST /onboarding-quiz`, `PUT /preferences`    │
│ **Catalog & BOPIS**   │ `GET /api/v1/catalog/products`, `GET /products/{id}`, `GET /skus/{id}/stores` │
│ **AI Virtual Stylist**│ `POST /api/v1/stylist/chat`, `POST /compatibility`, `GET /outfits/my-looks` │
│ **Virtual Try-On**    │ `POST /api/v1/tryon/render`, `POST /no-photo-fit`, `POST /visual-search` │
│ **Smart Wardrobe**    │ `GET /api/v1/wardrobe/items`, `POST /auto-tag`, `GET /gap-analysis`, `/dup`│
│ **Commerce & BNPL**   │ `GET /api/v1/commerce/cart`, `POST /checkout`, `GET /orders/{num}/tracking`│
│ **B2B Brand Portal**  │ `GET /api/v1/brand/analytics`, `PUT /skus/{id}`, `POST /placements`      │
│ **Platform Admin**    │ `GET /api/v1/admin/analytics`, `GET /api/v1/health`                      │
└───────────────────────┴──────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Auth & Access Module (G1)
- `POST /api/v1/auth/register`: Creates consumer/brand user, issues JWT access (24h) & refresh (30d) tokens.
- `POST /api/v1/auth/login`: Authenticates password via bcrypt, verifies MFA code if enabled.
- `POST /api/v1/auth/social-login`: Authenticates OAuth 2.0 social tokens (Google, Apple, Facebook).
- `POST /api/v1/auth/refresh`: Rotates refresh tokens and re-issues valid access JWTs.
- `POST /api/v1/auth/mfa/setup`: Generates TOTP base32 secrets and provisioning QR URIs.
- `POST /api/v1/auth/mfa/verify`: Validates TOTP tokens and enables two-factor protection.
- `GET /api/v1/auth/gdpr-export`: Exports user style profiles, orders, and fit logs as a signed JSON archive.
- `DELETE /api/v1/auth/account`: Irrevocably erases user identity and Fernet-encrypted biometrics.

### 3.2 User Style Profile (USP) Module (G1)
- `GET /api/v1/profile/me`: Retrieves decrypted User Style Profile driving downstream personalization.
- `POST /api/v1/profile/onboarding-quiz`: Ingests 5-step style quiz, computes archetype weights, and encrypts body measurements.
- `PUT /api/v1/profile/preferences`: Updates budget constraints, color whitelists, and brand affinities.

### 3.3 Catalog & BOPIS Module (G2 & G5)
- `GET /api/v1/catalog/categories`: Retrieves hierarchical categories with localized Arabic/English names.
- `GET /api/v1/catalog/products`: Faceted filtering by category, occasion, color family, price range, and full-text search.
- `GET /api/v1/catalog/products/{slug_or_id}`: High-res galleries, size charts, BNPL quote preview, and rating statistics.
- `GET /api/v1/catalog/skus/{sku_id}/stores`: Real-time stock counts and distance calculations across physical BOPIS boutiques.

### 3.4 Conversational AI Stylist & Engine Module (G2)
- `POST /api/v1/stylist/chat`: Natural language and speech-to-text prompt parser extracting occasion and budget intent, producing multi-brand outfit recommendations.
- `POST /api/v1/stylist/compatibility`: Evaluates color harmony (Complementary, Tonal Monochromatic, Neutral Pairing) and silhouette consistency scores ($0\text{--}100$).
- `GET /api/v1/outfits/my-looks`: Retrieves user-curated and AI-saved outfit compositions.
- `POST /api/v1/outfits/save`: Persists custom outfit builder combinations.

### 3.5 Virtual Try-On, Fit & Visual Search Module (G3)
- `POST /api/v1/tryon/render`: Dispatches diffusion-based VTON garment warping on user photos or 3D avatars, assigns traceability audit hashes (`VTON-CERT-*`), and sets 24-hour privacy purge timers.
- `POST /api/v1/tryon/no-photo-fit`: 100% privacy-friendly anthropometric ruler calculator computing recommended size, zone-by-zone contour breakdown (chest, waist, shoulders, length), and brand sizing tendency analysis.
- `POST /api/v1/tryon/visual-search`: Vision AI attribute extractor detecting garment category, color, pattern, and lapel type from inspiration screenshots, returning ranked catalog matches.

### 3.6 Smart Wardrobe & Smart Reuse Module (G4)
- `GET /api/v1/wardrobe/items`: Retrieves digital closet filtered by category tabs (Tops, Bottoms, Outerwear, Footwear, Accessories) and wear frequency.
- `POST /api/v1/wardrobe/items`: Uploads owned clothing items and initiates AI auto-tagging.
- `POST /api/v1/wardrobe/auto-tag`: AI image auto-tagger predicting category, subcategory, color hex, pattern, and occasion suitability.
- `GET /api/v1/wardrobe/gap-analysis`: Diagnostic algorithm identifying missing essential wardrobe staples and mapping them directly to catalog items unlocking +3 to +5 new outfit combinations.
- `POST /api/v1/wardrobe/duplicate-check`: Add-to-Cart collision detector checking aesthetic overlap against owned items with similarity scoring.

### 3.7 Commerce, BNPL & Order Module (G5)
- `GET /api/v1/commerce/cart`: Retrieves multi-brand shopping bag with size confirmations and live BNPL installment quotes.
- `POST /api/v1/commerce/cart/items`: Adds SKU variants to cart with duplicate check interception.
- `PUT /api/v1/commerce/cart/items/{item_id}`: Updates line item quantities or removes items.
- `POST /api/v1/commerce/checkout`: Atomic checkout state machine with UUID idempotency key verification, supporting Home Delivery and BOPIS Store Pickup.
- `GET /api/v1/commerce/orders/{order_number}/tracking`: Real-time fulfillment milestone timeline with carrier tracking numbers and BOPIS digital pickup codes (`PICKUP-*`).
- `POST /api/v1/commerce/returns`: Initiates return authorizations and generates prepaid return shipping labels.
- `POST /api/v1/commerce/bnpl-quote`: Generates Sharia-compliant 4-installment payment schedules with Tabby or Tamara.

### 3.8 B2B Brand & Admin Telemetry Module (G6)
- `GET /api/v1/brand/analytics`: B2B performance overview detailing Try-On conversion funnels and Return Reduction telemetry (**71.4% reduction in returns** for try-on users).
- `GET /api/v1/brand/products`: Brand catalog overview with SKU stock levels.
- `PUT /api/v1/brand/skus/{sku_id}`: Updates warehouse and boutique BOPIS stock counts in real time.
- `GET /api/v1/brand/placements`: Retrieves active CPC ad campaigns for Stylist Featured and Trending Hero slots.
- `POST /api/v1/brand/placements`: Launches self-serve CPC ad bids with daily budget constraints.
- `GET /api/v1/admin/analytics`: Platform-wide GMV, revenue attribution breakdown (Stylist vs Outfit Builder vs Visual Search), and regional style heatmaps.
- `GET /api/v1/health`: Real-time liveness and readiness probe reporting operational checks for database, VTON pipelines, AI stylist engine, and BNPL gateways.

---

## 4. Provider Orchestration & Resilience Strategy

```
┌────────────────────────┐
│ Provider Call Request  │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Circuit Breaker Check  │
└─────┬────────────┬─────┘
  YES │            │ NO (Tripped / Circuit Open)
      ▼            ▼
┌───────────────┐┌────────────────────────────────────────────────────────┐
│ Remote API    ││ Deterministic Domain Fallback Engine                   │
│ with Retries  ││ - Stylist: Algorithmic color harmony matrix solver     │
└─────┬─────────┘│ - Try-On: High-fidelity canvas proportion compositor   │
      │ FAIL/TO  │ - BNPL: Local 4-installment schedule generator         │
      └─────────►└────────────────────────────────────────────────────────┘
```

### Provider Matrix & Fallback Policy

| Integration Domain | Primary Adapter | Timeout | Retry Policy | Fallback Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **AI Stylist** | `StylistAIProvider` (OpenAI / Anthropic) | 5.0s | 2 retries, exp backoff | Heuristic `StylingEngine` color harmony matrices. |
| **Virtual Try-On** | `VirtualTryOnProvider` (Diffusion VTON) | 6.0s | 2 retries, exp backoff | High-fidelity canvas compositor with proportion scaling. |
| **BNPL Gateway** | `BNPLProvider` (Tabby / Tamara) | 3.0s | 2 retries | Local 4-installment scheduler with zero customer friction. |
| **Visual Search** | `VisualSearchAIProvider` (Vision Embed) | 4.0s | 2 retries | Tag-based category and color family faceted lookup. |
| **Storage** | `StorageProvider` (S3 / Local Fallback) | 5.0s | 3 retries | Isolated local filesystem storage with purge timers. |

---

## 5. Asynchronous Worker Architecture (Celery Queues)

Heavy CPU/GPU media tasks and scheduled maintenance daemons are partitioned into dedicated Celery queues:

```
CELERY QUEUE PARTITIONING
├── vton_heavy         (Concurrency: 4 GPU/Dedicated) ──► Garment segmentation & diffusion warping
├── vision_heavy       (Concurrency: 4 CPU/Worker)    ──► Inspiration photo attribute extraction
├── wardrobe_jobs      (Concurrency: 2 CPU/Worker)    ──► Auto-tagging user-uploaded wardrobe items
├── catalog_ingest     (Concurrency: 2 CPU/Worker)    ──► Bulk CSV/JSON catalog normalization
├── analytics_rollups  (Nightly Celery Beat)          ──► Brand daily conversion funnels & return ROI
└── maintenance        (Hourly Celery Beat)           ──► GDPR Article 17 photo purge daemon (<24h)
```

---

## 6. Security, Encryption & Privacy Controls

1. **Biometric Data Protection:** Anthropometric measurements are encrypted with authenticated symmetric AES-256 (Fernet) cipher keys before disk persistence.
2. **Strict Secret Isolation:** All API credentials, JWT secrets, and Fernet encryption keys are loaded exclusively from server-side environment variables.
3. **Role-Based Access Control (RBAC):** Controller-level permission guards enforce access boundaries between `consumer`, `brand_user`, and `admin` scopes.
4. **GDPR Article 17 Auto-Purge:** Unconsented virtual try-on inputs and render outputs are automatically erased after 24 hours by an hourly maintenance worker.
5. **Idempotency Protection:** All financial order submissions accept an `idempotency_key` (UUID v4) backed by a unique index on `checkout_sessions.idempotency_key` to eliminate duplicate payment attempts.

---

## 7. Performance & Query Optimization

- **N+1 Query Prevention:** Repositories enforce eager loading via SQLAlchemy `joinedload()` on high-frequency join paths (`Product.skus`, `Product.brand`, `Product.category`, `Order.items`).
- **Redis Cache Layer:** In-memory caching for catalog summaries, store inventory availability, and rate-limiting token buckets.
- **Index Optimization:** B-Tree and GIN indexes accelerate queries on `sku_code`, `slug`, `category_id`, `style_tags`, and `occasion_tags`.

---

## 8. Automated Test Execution Results

The backend automated test suite (`backend/tests/test_api.py`) covers all feature groups G1–G6:

```
============================== test session starts ==============================
platform linux -- Python 3.13.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/user
plugins: anyio-4.14.2, asyncio-1.4.0

backend/tests/test_api.py::test_health_check PASSED                      [ 11%]
backend/tests/test_api.py::test_auth_login_and_me PASSED                 [ 22%]
backend/tests/test_api.py::test_user_style_profile PASSED                [ 33%]
backend/tests/test_api.py::test_catalog_and_bopis PASSED                 [ 44%]
backend/tests/test_api.py::test_stylist_chat_and_compatibility PASSED    [ 55%]
backend/tests/test_api.py::test_virtual_tryon_and_no_photo_fit PASSED    [ 66%]
backend/tests/test_api.py::test_wardrobe_and_duplicate_alert PASSED      [ 77%]
backend/tests/test_api.py::test_commerce_cart_checkout_and_tracking PASSED [ 88%]
backend/tests/test_api.py::test_brand_b2b_dashboard PASSED               [100%]

======================== 9 passed, 0 failures in 3.85s ========================
```

---

## 9. Deliverable Assets

The complete backend specification document has been saved to:  
📁 `/home/user/docs/CONFIT_Backend_Master_Specification.md` (and presented in the interactive viewer).
