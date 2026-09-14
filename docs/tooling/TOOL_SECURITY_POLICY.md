# CONFIT_A Tool Security Policy

## Core Principle

**Never send production secrets to external tools.**

This policy applies to ALL tools in the CONFIT_A engineering toolchain, whether integrated at Level 1 (manual), Level 2 (local), Level 3 (automated), or higher.

---

## Classification of Inputs

Before using ANY tool (browser-based, local, or automated), classify the input data:

| Classification | Examples | External Tool Allowed? |
|----------------|----------|------------------------|
| **SECRET** | API keys, database passwords, JWT secrets, session cookies, payment credentials, admin credentials, Modal tokens, GitHub tokens | **NEVER** |
| **SENSITIVE PII** | User emails, names, addresses, body measurements, order history, private images | **NEVER** (use anonymized/synthetic) |
| **INTERNAL** | Internal architecture, schema structure, code paths, test fixtures, synthetic data | **LOCAL ONLY** (Level 2+) |
| **PUBLIC** | Public documentation, open-source code, public npm packages, public APIs | **YES** (with review) |

---

## Tool-Specific Security Constraints

### Bundlephobia (Level 2)
- **Input**: Package names only (public npm data)
- **Allowed**: ✅ No sensitive data involved
- **Constraint**: None

### drawDB / ERD Generation (Level 2)
- **Input**: SQLAlchemy model definitions (code)
- **Allowed**: ✅ Local script processes model code only
- **Constraint**: Never connect to production database; never include real data in diagrams

### Mermaid/Kroki Diagrams (Level 3)
- **Input**: Architecture descriptions (code/docs)
- **Allowed**: ✅ No sensitive data
- **Constraint**: No secrets, credentials, or real data in diagram source

### Hoppscotch (Level 1 - Manual)
- **Input**: API requests/responses
- **Allowed**: ⚠️ **Only with local/dev/staging environments**
- **Constraints**:
  - Never use production credentials
  - Never save collections with real tokens
  - Use `http://localhost:8000` or staging only
  - Clear cookies/sessions after testing

### JSON Crack (Level 1 - Manual)
- **Input**: JSON responses
- **Allowed**: ⚠️ **Only with sanitized data**
- **Constraints**:
  - Strip all secrets before pasting
  - Anonymize user IDs, emails, PII
  - Prefer local Electron app over browser version
  - Never paste production API responses with real data

### CSV Repair (Level 2)
- **Input**: Catalog CSV files
- **Allowed**: ✅ Local script only
- **Constraints**:
  - Do not upload production catalog data to external services
  - Use local `validate_csv.py` script
  - Server-side validation remains authoritative

### SQLChef (Level 1 - Manual)
- **Input**: Exported data (CSV/JSON)
- **Allowed**: ⚠️ **Only with anonymized exports**
- **Constraints**:
  - Export must be anonymized (no PII, no secrets)
  - Prefer local execution
  - Never connect to production database directly

### Log Voyager (Level 1 - Manual)
- **Input**: Production logs
- **Allowed**: ⚠️ **Only via internal logging infrastructure**
- **Constraints**:
  - Query via structured logging backend (Vercel, Modal, etc.)
  - Filter by correlation ID, not raw log paste
  - Never export logs with secrets to external tools
  - Use local analysis for sensitive investigations

### CyberChef (Level 1 - LOCAL ONLY)
- **Input**: Data to transform
- **Allowed**: ✅ **LOCAL ONLY** (Docker/npx)
- **Constraints**:
  - **NEVER** use browser version (sends data to client)
  - **NEVER** paste: production API keys, database passwords, JWT secrets, payment credentials, session cookies, live user secrets
  - Run locally via `npx cyberchef` or `docker run mikefarah/cyberchef`

### RegExr (Level 1 - Manual)
- **Input**: Test strings, regex patterns
- **Allowed**: ⚠️ **Only with synthetic test data**
- **Constraints**:
  - Never use real identifiers, SKUs, or user data as test cases
  - Generate synthetic test cases
  - Production validation remains in backend code

### privacy.sexy (Level 0 - Recommendation)
- **Input**: Workstation configuration
- **Allowed**: ✅ Developer choice
- **Constraints**:
  - Do not claim it secures CONFIT production
  - Do not run destructively without evidence
  - Optional, not required

### WebLLM (Level 0 - Experimentation)
- **Input**: Prompts, test inputs
- **Allowed**: ✅ Local browser only
- **Constraints**:
  - No production data in prompts
  - No production API keys
  - Experimentation only, never production

### Forge (Level 0 - Experimentation)
- **Input**: Prompts, model selections
- **Allowed**: ✅ Local only
- **Constraints**:
  - No production data
  - No production credentials
  - Never represents production integration

### Component Gallery (Level 1 - Manual)
- **Input**: None (browsing reference)
- **Allowed**: ✅ No data input
- **Constraints**: None

### Tiny Image (Level 2)
- **Input**: Image files
- **Allowed**: ✅ Local script only
- **Constraints**:
  - Do not upload sensitive user images to external services
  - Use local `optimize_images.py` for catalog images
  - Evaluate before/after locally

### SVG-Edit (Level 1 - Manual)
- **Input**: SVG content
- **Allowed**: ✅ Local editor
- **Constraints**: No sensitive data in SVGs

### SVGOMG (Level 2)
- **Input**: SVG files
- **Allowed**: ✅ Local script only
- **Constraints**: Use local `optimize_svgs.py`; no external upload

### Simple Icons (Level 1 - Manual)
- **Input**: None (browsing)
- **Allowed**: ✅ No data input
- **Constraints**: Verify licensing before commit

### CodeGraphContext (Level 2)
- **Input**: Repository source code
- **Allowed**: ✅ Local script only
- **Constraints**: 
  - No code sent to external services
  - Analyze local clone only

---

## Automation Security Rules

For Level 3+ (automated/CI) tooling:

1. **No network calls to external services** with repository data
2. **No secrets in CI logs** — use GitHub Actions secrets properly
3. **Artifacts must be sanitized** before upload
4. **Fail closed** — if sanitization fails, fail the build
5. **No telemetry** — tools must not silently collect usage data

---

## Incident Response

If a secret is accidentally exposed to an external tool:

1. **Immediately rotate** the exposed credential
2. **Audit access logs** for the affected service
3. **Document** the incident in security log
4. **Review** tool usage policy for gaps
5. **Update** this policy if needed

---

## Compliance Checklist (Pre-Tool-Use)

Before using any tool, verify:

- [ ] Input classification completed
- [ ] Secrets removed/redacted
- [ ] PII anonymized or synthetic data used
- [ ] Local execution preferred for sensitive data
- [ ] Tool security posture understood (local vs cloud)
- [ ] Output will not contain secrets
- [ ] Team member aware of constraints

---

## Enforcement

- CI gitleaks scan catches committed secrets
- Pre-commit hook runs gitleaks on staged changes
- Code review checks for tool usage compliance
- Security audit validates policy adherence
- Violations treated as security incidents

---

## Approved Tool Versions

| Tool | Approved Version/Source | Execution Method |
|------|------------------------|------------------|
| CyberChef | Latest via `npx cyberchef` or `docker run mikefarah/cyberchef` | Local only |
| Bundlephobia | bundlephobia.com (public API) | Query via script |
| drawDB | drawdb.app (reference) / local generation | Local script |
| Mermaid | mermaid.js via Kroki (kroki.io) or local CLI | CI + local |
| Hoppscotch | hoppscotch.io (local dev only) | Browser (localhost) |
| JSON Crack | jsoncrack.com / local Electron | Local preferred |
| Tiny Image | Local PIL/Pillow script | Local script |
| SVGOMG | Local SVGO via script | Local script |
| CodeGraphContext | Local AST analysis script | Local script |

---

## Review Cycle

This policy is reviewed:
- Quarterly
- After any security incident
- When new tools are evaluated
- When tool versions change significantly

Last reviewed: 2026-09-14
Next review: 2026-12-14