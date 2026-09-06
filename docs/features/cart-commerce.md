# Cart / Commerce — Feature Remediation Doc
**Branch:** `fix/cart-commerce` (new — no suitable existing branch; see MASTER_REMEDIATION_PLAN §1) · **Base:** `main` @ `c73dbf3`

## Problem (P0 — production blocking)
A guest who completed ONE checkout became permanently unable to shop from the same browser: every cart operation (GET /cart, POST /cart/items, next checkout) returned 500. Live evidence: preview API probes 2026-09-06 (`CONF-CC74A882` then GET/POST /cart = 500 indefinitely). Latent twin: the same collision after a guest→user cart merge + logout.

## Root cause
`carts.session_token` is UNIQUE + NOT NULL. On conversion (`clear_cart` after checkout, `merge_guest_into_user_cart`) the row kept holding the client-persisted token forever. The next `get_or_create_cart` found no **active** row for the token and INSERTed a duplicate → `IntegrityError` → unhandled 500. Secondary: two concurrent cold-start requests with one fresh token raced the INSERT (same 500); a checkout replay without an idempotency key surfaced as 500 instead of the honest empty-cart 422.

## Architecture / state machine
- Cart states: `active` → `converted` (checkout) / `active(guest)` → merged into `active(user)` + `converted` (login merge).
- Token lifecycle on conversion: `<token>::converted::<cart_id>` (deterministic, unique per cart, original preserved as a traceable prefix). The **authoritative** order↔session linkage remains `orders.guest_session_token`, which stores the ORIGINAL token at checkout time (set before conversion — verified by regression test).
- `get_or_create_cart` is now race-safe: INSERT→flush; on `IntegrityError` → rollback → SELECT active → adopt the winner's row.

## Why no migration
The fix is behavioral (token lifecycle), not structural: no schema change, no deploy-ordering hazard with the production schema gate, and the production Neon DB currently holds **zero** carts/orders (verified 2026-09-06) so no legacy converted rows exist. Historical converted rows (preview DBs only) stay as-is; they are inert because lookups filter `status == 'active'`.

## Failure modes covered
- Returning guest after checkout → fresh active cart (200/201), second order succeeds.
- Checkout replay without idempotency key → honest 422 "Cannot checkout an empty cart."
- Checkout replay WITH idempotency key → same order returned (no double charge/no duplicate order).
- Concurrent same-token cart creation → loser adopts winner's row (no 500).
- Merge + logout → same browser token can open a new guest cart.

## Tests
`backend/tests/test_cart_returning_guest.py` (5): exact P0 repro, duplicate-checkout 422, idempotency replay, traceability assertions (converted prefix + original token on order), merge-then-guest. Full backend suite: **1025 passed / 7 skipped** (baseline 1020 + 5).

## API contract
Unchanged (no endpoint/signature edits) — strictly server-side state handling.

## Security
No auth surface changed; guest tokens remain opaque; CSRF path unchanged.

## Rollback
Single revert of the fix commit restores prior behavior (with the P0 returning). Tests commit reverts cleanly. No data implications (no migration).

## Operational notes
Watch for `Cart` IntegrityError in logs — should be absent post-deploy; `X-Request-Id` correlates any recurrence.
