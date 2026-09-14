# CONFIT_A Engineering Tooling Architecture

## Overview

This document describes the engineering toolchain integrated around the CONFIT_A repository. The toolchain follows the principle: **each tool is integrated only where it provides measurable engineering value, at the lowest viable integration level, triggered by real engineering conditions.**

---

## Tool Categories

### Category A: Production Runtime Dependencies
Software required by the deployed CONFIT application.
- **Status**: Managed via `requirements.txt` (Vercel) and `backend/requirements.txt` (Docker/local)
- **Governance**: `check_runtime_imports.py` validates import closure per deployment target

### Category B: Engineering-Time Tooling
Software used by engineers, agents, auditors, QA, security reviewers, documentation workflows, or CI.
- **Integration Level**: Level 2 (local development) to Level 3 (automated workflow)

### Category C: Interactive Browser Utilities
Tools used manually when a specific task requires them.
- **Integration Level**: Level 1 (documented manual usage)

### Category D: Optional Experimentation Tools
Tools useful for research/prototyping but inappropriate as production dependencies.
- **Integration Level**: Level 0 (document/recommend only) or Level 1 (manual usage)

---

## Integrated Tool Matrix

| Tool | Category | Integration Level | Trigger | CONFIT Subsystem | Status |
|------|----------|-------------------|---------|------------------|--------|
| **Bundlephobia** | B | Level 2 (local script) | Pre-dependency-add | Frontend dependencies | ✅ Implemented |
| **drawDB** | B | Level 2 (local script) | Schema change / docs | Database / ERD | ✅ Implemented |
| **Mermaid/Kroki** | B | Level 3 (CI + docs) | Architecture change | System architecture, auth, VTON, Group 6 | ✅ Implemented |
| **Hoppscotch** | C | Level 1 (documented) | API validation needed | Auth, VTON, Group 6, Commerce | 📋 Documented |
| **JSON Crack** | C | Level 1 (documented) | Complex response inspection | Catalog, VTON, AI responses | 📋 Documented |
| **CSV Repair** | B | Level 2 (local script) | Catalog import workflow | Group 6 / B2B catalog | ✅ Implemented |
| **SQLChef** | C | Level 1 (documented) | Data export analysis | Analytics, inventory, orders | 📋 Documented |
| **Log Voyager** | C | Level 1 (documented) | Production incident investigation | All backend services | 📋 Documented |
| **Component Gallery** | C | Level 1 (documented) | UI pattern reference | B2B dashboards, admin | 📋 Documented |
| **Tiny Image** | B | Level 2 (local script) | Asset optimization | Catalog images, thumbnails | ✅ Implemented |
| **SVGOMG** | B | Level 2 (local script) | SVG asset optimization | UI assets, icons | ✅ Implemented |
| **CodeGraphContext** | B | Level 2 (local script) | Impact analysis before changes | All subsystems | ✅ Implemented |

---

## Integration Levels

| Level | Description | Examples |
|-------|-------------|----------|
| **0** | Document/recommend only | WebLLM, Forge, privacy.sexy |
| **1** | Manual developer usage documented | Hoppscotch, JSON Crack, Log Voyager, SQLChef, Component Gallery |
| **2** | Local development integration (scripts, config) | Bundlephobia, drawDB, CSV Repair, Tiny Image, SVGOMG, CodeGraphContext |
| **3** | Automated workflow integration (CI, pre-commit) | Mermaid/Kroki (diagram generation in CI) |
| **4** | CI integration (gate) | gitleaks, pip-audit, npm audit, migration chain, mutation gates |
| **5** | Production/runtime integration | None (no tooling promoted to runtime) |

---

## Security Policy

**Never send production secrets to external tools.**

Before using any browser-based or external utility:
1. Classify the input
2. Remove secrets
3. Remove unnecessary personal data
4. Anonymize production data where possible
5. Prefer synthetic fixtures for testing
6. Prefer local execution for sensitive analysis

**Never expose:**
- `DATABASE_URL` or database passwords
- API keys (Groq, Gemini, OpenAI, Modal, Vercel, etc.)
- JWT signing keys
- Session cookies
- Payment credentials
- Admin credentials
- Private user images
- Sensitive production logs

---

## Automation Philosophy

**Do not create static workflows where every tool runs on every change.**

Instead, implement decision-driven workflow:

```
New engineering event
        |
        v
Identify subsystem
        |
        v
Identify required evidence/input
        |
        v
Determine eligible tool
        |
        v
Check whether output already exists and is still valid
        |
        +---- valid evidence exists ---> reuse it
        |
        +---- evidence missing -------> run appropriate tool
        |
        v
Validate output
        |
        v
Persist useful artifact/result
        |
        v
Continue only when the next dependency is justified
```

### Examples

| Change Type | Tools Triggered |
|-------------|-----------------|
| Backend dependency change | CodeGraphContext, check_runtime_imports.py |
| API behavior change | Hoppscotch (manual) + automated API tests |
| Database schema change | drawDB, migration chain gate, schema gate |
| Frontend dependency change | Bundlephobia analysis |
| Production diagnostic | Log Voyager (manual) |
| Catalog import | CSV Repair + automated import tests |
| Architecture change | Mermaid/Kroki diagrams |

---

## Repository Structure for Tooling

```
docs/
  tooling/
    TOOLING_ARCHITECTURE.md        (this file)
    TOOL_USAGE_MATRIX.md           (detailed per-tool usage)
    TOOL_SECURITY_POLICY.md        (security constraints per tool)

scripts/
  tooling/
    analyze_bundlephobia.py        # Frontend dependency cost analysis
    generate_erd.py                # drawDB-compatible ERD from SQLAlchemy
    validate_csv.py                # CSV Repair integration for catalog
    optimize_images.py             # Tiny Image integration
    optimize_svgs.py               # SVGOMG integration
    dependency_graph.py            # CodeGraphContext integration
    generate_architecture_diagrams.py  # Mermaid diagram generation

docs/architecture/
    system-architecture.mmd        # System overview
    auth-rbac.mmd                  # Auth/RBAC boundaries
    tenant-boundaries.mmd          # Tenant isolation
    vton-flow.mmd                  # VTON request flow
    ai-provider-routing.mmd        # AI provider failover
    group6-architecture.mmd        # Group 6/B2B architecture
    commerce-flow.mmd              # Commerce/order flow
```

---

## Verification Standard

Every implemented tooling capability is classified as:
- **VERIFIED** - Executed and validated with evidence
- **IMPLEMENTED** - Code exists but not yet executed in CI
- **TESTED** - Executed locally with verified output
- **PARTIALLY VERIFIED** - Some paths verified
- **BLOCKED** - Cannot complete due to external dependency
- **NOT APPLICABLE** - Tool not relevant to CONFIT
- **UNVERIFIED** - No evidence yet

For every tool used, record:
```
Tool: [name]
Purpose: [what problem it solves]
CONFIT Subsystem: [which subsystem benefits]
Integration Level: [0-5]
Input: [required inputs]
Output: [produced outputs]
Security Constraints: [what must not be sent]
Execution Trigger: [when it runs]
Verification Method: [how to verify it works]
Observed Result: [actual outcome]
Evidence: [command output, artifacts, logs]
Known Limitation: [what it cannot do]
Status: [VERIFIED/IMPLEMENTED/TESTED/etc.]
```

---

## Anti-Redundancy Rules

Before performing any tool action:
1. Has the same artifact already been generated?
2. Is the existing result still valid?
3. Has the repository changed in a way that invalidates it?
4. Is a more authoritative source available?
5. Does another tool already provide the same evidence?
6. Will executing this tool add new information?

If the answer is no → reuse existing evidence.

---

## No Fake Integrations

Do not create:
- Fake MCP servers
- Fake adapters
- Empty wrappers
- Stub tool clients
- Fake API responses
- Hardcoded results
- Synthetic production metrics presented as real
- Placeholder tool status
- Mock "verified" outputs
- Static dashboards pretending to be dynamic
- Simulated logs presented as production logs
- Hardcoded tool availability
- Fake automation triggers

A tool is only considered integrated when the integration actually works and there is evidence proving it.