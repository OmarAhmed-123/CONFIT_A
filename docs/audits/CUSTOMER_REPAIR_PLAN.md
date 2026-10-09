# CUSTOMER_REPAIR_PLAN.md — CONFIT_A Customer Role: Forensic Audit & Repair Plan

> **Document type:** Role-based repair plan (PLANNING / AUDIT ONLY — no application code changed to produce it).
> **Target repo:** `OmarAhmed-123/CONFIT_A` · **Branch:** `main` @ `a44f1fb` (clean).
> **Audit date:** 2026-10-09.
> **Siblings:** `ADMIN_REPAIR_PLAN.md`, `BRAND_OWNER_REPAIR_PLAN.md`, `VIRTUAL_TRY_ON_REPAIR_PLAN.md`, `STYLELIST_AI_REPAIR_PLAN.md`.

---

## 1. Title & Scope

The **Customer (shopper)** role end-to-end: discovery → product detail → cart → coupons/promos → checkout → payment → order tracking → returns, plus account profile, wardrobe, outfits/looks, wishlists, and guest flows. This plan owns the shopper-facing commerce correctness (totals, currency, cards, coupons) and the shopper UI/UX.

**Out of scope:** admin order ops (`ADMIN_REPAIR_PLAN.md`), brand self-service (`BRAND_OWNER_REPAIR_PLAN.md`), try-on render pipeline (`VIRTUAL_TRY_ON_REPAIR_PLAN.md`), stylist (`STYLELIST_AI_REPAIR_PLAN.md`). The customer-facing *surface* of try-on/stylist is cross-referenced where relevant.

---

## 2. Status & Severity Legend

**Status:** `VERIFIED` · `IMPLEMENTED` · `TESTED-PASS` · `TESTED-FAIL` · `GAP` · `BUG-VERIFIED` · `LIKELY` · `UNVERIFIED` · `BLOCKED` · `NO-GO` · `NOT FOUND IN SEARCHED SCOPE`.
**Severity:** P0 (blocking/security) · P1 (major) · P2 (defect w/ workaround) · P3 (polish). Evidence cites `path:line` when directly inspected.

---

## 3. Executive Summary

The customer path has a **secure spine** — webhook signatures fail-closed, stock is validated server-side, prices are never trusted from the client, and live payments fail-closed in demo mode — but it has **money-correctness seams** where cart and checkout disagree, which is the most damaging class of bug for a storefront.

- **P1 (correctness):** express-shipping total differs between cart and checkout (**CUS-01**); checkout country vs. cart settlement currency can mismatch (**CUS-02**); guest order access keys on order-number only (**CUS-09**); guest returns not exposed (**CUS-10**).
- **P2:** optimistic cart totals go stale (**CUS-03**); demo-payment banner always shown even when not applicable (**CUS-04**); promo market not enforced (**CUS-11**); stale promo not cleared when cart changes (**CUS-13**).
- **Verified-positive (preserve):** webhook signature fail-closed (**CUS-16**), server-side stock validation (**CUS-17**), no client-trusted prices (**CUS-23**), live-payment fail-closed (**CUS-06**).

**Baseline tests (this audit):** backend 3732 passed / 4 env-only failed / 21 skipped; frontend build PASS. The payment package is `backend/app/providers/payment/{base,orchestrator,capability_registry,schemas}.py` (no separate adapter/idempotency/webhook submodules — see §12).

---

## 4. Baseline & Environment Evidence

| Item | Evidence | Status |
|---|---|---|
| Cart totals (optimistic) | `frontend/src/.../cartStore.ts` | VERIFIED (store exists) |
| Express shipping mismatch | `backend/app/services/commerce_service.py:1699–1701` vs checkout path L311–317 | BUG-VERIFIED |
| Demo banner | `frontend/src/views/consumer/CheckoutView.tsx:217–226` | BUG-VERIFIED |
| Payment package | `backend/app/providers/payment/base.py|orchestrator.py|capability_registry.py|schemas.py` | VERIFIED |
| Live payment fail-closed | payment orchestrator refuses live mode absent config | VERIFIED (positive) |
| Backend suite | 3732 passed / 4 env-only failed / 21 skipped | TESTED-PASS |
| Frontend build | tsc + vite build | TESTED-PASS |
| Spec Kit | absent → documentation-based process | VERIFIED (absent) |

---

## 5. Current-State Inventory (Customer)

**Frontend (exists):** `frontend/src/views/consumer/` — `DiscoverView`, `ProductDetailView`, `CheckoutView`, `OrderTrackingView`, `UserProfileView`, `WardrobeView`, `OutfitBuilderView`, `MyLooksView`, `HomeView`, `FitFinderView`, `TryOnFitView`; `cartStore.ts`; `AuthModal`.
**Backend (exists):** `commerce_controller.py` + `commerce_service.py` (cart, checkout, orders, returns), `catalog_controller.py`, `profile_controller.py`, `wardrobe_controller.py`, `outfit_controller.py`, `public_look_controller.py`, payment providers package.

**Wired/unwired highlights:**

| Capability | Backend | UI | Status |
|---|---|---|---|
| Add-to-cart, line dedupe | UNIQUE cart line (DB-20) | yes | VERIFIED |
| Cart totals | server authoritative | optimistic, can drift | BUG (CUS-03) |
| Coupon apply | promotion model | yes | partial (caps unenforced, DB-03) |
| Checkout + payment | orchestrator | CheckoutView | partial (CUS-01/02/04) |
| Order tracking (auth) | yes | OrderTrackingView | VERIFIED |
| Guest order access | order-number keyed | yes | WEAK (CUS-09) |
| Returns (auth) | yes | yes | VERIFIED |
| Returns (guest) | backend path | not exposed | GAP (CUS-10) |
| Saved cards / payment methods | demo mode | UI present | see CUS-06/§12 |

---

## 6. Findings Register (Customer)

| ID | Title | Sev | Status | Evidence |
|---|---|---|---|---|
| CUS-01 | Express shipping total differs cart vs checkout | P1 | BUG-VERIFIED | `commerce_service.py:1699–1701` vs L311–317 |
| CUS-02 | Checkout country vs cart settlement currency mismatch | P1 | BUG-VERIFIED | currency resolved differently in two paths |
| CUS-03 | Optimistic cart totals go stale after server recompute | P2 | BUG-VERIFIED | `cartStore.ts` |
| CUS-04 | Demo-payment banner always shown | P2 | BUG-VERIFIED | `CheckoutView.tsx:217–226` |
| CUS-05 | Coupon caps not enforced (over-redemption/race) | P1 | BUG-VERIFIED | depends DB-03 (this plan §12) |
| CUS-06 | Live payments fail-closed in demo mode | — | VERIFIED (positive) | orchestrator |
| CUS-07 | Saved cards are demo-only (no real vault/PSP token) | P2 | VERIFIED | demo mode by design; must be honest in UI |
| CUS-08 | Card entry lacks PSP-grade validation/tokenization path | P2 | LIKELY | demo mode; plan a real-PSP seam |
| CUS-09 | Guest order access keyed on order-number only | P1 | BUG-VERIFIED | needs email/token second factor |
| CUS-10 | Guest returns not exposed in UI | P1 | GAP | backend path exists |
| CUS-11 | Promo market/region not enforced at apply | P2 | BUG-VERIFIED | promo usable cross-market |
| CUS-12 | FX/settlement currency display inconsistencies | P2 | LIKELY | multiple currency sources |
| CUS-13 | Stale promo not cleared when cart contents change | P2 | BUG-VERIFIED | promo persists after eligibility lost |
| CUS-14 | Recently-viewed duplicates (jitter in UI list) | P2 | BUG-VERIFIED | DB-01 (duplicate rows) |
| CUS-15 | Wishlist toggle verified | — | VERIFIED (positive) | MOT-07 |
| CUS-16 | Webhook signature fail-closed | — | VERIFIED (positive) | payment webhook |
| CUS-17 | Server-side stock validation | — | VERIFIED (positive) | INSUFFICIENT_STOCK 409 |
| CUS-18 | Order discount allocation correctness | — | VERIFIED (positive) | `test_order_discount_allocation.py` green on clean DB |
| CUS-19 | Checkout a11y/animation gaps (upload/CTA) | P2 | LIKELY | see §14/§15 |
| CUS-20 | Address book / multi-address UX | P3 | LIKELY | enhancement |
| CUS-21 | Order status timeline not dynamic/live | P2 | LIKELY | OrderTrackingView static |
| CUS-22 | Empty/error/loading states uneven across consumer views | P2 | LIKELY | UX consistency |
| CUS-23 | No client-trusted prices | — | VERIFIED (positive) | server recompute |
| CUS-24 | Guest cart → account merge on login | P2 | LIKELY | cart continuity |

---

## 7. Root-Cause Analysis

1. **Two code paths compute money** (cart preview vs. checkout settlement) and drifted (CUS-01/02). The server is authoritative at checkout, but the cart preview uses a slightly different shipping/currency computation → user sees total A, pays total B.
2. **Optimistic UI without reconciliation** (CUS-03): the store updates locally and does not always overwrite with the server's authoritative recompute.
3. **Promotions lack DB-level invariants** (CUS-05/11/13): eligibility/market/caps are applied in service code but not enforced as constraints, so races and stale state slip through.
4. **Guest identity is under-specified** (CUS-09/10): order-number is treated as a bearer secret.

---

## 8. Target Architecture / Desired State

- **One money engine.** Cart preview and checkout settlement call the *same* pricing function (shipping, tax, FX, discounts) so the number never changes between pages.
- **Server-authoritative cart with optimistic overlay that always reconciles** to the server response.
- **Promotions enforced at the DB** (caps + market + validity) with the service layer as the first gate, matching `ADMIN_REPAIR_PLAN.md` promotions admin.
- **Guest access via order-number + verified email (or signed link token)**; guest returns reachable.
- **Honest payments:** demo mode clearly labeled only when active; a clean seam for a real PSP (tokenized cards, idempotency keys, webhook reconciliation).

---

## 9. Specification (Specify)

**Spec A — Total parity (CUS-01/02/03/12).** The order total shown in cart equals the total charged at checkout for the same inputs (items, address/country, shipping method, promo, currency). Acceptance: property test asserts `cart_total == checkout_total` across a matrix of countries × shipping methods × promos; optimistic UI always ends on the server number.

**Spec B — Promotion integrity (CUS-05/11/13).** A promo cannot be redeemed beyond its global or per-user cap, cannot apply outside its market, and is auto-removed when the cart no longer qualifies. Acceptance: concurrency test (N parallel redemptions ≤ cap); cross-market apply refused; cart mutation re-validates promo.

**Spec C — Guest trust (CUS-09/10/24).** Guest order lookup requires order-number **plus** the order email or a signed token; guests can view and initiate returns; a guest cart merges into the account on login. Acceptance: order-number alone is insufficient; guest return flow reachable; merge test.

**Spec D — Honest payment surface (CUS-04/06/07/08).** Demo-mode banner appears only in demo mode; card UI states it's a demo (no real charge) when demo; a documented seam exists for a real PSP with tokenization + idempotency + webhook reconciliation. Acceptance: banner conditional; live mode still fail-closed without config.

---

## 10. Plan (Plan)

1. Extract/confirm a single `price_quote(cart, address, method, promo, currency)` used by both cart and checkout (fix CUS-01/02).
2. Make `cartStore` reconcile to server quote on every mutation (CUS-03).
3. Add DB constraints + race-safe redemption for promos (CUS-05) and market/validity re-check on apply and on cart change (CUS-11/13).
4. Strengthen guest identity (CUS-09) and expose guest returns (CUS-10).
5. Conditional demo banner + PSP seam (CUS-04/07/08).
6. UX/a11y dynamism pass across consumer views (CUS-19/21/22) incl. the shared launch-button animation.
7. Converge: extend tests, keep positives green.

---

## 11. Tasks (Tasks)

**T-CUS-01 · Unify the pricing engine (total parity)**
- **Sev:** P1 · **Linked:** CUS-01, CUS-02, CUS-12
- **Preconditions:** none.
- **Steps:** 1) Identify the two computations (`commerce_service.py:1699–1701` cart vs L311–317 checkout). 2) Extract a single authoritative `price_quote()` covering items, shipping (incl. express), tax, FX/settlement currency, discounts. 3) Route both cart preview and checkout through it. 4) Resolve settlement currency from one source (country→market→currency).
- **Files:** `backend/app/services/commerce_service.py` (+ a pricing module if warranted), schemas.
- **Acceptance:** Spec A property test passes; express shipping identical in both; currency consistent.
- **Tests:** new parity property test (countries × methods × promos); keep `test_order_discount_allocation.py` green.
- **Rollback:** feature-flag the unified path. · **Risk:** high (money). · **Status:** BUG-VERIFIED → planned.

**T-CUS-02 · Cart store reconciliation**
- **Sev:** P2 · **Linked:** CUS-03
- **Steps:** after each mutation, overwrite optimistic totals with the server quote; show a brief "updating…" state; never display a stale total at rest.
- **Files:** `frontend/src/.../cartStore.ts`, cart view.
- **Acceptance:** displayed total always equals latest server quote once settled.
- **Tests:** store unit test (optimistic→reconcile); UI test.
- **Rollback:** revert reconcile. · **Risk:** low. · **Status:** planned.

**T-CUS-03 · Promotion DB enforcement + race safety**
- **Sev:** P1 · **Linked:** CUS-05 (and DB-03, DB-04)
- **Preconditions:** coordinate with `ADMIN_REPAIR_PLAN.md` T-ADM-05 (coupon CRUD writes caps).
- **Steps:** 1) Add DB columns/constraints for global + per-user caps and market/validity. 2) Enforce redemption atomically (row lock / conditional update) so N concurrent redemptions cannot exceed the cap. 3) Commit redemption **inside** the order transaction (fixes DB-04).
- **Files:** Alembic migration (forward from head; mind prod `0035` — §19), promotion service, order service.
- **Acceptance:** Spec B concurrency test; redemption atomic with order.
- **Tests:** parallel-redemption test ≤ cap; redemption rollback when order fails.
- **Rollback:** constraints are additive; keep service gate as fallback. · **Risk:** high. · **Status:** BUG-VERIFIED → planned.

**T-CUS-04 · Promo market + stale-promo auto-clear**
- **Sev:** P2 · **Linked:** CUS-11, CUS-13
- **Steps:** re-validate promo market on apply; on any cart mutation, re-check eligibility and silently remove + notify if no longer valid.
- **Files:** promotion service, `cartStore.ts`, cart UI.
- **Acceptance:** cross-market apply refused; promo removed when cart drops below threshold.
- **Tests:** market-mismatch refusal; cart-change clears promo.
- **Rollback:** revert checks. · **Risk:** low. · **Status:** planned.

**T-CUS-05 · Guest order trust + guest returns**
- **Sev:** P1 · **Linked:** CUS-09, CUS-10
- **Steps:** 1) Require order-number **plus** order email (or a signed, expiring link token) for guest lookup. 2) Expose guest return initiation in UI using the same second factor. 3) Rate-limit guest lookups.
- **Files:** `commerce_controller.py`/service, `OrderTrackingView.tsx`, guest return view.
- **Acceptance:** Spec C; order-number alone insufficient; guest returns reachable.
- **Tests:** "order-number alone is 403/404"; guest return happy path; rate-limit test.
- **Rollback:** behind flag. · **Risk:** medium (customer access). · **Status:** BUG-VERIFIED/GAP → planned.

**T-CUS-06 · Honest payment surface + PSP seam**
- **Sev:** P2 · **Linked:** CUS-04, CUS-06, CUS-07, CUS-08
- **Steps:** 1) Render demo banner only when payment mode is demo (`CheckoutView.tsx:217–226`). 2) Label card entry as demo when demo. 3) Define a provider-adapter seam in `backend/app/providers/payment/` for a real PSP: tokenized cards (no PAN stored), idempotency keys on capture, webhook reconciliation (extend the fail-closed signature check already verified, CUS-16). Do **not** enable live mode without config (preserve CUS-06).
- **Files:** `CheckoutView.tsx`, `providers/payment/{orchestrator,base,schemas}.py` (+ a new adapter module when a PSP is chosen).
- **Acceptance:** Spec D; banner conditional; live mode still fail-closed.
- **Tests:** banner-conditional test; idempotent-capture test; webhook replay idempotent (extends existing).
- **Rollback:** demo remains default. · **Risk:** medium. · **Status:** planned.

**T-CUS-07 · Recently-viewed dedupe (UI jitter)**
- **Sev:** P2 · **Linked:** CUS-14 (DB-01)
- **Steps:** enforce unique `(user, product)` for recently-viewed (upsert touch timestamp) so the list has no duplicates; UI orders by last-viewed.
- **Files:** Alembic migration (unique constraint) + repository upsert; profile/discovery UI.
- **Acceptance:** no duplicate rows; stable ordered list.
- **Tests:** repeated view → single row, timestamp updated.
- **Rollback:** additive constraint. · **Risk:** low. · **Status:** planned.

**T-CUS-08 · Consumer UX dynamism + a11y + animation pass**
- **Sev:** P2 · **Linked:** CUS-19, CUS-21, CUS-22, §14/§15
- **Steps:** live order-status timeline; consistent empty/loading/error states with skeletons; shared design tokens; the **launch (“rocket”) animation** on primary CTAs (add-to-cart, place order, upload) honoring `prefers-reduced-motion`; `HonestProductImage` everywhere; full RTL/i18n.
- **Files:** consumer views, shared components/tokens.
- **Acceptance:** §14/§15; axe passes.
- **Tests:** axe a11y, RTL snapshot, reduced-motion.
- **Rollback:** revert style layer. · **Risk:** low. · **Status:** planned.

**T-CUS-09 · Guest cart merge on login**
- **Sev:** P2 · **Linked:** CUS-24
- **Steps:** on login, merge guest cart into the user cart respecting line dedupe (DB-20) and re-quote.
- **Files:** auth/cart service, `cartStore.ts`.
- **Acceptance:** no lost items, no duplicate lines, totals re-quoted.
- **Tests:** merge test with overlapping lines.
- **Rollback:** behind flag. · **Risk:** low. · **Status:** planned.

---

## 12. Data Model / Migration Considerations

- **Promotions (CUS-05/11/13 / DB-03/DB-04):** add global cap, per-user cap, market scope, validity window columns + a redemption ledger with a uniqueness/atomic-decrement strategy; commit redemption inside the order transaction. This is the shared dependency with `ADMIN_REPAIR_PLAN.md` promotions admin — one migration, not two.
- **Recently-viewed (CUS-14/DB-01):** unique `(user_id, product_id)` + upsert.
- **Payment package shape:** today it is `backend/app/providers/payment/{base,orchestrator,capability_registry,schemas}.py` — there is **no** separate `adapters/`, `idempotency`, or `webhooks` module. A real-PSP task (T-CUS-06) should add an adapter module and an idempotency key store; keep the verified fail-closed webhook signature behavior (CUS-16).
- **Migration hygiene:** forward Alembic revision from head `0034_*`; production is already at `0035_product_images` (ahead of `main`). Coordinate so a new revision chains after `0035` once merged (see §19). **This document adds no migration.**
- **Money columns:** keep `Numeric(12,2)` (DB-19) — do not switch to float.

---

## 13. API Contract Changes (proposed)

| Endpoint | Change | Note |
|---|---|---|
| cart preview + checkout | both return a quote from unified `price_quote()` | parity (CUS-01/02) |
| apply promo | re-validate market/caps/validity server-side | CUS-05/11 |
| guest order lookup | require order-number **+ email/token** | CUS-09 |
| guest return | new endpoint, same second factor | CUS-10 |
| capture/webhook | idempotency key + reconciliation | CUS-06 |

All request/response bodies use explicit Pydantic schemas; never trust client prices or role; `await` all async calls.

---

## 14. UI/UX Plan (colors · animation · dynamism)

- Canonical gold token (fix UX-01 drift) across all consumer views.
- **Dynamic order tracking:** live-updating status timeline with animated step transitions.
- **Launch animation:** shared `<LaunchButton>` for "Add to cart", "Place order", and image upload — button morphs to a rising rocket (bottom→top) + success color shift, then a confirmation check. `prefers-reduced-motion` → opacity fade only.
- **Professional image presentation:** `HonestProductImage` with consistent aspect ratios, zoom on product detail, graceful fallbacks; no raw `<img>` for product media.
- Consistent skeletons for discovery/cart/checkout; explicit empty & error states.

---

## 15. Accessibility Plan (WCAG 2.2 AA)

- All CTAs and inputs have accessible names; checkout form fields associated with labels + error messaging via `aria-describedby`.
- Shared `Modal` focus trap (A11Y-03) for AuthModal and confirm dialogs.
- Visible consistent focus ring (UX-04); async actions announce status via `aria-live` without stealing focus (fixes MOT-02 pattern where disabling a pending button drops focus).
- Full RTL/Arabic parity on all consumer views.
- Launch animation respects reduced motion.

---

## 16. Security & Privacy

- Preserve: webhook signature fail-closed (CUS-16), server-side stock (CUS-17), no client-trusted prices (CUS-23), live-payment fail-closed (CUS-06).
- Guest access must not treat order-number as a bearer secret (CUS-09).
- Never store PAN; use PSP tokenization in any real-payment work (CUS-08).
- Rate-limit guest lookups and promo applies (anti-enumeration/abuse).
- Never render secrets/keys in checkout diagnostics.

---

## 17. Testing & Verification Plan

- **Total parity property test** (the headline test for this role).
- **Promotion concurrency** (≤ cap), market refusal, stale-clear.
- **Guest trust**: order-number-alone refused; guest return happy path.
- **Payment**: conditional banner, idempotent capture, webhook replay idempotent.
- **Cart**: reconciliation, guest merge, recently-viewed dedupe.
- **Frontend**: axe, RTL, reduced-motion, checkout flow e2e.
- **Baseline to preserve:** 3732 passed / 21 skipped (4 env-only failures unrelated); frontend build PASS. No new TESTED-FAIL.

---

## 18. Rollout / Deployment / Flags

- Unified pricing and guest-trust behind flags for staged rollout.
- Promotions migration deployed with admin CRUD (coordinated release).
- Vercel serverless limits are ample for checkout (short requests); no long-running customer job.

---

## 19. Risks, Assumptions, Open Questions

- **R1 (migration drift):** prod at `0035_product_images`, `main` at `0034` — chain new promo/recently-viewed migrations after `0035` merges. **UNVERIFIED in `main`.**
- **R2:** real-PSP choice is a product decision; until then demo mode remains and must be labeled honestly.
- **A1:** settlement currency is derived from country→market mapping (confirm the single source in T-CUS-01).
- **Q1:** should stale-promo removal be silent + toast, or require user confirmation? (Recommend toast.)

---

## 20. Acceptance Criteria / DoD + Traceability

**Role is "done" when:** the price shown equals the price charged for identical inputs; coupons respect caps/market/validity and never over-redeem; guests cannot access orders with just an order-number and can do returns; payments are honestly labeled and demo stays fail-closed for live; consumer views are dynamic, animated (launch CTA), image-polished, RTL, and WCAG 2.2 AA — with all verified-positive invariants preserved.

| Finding | Task | DoD signal |
|---|---|---|
| CUS-01/02/12 | T-CUS-01 | Parity test green; one pricing engine. |
| CUS-03 | T-CUS-02 | No stale totals. |
| CUS-05 | T-CUS-03 | Caps enforced, race-safe, in-txn. |
| CUS-11/13 | T-CUS-04 | Market enforced; stale promo cleared. |
| CUS-09/10 | T-CUS-05 | Guest trust + returns. |
| CUS-04/06/07/08 | T-CUS-06 | Honest banner + PSP seam; live fail-closed. |
| CUS-14 | T-CUS-07 | Recently-viewed deduped. |
| CUS-19/21/22 | T-CUS-08 | Dynamic/animated/a11y/RTL. |
| CUS-24 | T-CUS-09 | Guest cart merges cleanly. |

**Preserve:** CUS-06, CUS-15, CUS-16, CUS-17, CUS-18, CUS-23.
