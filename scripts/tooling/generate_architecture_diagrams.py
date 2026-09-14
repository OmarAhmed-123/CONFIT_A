#!/usr/bin/env python3
"""
Architecture Diagram Generator — Mermaid/Kroki Integration for CONFIT

Generates version-controlled architecture diagrams for:
- System architecture
- Auth/RBAC boundaries
- Tenant isolation
- VTON flow
- AI provider routing
- Group 6/B2B architecture
- Commerce flow

Output: Mermaid diagrams (.mmd) for docs/architecture/

Usage:
    python3 scripts/tooling/generate_architecture_diagrams.py
    python3 scripts/tooling/generate_architecture_diagrams.py --diagram system-architecture
    python3 scripts/tooling/generate_architecture_diagrams.py --validate
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCH_DIR = REPO_ROOT / "docs" / "architecture"

# Diagram definitions
DIAGRAMS = {
    "system-architecture": {
        "title": "CONFIT System Architecture",
        "content": '''erDiagram
    %% CONFIT System Architecture - High Level
    FRONTEND ||--o{ API_GATEWAY : "HTTPS /api/*"
    API_GATEWAY ||--o{ BACKEND : "FastAPI routes"
    BACKEND ||--|| POSTGRES : "SQLAlchemy ORM"
    BACKEND ||--|| REDIS : "Cache/Queue/Sessions"
    BACKEND ||--|| MEILISEARCH : "Search index"
    BACKEND ||--o{ VTON_WORKER : "Modal GPU (async)"
    BACKEND ||--o{ VLM_WORKER : "Modal GPU (async)"
    BACKEND ||--o{ AI_PROVIDERS : "Groq/Gemini/OpenAI"
    BACKEND ||--o{ PAYMENT_PROVIDERS : "Tabby/Tamara/Stripe"
    BACKEND ||--o{ OBJECT_STORAGE : "S3/R2 (wardrobe images)"
    
    FRONTEND {
        string React18_TypeScript
        string Vite_Tailwind_MVVM
        string Vercel_Static_Hosting
    }
    
    API_GATEWAY {
        string Vercel_Serverless
        string mangum_FastAPI_Adapter
        string Rewrites_/api/*
    }
    
    BACKEND {
        string FastAPI_MVC
        string Controllers_Services_Repositories
        string SQLAlchemy2_Pydantic2
        string JWT_Cookie_CSRF
        string structlog_RateLimit
    }
    
    POSTGRES {
        string Neon_Managed_Prod
        string SQLite_Local_Dev
        string Alembic_Migrations
    }
    
    REDIS {
        string Cache_Queue_Sessions
        string Celery_Broker
    }
    
    MEILISEARCH {
        string Search_Engine
        string Catalog_Index
    }
    
    VTON_WORKER {
        string Modal_Serverless
        string CatVTON_Legacy
        string fashn_vton_segfee_Prod
        string GPU_A10_A10G
    }
    
    VLM_WORKER {
        string Modal_Serverless
        string Qwen2.5-VL-7B
        string Apache-2.0_License
        string GPU_A10G
    }
    
    AI_PROVIDERS {
        string Groq_Primary
        string Gemini_Fallback
        string OpenAI_Fallback
        string Qwen_Local_Fallback
    }
    
    PAYMENT_PROVIDERS {
        string Tabby_Tamara_BNPL
        string Stripe_Cards
        string Paymob_Egypt
        string Demo_Mode_Default
    }
    
    OBJECT_STORAGE {
        string S3_R2_Compatible
        string Wardrobe_Moodboard
        string Presigned_URLs
    }''',
    },
    "auth-rbac": {
        "title": "Authentication & RBAC Boundaries",
        "content": '''flowchart TB
    %% Auth & RBAC Flow
    
    subgraph CLIENT [Client / Browser]
        A1[User Agent] --> A2[httpOnly Secure Cookie]
        A2 --> A3[CSRF Token Header]
    end
    
    subgraph EDGE [Edge / Vercel]
        B1[Vercel Function] --> B2[Mangum Adapter]
        B2 --> B3[FastAPI App]
    end
    
    subgraph AUTH [Auth Layer]
        B3 --> C1[Auth Middleware]
        C1 --> C2[JWT Verify / Refresh]
        C2 --> C3[Session Store / Redis]
        C3 --> C4[Rate Limiter / slowapi]
    end
    
    subgraph RBAC [RBAC Enforcement]
        C4 --> D1[Require Auth]
        C4 --> D2[Require Role]
        C4 --> D3[Require Permission]
        C4 --> D4[Require Brand Access]
        C4 --> D5[Require Tenant Isolation]
    end
    
    subgraph ROLES [Role Hierarchy]
        R1[super_admin] --> R2[admin]
        R2 --> R3[brand_admin]
        R3 --> R4[brand_staff]
        R4 --> R5[consumer]
    end
    
    subgraph TENANT [Tenant Boundaries]
        T1[Consumer Tenant] --> T2[Own Data Only]
        T3[Brand Tenant] --> T4[Own Brand Data Only]
        T5[Admin Tenant] --> T6[All Data]
    end
    
    D1 --> ROLES
    D2 --> ROLES
    D3 --> ROLES
    D4 --> TENANT
    D5 --> TENANT
    
    %% Protected Endpoints
    D1 --> E1[/api/v1/auth/*]
    D2 --> E2[/api/v1/admin/*]
    D3 --> E3[/api/v1/brand/*]
    D4 --> E4[/api/v1/catalog/*]
    D5 --> E5[/api/v1/wardrobe/*]
    
    style CLIENT fill:#e1f5fe
    style EDGE fill:#fff3e0
    style AUTH fill:#fce4ec
    style RBAC fill:#f3e5f5
    style ROLES fill:#e8eaf6
    style TENANT fill:#e0f2f1''',
    },
    "tenant-boundaries": {
        "title": "Multi-Tenant Isolation",
        "content": '''flowchart LR
    %% Tenant Isolation Architecture
    
    subgraph REQUEST [Incoming Request]
        R1[Request + JWT Cookie] --> R2[Auth Middleware]
    end
    
    subgraph EXTRACT [Context Extraction]
        R2 --> E1[Extract User ID]
        R2 --> E2[Extract Role]
        R2 --> E3[Extract Brand IDs]
        R2 --> E4[Extract Tenant ID]
    end
    
    subgraph ENFORCE [Enforcement Layer]
        E1 --> F1[Repository Layer]
        E2 --> F1
        E3 --> F1
        E4 --> F1
    end
    
    subgraph REPOS [Repository Filters]
        F1 --> G1[UserRepository: filter by user_id]
        F1 --> G2[BrandRepository: filter by brand_id]
        F1 --> G3[CatalogRepository: filter by brand_id]
        F1 --> G4[WardrobeRepository: filter by user_id]
        F1 --> G5[OrderRepository: filter by user_id/brand_id]
        F1 --> G6[AnalyticsRepository: filter by brand_id]
    end
    
    subgraph CROSS [Cross-Tenant Prevention]
        G1 -.-> H1[NEVER: user_id != request.user_id]
        G2 -.-> H2[NEVER: brand_id not in request.brand_ids]
        G3 -.-> H3[NEVER: catalog brand_id not in request.brand_ids]
        G4 -.-> H4[NEVER: wardrobe user_id != request.user_id]
        G5 -.-> H5[NEVER: order across tenant boundary]
        G6 -.-> H6[NEVER: analytics across brand boundary]
    end
    
    subgraph ADMIN [Admin Override]
        A1[Role: super_admin/admin] --> A2[Bypass tenant filters]
        A2 --> A3[Explicit audit logging]
        A3 --> A4[Require justification]
    end
    
    style REQUEST fill:#e3f2fd
    style EXTRACT fill:#e8eaf6
    style ENFORCE fill:#fff3e0
    style REPOS fill:#f3e5f5
    style CROSS fill:#ffebee
    style ADMIN fill:#e0f2f1''',
    },
    "vton-flow": {
        "title": "Virtual Try-On Request Flow",
        "content": '''sequenceDiagram
    %% VTON Request Flow
    actor User
    participant FE as Frontend (React)
    participant API as Backend API
    participant Queue as Redis Queue
    participant Worker as VTON Worker (Modal)
    participant Storage as Object Storage
    
    User->>FE: Upload person + garment images
    FE->>API: POST /api/v1/tryon/jobs (multipart)
    API->>API: Validate images (size, format, dimensions)
    API->>API: Check rate limit (per-IP, per-user)
    API->>API: Create job record (status=pending)
    API->>Storage: Upload images (presigned URLs)
    API->>Queue: Enqueue vton_heavy job
    API-->>FE: 202 Accepted + job_id
    
    FE->>API: GET /api/v1/tryon/jobs/{job_id} (poll)
    
    Worker->>Queue: Reserve job (Celery)
    Worker->>Storage: Download images
    Worker->>Worker: Validate inputs (SSRF, size, decompression)
    Worker->>Worker: Generate slot-aware mask (upper_outer, lower, dress, etc.)
    Worker->>Worker: Run diffusion (fashn-vton-segfee)
    Worker->>Worker: Validate output (no echo, pixel change)
    Worker->>Storage: Upload result
    Worker->>API: Callback /webhook/vton/complete
    API->>API: Update job status=completed
    API->>API: Store result URL + metadata
    
    FE->>API: GET /api/v1/tryon/jobs/{job_id}
    API-->>FE: 200 OK + result_url
    FE-->>User: Display try-on result
    
    alt Worker Failure
        Worker->>API: Callback /webhook/vton/failed
        API->>API: Update job status=failed + error
        FE->>API: Poll -> 503 VTON_ENGINE_UNAVAILABLE
    end
    
    Note over Worker: Honest failure modes:\n- 503 if worker not deployed\n- No static/echo substitution\n- Output validation rejects echo''',
    },
    "ai-provider-routing": {
        "title": "AI Provider Failover Routing",
        "content": '''flowchart TD
    %% AI Stylist Provider Routing
    
    REQUEST[Stylist Request] --> ORCHESTRATOR[AI Orchestrator]
    
    ORCHESTRATOR --> PROVIDERS[Provider Chain]
    
    subgraph PROVIDER_CHAIN [Failover Chain]
        P1[Groq Primary] -->|timeout/error| P2[Gemini Fallback]
        P2 -->|timeout/error| P3[OpenAI Fallback]
        P3 -->|timeout/error| P4[Qwen Local Fallback]
        P4 -->|unavailable| P5[Deterministic Grounded Fallback]
    end
    
    subgraph PROVIDER_DETAILS [Provider Details]
        P1 -.-> D1[Groq: llama-3.3-70b-versatile\nFast, free tier\nStructured output]
        P2 -.-> D2[Gemini: gemini-1.5-flash\nVision capable\nRate limited]
        P3 -.-> D3[OpenAI: gpt-4o-mini\nReliable\nPaid]
        P4 -.-> D4[Qwen: Qwen2.5-VL-7B\nLocal Modal GPU\nApache-2.0]
        P5 -.-> D5[StylingEngine: Rule-based\nGrounded in real catalog\nAlways available]
    end
    
    subgraph QUARANTINE [Quarantine Memory]
        Q1[Track consecutive failures] --> Q2[3 failures = quarantine 5min]
        Q2 --> Q3[Health check before retry]
        Q3 --> Q4[Circuit breaker pattern]
    end
    
    PROVIDERS --> QUARANTINE
    
    subgraph GROUNDING [Catalog Grounding]
        G1[Fetch real products] --> G2[Inject into prompt]
        G2 --> G3[Enforce product IDs only]
        G3 --> G4[Validate response against catalog]
        G4 --> G5[Reject hallucinated products]
    end
    
    P1 --> GROUNDING
    P2 --> GROUNDING
    P3 --> GROUNDING
    P4 --> GROUNDING
    P5 --> GROUNDING
    
    ORCHESTRATOR --> RESPONSE[Structured Response]
    RESPONSE --> R1[outfit_items: ProductRef[]]
    RESPONSE --> R2[reasoning: string]
    RESPONSE --> R3[confidence: float]
    RESPONSE --> R4[provider_used: string]
    
    style PROVIDER_CHAIN fill:#e8f5e9
    style QUARANTINE fill:#fff3e0
    style GROUNDING fill:#e3f2fd
    style PROVIDER_DETAILS fill:#f3e5f5''',
    },
    "group6-architecture": {
        "title": "Group 6 / B2B Brand Admin Architecture",
        "content": '''erDiagram
    %% Group 6 / B2B Architecture
    
    BRAND ||--o{ BRAND_STAFF : "has"
    BRAND ||--o{ CATALOG : "owns"
    BRAND ||--o{ ANALYTICS_EVENTS : "generates"
    BRAND ||--o{ PLACEMENTS : "manages"
    BRAND ||--o{ INVENTORY : "tracks"
    
    BRAND_STAFF {
        uuid id PK
        uuid brand_id FK
        uuid user_id FK
        enum role "admin/staff"
        datetime created_at
    }
    
    CATALOG {
        uuid id PK
        uuid brand_id FK
        string sku UK
        string name
        string category
        decimal price
        int stock_quantity
        jsonb attributes
        boolean is_active
        datetime created_at
    }
    
    ANALYTICS_EVENTS {
        uuid id PK
        uuid brand_id FK
        uuid product_id FK
        uuid order_item_id FK
        enum event_type "view/add_to_cart/purchase/refund"
        decimal revenue_amount
        datetime occurred_at
    }
    
    PLACEMENTS {
        uuid id PK
        uuid brand_id FK
        string placement_key UK
        string name
        jsonb config
        boolean is_active
        int priority
    }
    
    INVENTORY {
        uuid id PK
        uuid product_id FK
        uuid warehouse_id FK
        int quantity_available
        int quantity_reserved
        datetime updated_at
    }
    
    BRAND {
        uuid id PK
        string name
        string slug UK
        string owner_user_id FK
        jsonb settings
        boolean is_active
        datetime created_at
    }
    
    CATALOG_IMPORT {
        uuid id PK
        uuid brand_id FK
        uuid uploaded_by FK
        string filename
        int total_rows
        int processed_rows
        int failed_rows
        enum status "pending/processing/completed/failed"
        jsonb errors
        datetime created_at
    }
    
    BRAND ||--o{ CATALOG_IMPORT : "uploads"''',
    },
    "commerce-flow": {
        "title": "Commerce / Order Flow",
        "content": '''sequenceDiagram
    %% Commerce Flow: Cart -> Checkout -> Order -> Fulfillment
    actor User
    participant FE as Frontend
    participant API as Backend API
    participant Pay as Payment Orchestrator
    participant PSP as Payment Provider
    participant Queue as Redis Queue
    participant Worker as Celery Worker
    
    User->>FE: Browse catalog, add to cart
    FE->>API: POST /api/v1/cart/items
    API->>API: Validate stock, price, variant
    API-->>FE: Cart updated
    
    User->>FE: Proceed to checkout
    FE->>API: POST /api/v1/checkout/sessions
    API->>API: Calculate totals (tax, shipping, discount)
    API->>API: Create checkout_session (pending)
    API-->>FE: session_id + payment_methods
    
    User->>FE: Select payment (Tabby/Stripe/etc.)
    FE->>API: POST /api/v1/checkout/sessions/{id}/confirm
    API->>Pay: Create payment intent
    Pay->>PSP: Create charge (Tabby/Stripe/Paymob)
    PSP-->>Pay: Redirect URL / 3DS challenge
    Pay-->>API: payment_intent + redirect_url
    API-->>FE: redirect_url
    
    User->>PSP: Complete payment (redirect/3DS)
    PSP->>API: Webhook /webhook/payment/{provider}
    API->>API: Verify signature (fail if secret missing)
    API->>API: Idempotency check (dedupe)
    API->>API: Update checkout_session = paid
    API->>API: Create Order + OrderItems
    API->>API: Decrement inventory (atomic)
    API->>API: Create attribution events (brand revenue)
    API->>Queue: Enqueue fulfillment job
    API->>Queue: Enqueue notification job
    API-->>PSP: 200 OK
    
    Worker->>Queue: Process fulfillment
    Worker->>Worker: Generate packing slip
    Worker->>Worker: Notify warehouse (BOPIS/ship)
    Worker->>API: Update order status = confirmed
    
    alt Payment Failed
        PSP->>API: Webhook failed
        API->>API: Update checkout_session = failed
        API->>API: Release inventory holds
        FE->>User: Show error, retry option
    end
    
    alt Refund/Return
        User->>FE: Request return
        FE->>API: POST /api/v1/orders/{id}/returns
        API->>API: Validate return window (30 days)
        API->>API: Create return record
        API->>Pay: Initiate refund
        Pay->>PSP: Refund charge
        PSP-->>Pay: Refund confirmed
        API->>API: Update order + attribution (negative revenue)
        API->>API: Restock inventory
    end''',
    },
}


def validate_mermaid() -> bool:
    """Validate all Mermaid diagrams syntax using mermaid-cli if available."""
    try:
        # Check if mermaid-cli (mmdc) is available
        result = subprocess.run(["npx", "mmdc", "--version"], capture_output=True, timeout=10)
        if result.returncode != 0:
            result = subprocess.run(["mmdc", "--version"], capture_output=True, timeout=10)
        has_mmdc = result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        has_mmdc = False
    
    if not has_mmdc:
        print("mermaid-cli (mmdc) not found. Install with: npm install -g @mermaid-js/mermaid-cli")
        print("Skipping syntax validation...")
        return True
    
    all_valid = True
    for name, diagram in DIAGRAMS.items():
        filepath = ARCH_DIR / f"{name}.mmd"
        if not filepath.exists():
            print(f"  {name}: FILE NOT FOUND")
            continue
        
        # Validate with mmdc
        result = subprocess.run(
            ["npx", "mmdc", "-i", str(filepath), "-o", "/dev/null"],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            print(f"  ✅ {name}: Valid")
        else:
            print(f"  ❌ {name}: INVALID")
            print(f"     {result.stderr[:200]}")
            all_valid = False
    
    return all_valid


def generate_diagrams() -> None:
    """Generate all architecture diagrams."""
    ARCH_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Generating architecture diagrams...")
    
    for name, diagram in DIAGRAMS.items():
        filepath = ARCH_DIR / f"{name}.mmd"
        
        content = f"""%%
%% {diagram['title']}
%% Auto-generated by generate_architecture_diagrams.py
%% DO NOT EDIT DIRECTLY - edit the script instead
%%

{diagram['content']}
"""
        
        filepath.write_text(content, encoding="utf-8")
        print(f"  Generated: {filepath.relative_to(REPO_ROOT)}")
    
    print(f"\nAll diagrams generated in {ARCH_DIR.relative_to(REPO_ROOT)}")
    print("View with: https://mermaid.live or VS Code Mermaid extension")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate CONFIT architecture diagrams (Mermaid)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/tooling/generate_architecture_diagrams.py
  python3 scripts/tooling/generate_architecture_diagrams.py --diagram system-architecture
  python3 scripts/tooling/generate_architecture_diagrams.py --validate
        """
    )
    parser.add_argument("--diagram", choices=list(DIAGRAMS.keys()), help="Generate specific diagram only")
    parser.add_argument("--validate", action="store_true", help="Validate existing diagrams syntax")
    parser.add_argument("--list", action="store_true", help="List available diagrams")
    
    args = parser.parse_args()
    
    if args.list:
        print("Available diagrams:")
        for name, diagram in DIAGRAMS.items():
            print(f"  {name}: {diagram['title']}")
        return 0
    
    if args.validate:
        print("Validating Mermaid diagrams...")
        return 0 if validate_mermaid() else 1
    
    if args.diagram:
        if args.diagram not in DIAGRAMS:
            print(f"Unknown diagram: {args.diagram}", file=sys.stderr)
            return 1
        
        ARCH_DIR.mkdir(parents=True, exist_ok=True)
        diagram = DIAGRAMS[args.diagram]
        filepath = ARCH_DIR / f"{args.diagram}.mmd"
        
        content = f"""%%
%% {diagram['title']}
%% Auto-generated by generate_architecture_diagrams.py
%% DO NOT EDIT DIRECTLY - edit the script instead
%%

{diagram['content']}
"""
        filepath.write_text(content, encoding="utf-8")
        print(f"Generated: {filepath.relative_to(REPO_ROOT)}")
        return 0
    
    # Generate all
    generate_diagrams()
    return 0


if __name__ == "__main__":
    sys.exit(main())