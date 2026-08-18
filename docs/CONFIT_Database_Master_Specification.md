# CONFIT — Database Master Specification & Schema Architecture

**Document Version:** 1.0.0 (Production Delivery)  
**Target Database Engine:** PostgreSQL 16+ (Transactional System of Record)  
**ORM / Migration Targets:** SQLAlchemy 2.x Declarative Models & Alembic  
**Supporting Stores:** Redis 7 (Cache / Broker / Locks), S3-Compatible Object Storage (Media), Meilisearch (Faceted Search)  
**Prepared for:** Database Administrators, Principal Architects, Data Engineers, and Backend Systems Engineers  

---

## 1. Executive Purpose & Scope

This document defines the complete, production-grade database architecture for **CONFIT** — an AI-powered fashion technology platform integrating user identity, User Style Profiles (USP), AI conversational styling, diffusion-based virtual try-on (VTON), smart wardrobe reuse, multi-brand commerce, BOPIS fulfillment, and B2B brand analytics.

PostgreSQL serves as the immutable transactional source of truth for all structured entities, state machines, financial transactions, and audit records.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     CONFIT DATABASE ARCHITECTURE                                        │
├───────────────────────────────────┬───────────────────────────────────┬──────────────────────────────────┤
│        TRANSACTIONAL CORE         │         SUPPORTING CACHE          │         OBJECT STORAGE           │
│         (PostgreSQL 16)           │             (Redis 7)             │         (S3-Compatible)          │
│  - ACID Source of Truth           │  - Sub-ms Session State           │  - Raw & Warped Garment Imagery  │
│  - Identity & RBAC                │  - Rate Limit Token Buckets       │  - Unconsented 24h Purge Bucket  │
│  - User Style Profiles & Biometrics│ - Inventory Reservation Locks     │  - Brand CSV/JSON Ingestion Logs │
│  - Multi-Brand Catalog & BOPIS    │  - Celery Broker & Result Backend │  - Prepaid Return PDF Labels     │
│  - Orders, BNPL & Returns         │  - Common Query Document Cache    │  - Signed URL Presigned Targets  │
└───────────────────────────────────┴───────────────────────────────────┴──────────────────────────────────┘
```

---

## 2. Database Design Principles & Standards

### 2.1 Core Engineering Principles
1. **PostgreSQL as Sole Relational Truth:** All transactional decisions (orders, stock reservations, biometric consents, user profiles) originate and commit in PostgreSQL.
2. **Normalized 3NF Foundation with Selective JSONB:** Domain relations are normalized to third normal form. `JSONB` is reserved exclusively for bounded, semi-structured metadata (e.g., style aesthetic tags, size chart matrices, provider diagnostic dumps).
3. **Strict Foreign Keys & Referential Integrity:** Explicit foreign keys with deterministic cascade rules (`ON DELETE CASCADE`, `ON DELETE SET NULL`, `ON DELETE RESTRICT`) prevent orphaned records.
4. **Auditability & Soft Deletion:** Critical business entities support soft deletion (`deleted_at TIMESTAMPTZ NULL`) for legal compliance and operational disaster recovery.
5. **Money Handling Standard:** All currency amounts are represented as integer minor units (`price_minor BIGINT`, e.g., `$289.00` = `28900`) alongside an ISO-4217 currency code (`currency_code VARCHAR(3) DEFAULT 'USD'`).
6. **Fernet-256 Biometric Field Encryption:** Sensitive anthropometric measurements are encrypted before insertion into `user_body_profiles.encrypted_payload` using authenticated AES-256 symmetric cipher keys.
7. **Traceable Provider Telemetry:** External AI, vision, payment, and logistics provider calls are recorded in an append-only `provider_request_logs` table with sanitized payloads.

---

## 3. PostgreSQL Enums Catalogue

All enumerated domain types are defined natively in PostgreSQL for maximum data integrity:

```sql
-- 1. Identity & Permissions
CREATE TYPE user_role_enum AS ENUM ('consumer', 'brand_user', 'admin', 'super_admin');
CREATE TYPE user_status_enum AS ENUM ('active', 'invited', 'suspended', 'deleted');
CREATE TYPE auth_provider_enum AS ENUM ('local', 'google', 'apple', 'facebook');
CREATE TYPE mfa_method_enum AS ENUM ('totp', 'recovery_code');
CREATE TYPE consent_type_enum AS ENUM ('terms', 'privacy', 'photo_storage', 'marketing', 'analytics', 'ai_personalization');
CREATE TYPE consent_source_enum AS ENUM ('onboarding', 'settings', 'modal', 'support');

-- 2. Brands & Catalog
CREATE TYPE brand_status_enum AS ENUM ('active', 'pending', 'inactive');
CREATE TYPE brand_tier_enum AS ENUM ('basic', 'strategic', 'premium');
CREATE TYPE brand_user_role_enum AS ENUM ('owner', 'manager', 'analyst', 'catalog_editor');
CREATE TYPE product_visibility_enum AS ENUM ('draft', 'active', 'archived');
CREATE TYPE variant_status_enum AS ENUM ('active', 'inactive', 'out_of_stock');
CREATE TYPE inventory_source_enum AS ENUM ('central', 'store');

-- 3. Media & Assets
CREATE TYPE media_owner_enum AS ENUM ('user', 'brand', 'system');
CREATE TYPE asset_type_enum AS ENUM ('image', 'video', 'document');
CREATE TYPE media_purpose_enum AS ENUM ('avatar', 'product_image', 'tryon_input', 'tryon_output', 'wardrobe_item', 'visual_search_input', 'catalog_import', 'return_label');
CREATE TYPE media_visibility_enum AS ENUM ('private', 'internal', 'public');
CREATE TYPE retention_policy_enum AS ENUM ('temporary', 'retained_by_consent', 'permanent_business');

-- 4. Styling & Wardrobe
CREATE TYPE outfit_source_enum AS ENUM ('ai_stylist', 'manual_builder', 'imported');
CREATE TYPE outfit_slot_enum AS ENUM ('top', 'bottom', 'outerwear', 'dress', 'shoes', 'accessory', 'other');
CREATE TYPE item_source_enum AS ENUM ('catalog', 'wardrobe');
CREATE TYPE wardrobe_source_enum AS ENUM ('upload', 'manual', 'post_purchase');
CREATE TYPE wardrobe_tag_type_enum AS ENUM ('style', 'color', 'pattern', 'occasion', 'material');
CREATE TYPE wardrobe_tag_source_enum AS ENUM ('ai', 'manual', 'system');
CREATE TYPE duplicate_user_action_enum AS ENUM ('viewed', 'dismissed', 'opened_comparison', 'replaced', 'ignored');

-- 5. Visualization & Sizing
CREATE TYPE tryon_status_enum AS ENUM ('created', 'uploaded', 'queued', 'processing', 'completed', 'failed', 'expired');
CREATE TYPE fit_input_source_enum AS ENUM ('body_profile', 'explicit_measurements', 'size_history');
CREATE TYPE visual_search_status_enum AS ENUM ('created', 'queued', 'processing', 'completed', 'failed', 'expired');
CREATE TYPE visual_match_type_enum AS ENUM ('exact', 'similar');

-- 6. Commerce & Fulfillment
CREATE TYPE cart_status_enum AS ENUM ('active', 'converted', 'abandoned', 'expired');
CREATE TYPE fulfillment_method_enum AS ENUM ('delivery', 'bopis');
CREATE TYPE payment_state_enum AS ENUM ('pending', 'authorized', 'paid', 'failed', 'canceled');
CREATE TYPE checkout_state_enum AS ENUM ('created', 'confirmed', 'failed', 'expired');
CREATE TYPE payment_method_enum AS ENUM ('card', 'wallet', 'bnpl', 'cod');
CREATE TYPE payment_tx_status_enum AS ENUM ('initiated', 'authorized', 'captured', 'failed', 'refunded', 'canceled');
CREATE TYPE order_status_enum AS ENUM ('pending', 'confirmed', 'fulfilled', 'partially_fulfilled', 'delivered', 'canceled', 'returned', 'partially_returned');
CREATE TYPE shipment_status_enum AS ENUM ('pending', 'packed', 'shipped', 'in_transit', 'delivered', 'failed', 'returned');
CREATE TYPE bopis_status_enum AS ENUM ('awaiting_preparation', 'ready', 'picked_up', 'expired', 'canceled');
CREATE TYPE return_status_enum AS ENUM ('requested', 'approved', 'label_generated', 'in_transit', 'received', 'refunded', 'rejected', 'canceled');

-- 7. Analytics & Operations
CREATE TYPE notification_type_enum AS ENUM ('order', 'price_drop', 'restock', 'stylist', 'system', 'marketing');
CREATE TYPE notification_channel_enum AS ENUM ('in_app', 'email', 'push');
CREATE TYPE placement_surface_enum AS ENUM ('stylist_results', 'trending', 'discovery_grid');
CREATE TYPE bid_strategy_enum AS ENUM ('fixed', 'cpc', 'cpa_proxy');
CREATE TYPE placement_status_enum AS ENUM ('draft', 'active', 'paused', 'completed');
CREATE TYPE provider_type_enum AS ENUM ('llm', 'vision', 'embed', 'payment', 'shipping', 'notification', 'search');
CREATE TYPE provider_req_status_enum AS ENUM ('success', 'failure', 'timeout');
```

---

## 4. Complete Table Schema Specifications & DDL

### Group 1: Identity and Access Management

#### 4.1 `users`
**Purpose:** Master user record for consumer shoppers, brand managers, and platform administrators.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NULL,
    phone VARCHAR(50) NULL,
    password_hash VARCHAR(255) NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    avatar_asset_id UUID NULL,
    role user_role_enum DEFAULT 'consumer' NOT NULL,
    status user_status_enum DEFAULT 'active' NOT NULL,
    email_verified_at TIMESTAMPTZ NULL,
    last_login_at TIMESTAMPTZ NULL,
    preferred_language VARCHAR(10) DEFAULT 'en' NOT NULL, -- 'en' or 'ar'
    market_code VARCHAR(10) DEFAULT 'UAE' NOT NULL,
    timezone VARCHAR(50) DEFAULT 'Asia/Dubai' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX uq_users_email_active ON users (LOWER(email)) WHERE deleted_at IS NULL;
CREATE INDEX ix_users_role_status ON users (role, status);
CREATE INDEX ix_users_created_at ON users (created_at DESC);
```

#### 4.2 `auth_identities`
**Purpose:** Third-party OAuth 2.0 social authentication linkages (Google, Apple, Facebook).

```sql
CREATE TABLE auth_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider auth_provider_enum NOT NULL,
    provider_subject VARCHAR(255) NOT NULL,
    provider_email VARCHAR(255) NULL,
    provider_metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
    linked_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_auth_identities_provider_subject ON auth_identities (provider, provider_subject);
CREATE INDEX ix_auth_identities_user_id ON auth_identities (user_id);
```

#### 4.3 `refresh_tokens`
**Purpose:** Long-lived JWT session tracking, token rotation, and remote device revocation.

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    device_label VARCHAR(150) NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(500) NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_refresh_tokens_token_hash ON refresh_tokens (token_hash);
CREATE INDEX ix_refresh_tokens_user_expires ON refresh_tokens (user_id, expires_at) WHERE revoked_at IS NULL;
```

#### 4.4 `mfa_methods`
**Purpose:** Multi-Factor Authentication TOTP secrets and encrypted recovery codes.

```sql
CREATE TABLE mfa_methods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    method_type mfa_method_enum NOT NULL,
    secret_encrypted VARCHAR(500) NULL,
    is_primary BOOLEAN DEFAULT FALSE NOT NULL,
    verified_at TIMESTAMPTZ NULL,
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_mfa_methods_user_id ON mfa_methods (user_id);
```

#### 4.5 `privacy_consents`
**Purpose:** Explicit GDPR/CCPA consent lifecycle recording.

```sql
CREATE TABLE privacy_consents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type consent_type_enum NOT NULL,
    granted BOOLEAN NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    policy_version VARCHAR(20) DEFAULT 'v1.0' NOT NULL,
    source consent_source_enum DEFAULT 'onboarding' NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_privacy_consents_user_type ON privacy_consents (user_id, consent_type);
```

---

### Group 2: User Profile and Personalization

#### 5.1 `user_style_profiles`
**Purpose:** Canonical User Style Profile (USP) driving styling and recommendation engines.

```sql
CREATE TABLE user_style_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    style_archetypes JSONB DEFAULT '[]'::jsonb NOT NULL,
    preferred_colors JSONB DEFAULT '[]'::jsonb NOT NULL,
    avoided_colors JSONB DEFAULT '[]'::jsonb NOT NULL,
    preferred_patterns JSONB DEFAULT '[]'::jsonb NOT NULL,
    aesthetics JSONB DEFAULT '[]'::jsonb NOT NULL,
    budget_min_minor BIGINT DEFAULT 10000 NOT NULL,     -- $100.00
    budget_max_minor BIGINT DEFAULT 100000 NOT NULL,    -- $1,000.00
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    fit_preferences JSONB DEFAULT '{"fit": "regular"}'::jsonb NOT NULL,
    preferred_occasions JSONB DEFAULT '["work", "casual"]'::jsonb NOT NULL,
    preferred_brands JSONB DEFAULT '[]'::jsonb NOT NULL,
    excluded_brands JSONB DEFAULT '[]'::jsonb NOT NULL,
    profile_completion_percent INTEGER DEFAULT 0 NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_user_style_profiles_user_id ON user_style_profiles (user_id);
```

#### 5.2 `user_body_profiles`
**Purpose:** Encrypted anthropometric body data for sizing and proportion scaling.

```sql
CREATE TABLE user_body_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    height_cm NUMERIC(5, 2) NULL,
    weight_kg NUMERIC(5, 2) NULL,
    body_shape VARCHAR(50) NULL,           -- 'Athletic', 'Hourglass', 'Rectangle', etc.
    shoulder_cm NUMERIC(5, 2) NULL,
    chest_cm NUMERIC(5, 2) NULL,
    waist_cm NUMERIC(5, 2) NULL,
    hip_cm NUMERIC(5, 2) NULL,
    inseam_cm NUMERIC(5, 2) NULL,
    shoe_size VARCHAR(20) NULL,
    measurement_system VARCHAR(10) DEFAULT 'metric' NOT NULL,
    confidence_level NUMERIC(3, 2) DEFAULT 0.95 NOT NULL,
    encrypted_payload TEXT NULL,           -- Authenticated Fernet AES-256 cipher text
    last_confirmed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_user_body_profiles_user_id ON user_body_profiles (user_id);
```

#### 5.3 `style_quiz_responses`
**Purpose:** Granular step-by-step history of onboarding and style quiz submissions.

```sql
CREATE TABLE style_quiz_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    question_key VARCHAR(100) NOT NULL,
    response_value JSONB NOT NULL,
    submitted_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_style_quiz_responses_user_step ON style_quiz_responses (user_id, step_number);
```

---

### Group 3: Brand, Catalog, Stores, and Media

#### 6.1 `brands`
**Purpose:** Master brand entity for fashion house partners.

```sql
CREATE TABLE brands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT NULL,
    description_ar TEXT NULL,
    logo_asset_id UUID NULL,
    website_url VARCHAR(500) NULL,
    status brand_status_enum DEFAULT 'active' NOT NULL,
    partnership_tier brand_tier_enum DEFAULT 'strategic' NOT NULL,
    market_scope JSONB DEFAULT '["UAE", "KSA", "UK"]'::jsonb NOT NULL,
    commission_rate_percent NUMERIC(4, 2) DEFAULT 15.00 NOT NULL,
    return_rate_benchmark_percent NUMERIC(4, 2) DEFAULT 28.00 NOT NULL, -- Pre-VTON rate
    current_return_rate_percent NUMERIC(4, 2) DEFAULT 8.00 NOT NULL,    -- Post-VTON rate
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_brands_slug ON brands (slug);
CREATE INDEX ix_brands_status_tier ON brands (status, partnership_tier);
```

#### 6.2 `brand_users`
**Purpose:** B2B brand manager and staff authorization mapping.

```sql
CREATE TABLE brand_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role brand_user_role_enum DEFAULT 'manager' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_brand_users_brand_user ON brand_users (brand_id, user_id);
CREATE INDEX ix_brand_users_user_id ON brand_users (user_id);
```

#### 6.3 `brand_stores`
**Purpose:** Physical boutique locations supporting Buy Online, Pick Up In Store (BOPIS).

```sql
CREATE TABLE brand_stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    name_ar VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    address_line_1 VARCHAR(255) NOT NULL,
    address_line_2 VARCHAR(255) NULL,
    city VARCHAR(100) NOT NULL,
    region VARCHAR(100) NOT NULL,
    country_code VARCHAR(3) DEFAULT 'UAE' NOT NULL,
    postal_code VARCHAR(20) NULL,
    latitude NUMERIC(10, 7) NOT NULL,
    longitude NUMERIC(10, 7) NOT NULL,
    phone VARCHAR(50) NULL,
    is_bopis_enabled BOOLEAN DEFAULT TRUE NOT NULL,
    hours_json JSONB DEFAULT '{"mon_sun": "10:00 - 22:00"}'::jsonb NOT NULL,
    pickup_instructions TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_brand_stores_brand_code ON brand_stores (brand_id, code);
CREATE INDEX ix_brand_stores_city_country ON brand_stores (brand_id, city, country_code);
```

#### 6.4 `catalog_products`
**Purpose:** Logical fashion product catalog entity.

```sql
CREATE TABLE catalog_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    slug VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    name_ar VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    description_ar TEXT NOT NULL,
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100) NULL,
    style_tags JSONB DEFAULT '[]'::jsonb NOT NULL,
    material_info JSONB DEFAULT '{}'::jsonb NOT NULL,
    care_info JSONB DEFAULT '{}'::jsonb NOT NULL,
    gender_target VARCHAR(20) NULL,
    occasion_tags JSONB DEFAULT '[]'::jsonb NOT NULL,
    color_family VARCHAR(50) NOT NULL,
    dominant_hex VARCHAR(20) DEFAULT '#1B1F3B' NOT NULL,
    base_price_minor BIGINT NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    rating NUMERIC(3, 2) DEFAULT 4.80 NOT NULL,
    review_count INTEGER DEFAULT 0 NOT NULL,
    style_compatibility_base INTEGER DEFAULT 95 NOT NULL,
    visibility_status product_visibility_enum DEFAULT 'active' NOT NULL,
    is_featured BOOLEAN DEFAULT FALSE NOT NULL,
    search_document_version INTEGER DEFAULT 1 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX uq_catalog_products_slug ON catalog_products (slug) WHERE deleted_at IS NULL;
CREATE INDEX ix_catalog_products_brand_visibility ON catalog_products (brand_id, visibility_status);
CREATE INDEX ix_catalog_products_category ON catalog_products (category, subcategory);
CREATE INDEX ix_catalog_products_color ON catalog_products (color_family);
CREATE INDEX gin_catalog_products_style_tags ON catalog_products USING gin (style_tags);
CREATE INDEX gin_catalog_products_occasions ON catalog_products USING gin (occasion_tags);
```

#### 6.5 `product_variants`
**Purpose:** Physical SKU units with specific size, colorway, pricing overrides, and barcodes.

```sql
CREATE TABLE product_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES catalog_products(id) ON DELETE CASCADE,
    sku VARCHAR(100) UNIQUE NOT NULL,
    color_name VARCHAR(100) NOT NULL,
    color_hex VARCHAR(20) DEFAULT '#1B1F3B' NOT NULL,
    size_label VARCHAR(30) NOT NULL,       -- 'S', 'M', 'L', 'XL', '32x30'
    fit_note VARCHAR(150) NULL,
    price_minor BIGINT NOT NULL,
    compare_at_price_minor BIGINT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    barcode VARCHAR(100) NULL,
    status variant_status_enum DEFAULT 'active' NOT NULL,
    attributes JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX uq_product_variants_sku ON product_variants (sku) WHERE deleted_at IS NULL;
CREATE INDEX ix_product_variants_product_status ON product_variants (product_id, status);
CREATE INDEX ix_product_variants_price ON product_variants (price_minor);
CREATE INDEX ix_product_variants_size_color ON product_variants (size_label, color_name);
```

#### 6.6 `inventory_items`
**Purpose:** Real-time stock levels per variant and store location (for BOPIS reservation).

```sql
CREATE TABLE inventory_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id UUID NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    store_id UUID NULL REFERENCES brand_stores(id) ON DELETE CASCADE, -- NULL = central DC
    quantity_available INTEGER DEFAULT 0 NOT NULL,
    quantity_reserved INTEGER DEFAULT 0 NOT NULL,
    inventory_source inventory_source_enum DEFAULT 'central' NOT NULL,
    last_synced_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_inventory_items_variant_store_src ON inventory_items (variant_id, store_id, inventory_source);
CREATE INDEX ix_inventory_items_store_stock ON inventory_items (store_id, quantity_available);
```

#### 6.7 `media_assets`
**Purpose:** Centralized media asset registry with retention lifecycle management.

```sql
CREATE TABLE media_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_type media_owner_enum DEFAULT 'system' NOT NULL,
    owner_id UUID NOT NULL,
    asset_type asset_type_enum DEFAULT 'image' NOT NULL,
    purpose media_purpose_enum NOT NULL,
    storage_key VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    width INTEGER NULL,
    height INTEGER NULL,
    duration_seconds NUMERIC(6, 2) NULL,
    sha256_hash VARCHAR(64) NULL,
    visibility media_visibility_enum DEFAULT 'public' NOT NULL,
    retention_policy retention_policy_enum DEFAULT 'temporary' NOT NULL,
    expires_at TIMESTAMPTZ NULL,          -- Evaluated by hourly GDPR purge daemon
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX ix_media_assets_owner ON media_assets (owner_type, owner_id);
CREATE INDEX ix_media_assets_purpose_vis ON media_assets (purpose, visibility);
CREATE INDEX ix_media_assets_expires ON media_assets (expires_at) WHERE expires_at IS NOT NULL;
```

---

### Group 4: Discovery, Outfits, and Smart Wardrobe

#### 7.1 `outfits`
**Purpose:** User-curated or AI-generated outfit compositions.

```sql
CREATE TABLE outfits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NULL,
    source outfit_source_enum DEFAULT 'ai_stylist' NOT NULL,
    occasion VARCHAR(100) NOT NULL,
    style_summary TEXT NULL,
    total_price_minor BIGINT DEFAULT 0 NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    compatibility_score INTEGER DEFAULT 95 NOT NULL,
    color_palette JSONB DEFAULT '[]'::jsonb NOT NULL,
    style_tags JSONB DEFAULT '[]'::jsonb NOT NULL,
    share_token VARCHAR(100) UNIQUE NULL,
    is_saved BOOLEAN DEFAULT FALSE NOT NULL,
    is_system_curated BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX ix_outfits_user_saved ON outfits (user_id, is_saved) WHERE deleted_at IS NULL;
CREATE INDEX ix_outfits_source ON outfits (source);
```

#### 7.2 `outfit_items`
**Purpose:** Slot mappings linking outfits to catalog variants or owned wardrobe items.

```sql
CREATE TABLE outfit_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
    variant_id UUID NULL REFERENCES product_variants(id) ON DELETE SET NULL,
    wardrobe_item_id UUID NULL,
    slot_type outfit_slot_enum DEFAULT 'top' NOT NULL,
    position_index INTEGER DEFAULT 0 NOT NULL,
    source item_source_enum DEFAULT 'catalog' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_outfit_items_outfit_pos ON outfit_items (outfit_id, position_index);
```

#### 7.3 `wardrobe_items`
**Purpose:** User's digital closet of owned garments supporting smart reuse.

```sql
CREATE TABLE wardrobe_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    media_asset_id UUID NULL REFERENCES media_assets(id) ON DELETE SET NULL,
    image_url VARCHAR(1000) NOT NULL,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,        -- 'Outerwear', 'Tops', 'Bottoms', etc.
    subcategory VARCHAR(100) NULL,
    color_primary VARCHAR(50) NOT NULL,
    color_hex VARCHAR(20) DEFAULT '#000000' NOT NULL,
    pattern VARCHAR(50) DEFAULT 'Solid' NOT NULL,
    brand_name VARCHAR(100) DEFAULT 'Own Collection' NOT NULL,
    seasonality JSONB DEFAULT '["all_season"]'::jsonb NOT NULL,
    occasion_tags JSONB DEFAULT '["casual"]'::jsonb NOT NULL,
    wear_frequency VARCHAR(30) DEFAULT 'regular' NOT NULL, -- 'favorite', 'regular', 'rarely_worn'
    wear_count INTEGER DEFAULT 0 NOT NULL,
    last_worn_date TIMESTAMPTZ NULL,
    purchase_price_minor BIGINT NULL,
    favorite BOOLEAN DEFAULT FALSE NOT NULL,
    rarely_worn BOOLEAN DEFAULT FALSE NOT NULL,
    source wardrobe_source_enum DEFAULT 'upload' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX ix_wardrobe_items_user_category ON wardrobe_items (user_id, category) WHERE deleted_at IS NULL;
CREATE INDEX ix_wardrobe_items_user_favorite ON wardrobe_items (user_id, favorite);
CREATE INDEX gin_wardrobe_items_occasions ON wardrobe_items USING gin (occasion_tags);
```

#### 7.4 `wardrobe_tags`
**Purpose:** Normalized AI auto-tags extracted from garment photos.

```sql
CREATE TABLE wardrobe_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wardrobe_item_id UUID NOT NULL REFERENCES wardrobe_items(id) ON DELETE CASCADE,
    tag_type wardrobe_tag_type_enum NOT NULL,
    tag_value VARCHAR(100) NOT NULL,
    confidence NUMERIC(3, 2) DEFAULT 0.95 NOT NULL,
    source wardrobe_tag_source_enum DEFAULT 'ai' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_wardrobe_tags_item_type ON wardrobe_tags (wardrobe_item_id, tag_type);
CREATE INDEX ix_wardrobe_tags_type_val ON wardrobe_tags (tag_type, tag_value);
```

#### 7.5 `duplicate_alert_logs`
**Purpose:** Telemetry tracking when an Add-to-Cart action triggers a wardrobe duplicate alert.

```sql
CREATE TABLE duplicate_alert_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    candidate_variant_id UUID NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    matched_wardrobe_item_id UUID NOT NULL REFERENCES wardrobe_items(id) ON DELETE CASCADE,
    similarity_score INTEGER NOT NULL,
    threshold_used INTEGER DEFAULT 82 NOT NULL,
    user_action duplicate_user_action_enum DEFAULT 'viewed' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_duplicate_alert_logs_user ON duplicate_alert_logs (user_id, created_at DESC);
CREATE INDEX ix_duplicate_alert_logs_candidate ON duplicate_alert_logs (candidate_variant_id);
```

---

### Group 5: Try-On, Fit, and Visual Search

#### 8.1 `tryon_sessions`
**Purpose:** Virtual try-on rendering lifecycle, traceability hashes, and privacy timers.

```sql
CREATE TABLE tryon_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    input_asset_id UUID NULL REFERENCES media_assets(id) ON DELETE SET NULL,
    output_asset_id UUID NULL REFERENCES media_assets(id) ON DELETE SET NULL,
    variant_id UUID NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    provider_name VARCHAR(100) DEFAULT 'fashn_diffusion_v2' NOT NULL,
    status tryon_status_enum DEFAULT 'completed' NOT NULL,
    body_profile_snapshot JSONB DEFAULT '{}'::jsonb NOT NULL,
    fit_confidence_score INTEGER DEFAULT 95 NOT NULL,
    body_fit_verdict VARCHAR(100) DEFAULT 'True to Size' NOT NULL,
    body_scaling_factor NUMERIC(4, 2) DEFAULT 1.00 NOT NULL,
    traceability_hash VARCHAR(64) NOT NULL,
    ai_disclosure_text VARCHAR(255) DEFAULT 'AI Synthesized Garment Fit — Certified CONFIT VTON Engine v2.4' NOT NULL,
    error_code VARCHAR(50) NULL,
    error_message_sanitized TEXT NULL,
    consent_retained BOOLEAN DEFAULT FALSE NOT NULL,
    expires_at TIMESTAMPTZ NULL,          -- Default: NOW() + 24 hours if unconsented
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_tryon_sessions_user_status ON tryon_sessions (user_id, status);
CREATE INDEX ix_tryon_sessions_variant ON tryon_sessions (variant_id);
CREATE INDEX ix_tryon_sessions_expires ON tryon_sessions (expires_at) WHERE expires_at IS NOT NULL;
```

#### 8.2 `fit_recommendations`
**Purpose:** Stored explainable fit outputs and size recommendations.

```sql
CREATE TABLE fit_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    variant_id UUID NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    recommendation_size VARCHAR(20) NOT NULL,
    fit_score INTEGER DEFAULT 95 NOT NULL,
    explanation JSONB NOT NULL,
    input_source fit_input_source_enum DEFAULT 'body_profile' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_fit_recommendations_user ON fit_recommendations (user_id, created_at DESC);
CREATE INDEX ix_fit_recommendations_variant ON fit_recommendations (variant_id);
```

#### 8.3 `visual_search_sessions`
**Purpose:** Photo style match input tracking and detected fashion attributes.

```sql
CREATE TABLE visual_search_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    input_asset_id UUID NULL REFERENCES media_assets(id) ON DELETE SET NULL,
    input_image_url VARCHAR(1000) NOT NULL,
    provider_name VARCHAR(100) DEFAULT 'confit_vision_ai' NOT NULL,
    status visual_search_status_enum DEFAULT 'completed' NOT NULL,
    extracted_attributes JSONB DEFAULT '{}'::jsonb NOT NULL,
    top_result_count INTEGER DEFAULT 0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_visual_search_sessions_user ON visual_search_sessions (user_id, created_at DESC);
```

#### 8.4 `visual_search_results`
**Purpose:** Result rankings linking visual search queries to catalog variants.

```sql
CREATE TABLE visual_search_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES visual_search_sessions(id) ON DELETE CASCADE,
    variant_id UUID NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    rank_position INTEGER NOT NULL,
    confidence_score NUMERIC(5, 2) NOT NULL,
    match_type visual_match_type_enum DEFAULT 'exact' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_visual_search_results_session_rank ON visual_search_results (session_id, rank_position);
CREATE INDEX ix_visual_search_results_variant ON visual_search_results (variant_id);
```

---

### Group 6: Commerce, Payments, and Fulfillment

#### 9.1 `carts`
**Purpose:** Active multi-brand cart sessions (guest and authenticated).

```sql
CREATE TABLE carts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
    guest_token VARCHAR(100) UNIQUE NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    status cart_status_enum DEFAULT 'active' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_carts_guest_token ON carts (guest_token) WHERE guest_token IS NOT NULL;
CREATE INDEX ix_carts_user_status ON carts (user_id, status);
```

#### 9.2 `cart_items`
**Purpose:** Line items in the multi-brand cart with optional outfit source tracking.

```sql
CREATE TABLE cart_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id UUID NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
    variant_id UUID NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    quantity INTEGER DEFAULT 1 NOT NULL,
    unit_price_minor BIGINT NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    source_outfit_id UUID NULL REFERENCES outfits(id) ON DELETE SET NULL,
    fit_recommendation_id UUID NULL REFERENCES fit_recommendations(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_cart_items_cart_variant ON cart_items (cart_id, variant_id);
CREATE INDEX ix_cart_items_outfit ON cart_items (source_outfit_id);
```

#### 9.3 `checkout_sessions`
**Purpose:** Idempotency boundary and state machine for checkout initiation.

```sql
CREATE TABLE checkout_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id UUID NOT NULL REFERENCES carts(id) ON DELETE RESTRICT,
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    checkout_token VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    shipping_address JSONB NOT NULL,
    billing_address JSONB NULL,
    fulfillment_method fulfillment_method_enum DEFAULT 'delivery' NOT NULL,
    store_id UUID NULL REFERENCES brand_stores(id),
    subtotal_minor BIGINT NOT NULL,
    discount_minor BIGINT DEFAULT 0 NOT NULL,
    shipping_minor BIGINT DEFAULT 0 NOT NULL,
    tax_minor BIGINT DEFAULT 0 NOT NULL,
    total_minor BIGINT NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    payment_state payment_state_enum DEFAULT 'pending' NOT NULL,
    checkout_state checkout_state_enum DEFAULT 'created' NOT NULL,
    idempotency_key VARCHAR(100) UNIQUE NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_checkout_sessions_token ON checkout_sessions (checkout_token);
CREATE UNIQUE INDEX uq_checkout_sessions_idemp ON checkout_sessions (idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX ix_checkout_sessions_user ON checkout_sessions (user_id, created_at DESC);
```

#### 9.4 `payment_transactions`
**Purpose:** Provider-agnostic ledger for Card, Apple Pay, Tabby, Tamara, and COD.

```sql
CREATE TABLE payment_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checkout_session_id UUID NOT NULL REFERENCES checkout_sessions(id) ON DELETE CASCADE,
    provider_name VARCHAR(100) NOT NULL,   -- 'stripe', 'tabby', 'tamara', 'checkout_dot_com'
    provider_reference VARCHAR(255) NULL,
    payment_method payment_method_enum DEFAULT 'card' NOT NULL,
    amount_minor BIGINT NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    status payment_tx_status_enum DEFAULT 'initiated' NOT NULL,
    installments_count INTEGER DEFAULT 1 NOT NULL,
    raw_response_sanitized JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_payment_tx_checkout ON payment_transactions (checkout_session_id);
CREATE INDEX ix_payment_tx_provider_ref ON payment_transactions (provider_name, provider_reference);
```

#### 9.5 `orders`
**Purpose:** Immutable final order entity.

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checkout_session_id UUID UNIQUE NOT NULL REFERENCES checkout_sessions(id),
    order_number VARCHAR(50) UNIQUE NOT NULL,
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    status order_status_enum DEFAULT 'pending' NOT NULL,
    fulfillment_method fulfillment_method_enum DEFAULT 'delivery' NOT NULL,
    subtotal_minor BIGINT NOT NULL,
    discount_minor BIGINT DEFAULT 0 NOT NULL,
    shipping_minor BIGINT DEFAULT 0 NOT NULL,
    tax_minor BIGINT DEFAULT 0 NOT NULL,
    total_minor BIGINT NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    try_on_assisted BOOLEAN DEFAULT FALSE NOT NULL,
    stylist_assisted BOOLEAN DEFAULT FALSE NOT NULL,
    placed_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_orders_number ON orders (order_number);
CREATE INDEX ix_orders_user_placed ON orders (user_id, placed_at DESC);
CREATE INDEX ix_orders_status ON orders (status);
```

#### 9.6 `order_items`
**Purpose:** Order line items capturing snapshot pricing, brand metadata, and return state.

```sql
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    variant_id UUID NOT NULL REFERENCES product_variants(id),
    product_title VARCHAR(255) NOT NULL,
    brand_name VARCHAR(255) NOT NULL,
    size_label VARCHAR(30) NOT NULL,
    color_name VARCHAR(100) NOT NULL,
    quantity INTEGER DEFAULT 1 NOT NULL,
    unit_price_minor BIGINT NOT NULL,
    subtotal_minor BIGINT NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    source_outfit_id UUID NULL REFERENCES outfits(id) ON DELETE SET NULL,
    is_returned BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_order_items_order ON order_items (order_id);
CREATE INDEX ix_order_items_variant ON order_items (variant_id);
```

#### 9.7 `shipments`
**Purpose:** Courier tracking milestones for home deliveries.

```sql
CREATE TABLE shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    carrier_name VARCHAR(100) DEFAULT 'CONFIT Express Logistics' NOT NULL,
    tracking_number VARCHAR(100) NULL,
    tracking_url VARCHAR(500) NULL,
    shipment_status shipment_status_enum DEFAULT 'pending' NOT NULL,
    estimated_delivery_at TIMESTAMPTZ NULL,
    actual_delivery_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_shipments_order ON shipments (order_id);
CREATE INDEX ix_shipments_tracking ON shipments (tracking_number);
```

#### 9.8 `bopis_pickups`
**Purpose:** Store-level pickup readiness, digital QR pass codes, and customer handoffs.

```sql
CREATE TABLE bopis_pickups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID UNIQUE NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    store_id UUID NOT NULL REFERENCES brand_stores(id),
    pickup_code VARCHAR(30) UNIQUE NOT NULL, -- e.g., 'PICKUP-8821'
    ready_at TIMESTAMPTZ NULL,
    picked_up_at TIMESTAMPTZ NULL,
    status bopis_status_enum DEFAULT 'awaiting_preparation' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_bopis_pickups_code ON bopis_pickups (pickup_code);
CREATE INDEX ix_bopis_pickups_store_status ON bopis_pickups (store_id, status);
```

#### 9.9 `returns`
**Purpose:** Return authorization lifecycle and prepaid label generation.

```sql
CREATE TABLE returns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    return_number VARCHAR(50) UNIQUE NOT NULL,
    status return_status_enum DEFAULT 'requested' NOT NULL,
    reason_code VARCHAR(100) NOT NULL,     -- 'Wrong Size', 'Style Mismatch', etc.
    reason_notes TEXT NULL,
    label_asset_id UUID NULL REFERENCES media_assets(id) ON DELETE SET NULL,
    refund_amount_minor BIGINT NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    try_on_used_for_item BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_returns_number ON returns (return_number);
CREATE INDEX ix_returns_order ON returns (order_id);
CREATE INDEX ix_returns_status ON returns (status);
```

#### 9.10 `return_items`
**Purpose:** Itemized inventory returns and inspection condition logs.

```sql
CREATE TABLE return_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    return_id UUID NOT NULL REFERENCES returns(id) ON DELETE CASCADE,
    order_item_id UUID NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    quantity INTEGER DEFAULT 1 NOT NULL,
    condition_note VARCHAR(255) NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_return_items_return ON return_items (return_id);
```

---

### Group 7: Analytics, Sponsored Placements, and Operations

#### 10.1 `notifications`
**Purpose:** In-app, push, and email notification queue.

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type notification_type_enum DEFAULT 'system' NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    action_url VARCHAR(500) NULL,
    read_at TIMESTAMPTZ NULL,
    delivered_at TIMESTAMPTZ NULL,
    channel notification_channel_enum DEFAULT 'in_app' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_notifications_user_unread ON notifications (user_id, read_at) WHERE read_at IS NULL;
CREATE INDEX ix_notifications_user_created ON notifications (user_id, created_at DESC);
```

#### 10.2 `analytics_events`
**Purpose:** High-throughput raw event log for conversion attribution and style signals.

```sql
CREATE TABLE analytics_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    session_id VARCHAR(100) NULL,
    event_name VARCHAR(100) NOT NULL,      -- 'vton_rendered', 'outfit_saved', 'cart_added'
    event_category VARCHAR(100) NOT NULL,  -- 'styling', 'tryon', 'commerce'
    page_name VARCHAR(100) NULL,
    entity_type VARCHAR(50) NULL,
    entity_id VARCHAR(100) NULL,
    properties JSONB DEFAULT '{}'::jsonb NOT NULL,
    occurred_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_analytics_events_name_time ON analytics_events (event_name, occurred_at DESC);
CREATE INDEX ix_analytics_events_user_time ON analytics_events (user_id, occurred_at DESC);
CREATE INDEX gin_analytics_events_properties ON analytics_events USING gin (properties);
```

#### 10.3 `sponsored_placements`
**Purpose:** B2B merchant self-serve CPC ad campaigns and impression tracking.

```sql
CREATE TABLE sponsored_placements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    variant_id UUID NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    campaign_name VARCHAR(255) NOT NULL,
    placement_surface placement_surface_enum DEFAULT 'stylist_results' NOT NULL,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    bid_strategy bid_strategy_enum DEFAULT 'cpc' NOT NULL,
    bid_value_minor BIGINT NOT NULL,       -- e.g., $0.75 = 75 minor units
    currency_code VARCHAR(3) DEFAULT 'USD' NOT NULL,
    daily_budget_minor BIGINT NOT NULL,
    spent_today_minor BIGINT DEFAULT 0 NOT NULL,
    impressions_count INTEGER DEFAULT 0 NOT NULL,
    clicks_count INTEGER DEFAULT 0 NOT NULL,
    conversions_count INTEGER DEFAULT 0 NOT NULL,
    status placement_status_enum DEFAULT 'active' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_sponsored_placements_brand_status ON sponsored_placements (brand_id, status);
CREATE INDEX ix_sponsored_placements_active ON sponsored_placements (placement_surface, start_at, end_at) WHERE status = 'active';
```

#### 10.4 `provider_request_logs`
**Purpose:** External API audit ledger with latency tracing and error codes.

```sql
CREATE TABLE provider_request_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_type provider_type_enum NOT NULL,
    provider_name VARCHAR(100) NOT NULL,
    operation_name VARCHAR(100) NOT NULL,
    request_id VARCHAR(100) NULL,
    related_entity_type VARCHAR(50) NULL,
    related_entity_id UUID NULL,
    status provider_req_status_enum DEFAULT 'success' NOT NULL,
    latency_ms INTEGER NOT NULL,
    error_code VARCHAR(50) NULL,
    sanitized_payload JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_provider_logs_lookup ON provider_request_logs (provider_type, provider_name, created_at DESC);
CREATE INDEX ix_provider_logs_entity ON provider_request_logs (related_entity_type, related_entity_id);
```

#### 10.5 `audit_logs`
**Purpose:** Append-only security audit trail for administrative and privileged mutations.

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    actor_role VARCHAR(50) NULL,
    action VARCHAR(100) NOT NULL,          -- 'MFA_ENABLED', 'STOCK_OVERRIDDEN', 'GDPR_EXPORT'
    entity_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(100) NULL,
    change_summary JSONB DEFAULT '{}'::jsonb NOT NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(500) NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id);
CREATE INDEX ix_audit_logs_actor ON audit_logs (actor_user_id, created_at DESC);
CREATE INDEX ix_audit_logs_action ON audit_logs (action, created_at DESC);
```

---

### Group 8: Derived & Aggregated Analytics Tables

#### 11.1 `brand_daily_metrics`
**Purpose:** Nightly precomputed aggregates for B2B Brand Dashboards (sub-5ms retrieval).

```sql
CREATE TABLE brand_daily_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL,
    product_views INTEGER DEFAULT 0 NOT NULL,
    tryon_sessions INTEGER DEFAULT 0 NOT NULL,
    add_to_cart_count INTEGER DEFAULT 0 NOT NULL,
    purchase_count INTEGER DEFAULT 0 NOT NULL,
    gross_revenue_minor BIGINT DEFAULT 0 NOT NULL,
    return_count INTEGER DEFAULT 0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_brand_daily_metrics_brand_date ON brand_daily_metrics (brand_id, metric_date);
```

#### 11.2 `feature_attribution_metrics`
**Purpose:** Business ROI attribution across AI Stylist, Outfit Builder, and Visual Search.

```sql
CREATE TABLE feature_attribution_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_date DATE NOT NULL,
    feature_name VARCHAR(100) NOT NULL,   -- 'ai_virtual_stylist', 'outfit_builder', 'visual_search'
    session_count INTEGER DEFAULT 0 NOT NULL,
    influenced_orders INTEGER DEFAULT 0 NOT NULL,
    influenced_revenue_minor BIGINT DEFAULT 0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX uq_feature_attribution_date_feat ON feature_attribution_metrics (metric_date, feature_name);
```

---

## 5. Indexing & Query Optimization Strategy

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   INDEXING MATRIX OVERVIEW                                       │
├───────────────────────┬───────────────────────────────┬──────────────────────────────────────────┤
│ INDEX TYPE            │ TARGET COLUMNS                │ OPTIMIZED APPLICATION PATTERN            │
├───────────────────────┼───────────────────────────────┼──────────────────────────────────────────┤
│ B-Tree Unique Partial │ `LOWER(email)` WHERE del IS N │ Active user email lookup and deduplication│
│ B-Tree Foreign Key    │ `brand_id`, `user_id`         │ High-frequency join paths in queries     │
│ B-Tree Filter Cluster │ `(brand_id, visibility)`      │ Catalog storefront pagination & filtering│
│ B-Tree Composite      │ `(store_id, quantity_avail)`  │ BOPIS immediate boutique stock checks    │
│ GIN (Generalized Inv) │ `style_tags`, `occasion_tags` │ Multi-tag JSONB array overlaps           │
│ B-Tree Temporal       │ `expires_at` WHERE exp IS N   │ Hourly GDPR privacy purge daemon         │
└───────────────────────┴───────────────────────────────┴──────────────────────────────────────────┘
```

---

## 6. SQLAlchemy 2.0 Declarative Model Blueprint

```python
import enum
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class UserRoleEnum(str, enum.Enum):
    CONSUMER = "consumer"
    BRAND_USER = "brand_user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    password_hash = Column(String(255), nullable=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
    role = Column(Enum(UserRoleEnum, name="user_role_enum"), default=UserRoleEnum.CONSUMER, nullable=False)
    preferred_language = Column(String(10), default="en", nullable=False)
    market_code = Column(String(10), default="UAE", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    style_profile = relationship("UserStyleProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    body_profile = relationship("UserBodyProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    wardrobe_items = relationship("WardrobeItem", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user")

    __table_args__ = (
        Index("uq_users_email_active", "email", unique=True, postgresql_where=(deleted_at == None)),
        Index("ix_users_role_status", "role"),
    )
```

---

## 7. Migration & Alembic Evolution Protocol

1. **Strict Version Control:** Every database change is scripted into an explicit Alembic migration version. Direct DDL mutations on production databases are prohibited.
2. **Zero-Downtime Deployment Safe:** Migrations introducing new non-nullable columns must supply default values or be applied in multi-stage deployments (1: Add nullable column -> 2: Backfill data -> 3: Set `NOT NULL`).
3. **Rollback Verification:** Every `upgrade()` migration must be paired with an idempotent, fully reversible `downgrade()` handler.

---

## 8. Data Retention & GDPR Article 17 Automation

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 AUTOMATED PRIVACY PURGE LIFECYCLE                                │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   ┌───────────────────────────┐         ┌───────────────────────────┐                            │
│   │ TryOn / VisualSearch Upload │ ──────► │ expires_at = NOW() + 24h  │ (Unconsented Temporary)  │
│   └───────────────────────────┘         └─────────────┬─────────────┘                            │
│                                                       │                                          │
│                                                       ▼ (Hourly Celery Beat Daemon)              │
│                                         ┌───────────────────────────┐                            │
│                                         │ purge_expired_sessions()  │                            │
│                                         └─────────────┬─────────────┘                            │
│                                                       │                                          │
│                                                       ▼                                          │
│                                         ┌───────────────────────────┐                            │
│                                         │ Delete S3 Objects & Wipe  │ (GDPR Art. 17 Compliant)   │
│                                         └───────────────────────────┘                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Hourly Maintenance Daemon:** Evaluates `media_assets` and `tryon_sessions` where `expires_at < NOW()` and `consent_retained = FALSE`.
- **Fernet Biometric Encryption:** Raw chest, waist, height, and hip measurements remain inaccessible to raw SQL queries without the server-side Fernet key.
- **Audit Immutability:** `audit_logs` and `provider_request_logs` tables operate with application-level append-only rules.
