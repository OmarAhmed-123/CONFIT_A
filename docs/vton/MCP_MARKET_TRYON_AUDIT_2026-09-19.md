# MCP Market (mcpmarket.com) — Virtual Try-On Discovery Audit
**Date:** 2026-09-19 · **Author:** CONFIT_A Phase 5 (agent) · **Scope:** exhaustive discovery, classification, and pre-install security review of MCP Servers AND Agent Skills relevant to virtual try-on, garment transfer, fashion e-commerce imagery, and supporting tools.
**Claim standard:** every material statement below is tagged `CLAIM → EVIDENCE → STATUS`. No candidate was installed, connected, or called. This document is discovery + screening, NOT integration.

---

## A. Scope and method

**A.1 Surfaces searched.** Two surfaces, per Phase-5 directive:
1. **MCP Servers** — `mcpmarket.com/search?q=<keyword>` (server-side top-20 ranking per query; "Load More" is client-side only, `&page=N` on /search returns 404, `&type=` ignored). Category pages support server-side pagination: `/categories/<slug>/page/N`.
2. **Agent Skills** — `/tools/skills` (358,558 skills). **No server-side search exists on the skills surface** (`?search=` is ignored). Category pages: `/tools/skills/categories/<slug>/page/N` (100 pages for e-commerce-solutions).

**A.2 Keyword sweep.** Search executed for: `weshop`, `ai clothes changer`, `virtual try on`, `bikini try on`, `garment`, `outfit`, `human parsing`, `background removal`, `rembg`, plus the earlier-phase sweep (2026-09-15/16) covering: virtual-try-on variants (try-on/tryon/try on clothing/dress/shirt/hijab), garment transfer/swap, fashion, commerce, Shopify, catalog, segmentation, pose, human parsing, background removal, identity/face preservation, OCR/logo, multi-garment, layered outfit, fashion video. Category page 1 reviewed for: E-commerce Solutions (1,297 servers / 67 pages), E-commerce Skills (5,232 / 100 pages), plus search-driven coverage of Design Tools, Data Science & ML, API Development, Developer Tools, Marketing Automation, Browser Automation.

**A.3 Known limits (honest, not hidden).**
- Search returns only the top-20 ranked results per keyword; a server outside the top-20 for a given keyword is not guaranteed to be in this audit (mitigated by multi-keyword coverage + category page 1 + detail-page follow-through).
- The skills surface cannot be exhaustively enumerated (358,558 items, no server-side search). Page 1 of the e-commerce skills category + featured + search-adjacent keywords were scanned; **the skills surface is NOT exhaustively enumerated** — this is a genuine residual gap, documented per Phase-5 "fearless truth" requirement.
- `curl` is blocked by mcpmarket (403); all fetching via fetch_page (server-rendered HTML).

## B. Platform snapshot (2026-09-19)

| Fact | Value | Evidence |
|---|---|---|
| MCP servers | 48,857 | mcpmarket.com home (fetched 2026-09-19) |
| Agent skills | 358,558 | /tools/skills header (fetched 2026-09-19) |
| Top skills | openclaw variants ~388k installs each | /tools/skills featured list |
| Featured skills pricing | $19 premium prompt packs | featured cards (fetched 2026-09-19) |
| Skills "GitHub stars" labels | mislabeled — they are install counts (e.g., fal-tryon "64,192 GitHub stars" = 64,192 installs; upstream repo has 243 stars) | mcpmarket skill card vs github.com/fal-ai-community/skills |

## C. Re-verification of the 6 known examples

All 6 were re-verified against the live site on 2026-09-19:

| # | Example (from earlier list) | Search / slug result (2026-09-19) | STATUS |
|---|---|---|---|
| 1 | WeShop AI Virtual Try-On | `q=weshop` → zero vendor hits (generic e-commerce tools only); `/server/weshop-ai-virtual-try-on` → 404; `/server/weshop` → 404 | **NOT FOUND / UNVERIFIED** |
| 2 | WeShop Image & Video Studio | not in any try-on/garment/outfit search top-20 | **NOT FOUND / UNVERIFIED** |
| 3 | WeShop Visual Studio | not in any search top-20 | **NOT FOUND / UNVERIFIED** |
| 4 | WeShop Model Generator | not in any search top-20 | **NOT FOUND / UNVERIFIED** |
| 5 | AI Clothes Changer | `q=ai clothes changer` → no server with this name; closest is TryOnfy | **NOT FOUND as standalone** |
| 6 | AI / Bikini Virtual Try-On | `q=bikini try on` → no bikini-specific server; only the 4 known try-on servers | **NOT FOUND** |

> ⚠️ **SUPERSEDED BY RECONCILIATION (2026-09-19, Phase 6).** The six
> NOT-FOUND verdicts above are PRESERVED AS WRITTEN (they are the accurate
> record of what the Phase-5 search surface found), but the underlying
> conclusion is superseded: all six items are **LIVE Agent Skills** at
> direct slug URLs, plus a sixth WeShop skill discovered during
> reconciliation. Full details, exact URLs, and the miss cause: see the
> **RECONCILIATION ADDENDUM** at the end of this document.

**Interpretation (evidence-bound, preserved):** the earlier list is NOT the current complete list of try-on servers, and at least these 6 named items cannot be located on the live site today (delisted, renamed, or sourced from another platform). None of them is used as evidence of availability anywhere in this audit. *(Reconciliation 2026-09-19: they ARE locatable — via the skills surface, not the server search used here; see addendum.)*

## D. Try-on generation candidates (every candidate classified on all 6 facets)

Facets: **identity** (name/URL/type/vendor/repo) · **technical** (inputs, sleeves/hijab/multi-garment/layering, identity/pose/background preservation, batch/async) · **runtime** (local/hosted, auth, upload, rate limits) · **model** (named engine, OSS, weights, native multi-garment) · **legal** (license, training data, retention, residency) · **cost** (never inferred "free").

### D.1 Vybe Virtual Try-On — **REJECTED (engine no longer exists)**
- **identity:** mcpmarket.com/server/vybe-virtual-try-on · MCP server · vendor `arnabgho` · repo `github.com/arnabgho/mcp-vybe` (verified, FastMCP, 0 stars).
- **technical:** tool `virtual_tryon(model_image, garment_image, seed, prompt, size, guidance, steps…)` + `base64_to_url`; single garment only (one garment_image); no multi-garment/layering; identity/pose preservation = whatever the underlying model does (unverifiable).
- **runtime:** local wrapper, calls **Replicate** (hosted) with `REPLICATE_API_TOKEN`; images uploaded to Replicate; 600 s timeouts.
- **model:** engine = Replicate model `arnab-optimatik/vybe-virtual-tryon` (same author, custom published model; **not an established OSS engine**). **`replicate.com/arnab-optimatik/vybe-virtual-tryon` → 404 on 2026-09-19** (fetched). CLAIM: the wrapped model is no longer publicly available. EVIDENCE: 404 on the model page. STATUS: **VERIFIED** — the wrapper's core function is unverifiable/likely broken.
- **legal:** wrapper license permissive; Replicate model terms unknown (model gone); no evidence of training-data disclosure.
- **cost:** Replicate pay-per-use (token required) — not free.
- **Class: REJECTED** — underlying engine unreachable; nothing testable.

### D.2 Virtual Try-On (fal.ai) **skill** — **EVALUATION (only viable hosted path; not tested)**
- **identity:** mcpmarket.com/tools/skills/virtual-try-on-fal-ai · **Agent Skill** · listed vendor `nexu-io` (64,192 installs) · upstream `github.com/fal-ai-community/skills` (243 stars, 35 forks).
- **technical:** knowledge-layer skill (SKILL.md + genmedia CLI) driving **fal.ai hosted try-on endpoints**; upstream description: "Transfers clothing onto person photos… Supports tops, bottoms, dresses, and **full-body outfits**" (officialskills.sh, fetched); async endpoint calls with status polling; no local model.
- **runtime:** hosted (fal.ai); requires `FAL_KEY`; person + garment images uploaded to fal.ai; rate limits per fal.ai account tier (not specified in skill).
- **model:** fal.ai's hosted try-on models (fal.ai hosts multiple community VTO models; the skill no longer hardcodes a model table — "Replace all hardcoded model tables with dynamic search instructions", upstream commit 282eba6, 2026-03-06). Exact engine per call is **dynamic and not fixed by the skill** → engine identity UNVERIFIED.
- **legal:** skill layer permissive (community repo); fal.ai = commercial API ToS; model weights/licenses not ours; data retention per fal.ai ToS (not audited).
- **cost:** per-image hosted pricing (fal.ai); **not free**.
- **Status notes:** upstream skill folder `skills/fal-tryon` no longer present on `main` (repo restructured 2026-05-04 "flatten skills/claude.ai into skills/"; current tree listing fetched 2026-09-19 shows no fal-tryon) — the mcpmarket listing may reference a stale revision.
- **Class: EVALUATION** — real hosted VTO surface, but: engine identity unverified, no FAL_KEY in this environment (not tested), third-party upload of user images, per-use cost. **Not a replacement for FASHN; not an integration.**

### D.3 HeyBeauty — **RESEARCH**
- **identity:** mcpmarket.com/server/heybeauty · MCP server · vendor `chatmcp` (11 stars).
- **technical:** async task model — submit try-on task (user image + cloth image), query task status; clothing-item resources with metadata; single garment.
- **runtime:** hosted HeyBeauty API; vendor account/auth; images uploaded to vendor.
- **model:** HeyBeauty proprietary hosted service — **engine name undisclosed**; no OSS weights.
- **legal:** commercial API terms (not audited); no training-data disclosure found.
- **cost:** vendor pricing (account required); not free.
- **Class: RESEARCH** — wrapper around an unverifiable proprietary API.

### D.4 TryOnfy — **RESEARCH**
- **identity:** mcpmarket.com/server/tryonfy · MCP server · vendor `blasfin-finance` (0 stars).
- **technical:** tools = list features, **get direct try-on links** (web-app links, not raw image API), feature suggestion by natural language, pricing lookup; clothing/hair/accessories.
- **runtime:** hosted SaaS (tryonfy.com); the MCP surface returns **links to a web app** — programmatic image generation requires the underlying API (not documented in the server page).
- **model:** proprietary; undisclosed.
- **legal:** SaaS ToS (not audited).
- **cost:** pricing plans published via tool; not free.
- **Class: RESEARCH** — thin link-redirect client, not a generation API.

### D.5 GenPark Virtual Try-On Fit Profile Attribute Matcher — **RESEARCH (not an engine)**
- **identity:** mcpmarket.com/server/genpark-virtual-try-on-fit-profile-attribute-matcher · MCP "skill"/server · vendor `alphaparkinc` (8 stars).
- **technical:** deterministic **sizing/stretch attribute matching** for Google Virtual Try-On (VTO) — no image generation at all; JSON-schema-validated stdlib-only Python.
- **model:** none (attribute logic, not a model).
- **legal:** permissive (zero-dependency); Google VTO is Google's product.
- **cost:** free to run (code) — stated, not inferred; no API fees (no API called).
- **Class: RESEARCH** — complementary sizing-metaphysics; irrelevant to image generation; no multi-garment.

### D.6 CLO3D — **REJECTED (different domain)**
- **identity:** mcpmarket.com/server/clo3d · MCP server · vendor `Ubani-Studio` (0 stars).
- **technical:** controls **CLO3D** (commercial 3D garment CAD) locally: patterns, fabrics, simulation, export OBJ/FBX/GLB/turntables.
- **model:** CLO3D is 3D garment design software, **not a photo try-on renderer**; requires a CLO3D license + desktop install.
- **legal:** CLO3D = proprietary commercial software (per-seat license).
- **cost:** commercial license; not free.
- **Class: REJECTED** for the VTO pipeline (wrong domain: 3D CAD, not 2D garment-to-person rendering).

### D.7 ComfyUI wrappers (artokun `comfyui-9`, joenorton `comfyui` 409, lalanikarim `comfy` 46) — **RESEARCH**
- **identity:** MCP servers wrapping local/remote **ComfyUI**.
- **technical:** general image-gen workflow execution; try-on only via manual workflow wiring with third-party VTO nodes/models (IDM/OOTD-style) — **not turnkey VTO**.
- **model:** whatever nodes the user wires; model licensing is the integrator's burden (VTO community models are mostly NC-licensed per our Phase-0.5 license work).
- **runtime:** local ComfyUI (or remote URL); no auth.
- **cost:** free runtime; per-model license constraints apply.
- **Class: RESEARCH** — generic substrate, not a VTO candidate.

### D.8 Shopping/styling/product-photography (NOT try-on generation) — **RESEARCH, one-line each**
- **ApparelHub** (ApparelHub-AI) — autonomous apparel-store management (setup→fulfillment); no VTO.
- **ApparelMagic Demo Stager** (apparelmagic-johnc) — scrapes e-commerce data to populate ApparelMagic demos.
- **FitCheck** (pramodganapati) — weather + wardrobe outfit recommendations; no imagery.
- **Claude Personal Stylist** (wat-hiroaki) — scrapes fashion sites for recommendations.
- **FindMine Shopping Stylist** (findmine) — product-styling AI API (recommendations).
- **Phottly** (n1-ghosty) — 9:16 AI photoshoots from a single reference face (identity-conditioned photography, **not garment-conditioned VTO**); hosted.
- **PhotoShoot AI Design** (photoshootapp) — AI product photos/visuals; hosted.
- **discoverGPT** (vairetail.com) — e-commerce discovery.
- **Klydo / Vistoya / Totvs Moda / The Bag Kenya / Bridge to Agentia / StyleCLIP** — store/POS/retail-integration and styling surfaces; no VTO generation.
- **E-commerce 3D ×2** (ThomasGorisse, sceneview-tools) — 3D scene display for commerce.
- **Clipforge** (xixihhhh) — product-image → e-commerce short videos (fashion-video adjacent; not VTO).
- **VRCForge** (ayyitong888) — VRChat avatar editor (avatar domain, not photo VTO).
- **Hashidate** (libraz) — VTuber rendering (not VTO).

## E. Supporting (non-inference) tools

| Tool (URL) | Function | Runtime | License note | Class |
|---|---|---|---|---|
| **Rembg** (mcpmarket.com/server/rembg-1, holocode-ai) | background removal | **local** inference; downloads matting weights | rembg software Apache-2.0, **but model weights have separate licenses** (default u2net family: research/non-commercial provenance; alternative models (isnet, birefnet…) have their own terms) — wrapper license ≠ weights license | RESEARCH (supporting; license-gated per project rule) |
| **Scenario.com** (pasie15) | text→image + background removal | hosted API | commercial | RESEARCH |
| **Photoroom** (AourpallyNikhil) | background removal/product imagery | hosted | commercial | RESEARCH |
| **Peelaway** (jakeloo) | object/background removal, generative edits | hosted | commercial | RESEARCH |
| **VectoSolve** (Vectosolve) | vectorization, BG removal, upscaling, logos | hosted | commercial | RESEARCH |
| **ChangeImageTo** (vipul510-web) | BG removal, upscaling, OCR | hosted | commercial | RESEARCH |
| **AI Creative Servers** (resollo) | offline AI BG removal + GIMP/Inkscape automation | local | mixed (see repo) | RESEARCH |
| **PixelPanda ×2, Envious Canvas, Aws Nova Canvas, Image-1** | general image processing / hosted editing | local/hosted | mixed | RESEARCH |
| **YOLO** (GongRzhe) | object detection | local (weights per model license) | YOLO variants: AGPL/enterprise — **license-gated** | RESEARCH |
| **DINO-X** (IDEA-Research) | vision model | local | research terms | RESEARCH |
| **Posecode** (posecode-dev) | kinematic human-figure animation language | — | **not** a pose-estimation/VTO tool — name-collision only | REJECTED (not applicable) |
| **ImageSorcery** (xixihhhh) | crop/detect/OCR | mixed | per repo | RESEARCH |
| **FaceTron / Avots / MuAPI / Face Transform** | face/identity-adjacent generation | hosted | commercial, deepfake-adjacent — identity rights unresolved | REJECTED (identity use is LICENSE-GATED by project policy) |
| **Recraft ×2, Gemini Image Studio, Photo AI Studio, Nano Banana ×2, Seedream ×2, Stability AI, Flux, Z.AI, Kling, Pollinations, JigsawStack, DiffuGen, Game Asset Generator, ImageGen** | general image/video generation (text/prompt-driven) | mostly hosted | per vendor ToS | RESEARCH — **prompt-driven generators are NOT garment-conditioned VTO engines**; "can do try-on by prompting" ≠ VTO capability (no garment mask/transfer contract, no identity guarantee, no multi-garment layering contract) |
| **Hugging Face ×3 + Hub Semantic Search, Hfspace, vMLX** | model hosting/discovery infrastructure | hosted | platform ToS | RESEARCH (infrastructure, not an engine) |
| **Meshy, VGGT, Open Reality, 3DP, OpenSCAD, Blender family** | 3D/geometry | local/hosted | mixed | RESEARCH (different domain) |
| **EasyOCR-family OCR (via various)**, **ImageSorcery OCR** | logo/text read | local/hosted | per repo | RESEARCH (supporting) |

## F. Engine verification ("what actually performs the generation")

| Candidate | Engine behind the wrapper | Verified? |
|---|---|---|
| Vybe | Replicate `arnab-optimatik/vybe-virtual-tryon` | **GONE (404 on Replicate, 2026-09-19)** |
| fal-tryon skill | fal.ai hosted try-on endpoints (dynamic, not pinned) | NOT VERIFIED (no key, no run) |
| HeyBeauty | HeyBeauty proprietary API | NOT VERIFIED (no access) |
| TryOnfy | TryOnfy SaaS (web links) | NOT VERIFIED (no access) |
| CLO3D | CLO3D (3D CAD software) | Verified as CAD, not VTO |

**CLAIM: no open-source VTO engine with auditable weights is distributed through MCP Market (servers or skills) as of 2026-09-19.** EVIDENCE: every try-on-labeled candidate resolves to a hosted commercial API (fal.ai, Replicate, HeyBeauty, TryOnfy), a 3D CAD tool (CLO3D), or a generic image generator; the only OSS-adjacent path (ComfyUI) requires the integrator to source VTO models themselves (and the OSS VTO models available publicly are NC-licensed per Phase-0.5 work). STATUS: **VERIFIED within the reachable surfaces** (limit in §A.3 applies).

**FASHN HOLDS.** No candidate qualifies as a blind-replacement or verified-equal; marketing adjectives in listings ("realistic", "state-of-the-art", "high fidelity", "production-grade" — e.g., GenPark "production-grade", fal-tryon "high fidelity") were treated as unverified claims per Phase-5 rule.

## G. Security review (pre-install; NOTHING installed)

1. **Credentials:** wrappers require vendor API keys via env vars (`REPLICATE_API_TOKEN` in mcp-vybe source — reviewed in full; `FAL_KEY` for fal skills; vendor keys for HeyBeauty/TryOnfy). No hardcoded secrets observed in the one source fully reviewed (mcp-vybe `server.py`).
2. **Upload path:** every hosted VTO candidate requires uploading the **user's person image + garment image to a third party** (Replicate/fal.ai/HeyBeauty/TryOnfy). For CONFIT (real customers, modesty-sensitive context incl. hijab), this is a privacy/residency exposure with **no retention/residency terms evidenced in any wrapper**.
3. **Domains:** replicate.com, fal.ai, heybeauty (vendor), tryonfy.com — all third-party egress; our production egress policy currently restricts the sandbox to known hosts; none of these is approved.
4. **Retention/telemetry:** not documented in any reviewed wrapper → vendor ToS governs; **no evidence of deletion guarantees**.
5. **SSRF:** mcp-vybe `virtual_tryon` accepts `model_image`/`garment_image` as URLs — the *remote* service fetches them (no local fetch observed); `base64_to_url` handles data URIs only. No local SSRF surface observed in reviewed code. Hosted APIs inherit vendor SSRF posture (not auditable).
6. **Supply chain:** thin repos, 0–243 stars, recent activity, no audit history; dependencies (fastmcp, replicate, httpx) are standard. Low provenance = treat as untrusted code until audited.
7. **No auto-install; no production connection; no test calls made** (credentials for fal.ai/Replicate not present in this environment; obtaining them would be a procurement decision, not a discovery step).

## H. Five-way classification (complete candidate set)

| Class | Candidates |
|---|---|
| **RESEARCH** | HeyBeauty, TryOnfy, GenPark VTO Fit Matcher, ComfyUI wrappers ×3, ApparelHub, ApparelMagic Demo Stager, FitCheck, Claude Personal Stylist, FindMine, Phottly, PhotoShoot AI Design, discoverGPT, Klydo, Vistoya, Totvs Moda, The Bag Kenya, Bridge to Agentia, StyleCLIP, E-commerce 3D ×2, Clipforge, VRCForge, Hashidate, Rembg-1, Scenario.com, Photoroom, Peelaway, VectoSolve, ChangeImageTo, AI Creative Servers, PixelPanda ×2, Envious Canvas, Aws Nova Canvas, YOLO, DINO-X, ImageSorcery, Recraft ×2, Gemini Image Studio, Photo AI Studio, Nano Banana ×2, Seedream ×2, Stability AI, Flux, Z.AI, Kling, Pollinations, JigsawStack, DiffuGen, Game Asset Generator, ImageGen, Hugging Face ×3, Hfspace, vMLX, Meshy, VGGT, 3DP, Blender family (and all other general image/video generation and 3D entries) |
| **EVALUATION** | **Virtual Try-On (fal.ai) skill** (nexu-io / fal-ai-community) — only candidate with a real hosted VTO surface AND a plausible multi-garment claim (full-body outfits); blocked on: engine identity, FAL_KEY availability, privacy terms, cost, dynamic-input measurement vs FASHN |
| **ENGINEERING TOOL** | (none qualified — GenPark Fit Matcher is research-grade sizing metadata, not an engineering tool for the pipeline) |
| **PRODUCTION CANDIDATE** | (none) |
| **REJECTED** | Vybe Virtual Try-On (engine 404/dead), CLO3D (wrong domain: 3D CAD), Posecode (name collision, not pose/VTO), FaceTron/Avots/MuAPI/Face Transform (identity generation — LICENSE-GATED, deepfake-adjacent), and all 6 unverifiable known examples (C) |

## I. Legal / licensing summary

- **MCP server code license ≠ underlying model/API rights** (confirmed live: permissive wrapper repos wrapping commercial APIs; weights never included).
- No candidate provides an **OSS VTO model with commercial rights**; the public OSS VTO ecosystem (IDM/OOT/CatVTON/MV-Fashion/FastFit etc., per Phase-0.5) is NC-licensed — unchanged by this audit.
- Hosted APIs (fal.ai, Replicate, HeyBeauty, TryOnfy): commercial ToS govern inference; **no training-data disclosure, no retention guarantee, no residency guarantee evidenced** for any of them.
- rembg/YOLO-type supporting tools: software license ≠ weight license (u2net/AGPL caveats) → any supporting-tool adoption stays license-gated.

## J. Cost (stated, never inferred)

- Vybe → Replicate per-second GPU billing (token required). Not free.
- fal-tryon → fal.ai per-image billing (FAL_KEY). Not free.
- HeyBeauty → vendor pricing plans (account required). Not free.
- TryOnfy → published pricing plans (via its own tool). Not free.
- CLO3D → commercial per-seat software license. Not free.
- GenPark Fit Matcher → runnable free (stdlib-only code); makes no API calls. Stated from the server page, not inferred.
- No candidate was found that is a free **generation** service.

## K. Integration decision — **INTEGRATION BLOCKED**

Per Phase-5, integration requires ALL 15 conditions. Status against the only EVALUATION-class candidate (fal-tryon skill):

1. Engine identity verified → **NO** (dynamic fal.ai endpoints, not pinned; no run)
2. OSS or verifiable commercial rights for the model → **NO** (API ToS only, un-audited)
3. Native multi-garment / layered outfit support demonstrated → **NO** (claimed "full-body outfits", not measured)
4. Sleeve/hijab/long-sleeve handling demonstrated → **NO**
5. Identity preservation measured vs FASHN → **NO**
6. Pose preservation measured → **NO**
7. Background handling measured → **NO**
8. Privacy: no third-party upload of user images (or approved vendor DPA) → **NO** (upload is inherent; no DPA)
9. Data residency acceptable → **NO** (no residency evidence)
10. Rate limits / batch / async documented → **PARTIAL** (async via polling; limits = vendor-tier, not documented)
11. Cost approved with budget → **NO**
12. Failure semantics (explicit canonical errors, no fake success) → **UNTESTED**
13. Regression test coverage in repo → **NO**
14. Security review passed (this document = screening only) → **NOT PASSED FOR INSTALL**
15. Full test matrix (unit/integration/negative/security/privacy/failure/regression/dynamic/local/global/production-like) → **NO**

One unverified condition is disqualifying. **INTEGRATION BLOCKED.** No auto-install, no connection, no test calls.

## L. Comparison against the FASHN baseline (why nothing replaces FASHN)

- FASHN (fashn-vton-v1.5, Apache-2.0 engine weights, our fork 7c0f10af) is the **only** engine in this project with: measured multi-garment layering (L1→L2 chain), a calibrated sleeve anatomical-integrity gate (v2.3, 50/50-row matrix, class-E rejection), explicit canonical failure semantics (502 + `VTON_SLEEVES_NOT_VERIFIED` / `VTON_LAYER_NOT_APPLIED`, no fake success), and an audited license posture.
- Every MCP-market candidate fails at least one of {engine identity, rights, multi-garment, identity, privacy, cost} — see §K. Marketing adjectives were never treated as evidence.
- The only actionable long-term lead is the **fal.ai hosted VTO endpoint surface** (§D.2), which would require a procurement + privacy review before any measurement — and even then only as an **EVALUATION** comparison, not a replacement.

## M. Residual risks and recommendations

1. **Residual discovery gap:** skills surface (358,558) not exhaustively enumerable; new try-on skills could appear. Recommendation: re-run this audit monthly during Phase 5; treat any new try-on-named skill as RESEARCH until classified.
2. **Market volatility:** a listed engine (Vybe's Replicate model) is already dead 404 — listings are NOT availability guarantees. Never cite a listing as "the tool works".
3. **Privacy posture:** all hosted VTO paths conflict with the current no-third-party-user-image egress posture; any future evaluation requires an explicit privacy decision (DPA or on-prem engine only).
4. **No action taken:** nothing installed, nothing connected, nothing called, no credentials requested. FASHN path untouched.
5. **Report Part 5 reference:** this audit feeds the authoritative report's MCP section with the single release state: **MCP Market — no integration; FASHN HOLDS.**

---
*Artifact provenance: all fetches 2026-09-19 via fetch_page (mcpmarket.com blocks curl/403); repo/source verification via github.com raw + web search (mcp-vybe server.py in full; fal-ai-community/skills tree + commit history; Replicate model page 404). No images, keys, or user data involved in this audit.*

---

# RECONCILIATION ADDENDUM (2026-09-19, Phase 6 — P2)

**Purpose:** reconcile the Phase-5 "WeShop NOT FOUND" findings against new
evidence obtained 2026-09-19 by direct slug fetches + official-repo
verification. The original findings in §C are **preserved verbatim above**
and marked `SUPERSEDED BY RECONCILIATION`; this addendum does not rewrite
history — it records what was missed, why, and the current verified state.

## 1. Why the old search missed

1. **Two different surfaces were conflated.** The Phase-5 sweep used the
   MCP **Server** search (`/search?q=`), which is: top-20 results only,
   client-side "Load More", **no server-side pagination** (`&page=N` → 404).
   The WeShop items are **Agent Skills** (`/tools/skills`), which have
   **no server-side search at all**.
2. **The e-commerce skills category page 1 was scanned, but the WeShop
   skills do not rank in its first page** (5,232 skills / 100 pages) and
   live in other categories as well.
3. **Direct slug URLs work for skills** (`/tools/skills/<slug>` renders the
   full card) — the skills were discoverable by slug all along; the search
   surface simply never exposes them.

**Process fix (binding for future phases):** discovery claims are
`REACHABLE-SURFACE DISCOVERY` with documented limits (server surface =
top-20 only; skills surface = slug + deep pagination only), never
"exhaustive searched". Existence = `DISCOVERED`, never
`PRODUCTION CANDIDATE`.

## 2. Exact current URLs (all fetched live 2026-09-19, fetch_page)

| # | Skill | URL | active? |
|---|---|---|---|
| 1 | WeShop AI Virtual Try-On | `https://mcpmarket.com/tools/skills/weshop-ai-virtual-try-on` | **LIVE** |
| 2 | WeShop AI Clothes Changer | `https://mcpmarket.com/tools/skills/ai-clothes-changer` | **LIVE** |
| 3 | WeShop AI Bikini Virtual Try-On | `https://mcpmarket.com/tools/skills/ai-bikini-virtual-try-on` | **LIVE** |
| 4 | WeShop Bikini Virtual Try-On | `https://mcpmarket.com/tools/skills/bikini-virtual-try-on` | **LIVE** |
| 5 | WeShop AI Visual Studio | `https://mcpmarket.com/tools/skills/weshop-ai-visual-studio` | **LIVE** |
| 6 | AI Outfit Generator (WeShop ecosystem, found during reconciliation) | `https://mcpmarket.com/tools/skills/ai-outfit-generator` | **LIVE** |

Official repos (verified 2026-09-19): `github.com/weshopai/skills` (MIT;
VTO CLI + OpenAPI skill variants), `github.com/weshopai/weshop-skill-package`
(official npm CLI; `WESHOP_API_KEY` env-only, sent only to
`https://openapi.weshop.ai`).

## 3. Vendor API identifiable? — YES

All six skills are thin wrappers over the **WeShop OpenAPI**
(`openapi.weshop.ai`). VTO contract (from the official
`virtualtryon-openapi-skill` SKILL.md): `POST /openapi/agent/runs` → poll
`GET /openapi/agent/runs/{executionId}`; asset upload
`POST /openapi/agent/assets/images`; auth = raw key in `Authorization`.
Inputs: `originalImage` (garment URL, required) + optional
`fashionModelImage` (generated model "will resemble this person" —
**approximate identity, NOT preservation**) + optional `locationImage`.
Engines: `weshopFlash` / `weshopPro` (aspectRatio) / `bananaPro`
(1K/2K/4K; identity unverified). `batchCount` 1–16. States:
Pending/Segmenting/Running/Success/Failed. **Single garment per run — no
native multi-garment/layering.**

## 4. Evaluation possible? — NO (not without authorized access + privacy decision)

- No WeShop API key is authorized in this workspace; **none was requested
  or invented** (standing constraint).
- Even with a key, P3-B applies: the vendor publishes **no statements on
  uploaded/generated-image retention, model-training usage, deletion, data
  residency, or DPA** (weshop.ai/privacy is a standard template policy).
  → `EXTERNAL VTO INTEGRATION = BLOCKED` until documented.
- No real user images were sent to discover policy.

## 5. Production integration possible? — NO

Skill code license = MIT; **skill license ≠ underlying model/API terms**
(engines proprietary, hosted). Missing conditions for integration
(15-point gate, §K of this audit): identity preservation (no), multi-garment
(no), privacy (undocumented), cost (vendor-tier, unapproved), failure
semantics (untested), regression coverage (none), etc. One unverified
condition is disqualifying → **INTEGRATION BLOCKED** (unchanged; the
reconciliation changes DISCOVERY state only, not integration state).

## 6. Disposition

- §C rows 1–6: `NOT FOUND / UNVERIFIED` **preserved** + marked
  `SUPERSEDED BY RECONCILIATION` (this addendum is the stronger, newer
  evidence).
- New classification for all six skills: **DISCOVERED** (not PRODUCTION
  CANDIDATE; not RESEARCH-pending-access — evaluation is blocked on
  authorized credentials + privacy documentation, §4).
- FASHN baseline: **HOLDS** (unchanged by reconciliation).

---
*Addendum provenance: direct slug fetches via fetch_page 2026-09-19
(mcpmarket.com blocks curl/403); official repos verified via github.com;
no credentials requested, used, or stored; no images or user data involved.*

---

# PHASE 7 VERIFICATION (2026-09-19) — two additional WeShop skills + surface/identity/multi-garment distinctions

**Scope:** the Phase-7 directive lists two WeShop skills not covered by
the Phase-6 addendum. Both were verified live by direct slug fetch
(fetch_page, 2026-09-19). Everything above is preserved unchanged.

## 7.1. Newly verified skills (fetched live 2026-09-19)

| # | Skill | URL | active? | nature (from the listing's own text) |
|---|---|---|---|---|
| 7 | WeShop AI Studio — Image & Video | `https://mcpmarket.com/tools/skills/weshop-ai-image-video-studio` | **LIVE** | WeShop OpenAPI umbrella skill: virtual garment try-on, ghost mannequin, model & background swapping, pose adjustments, canvas expansion, flat-lay, background removal, AI video generation/enhancement; asset upload + async run polling |
| 8 | WeShop AI Model Generator | `https://mcpmarket.com/tools/skills/weshop-ai-model-generator` | **LIVE** | Converts a personal portrait or full-body photo into **stylized model imagery/video** with scene-description prompts; "natural body proportion preservation"; batch up to 16 outputs; images + short video |

Both are the same class as the other six: **Agent Skills** (thin
wrappers over the WeShop OpenAPI; `WESHOP_API_KEY` env-only in the
official package). Neither is an MCP Server; neither is a model.

## 7.2. P3-A — surface distinction (binding, must not recur)

For every item in this audit the four layers are recorded separately:

| layer | WeShop items |
|---|---|
| MCP Server | **none of the 8** — all are Agent Skills, not servers |
| Agent Skill | the 8 listings (SKILL.md + official npm CLI) — MIT skill code |
| Underlying API | WeShop OpenAPI (`openapi.weshop.ai`), proprietary, commercial ToS |
| Underlying engine/model | proprietary hosted (VTO: `weshopFlash`/`weshopPro`/`bananaPro`; video engines unnamed) — **not open, weights not auditable** |

Calling an Agent Skill "an MCP server", the wrapper "an AI model", or
the WeShop API "an open VTON model" is forbidden by the Phase-7
directive; this document uses only the table above.

## 7.3. P3-B — license separation for the two new skills

- Skill code: MIT (official `weshopai/skills` repo, same as the other six).
- CLI/package: official npm `weshop-skill-package` (same as the others).
- API terms: WeShop OpenAPI commercial ToS (vendor-tier; not published
  in the listing).
- Model rights: **unknown — proprietary hosted engines; no weights, no
  license statement.** MIT on the wrapper grants NO rights to the
  underlying engines (Phase 7 §14).
- Input-image handling / output rights / retention / training usage /
  residency: **undocumented** (same gap as §4). → privacy conditions
  unmet.

## 7.4. P3-C — identity requirement (the critical one)

- **WeShop AI Model Generator = identity SUBSTITUTION, not preservation.**
  Its stated function is to convert the user's portrait "into stylized
  model imagery" — i.e., the person is replaced by a generated model
  look. Classified per the Phase-7 directive:
  **`NOT SUITABLE AS A CONFIT REAL-USER IDENTITY-PRESERVING VTON ENGINE`**
  (the product requirement is identity preservation; the service does the
  opposite by design). It is not hidden behind the phrase "model
  reference" — the listing itself says "converts portrait photos into
  realistic … model visuals".
- **VTO skill's `fashionModelImage`** ("will resemble this person") =
  approximate-identity option on top of a model-generation workflow —
  still not verified preservation (Phase-6 §3 stands).
- **Studio skill's "model swapping"** = catalog-model composition for
  product photos (e-commerce catalog workflow), not real-user identity
  rendering.

## 7.5. P3-D — multi-garment requirement

`batchCount` 1–16 (VTO) and "batch generation of up to 16 outputs"
(Model Generator) mean **16 outputs generated from one input set** —
different crops/angles/variations. It is NOT "one person + multiple
garments in one composition". The VTO contract accepts exactly one
garment (`originalImage`) per run. **No WeShop skill or endpoint
demonstrates native multi-garment/layered composition or a deterministic
layer order.** (Phase-6 §3 stands; stated explicitly per Phase-7 §16.)

## 7.6. P3-E — integration decision (unchanged, progression states explicit)

Allowed progression: `DISCOVERED → SCREENED → EVALUATED → PRODUCTION
CANDIDATE → INTEGRATED`. Current state for all 8 WeShop-ecosystem
skills: **DISCOVERED → SCREENED** (identity/capability/engine/commercial/
security audited above and in the Phase-6 addendum). None reaches
EVALUATED: no authorized credentials (none requested), no documented
retention/training/deletion/residency/DPA, no identity preservation, no
multi-garment. **EXTERNAL LIVE EVALUATION = BLOCKED** (Phase-7 §18: no
real user images sent to any hosted VTO; synthetic-only testing only if
terms permit — they do not document it). **FASHN HOLDS.** Nothing was
installed in any phase.

---
*Phase-7 provenance: direct slug fetches via fetch_page 2026-09-19;
listing text quoted above is the evidence; no credentials requested,
used, or stored; no images sent to any vendor.*
