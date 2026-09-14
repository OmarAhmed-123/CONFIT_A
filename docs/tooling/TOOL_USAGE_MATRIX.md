# CONFIT_A Tool Usage Matrix

Detailed per-tool usage guide for the CONFIT_A engineering toolchain.

---

## Bundlephobia — Frontend Dependency Cost Analysis

**Purpose**: Evaluate package size, dependency tree impact, maintenance/security implications before adding frontend dependencies.

**CONFIT Subsystem**: Frontend (`frontend/`)

**Integration Level**: 2 (local script)

**Trigger**: Before adding any significant frontend dependency

**Input**: Package name(s) to evaluate

**Output**: Bundle size analysis, dependency tree, maintenance status

**Security Constraints**: None (public npm data only)

**Execution**:
```bash
# Using the analysis script
python3 scripts/tooling/analyze_bundlephobia.py <package-name>

# Or manually via browser
# https://bundlephobia.com/package/<package-name>
```

**Verification Method**: Compare reported size with actual `npm install` + `npm ls` output

**Status**: IMPLEMENTED

**Known Limitation**: Does not evaluate tree-shaking effectiveness in Vite build

---

## drawDB — Database ERD Visualization

**Purpose**: Generate Entity Relationship Diagrams from SQLAlchemy models for schema understanding, ERD review, tenant boundary review.

**CONFIT Subsystem**: Database (`backend/app/models/`)

**Integration Level**: 2 (local script generating drawDB-compatible JSON)

**Trigger**: Schema change, documentation update, tenant boundary review

**Input**: SQLAlchemy model definitions

**Output**: drawDB-compatible JSON schema, Mermaid ERD

**Security Constraints**: Never expose production schema with real data; use model definitions only

**Execution**:
```bash
# Generate ERD from SQLAlchemy models
python3 scripts/tooling/generate_erd.py --output docs/architecture/erd.drawio.json
python3 scripts/tooling/generate_erd.py --format mermaid --output docs/architecture/erd.mmd
```

**Verification Method**: Reconcile generated diagram against actual schema (Alembic migrations + `validate_database.py`)

**Status**: IMPLEMENTED

**Known Limitation**: Diagram must be derived from verified schema state; manual diagrams are not authoritative

---

## Mermaid/Kroki — Architecture Diagrams

**Purpose**: Version-controlled architecture and engineering visualization.

**CONFIT Subsystem**: Documentation (`docs/architecture/`)

**Integration Level**: 3 (CI + docs)

**Trigger**: Architecture change, new subsystem, documentation update

**Input**: Mermaid diagram source (`.mmd` files)

**Output**: Rendered diagrams in documentation, Kroki-compatible URLs

**Security Constraints**: No secrets in diagrams; architecture only

**Execution**:
```bash
# Generate all architecture diagrams
python3 scripts/tooling/generate_architecture_diagrams.py

# CI validates diagrams render correctly
# kroki.io renders Mermaid via GET/POST
```

**Diagrams Maintained**:
- `docs/architecture/system-architecture.mmd` — System overview
- `docs/architecture/auth-rbac.mmd` — Auth/RBAC boundaries
- `docs/architecture/tenant-boundaries.mmd` — Tenant isolation
- `docs/architecture/vton-flow.mmd` — VTON request flow
- `docs/architecture/ai-provider-routing.mmd` — AI provider failover
- `docs/architecture/group6-architecture.mmd` — Group 6/B2B architecture
- `docs/architecture/commerce-flow.mmd` — Commerce/order flow

**Verification Method**: CI validates Mermaid syntax; diagrams reviewed in PR

**Status**: IMPLEMENTED

**Known Limitation**: One authoritative diagram per concept; no conflicting diagrams

---

## Hoppscotch — API Validation & Manual Testing

**Purpose**: Interactive API testing for authentication, authorization, CSRF, RBAC, tenant isolation, API contracts.

**CONFIT Subsystem**: Backend API (`/api/v1/*`)

**Integration Level**: 1 (documented manual usage)

**Trigger**: Auth testing, authorization testing, VTON endpoints, Group 6 endpoints, commerce endpoints, health endpoints

**Required Test Cases (Negative)**:
- Unauthenticated → protected endpoint
- Consumer → admin endpoint
- Brand A → Brand B resource
- Malformed payload
- Invalid identifier
- Invalid upload
- Unsupported content type
- Oversized payload
- Expired/invalid session
- Unauthorized mutation

**Security Constraints**: 
- Never use production credentials
- Use local dev environment or staging
- Do not save collections with real tokens

**Execution**: 
- Local: `http://localhost:8000/docs` (FastAPI Swagger) or import OpenAPI spec into Hoppscotch
- Staging: Use staging environment URL

**Verification Method**: Automated test suite is authoritative; Hoppscotch supplements only

**Status**: DOCUMENTED

**Known Limitation**: Does not replace automated tests; manual only

---

## JSON Crack — Complex Response Visualization

**Purpose**: Visual inspection of difficult nested JSON structures.

**CONFIT Subsystem**: API responses (catalog, inventory, analytics, orders, AI responses, VTON jobs)

**Integration Level**: 1 (documented manual usage)

**Trigger**: Debugging complex nested API responses

**Security Constraints**: 
- Never paste production responses with secrets
- Anonymize user data before visualization
- Prefer local execution for sensitive data

**Execution**: 
- Copy sanitized JSON response
- Paste into https://jsoncrack.com (or use local Electron app)

**Status**: DOCUMENTED

**Known Limitation**: Browser-based; not for sensitive data

---

## CSV Repair — Catalog/CSV Preparation & Diagnosis

**Purpose**: Diagnose malformed CSV, inconsistent columns, broken delimiters, encoding issues in Group 6 catalog imports.

**CONFIT Subsystem**: Group 6 / B2B Catalog Import (`backend/app/services/brand_catalog_service.py`)

**Integration Level**: 2 (local script)

**Trigger**: Catalog import workflow, CSV validation failures

**Input**: CSV file to diagnose

**Output**: Diagnostics report, repaired CSV (if safe)

**Security Constraints**: 
- Do not process production catalog data with PII externally
- Use local script for sensitive data
- Server-side validation remains authoritative

**Execution**:
```bash
# Diagnose CSV issues
python3 scripts/tooling/validate_csv.py --diagnose path/to/catalog.csv

# Attempt safe repair (dry-run first)
python3 scripts/tooling/validate_csv.py --repair path/to/catalog.csv --output path/to/fixed.csv
```

**Verification Method**: Automated import tests (`test_group6_brand_admin.py`) are authoritative

**Status**: IMPLEMENTED

**Known Limitation**: Does not replace server-side validation (schema, SKU uniqueness, ownership, tenant isolation, transactional correctness)

---

## SQLChef — Structured Data Inspection

**Purpose**: SQL-style analysis of exported/anonymized datasets (catalog, inventory, analytics, orders).

**CONFIT Subsystem**: Data exports, analytics

**Integration Level**: 1 (documented manual usage)

**Trigger**: Data quality investigation, duplicate detection, distribution analysis

**Security Constraints**: 
- Never expose secrets or unnecessary personal data
- Use anonymized exports only
- Prefer local execution

**Execution**: Use SQLChef locally with exported CSV/JSON data

**Status**: DOCUMENTED

**Known Limitation**: Not a replacement for database queries; works on exported data only

---

## Log Voyager — Log Inspection & Incident Investigation

**Purpose**: Investigate API failures, auth failures, VTON failures, worker failures, provider errors, latency issues.

**CONFIT Subsystem**: All backend services (production logs)

**Integration Level**: 1 (documented manual usage)

**Trigger**: Production incident, recurring errors, suspicious patterns

**Security Constraints**: 
- Prefer request/correlation IDs
- Never expose credentials or sensitive production data unnecessarily
- Use structured log queries, not raw log paste

**Execution**: 
- Query structured logs via logging backend (Vercel, Modal, etc.)
- Filter by correlation ID, service, time range
- Use local analysis for sensitive logs

**Status**: DOCUMENTED

**Known Limitation**: External tool; use internal logging infrastructure first

---

## CyberChef — Safe Local Data Transformation Analysis

**Purpose**: Encoding/decoding analysis, hashes, parsing, reproducible test payload construction.

**CONFIT Subsystem**: Test payload generation, data transformation debugging

**Integration Level**: 1 (documented manual usage) — **LOCAL ONLY**

**Trigger**: Need to analyze/decode/encode test data

**Security Constraints**: 
- **NEVER** paste production API keys, database passwords, JWT secrets, payment credentials, session cookies, live user secrets
- Use ONLY local/offline version (CyberChef can run locally via `npx cyberchef` or Docker)
- If task requires sensitive analysis, use local equivalent

**Execution**: 
```bash
# Local CyberChef (no network)
npx cyberchef
# or
docker run -p 8000:8000 mikefarah/cyberchef
```

**Status**: DOCUMENTED (local only)

**Known Limitation**: Browser version sends data to client; use local only for CONFIT

---

## RegExr — Regex Development & Test-Case Generation

**Purpose**: Develop and test regex patterns for SKU, slug, identifier, filename validation.

**CONFIT Subsystem**: Validation patterns (`backend/app/core/security.py`, schemas)

**Integration Level**: 1 (documented manual usage)

**Trigger**: New validation pattern needed

**Requirements**: Every new regex must have:
- Valid examples
- Invalid examples  
- Boundary cases
- Regression tests where production-relevant

**Security Constraints**: Never treat browser regex tester as production validation layer

**Status**: DOCUMENTED

**Known Limitation**: Production validation remains in backend code with tests

---

## privacy.sexy — Developer Workstation Hardening

**Purpose**: Optional developer-environment privacy/security hardening.

**CONFIT Subsystem**: Developer workstation (not CONFIT production)

**Integration Level**: 0 (document/recommend only)

**Trigger**: Developer onboarding, workstation setup

**Security Constraints**: 
- Do not claim it secures CONFIT production environment
- Do not modify development machine destructively without explicit evidence
- Strictly optional

**Status**: DOCUMENTED (recommendation only)

**Known Limitation**: Not a CONFIT production security control

---

## WebLLM — Client-Side AI Experimentation

**Purpose**: Local AI experimentation (prompt experiments, model behavior comparison, structured-output experiments).

**CONFIT Subsystem**: AI experimentation (not production)

**Integration Level**: 0 (document/recommend only)

**Trigger**: Prompt engineering, local model comparison

**Security Constraints**: 
- Never silently use as production AI replacement
- Never represent local experiment as production AI functionality
- No production data in prompts

**Status**: DOCUMENTED (experimentation only)

**Known Limitation**: Not a production AI backend

---

## Forge — AI Experimentation & Model Comparison

**Purpose**: Prompt experiments, model behavior comparison, prototyping, evaluating candidate model behaviors.

**CONFIT Subsystem**: AI experimentation (not production)

**Integration Level**: 0 (document/recommend only)

**Trigger**: Model evaluation, prompt engineering

**Security Constraints**: 
- Never claim Forge usage constitutes production model integration
- Production model selection must be independently validated against CONFIT requirements

**Status**: DOCUMENTED (experimentation only)

**Known Limitation**: Not a production model integration

---

## Component Gallery — UI/Component Pattern Reference

**Purpose**: Design reference for B2B dashboards, admin interfaces, tables, forms, dialogs, navigation.

**CONFIT Subsystem**: Frontend UI (`frontend/src/components/`)

**Integration Level**: 1 (documented manual usage)

**Trigger**: New B2B/admin component design

**Constraints**: 
- Maintain CONFIT's existing design language (Tailwind + custom components)
- Do not import arbitrary components merely because they look attractive
- Do not introduce unnecessary frontend dependencies

**Reference**: https://component.gallery

**Status**: DOCUMENTED

**Known Limitation**: Reference only; CONFIT has its own component library in `frontend/src/components/ui/`

---

## Tiny Image — Image Optimization/Preparation

**Purpose**: Safe preprocessing of catalog images, thumbnails, marketing imagery, static assets.

**CONFIT Subsystem**: Frontend assets, catalog images

**Integration Level**: 2 (local script)

**Trigger**: New catalog images, asset optimization

**Input**: Image files

**Output**: Optimized images with size/quality metrics

**Security Constraints**: 
- Do not process sensitive user imagery through external service
- Evaluate dimensions, file size, quality, format before/after
- Use local script for production catalog images

**Execution**:
```bash
# Optimize images locally
python3 scripts/tooling/optimize_images.py --input frontend/public/images --output frontend/public/images/optimized
```

**Verification Method**: Compare file sizes, dimensions, visual quality before/after

**Status**: IMPLEMENTED

**Known Limitation**: External service not used for production catalog images

---

## SVG-Edit — SVG Creation/Editing

**Purpose**: Legitimate UI or brand asset creation where required.

**CONFIT Subsystem**: UI assets, brand assets

**Integration Level**: 1 (documented manual usage)

**Trigger**: New SVG asset needed

**Verification**: 
- Dimensions
- Accessibility implications
- Unwanted metadata
- Visual correctness
- File size
- Repository licensing

**Status**: DOCUMENTED

**Known Limitation**: Manual tool; not automated

---

## SVGOMG — SVG Optimization

**Purpose**: Optimize repository SVG assets.

**CONFIT Subsystem**: Repository SVG assets

**Integration Level**: 2 (local script)

**Trigger**: New SVG assets, asset optimization pass

**Input**: SVG files

**Output**: Optimized SVGs

**Verification**: 
- Rendering unchanged
- Accessibility preserved
- viewBox, IDs, fills/strokes intact
- No embedded behavior broken

**Execution**:
```bash
# Optimize SVGs locally
python3 scripts/tooling/optimize_svgs.py --input frontend/src/assets/icons --output frontend/src/assets/icons
```

**Status**: IMPLEMENTED

**Known Limitation**: Verify optimization doesn't break semantics

---

## Simple Icons — Brand/Technology SVG References

**Purpose**: Legally and visually appropriate brand/technology icons.

**CONFIT Subsystem**: UI icons (technology logos)

**Integration Level**: 1 (documented manual usage)

**Trigger**: Need for technology brand icon

**Constraints**: 
- Verify licensing before committing
- Do not imply partnerships/endorsements that don't exist
- Use only where legally appropriate

**Reference**: https://simpleicons.org

**Status**: DOCUMENTED

**Known Limitation**: Licensing verification required per icon

---

## CodeGraphContext — Repository Relationship Analysis

**Purpose**: Dependency analysis, impact analysis, tracing frontend→API→service→database paths, locating duplicated logic.

**CONFIT Subsystem**: All subsystems

**Integration Level**: 2 (local script)

**Trigger**: Non-trivial repository change evaluation, impact analysis

**Input**: Repository codebase

**Output**: Dependency graphs, impact reports

**Security Constraints**: Local analysis only; no code sent externally

**Execution**:
```bash
# Generate dependency graph
python3 scripts/tooling/dependency_graph.py --output docs/architecture/dependency-graph.json

# Impact analysis for a file
python3 scripts/tooling/dependency_graph.py --impact backend/app/services/tryon_service.py
```

**Verification Method**: Cross-reference with actual import statements and test results

**Status**: IMPLEMENTED

**Known Limitation**: Static analysis only; runtime dependencies may differ