# CONFIT_FIX_RESEARCH — Research & Architectural Decisions
**Branch:** `fix/confit-audit-2026-09-06` (from main `97dff67`) · **Date:** 2026-09-06
**Scope:** evidence-backed sources for each audit fix area. Search snippets were NOT accepted as evidence — each decision below was validated against the referenced primary source and/or our live runtime.

---

## 1. HTTP 413 & Large-Image Upload Pipeline (P0-02/P0-03)

**Primary sources**
- RFC 9110 §15.5.14 — `413 Content Too Large`: the request body exceeds server-defined limits; the server MAY close the connection. <https://www.rfc-editor.org/rfc/rfc9110.html#status.413> (mirror summaries: runebook.dev/en/docs/http/rfc9110/section-15.5.14)
- Vercel Functions Limits (official): request/response body **4.5 MB** hard limit for Serverless Functions; exceeding it returns `413 FUNCTION_PAYLOAD_TOO_LARGE`. <https://vercel.com/docs/functions/limitations> — community corroboration: github.com/vercel/fun issue #84 (AWS Lambda layer enforces 6MB).
- MDN `HTMLCanvasElement.toDataURL` / `toBlob`: canvas exports a **newly encoded** image from the decoded bitmap — original container metadata (EXIF/XMP/C2PA APP segments) is not part of the bitmap and therefore does not survive re-encoding. <https://developer.mozilla.org/docs/Web/API/HTMLCanvasElement/toDataURL>

**Options considered**
| Option | License | Pros | Cons | Verdict |
|---|---|---|---|---|
| A. Raise server body limit | — | trivial | impossible on Vercel (platform 4.5MB hard), anti-pattern per RFC 9110 guidance | ❌ rejected |
| B. Client-side validate + resize + compress (canvas → JPEG ≤3MB, ≤1280px) | — (original code) | fits ALL paths incl. JSON-base64 VTON payloads; zero infra; strips EXIF/GPS (privacy win, MDN above) | quality trade-off; no resume | ✅ **implemented** (`src/lib/imageUpload.ts`, 11 unit tests; live proof: 4.5MB original → 0.27MB wire → GPU render RESULT_RENDERED) |
| C. Direct presigned upload (S3/R2) | AWS SDK Apache-2.0 | bypasses function body limit; unlimited size | requires object storage credentials **not provisioned** (STORAGE_PROVIDER=local — server honestly 501s wardrobe photo upload) | ⏸ BLOCKED on infra (owner decision B-03) |
| D. Resumable upload (tus 1.0.0) | tus spec open; `tus-node-server` **MIT**; `tus-js-client` **MIT**; Uppy **MIT** (tus.io/implementations) | resume interrupted uploads; standardizing in IETF draft | needs a running tus server/store — same infra dependency as C | ⏸ same blocker |

**Decision:** Option B now (documented, tested, live-verified); C/D documented as the escalation path the moment object storage exists. E2E coverage includes: JPEG/PNG/WebP valid, oversized (4.5MB phone photo), text-file spoof (`text/plain` → rejected client-side, **zero network POST**), corrupt PNG (decode fails → honest error, no POST), and a mapped 413→`IMAGE_TOO_LARGE` message if the gateway ever trips.

## 2. Cart / Commerce (P0-01, P1-03)

**Primary sources**
- Medusa.js docs (MIT-licensed platform): cart completion generates/requires an **Idempotency-Key**; guest cart is re-associated to the customer on login ("Set Cart's Customer"). <https://docs.medusajs.com/v1/references/js-client/CartsResource> · <https://docs.medusajs.com/resources/storefront-development/cart/update>
- Adobe Commerce (Magento) headless cart pattern: guest cart token (cookie) + customer cart + **`mergeCarts`** on login + stock revalidation on every cart fetch. <https://bemeir.com/articles/headless-adobe-commerce-cart-recovery-api-patterns-native-behavior>

**Mapping to CONFIT (all pre-existing/verified this branch):** server-authoritative cart keyed by `X-Session-Token` guest token (cookie-backed), `merge_guest_cart` on login, checkout `Idempotency-Key` header, optimistic add/update/remove with rollback to the server response, quantity merge on duplicate add (verified live: 3 adds → merged quantity, `PUT`/`DELETE` 200). Builder uses the same `cartStore.addItem` service with **real server SKUs only** (fabricated-SKU fallback removed + 4 regression tests).

## 3. Accessibility (P1-05/P1-06)

**Primary sources**
- WCAG 2.2 SC **1.4.4 Resize Text (AA)** — user agents must be able to scale to 200%; blocking pinch-zoom via `user-scalable=no`/`maximum-scale=1` fails it. <https://www.w3.org/WAI/WCAG22/Understanding/resize-text> (summaries: sitecockpit.com lexicon; equalweb academy 1.4.4)
- WCAG 2.2 SC **1.4.3 Contrast (AA)** — 4.5:1 normal text / 3:1 large text. <https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum>
- WCAG 2.2 SC **2.1.1/2.1.2 Keyboard** + no keyboard trap — basis for the modal focus contract. <https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html>
- **axe-core** (Deque, **MPL-2.0**) + `@axe-core/playwright` (MPL-2.0): engine used (v4.10.2 injected into Playwright) — zero-false-positive rule set; automated ≠ complete (Deque's own guidance: manual review required). <https://github.com/dequelabs/axe-core>

**Implemented:** zoom unblocked; **axe serious/critical = 0** across 10 routes × EN/AR (was up to 29 serious/route); labels/aria-labels on all form controls incl. previously-unlabelled selects; size-picker `listbox/aria-selected` invalid pattern → `group/aria-pressed`; this branch adds `useModalFocus` (Escape close, Tab trap with edge wrap, focus-in on open, focus restore to opener, stacked-modal guard) wired into 6 surfaces: AuthModal, VirtualTryOnModal, VisualSearchModal, CameraScanModal, VirtualStylistDrawer, Wardrobe upload modal — 5 unit tests + preview keyboard E2E.

## 4. Demo Payment Honesty (P1-04)

Per directive: PSP docs count only when actually connected. No Stripe/Tabby/Tamara account, key, or webhook exists in this environment (server `capabilities`: `payments_mode: "demo"`, `bnpl_live: false`). UI therefore renders "DEMO PAYMENT MODE — no real money will be charged" at checkout + product-page BNPL badge disclosure, driven by the server flags — not by static text. Payments-live remains **BLOCKED** on PSP credentials (owner decision).

## 5. VTON & AI Stylist (P0-03/P0-04)

- Live path exists and is verified: GPU worker (Modal, `fashn-vton` v1.5) with **pixel-level verification** of returned renders (rejects composites/overlays masquerading as inference), 30s client timeout + honest failure/`RESULT_RENDERED` states; result watermarked "temporary render".
- Stylist: multi-provider failover server-side, structured grounded output **restricted to live catalog product IDs** (verified grounded answers incl. 2nd prompt), explicit budget parsing (`explicit_budget` vs soft profile default — `stylist_service.py`), terminates (no infinite Styling). Prompt-injection probe added to the retest matrix.

## 6. Security (P1-07 + audit)

- **OWASP API Security Top 10 (2023)** — API1 BOLA, API5 BFLA, API4 rate limiting: <https://owasp.org/API-Security/editions/2023/en/0x11-t10/>
- **OWASP ASVS 4.0** (verification standard) — session/cookie/CSRF chapters: <https://owasp.org/www-project-application-security-verification-standard/>

**Verified controls:** server-side RBAC (shopper→admin/partner = 403; anonymous = 401), brand tenant scoping (`/partner/products` returns only brand_id=1 for that account), httpOnly+secure+SamesSite=Lax session cookie, double-submit CSRF compared server-side (403 CSRF_TOKEN_MISMATCH path tested in repo tests), login rate limiting (observed live when test logins throttled), no secrets in repo (gitleaks full-history ✅), GDPR export/delete endpoints scoped to the authenticated user.

## 7. License hygiene
No third-party code was copied into the repository for these fixes: `imageUpload.ts`, `useModalFocus.ts`, cart wiring, and tests are original implementations informed by the standards/primary docs above. Referenced OSS (tus-node-server MIT, Uppy MIT, axe-core MPL-2.0, Medusa MIT) is cited as pattern/decision evidence only.
